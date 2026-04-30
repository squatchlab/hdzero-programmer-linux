# internet_panel.py
import os
import tempfile
from pathlib import Path
from typing import List, Optional

import requests
from PyQt6 import QtCore
from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Keep these in sync with the constants in main.py — single shared key so
# toggling on either tab persists app-wide.
_SETTINGS_ORG = "HDZero"
_SETTINGS_APP = "Programmer"
_SETTINGS_KEY_AUTOBACKUP = "autobackup"

API_BASE = os.environ.get("HDZERO_API_BASE", "https://hdzero.go-next.co").rstrip("/")

def resource_path(relpath: str) -> str:
    # AppImage build sets HDZERO_APP_DIR to the bundled source/asset dir.
    # PyInstaller frozen builds expose sys._MEIPASS. Otherwise fall back to
    # the directory of this file (works for pip-installed flat modules and
    # plain checkouts).
    env_dir = os.environ.get("HDZERO_APP_DIR")
    if env_dir:
        return str(Path(env_dir) / relpath)
    base = getattr(__import__('sys').modules['__main__'], "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / relpath)

# Workers HTTP locales al panel Internet
class LoadDevicesWorker(QThread):
    ok = pyqtSignal(list); fail = pyqtSignal(str)
    def run(self):
        try:
            url = f"{API_BASE}/api/devices"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            self.ok.emit(r.json().get("devices", []))
        except Exception as e:
            self.fail.emit(str(e))

class LoadFirmwaresWorker(QThread):
    ok = pyqtSignal(list); fail = pyqtSignal(str)
    def __init__(self, device_id: int):
        super().__init__()
        self.device_id = device_id
    def run(self):
        try:
            url = f"{API_BASE}/api/firmwares/{self.device_id}"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            self.ok.emit(r.json().get("firmwares", []))
        except Exception as e:
            self.fail.emit(str(e))

class LoadImageWorker(QThread):
    ok = pyqtSignal(bytes); fail = pyqtSignal(str)
    def __init__(self, url: str):
        super().__init__()
        self.url = url
    def run(self):
        try:
            r = requests.get(self.url, timeout=10)
            r.raise_for_status()
            self.ok.emit(r.content)
        except Exception as e:
            self.fail.emit(str(e))

class DownloadFirmwareWorker(QThread):
    progress = pyqtSignal(int); ok = pyqtSignal(str); fail = pyqtSignal(str)
    def __init__(self, url: str):
        super().__init__()
        self.url = url
    def run(self):
        try:
            r = requests.get(self.url, stream=True, timeout=30)
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            tmp = tempfile.NamedTemporaryFile(prefix="hdzero_dl_", suffix=".bin", delete=False)
            tmp_path = tmp.name
            tmp.close()
            read = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    read += len(chunk)
                    if total > 0:
                        self.progress.emit(int(read * 100 / total))
            self.progress.emit(100)
            self.ok.emit(tmp_path)
        except Exception as e:
            self.fail.emit(str(e))

class InternetPanel(QWidget):
    firmwareSelected = pyqtSignal(str)        # path local descargado (lo ve Local)
    log = pyqtSignal(str)                     # logs hacia Local
    flashRequested = pyqtSignal(str, bool)    # (path local, autobackup)

    def __init__(self):
        super().__init__()
        self.devices: List[dict] = []
        self.firmwares: List[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10,10,10,10)
        root.setSpacing(10)

        # ======= Fila principal (2 columnas): IZQ (device + img + estado) | DER (version + Notes + FLASH)
        row = QHBoxLayout()
        row.setSpacing(12)

        # --- Columna IZQUIERDA
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        lbl_dev = QLabel("Device")
        lbl_dev.setStyleSheet("font-weight:600;")
        self.cb_devices = QComboBox()
        self.cb_devices.currentIndexChanged.connect(self.on_device_changed)

        btn_reload = QPushButton(" Reload")
        rld = resource_path("reload.png")
        if Path(rld).exists():
            btn_reload.setIcon(QIcon(rld))
            btn_reload.setIconSize(QtCore.QSize(15, 15))
        btn_reload.clicked.connect(self.load_devices)

        left_col.addWidget(lbl_dev, 0, Qt.AlignmentFlag.AlignTop)
        left_col.addWidget(self.cb_devices)
        left_col.addWidget(btn_reload)

        self.device_img = QLabel("No image")
        self.device_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.device_img.setMinimumSize(260, 180)
        self.device_img.setStyleSheet("background:#0e0e0e; border:1px solid #2c2c2c;")
        left_col.addSpacing(8)
        left_col.addWidget(self.device_img, 1)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(90)
        self.status_box.setStyleSheet("font-family: Menlo, monospace; font-size:12px;")
        left_col.addWidget(self.status_box)

        left_panel = QWidget()
        left_panel.setLayout(left_col)
        left_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- Columna DERECHA
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        lbl_fw = QLabel("Firmware (version):")
        self.cb_fw = QComboBox()
        self.cb_fw.currentIndexChanged.connect(self.on_fw_changed)

        lbl_notes = QLabel("Notes:")
        lbl_notes.setStyleSheet("font-weight:600; margin-top:6px;")

        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMinimumHeight(140)

        self.btn_flash = QPushButton("FLASH")
        flash_icon_path = resource_path("flash.png")
        if Path(flash_icon_path).exists():
            self.btn_flash.setIcon(QIcon(flash_icon_path))
            self.btn_flash.setIconSize(QtCore.QSize(22, 22))
        self.btn_flash.clicked.connect(self.download_selected_fw)

        self.cb_autobackup = QCheckBox("Backup chip before flashing")
        _s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self.cb_autobackup.setChecked(
            _s.value(_SETTINGS_KEY_AUTOBACKUP, True, type=bool)
        )
        self.cb_autobackup.toggled.connect(
            lambda checked: QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(
                _SETTINGS_KEY_AUTOBACKUP, checked
            )
        )

        right_col.addWidget(lbl_fw)
        right_col.addWidget(self.cb_fw)
        right_col.addWidget(lbl_notes)
        right_col.addWidget(self.notes, 1)
        right_col.addWidget(self.cb_autobackup)
        right_col.addWidget(self.btn_flash)

        right_panel = QWidget()
        right_panel.setLayout(right_col)

        row.addWidget(left_panel, 2)
        row.addWidget(right_panel, 1)
        root.addLayout(row)

        self.lbl_state = QLabel("Ready")
        root.addWidget(self.lbl_state)
        
        self.lbl_phase = QLabel("Ready.")
        self.lbl_phase.setStyleSheet("color:#dddddd; margin-top:4px;")
        root.addWidget(self.lbl_phase)

        self.load_devices()
        
    def set_phase(self, text: str):
        self.lbl_phase.setText(text)

    # ===== Helpers de estado =====
    def status_append(self, text: str):
        self.status_box.moveCursor(QTextCursor.MoveOperation.End)
        self.status_box.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.status_box.moveCursor(QTextCursor.MoveOperation.End)

    def status_set(self, text: str):
        self.status_box.setPlainText(text)
        self.status_box.moveCursor(QTextCursor.MoveOperation.End)

    def set_loading(self, msg: str):
        self.lbl_state.setText(msg)

    def on_fail(self, msg: str):
        self.set_loading(f"Error: {msg}")
        self.status_append(f"ERROR: {msg}")
        self.log.emit(f"[Internet] ERROR: {msg}\n")

    # ===== HTTP logic =====
    def load_devices(self):
        self.set_loading("Loading devices…")
        self.cb_devices.clear()
        w = LoadDevicesWorker()
        w.ok.connect(self.on_devices_ok)
        w.fail.connect(self.on_fail)
        w.start()
        self._w_dev = w

    def on_devices_ok(self, devices: list):
        self.devices = devices or []
        self.cb_devices.clear()
        for d in self.devices:
            name = d.get("device_name") or f"Device {d.get('device_id')}"
            self.cb_devices.addItem(name, d)
        self.set_loading(f"{len(self.devices)} device(s) loaded")
        if self.devices:
            self.cb_devices.setCurrentIndex(0)
            self.on_device_changed()

    def _set_device_image(self, url: Optional[str]):
        if not url:
            self.device_img.setText("No image")
            self.device_img.setPixmap(QPixmap())
            return
        self.device_img.setText("Loading image…")
        self.device_img.setPixmap(QPixmap())
        w = LoadImageWorker(url)
        w.ok.connect(self._on_image_loaded)
        w.fail.connect(self._on_image_failed)
        w.start()
        self._w_img = w

    def _on_image_loaded(self, data: bytes):
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.device_img.setText("Image load error")
            self.device_img.setPixmap(QPixmap())
            return
        scaled = pix.scaled(300, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.device_img.setPixmap(scaled)
        self.device_img.setText("")

    def _on_image_failed(self, _msg: str):
        self.device_img.setText("Image load error")
        self.device_img.setPixmap(QPixmap())

    def on_device_changed(self):
        data = self.cb_devices.currentData()
        if not data:
            self.cb_fw.clear()
            self.notes.clear()
            self._set_device_image(None)
            return
        self._set_device_image(data.get("image_url") or data.get("image"))
        device_id = data.get("device_id")
        self.set_loading("Loading firmwares…")
        self.cb_fw.clear()
        w = LoadFirmwaresWorker(device_id)
        w.ok.connect(self.on_fw_ok)
        w.fail.connect(self.on_fail)
        w.start()
        self._w_fw = w

    def on_fw_ok(self, firmwares: list):
        self.firmwares = firmwares or []
        self.cb_fw.clear()
        for fw in self.firmwares:
            label = fw.get("version") or "unknown"
            self.cb_fw.addItem(label, fw)
        self.set_loading(f"{len(self.firmwares)} firmware(s) loaded")
        if self.firmwares:
            self.cb_fw.setCurrentIndex(0)
            self.on_fw_changed()

    def on_fw_changed(self):
        fw = self.cb_fw.currentData()
        self.notes.setPlainText("" if not fw else (fw.get("notes") or ""))

    # ===== Descargar y pedir flash =====
    def download_selected_fw(self):
        fw = self.cb_fw.currentData()
        if not fw:
            self.on_fail("No firmware selected.")
            return
        url = fw.get("firmware_url")
        if not url:
            self.on_fail("No firmware_url provided by API.")
            return

        self.set_phase("Wait - Downloading.")
        self.status_set(f"Downloading: {url}")
        w = DownloadFirmwareWorker(url)
        w.progress.connect(lambda p: self.set_loading(f"Downloading… {p}%"))
        w.ok.connect(self.on_download_ok_then_flash)
        w.fail.connect(self.on_fail)
        w.start()
        self._w_dl = w

    def on_download_ok_then_flash(self, local_path: str):
        self.firmwareSelected.emit(local_path)
        self.status_append(f"Downloaded: {local_path}")
        self.set_phase("Wait - Prepare firmware")
        self.flashRequested.emit(local_path, self.cb_autobackup.isChecked())
