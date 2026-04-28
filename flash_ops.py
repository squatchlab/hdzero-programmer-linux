# flash_ops.py
import os, subprocess, tempfile
from pathlib import Path
from typing import Optional

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

def find_flashrom() -> Optional[str]:
    for p in FLASHROM_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    from shutil import which
    return which("flashrom")

def run_admin(cmd: str) -> subprocess.CompletedProcess:
    """Run a shell command with elevated privileges on Linux.

    Prefers pkexec (polkit GUI prompt — integrates with the desktop session),
    then sudo -A if SUDO_ASKPASS is set, then non-interactive sudo as a last
    resort. Returns a CompletedProcess so callers see a uniform contract.
    """
    if os.geteuid() == 0 or os.environ.get("HDZERO_NO_ESCALATE"):
        # Already root, or user opted out of escalation (typically because
        # they installed the CH341A udev rule in packaging/99-ch341a.rules
        # and flashrom can talk to /dev/bus/usb/ as the unprivileged user).
        return subprocess.run(["/bin/sh", "-c", cmd], text=True, capture_output=True)

    from shutil import which
    pkexec = which("pkexec")
    if pkexec:
        return subprocess.run(
            [pkexec, "/bin/sh", "-c", cmd], text=True, capture_output=True
        )

    sudo = which("sudo")
    if sudo and os.environ.get("SUDO_ASKPASS"):
        return subprocess.run(
            [sudo, "-A", "/bin/sh", "-c", cmd], text=True, capture_output=True
        )
    if sudo:
        # No GUI askpass — try non-interactive sudo. Fails fast with a clear
        # message instead of hanging on a missing TTY.
        return subprocess.run(
            [sudo, "-n", "/bin/sh", "-c", cmd], text=True, capture_output=True
        )

    return subprocess.CompletedProcess(
        args=cmd, returncode=127, stdout="",
        stderr=(
            "No privilege escalation tool found. Install polkit (pkexec) "
            "or sudo, then retry. See README for udev-rule alternative.\n"
        ),
    )

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

    def __init__(self, flashrom_path: str, fw_path: str):
        super().__init__()
        self.flashrom = flashrom_path
        self.fw = fw_path

    def run(self):
        try:
            # Fase: preparar imagen
            self.status.emit("Wait - Prepare firmware")
            self.progress.emit(10)

            self.log.emit("== Building 1MiB padded image ==\n")
            padded = make_padded_image_1mib(self.fw)
            self.log.emit(f"→ padded image: {padded}\n")
            self.progress.emit(40)

            # Fase: flasheando
            self.status.emit("Wait - Flashing")
            cmd = f'{self.flashrom} -p ch341a_spi -w "{padded}"'
            self.log.emit("\n== Flash (1 prompt) ==\n")
            self.log.emit(f"→ {cmd}\n")
            r = run_admin(cmd)
            self.log.emit(r.stdout)
            if r.returncode != 0:
                self.log.emit(r.stderr)
                raise RuntimeError("Flash failed")

            self.progress.emit(100)
            self.status.emit("Done.")
            self.ok.emit()
        except Exception as e:
            self.fail.emit(str(e))

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
            cmd = f'{self.flashrom} -p ch341a_spi -r "{self.out}"'
            self.log.emit(f"→ {cmd}\n")
            r = run_admin(cmd)
            self.log.emit(r.stdout)
            if r.returncode != 0:
                self.log.emit(r.stderr)
                raise RuntimeError("Backup failed")
            self.ok.emit(self.out)
        except Exception as e:
            self.fail.emit(str(e))
