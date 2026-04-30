# flash_ops.py
import os
import shlex
import subprocess
import tempfile
from typing import Callable, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

HDZERO_MAX = 64 * 1024
FLASH_SIZE_BYTES = 1024 * 1024  # 1 MiB (W25Q80)

FLASHROM_PATHS = [
    # Standard Linux distro packages (apt/dnf/pacman) land in /usr/bin or /usr/sbin.
    "/usr/bin/flashrom",
    "/usr/sbin/flashrom",
    # Manually compiled / locally installed builds.
    "/usr/local/bin/flashrom",
    "/usr/local/sbin/flashrom",
    # Linuxbrew (homebrew on Linux) — uncommon but supported.
    "/home/linuxbrew/.linuxbrew/bin/flashrom",
    "/home/linuxbrew/.linuxbrew/sbin/flashrom",
    # macOS Homebrew — kept so the source stays cross-platform-compatible.
    "/opt/homebrew/bin/flashrom",
    "/opt/homebrew/sbin/flashrom",
]

NO_ESCALATE_TOOL_MSG = (
    "No privilege escalation tool found. Install polkit (pkexec) "
    "or sudo, then retry. See README for udev-rule alternative.\n"
)


def find_flashrom() -> Optional[str]:
    for p in FLASHROM_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    from shutil import which
    return which("flashrom")


def _build_admin_argv(cmd: str) -> Optional[List[str]]:
    """Return the argv that runs `cmd` with elevated privileges, or None if no
    escalation tool is available. pkexec is preferred (polkit GUI prompt);
    SUDO_ASKPASS-driven `sudo -A` is next; finally non-interactive `sudo -n`.
    Already-root or HDZERO_NO_ESCALATE skips escalation entirely.
    """
    if os.geteuid() == 0 or os.environ.get("HDZERO_NO_ESCALATE"):
        return ["/bin/sh", "-c", cmd]

    from shutil import which
    pkexec = which("pkexec")
    if pkexec:
        return [pkexec, "/bin/sh", "-c", cmd]

    sudo = which("sudo")
    if sudo and os.environ.get("SUDO_ASKPASS"):
        return [sudo, "-A", "/bin/sh", "-c", cmd]
    if sudo:
        # No GUI askpass — try non-interactive sudo. Fails fast with a clear
        # message instead of hanging on a missing TTY.
        return [sudo, "-n", "/bin/sh", "-c", cmd]

    return None


def run_admin(cmd: str) -> subprocess.CompletedProcess:
    """Buffered elevated execution. Returns a CompletedProcess so callers see a
    uniform contract regardless of which escalation path was taken.
    """
    argv = _build_admin_argv(cmd)
    if argv is None:
        return subprocess.CompletedProcess(
            args=cmd, returncode=127, stdout="", stderr=NO_ESCALATE_TOOL_MSG,
        )
    return subprocess.run(argv, text=True, capture_output=True)


def run_admin_streaming(cmd: str, line_cb: Callable[[str], None]) -> int:
    """Elevated execution with line-by-line stdout streaming so the GUI can
    update phase/status while a long flashrom pipeline runs. stderr is folded
    into stdout to keep ordering. Returns the process exit code.
    """
    argv = _build_admin_argv(cmd)
    if argv is None:
        line_cb(NO_ESCALATE_TOOL_MSG)
        return 127
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line_cb(line)
    return proc.wait()


def make_padded_image_1mib(fw_path: str) -> str:
    with open(fw_path, "rb") as f:
        data = f.read()
    if len(data) > FLASH_SIZE_BYTES:
        raise RuntimeError("Firmware is larger than 1 MiB.")
    tmp = tempfile.NamedTemporaryFile(prefix="hdzero_", suffix=".bin", delete=False)
    tmp_path = tmp.name
    tmp.close()
    with open(tmp_path, "wb") as out:
        out.write(b"\xFF" * FLASH_SIZE_BYTES)
        out.seek(0)
        out.write(data)
    return tmp_path


