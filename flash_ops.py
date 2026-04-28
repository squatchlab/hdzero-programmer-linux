# flash_ops.py
import os, subprocess, tempfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

HDZERO_MAX = 64 * 1024
FLASH_SIZE_BYTES = 1024 * 1024  # 1 MiB (W25Q80)

FLASHROM_PATHS = [
    "/opt/homebrew/bin/flashrom",
    "/opt/homebrew/sbin/flashrom",
    "/usr/local/bin/flashrom",
    "/usr/local/sbin/flashrom",
    "/usr/bin/flashrom",
]

def find_flashrom() -> Optional[str]:
    for p in FLASHROM_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    from shutil import which
    return which("flashrom")

def run_admin(cmd: str) -> subprocess.CompletedProcess:
    safe = cmd.replace('"', '\\"')
    return subprocess.run(
        ["/usr/bin/osascript", "-e", f'do shell script "{safe}" with administrator privileges'],
        text=True, capture_output=True
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
