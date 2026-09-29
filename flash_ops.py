# flash_ops.py
import os
import select
import shlex
import subprocess
import tempfile
import time
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

HDZERO_MAX = 64 * 1024
FLASH_SIZE_BYTES = 1024 * 1024  # 1 MiB (W25Q80)

# Grace period between SIGTERM and SIGKILL when a wedged flashrom is being
# torn down. Named (not inlined) so tests can shrink it; see test_error_paths.
_SIGTERM_GRACE_SECS = 5

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


def find_flashrom() -> str | None:
    for p in FLASHROM_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    from shutil import which
    return which("flashrom")


def _build_admin_argv(cmd: str) -> list[str] | None:
    """Return the argv that runs `cmd` with elevated privileges, or None if no
    escalation tool is available. pkexec is preferred (polkit GUI prompt);
    SUDO_ASKPASS-driven `sudo -A` is next; finally non-interactive `sudo -n`.
    Already-root or HDZERO_NO_ESCALATE skips escalation entirely.

    SECURITY: `cmd` is passed verbatim to `/bin/sh -c` with NO escaping
    applied here. Every path or value interpolated into `cmd` MUST be quoted
    by the caller via `shlex.quote()` — otherwise this is a shell-injection
    surface on a privilege-escalated command. See ADR-0001.
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


def run_admin(cmd: str) -> "subprocess.CompletedProcess[str]":
    """Buffered elevated execution. Returns a CompletedProcess so callers see a
    uniform contract regardless of which escalation path was taken.
    """
    argv = _build_admin_argv(cmd)
    if argv is None:
        return subprocess.CompletedProcess(
            args=cmd, returncode=127, stdout="", stderr=NO_ESCALATE_TOOL_MSG,
        )
    return subprocess.run(argv, text=True, capture_output=True)


def run_admin_streaming(
    cmd: str,
    line_cb: Callable[[str], None],
    timeout: float = 600.0,
) -> int:
    """Elevated execution with line-by-line stdout streaming so the GUI can
    update phase/status while a long flashrom pipeline runs. stderr is folded
    into stdout to keep ordering. Returns the process exit code.

    `timeout` is a wall-clock cap on the whole pipeline (default 10 min).
    A legitimate W25Q80 1 MiB write at CH341A USB-SPI rates is well under
    2 minutes; if 10 minutes elapse, the process is wedged and the GUI is
    better off killing it than hanging on `proc.wait()` forever. SIGTERM is
    sent first; if the process doesn't exit within 5s, SIGKILL.
    """
    argv = _build_admin_argv(cmd)
    if argv is None:
        line_cb(NO_ESCALATE_TOOL_MSG)
        return 127
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    # stdout=PIPE guarantees proc.stdout is set; raise explicitly rather
    # than assert so the invariant survives `python -O`.
    if proc.stdout is None:
        raise RuntimeError("subprocess stdout pipe was not created")
    deadline = time.monotonic() + timeout

    def _kill_after_timeout(reason: str) -> int:
        line_cb(f"(timeout: {reason}; terminating flashrom)\n")
        proc.terminate()
        try:
            return proc.wait(timeout=_SIGTERM_GRACE_SECS)
        except subprocess.TimeoutExpired:
            line_cb("(timeout: SIGTERM ignored, sending SIGKILL)\n")
            proc.kill()
            return proc.wait()

    try:
        # Poll the stdout fd with `select` so the deadline check fires
        # even when the child is wedged with no output (e.g. a hung
        # flashrom mid-erase). Plain `for line in proc.stdout:` blocks
        # on readline until EOF, which would let a wedged process burn
        # through the entire wall-clock budget before we noticed.
        buf = ""
        fd = proc.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _kill_after_timeout(f"exceeded {timeout:.0f}s")
            # 1s poll keeps the deadline check responsive without
            # busy-looping. select returns ready fds OR timeout-empty.
            ready, _, _ = select.select([fd], [], [], min(1.0, remaining))
            if not ready:
                continue
            chunk = os.read(fd, 4096)
            if not chunk:  # EOF — process closed stdout
                if buf:
                    line_cb(buf)
                break
            buf += chunk.decode(errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line_cb(line + "\n")
                if time.monotonic() >= deadline:
                    return _kill_after_timeout(f"exceeded {timeout:.0f}s")

        # stdout closed; bound proc.wait() by what's left of the budget.
        remaining = max(0.0, deadline - time.monotonic())
        try:
            return proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return _kill_after_timeout(f"exceeded {timeout:.0f}s after stdout close")
    finally:
        # If we returned via kill, proc.stdout might still be open. Close
        # it so we don't leak the FD.
        if proc.stdout and not proc.stdout.closed:
            proc.stdout.close()


def _chip_probe_prelude(flashrom_q: str) -> str:
    """Shell snippet that probes the chip and sets $HDZ_CHIP when ambiguous.

    Newer flashrom (1.4+) ships several definitions sharing the W25Q80 JEDEC
    ID (e.g. "W25Q80BV/W25Q80DV" and "W25Q80RV") and refuses to run without
    `-c <chipname>`. Older flashrom names the same part "W25Q80.V", so a
    hard-coded name would break those installs. Instead, probe once (no
    operation) inside the same privileged chain and, only when flashrom
    reports multiple matches, reuse the first "Found ... flash chip" name.
    The definitions are the same part, so which one we pick doesn't matter.
    The probe's exit code is ignored; the real operation reports failures.
    """
    return (
        f"HDZ_PROBE=$({flashrom_q} -p ch341a_spi 2>&1); "
        'printf "%s\\n" "$HDZ_PROBE"; '
        "HDZ_CHIP=; "
        'case "$HDZ_PROBE" in *"Multiple flash chip definitions"*) '
        'HDZ_CHIP=$(printf "%s\\n" "$HDZ_PROBE" '
        "| sed -n 's/.*Found .* flash chip \"\\([^\"]*\\)\".*/\\1/p' | head -n 1); "
        'echo "Ambiguous chip definitions; using -c $HDZ_CHIP";; '
        "esac; "
    )


# Expands to `-c "<name>"` after _chip_probe_prelude set $HDZ_CHIP, else nothing.
_CHIP_ARG = '${HDZ_CHIP:+-c "$HDZ_CHIP"}'


def make_padded_image_1mib(fw_path: str) -> str:
    with open(fw_path, "rb") as f:
        data = f.read()
    if len(data) > FLASH_SIZE_BYTES:
        raise RuntimeError("Firmware is larger than 1 MiB.")
    # delete=False: the temp file must outlive this function so flashrom can
    # read it later in the privileged chain; the caller is responsible for it.
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

    def __init__(self, flashrom_path: str, fw_path: str, backup_path: str | None = None,
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

    def run(self) -> None:
        padded: str | None = None
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
            parts: list[str] = []
            if self.backup_path:
                parts.append(
                    f"{flashrom_q} -p ch341a_spi {_CHIP_ARG} -r "
                    f"{shlex.quote(self.backup_path)}"
                )
            parts.append(f"{flashrom_q} -p ch341a_spi {_CHIP_ARG} -w {padded_q}")
            # Explicit re-verify pass: re-reads the chip and diffs against the
            # padded image. flashrom's -w already verifies internally; this
            # second pass catches drift between write completion and end-of-op
            # and gives the user an audit line in the log.
            parts.append(f"{flashrom_q} -p ch341a_spi {_CHIP_ARG} -v {padded_q}")
            cmd = _chip_probe_prelude(flashrom_q) + " && ".join(parts)

            phases = "backup → write → verify" if self.backup_path else "write → verify"
            self.status.emit(f"Wait - Safe flash ({phases})")
            self.log.emit(f"\n== Safe flash (1 prompt) ==\n→ {cmd}\n")

            # Phase tracking is best-effort string match against flashrom
            # stdout — the ordering matches the && chain so a one-shot toggle
            # per phase is sufficient.
            seen = {"backup": False, "write": False, "verify": False}

            def on_line(line: str) -> None:
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
        except (subprocess.SubprocessError, OSError, RuntimeError) as e:
            # RuntimeError covers our own raise-on-rc-nonzero, OSError covers
            # padding/IO, SubprocessError covers Popen/wait failures. Programmer
            # errors (TypeError, AttributeError) propagate so they surface
            # honestly rather than masquerading as flash failures.
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

    def run(self) -> None:
        try:
            flashrom_q = shlex.quote(self.flashrom)
            cmd = _chip_probe_prelude(flashrom_q) + (
                f"{flashrom_q} -p ch341a_spi {_CHIP_ARG} -r "
                f"{shlex.quote(self.out)}"
            )
            self.log.emit(f"→ {cmd}\n")
            r = run_admin(cmd)
            self.log.emit(r.stdout)
            if r.returncode != 0:
                self.log.emit(r.stderr)
                raise RuntimeError("Backup failed")
            self.ok.emit(self.out)
        except (subprocess.SubprocessError, OSError, RuntimeError) as e:
            self.fail.emit(str(e))