class FlashWorker(QThread):
    progress = pyqtSignal(int)
    status   = pyqtSignal(str)
    log      = pyqtSignal(str)
    ok       = pyqtSignal()
    fail     = pyqtSignal(str)

    def __init__(self, flashrom_path: str, fw_path: str, backup_path: Optional[str] = None,
                 cleanup_fw: bool = False):
        super().__init__()
        self.flashrom = flashrom_path
        self.fw = fw_path
        # When set, a full chip read is chained before the write so the user
        # has a rollback image. The whole pipeline runs under one privilege
        # prompt via `sh -c '... && ... && ...'`.
        self.backup_path = backup_path
        # When True, the worker unlinks self.fw after run() finishes. Set by
        # callers passing a tempfile they own (InternetPanel's downloaded
        # firmware blob); LocalPanel's user-selected .bin must stay False.
        self.cleanup_fw = cleanup_fw

    def run(self):
        padded: Optional[str] = None
        try:
            self.status.emit("Wait - Prepare firmware")
            self.progress.emit(5)

            self.log.emit("== Building 1MiB padded image ==\n")
            padded = make_padded_image_1mib(self.fw)
            self.log.emit(f"→ padded image: {padded}\n")
            self.progress.emit(15)

            # Each phase is built as an argv list and shell-escaped through
            # shlex.quote so a path with whitespace or shell-meta chars (e.g.
            # an XDG dir set to "$HOME/odd dir") can't break out of the chain.
            # We still use sh -c because pkexec/sudo run a single program and
            # the `&&` chain is what gives us one privilege prompt covering
            # backup -> write -> verify.
            flashrom_q = shlex.quote(self.flashrom)
            padded_q = shlex.quote(padded)
            parts: List[str] = []
            if self.backup_path:
                parts.append(
                    f"{flashrom_q} -p ch341a_spi -r {shlex.quote(self.backup_path)}"
                )
            parts.append(f"{flashrom_q} -p ch341a_spi -w {padded_q}")
            # Explicit re-verify pass: re-reads the chip and diffs against the
            # padded image. flashrom's -w already verifies internally; this
            # second pass catches drift between write completion and end-of-op
            # and gives the user an audit line in the log.
            parts.append(f"{flashrom_q} -p ch341a_spi -v {padded_q}")
            cmd = " && ".join(parts)

            phases = "backup → write → verify" if self.backup_path else "write → verify"
            self.status.emit(f"Wait - Safe flash ({phases})")
            self.log.emit(f"\n== Safe flash (1 prompt) ==\n→ {cmd}\n")

            # Phase tracking is best-effort string match against flashrom
            # stdout — the ordering matches the && chain so a one-shot toggle
            # per phase is sufficient.
            seen = {"backup": False, "write": False, "verify": False}

            def on_line(line: str):
                self.log.emit(line)
                low = line.lower()
                if not seen["backup"] and self.backup_path and "reading flash" in low:
                    seen["backup"] = True
                    self.status.emit("Wait - Backup (reading chip)")
                    self.progress.emit(35)
                elif not seen["write"] and ("writing flash" in low or "erasing and writing" in low):
                    seen["write"] = True
                    self.status.emit("Wait - Flashing")
                    self.progress.emit(60)
                elif not seen["verify"] and "verifying flash" in low:
                    seen["verify"] = True
                    self.status.emit("Wait - Verifying")
                    self.progress.emit(85)

            rc = run_admin_streaming(cmd, on_line)
            if rc != 0:
                raise RuntimeError(f"Safe flash failed (rc={rc})")

            self.progress.emit(100)
            self.status.emit("Done.")
            if self.backup_path:
                self.log.emit(f"\nPre-flash backup saved: {self.backup_path}\n")
            self.ok.emit()
        except Exception as e:
            self.fail.emit(str(e))
        finally:
            # Unlink the padded image we always own. Best-effort: if the
            # path is gone, that's fine; if unlink fails, log and move on
            # rather than masking the original outcome.
            if padded is not None:
                try:
                    os.unlink(padded)
                except OSError as cleanup_err:
                    self.log.emit(f"(temp cleanup: {cleanup_err})\n")
            # Unlink the source firmware only when caller flagged it as a
            # tempfile they handed off (InternetPanel download path).
            if self.cleanup_fw:
                try:
                    os.unlink(self.fw)
                except OSError as cleanup_err:
                    self.log.emit(f"(fw cleanup: {cleanup_err})\n")


class BackupWorker(QThread):
    log  = pyqtSignal(str)
    ok   = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, flashrom_path: str, out_path: str):
        super().__init__()
        self.flashrom = flashrom_path
        self.out = out_path

    def run(self):
        try:
            cmd = (
                f"{shlex.quote(self.flashrom)} -p ch341a_spi -r "
                f"{shlex.quote(self.out)}"
            )
            self.log.emit(f"→ {cmd}\n")
            r = run_admin(cmd)
            self.log.emit(r.stdout)
            if r.returncode != 0:
                self.log.emit(r.stderr)
                raise RuntimeError("Backup failed")
            self.ok.emit(self.out)
        except Exception as e:
            self.fail.emit(str(e))
