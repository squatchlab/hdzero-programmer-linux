# internet_panel.py
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import requests
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
from requests.exceptions import RequestException

from app_settings import SETTINGS_KEY_AUTOBACKUP
from app_settings import settings as _qsettings

# Narrow exception class for HTTP-worker run(). Catches network/HTTP
# failures + malformed JSON. Anything else (AttributeError, KeyError on a
# changed schema, programmer error) propagates so it surfaces as a real
# bug rather than a misleading "connectivity error" string.
_HTTP_FAILURES = (RequestException, json.JSONDecodeError, OSError)

API_BASE = os.environ.get("HDZERO_API_BASE", "https://hdzero.go-next.co").rstrip("/")

def resource_path(relpath: str) -> str:
    # AppImage build sets HDZERO_APP_DIR to the bundled source/asset dir.
    # PyInstaller frozen builds expose sys._MEIPASS. Otherwise fall back to
    # the directory of this file (works for pip-installed flat modules and
    # plain checkouts).
    env_dir = os.environ.get("HDZERO_APP_DIR")
    if env_dir:
        return str(Path(env_dir) / relpath)
    base = getattr(sys.modules["__main__"], "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / relpath)

# Generic HTTP worker for InternetPanel — single QThread shape with hooks
# for response shape (raw bytes, JSON parser, streamed-to-tempfile). All
# four legacy workers (LoadDevices/LoadFirmwares/LoadImage/DownloadFirmware)
# collapse onto this; uniform retry/backoff/timeout policy lives in one
# place. See ticket #25 + #37.
class HttpWorker(QThread):
    """One QThread for every flavour of HTTP fetch the panel needs.

    - JSON-parsed response: pass `parser=lambda r: r.json().get("foo", [])`.
      Emitted via `ok` as whatever the parser returns.
    - Raw bytes: leave `parser` and `stream_to_temp_bin` unset; `ok`
      emits the response body bytes.
    - Streamed download to a temp .bin: set `stream_to_temp_bin=True`.
      `progress` fires with percent (0..100); `ok` emits the temp path.

    Retries on `_HTTP_FAILURES` with exponential backoff
    (`backoff * 2^attempt`), default 2 retries → 1s, 2s. Each retry is
    surfaced via `log` so a user investigating a flake sees the
    attempts. `time.sleep` runs on this worker thread, not the GUI.
    """
    ok = pyqtSignal(object)
    fail = pyqtSignal(str)
    progress = pyqtSignal(int)
    log = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        *,
        parser: Optional[Callable[[requests.Response], Any]] = None,
        stream_to_temp_bin: bool = False,
        timeout: float = 15.0,
        retries: int = 2,
        backoff: float = 1.0,
    ):
        super().__init__()
        self.url = url
        self.parser = parser
        self.stream_to_temp_bin = stream_to_temp_bin
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def run(self) -> None:
        last_err: Optional[str] = None
        for attempt in range(1, self.retries + 2):
            try:
                if self.stream_to_temp_bin:
                    self._stream_download()
                else:
                    r = requests.get(self.url, timeout=self.timeout)
                    r.raise_for_status()
                    self.ok.emit(self.parser(r) if self.parser else r.content)
                return
            except _HTTP_FAILURES as e:
                last_err = str(e)
                if attempt <= self.retries:
                    wait = self.backoff * (2 ** (attempt - 1))
                    self.log.emit(
                        f"http attempt {attempt} failed: {last_err}; "
                        f"retrying in {wait:.1f}s"
                    )
                    time.sleep(wait)
        self.fail.emit(last_err or "unknown error")

    def _stream_download(self) -> None:
        r = requests.get(self.url, stream=True, timeout=self.timeout)
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

class InternetPanel(QWidget):
    firmwareSelected = pyqtSignal(str)        # local downloaded path (consumed by Local panel)
    log = pyqtSignal(str)                     # log lines forwarded to Local panel
    flashRequested = pyqtSignal(str, bool)    # (local path, autobackup)

    def __init__(self) -> None:
        super().__init__()
        self.devices: List[dict] = []
        self.firmwares: List[dict] = []
        # (label shown on the button, callable that re-runs the failed op).
        # Set by every loader before kicking; cleared on success; consulted
        # by the Retry button which sits next to lbl_state.
        self._last_loader: Optional[Tuple[str, Callable[[], None]]] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10,10,10,10)
        root.setSpacing(10)

        # ======= Main row (2 columns): LEFT (device + img + status) | RIGHT (version + notes + FLASH)
        row = QHBoxLayout()
        row.setSpacing(12)

        # --- LEFT column
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

        # --- RIGHT column
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
        self.cb_autobackup.setChecked(
            _qsettings().value(SETTINGS_KEY_AUTOBACKUP, True, type=bool)
        )
        self.cb_autobackup.toggled.connect(self._persist_autobackup)

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

        state_row = QHBoxLayout()
        state_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_state = QLabel("Ready")
        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setVisible(False)
        self.btn_retry.setStyleSheet("padding:2px 10px;")
        self.btn_retry.clicked.connect(self._retry_last)
        state_row.addWidget(self.lbl_state, 1)
        state_row.addWidget(self.btn_retry, 0)
        root.addLayout(state_row)

        self.lbl_phase = QLabel("Ready.")
        self.lbl_phase.setStyleSheet("color:#dddddd; margin-top:4px;")
        root.addWidget(self.lbl_phase)

        self.load_devices()
        
    @staticmethod
    def _persist_autobackup(checked: bool) -> None:
        _qsettings().setValue(SETTINGS_KEY_AUTOBACKUP, checked)

    def set_phase(self, text: str) -> None:
        self.lbl_phase.setText(text)

    # ===== Status helpers =====
    def status_append(self, text: str) -> None:
        self.status_box.moveCursor(QTextCursor.MoveOperation.End)
        self.status_box.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.status_box.moveCursor(QTextCursor.MoveOperation.End)

    def status_set(self, text: str) -> None:
        self.status_box.setPlainText(text)
        self.status_box.moveCursor(QTextCursor.MoveOperation.End)

    def set_loading(self, msg: str) -> None:
        self.lbl_state.setText(msg)

    def _arm_loader(self, label: str, fn: Callable[[], None]) -> None:
        """Record the most recent loader so a subsequent on_fail() can offer
        a one-click retry pointing at the right action.
        """
        self._last_loader = (label, fn)
        self.btn_retry.setVisible(False)

    def _clear_loader(self) -> None:
        self._last_loader = None
        self.btn_retry.setVisible(False)

    def _retry_last(self) -> None:
        if self._last_loader is None:
            return
        _, fn = self._last_loader
        self.btn_retry.setVisible(False)
        fn()

    def on_fail(self, msg: str) -> None:
        self.set_loading(f"Error: {msg}")
        self.status_append(f"ERROR: {msg}")
        self.log.emit(f"[Internet] ERROR: {msg}\n")
        if self._last_loader is not None:
            label, _ = self._last_loader
            self.btn_retry.setText(f"Retry {label}")
            self.btn_retry.setVisible(True)

    # ===== HTTP logic =====
    def load_devices(self) -> None:
        self._arm_loader("device list", self.load_devices)
        self.set_loading("Loading devices…")
        self.cb_devices.clear()
        w = HttpWorker(
            f"{API_BASE}/api/devices",
            parser=lambda r: r.json().get("devices", []),
        )
        w.ok.connect(self.on_devices_ok)
        w.fail.connect(self.on_fail)
        w.log.connect(self.log.emit)
        w.start()
        self._w_dev = w

    def on_devices_ok(self, devices: list[dict[str, Any]]) -> None:
        self._clear_loader()
        self.devices = devices or []
        self.cb_devices.clear()
        for d in self.devices:
            name = d.get("device_name") or f"Device {d.get('device_id')}"
            self.cb_devices.addItem(name, d)
        self.set_loading(f"{len(self.devices)} device(s) loaded")
        if self.devices:
            self.cb_devices.setCurrentIndex(0)
            self.on_device_changed()

    def _set_device_image(self, url: Optional[str]) -> None:
        if not url:
            self.device_img.setText("No image")
            self.device_img.setPixmap(QPixmap())
            return
        self.device_img.setText("Loading image…")
        self.device_img.setPixmap(QPixmap())
        # Image worker keeps the historic 10s timeout (vs 15s default); a
        # device thumbnail is small enough that a longer wait is just a UX
        # delay. Retries default to 2.
        w = HttpWorker(url, timeout=10.0)
        w.ok.connect(self._on_image_loaded)
        w.fail.connect(self._on_image_failed)
        w.log.connect(self.log.emit)
        w.start()
        self._w_img = w

    def _on_image_loaded(self, data: bytes) -> None:
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.device_img.setText("Image load error")
            self.device_img.setPixmap(QPixmap())
            return
        scaled = pix.scaled(300, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.device_img.setPixmap(scaled)
        self.device_img.setText("")

    def _on_image_failed(self, _msg: str) -> None:
        self.device_img.setText("Image load error")
        self.device_img.setPixmap(QPixmap())

    def on_device_changed(self) -> None:
        data = self.cb_devices.currentData()
        if not data:
            self.cb_fw.clear()
            self.notes.clear()
            self._set_device_image(None)
            return
        self._set_device_image(data.get("image_url") or data.get("image"))
        device_id = data.get("device_id")
        self._arm_loader("firmware list", self.on_device_changed)
        self.set_loading("Loading firmwares…")
        self.cb_fw.clear()
        w = HttpWorker(
            f"{API_BASE}/api/firmwares/{device_id}",
            parser=lambda r: r.json().get("firmwares", []),
        )
        w.ok.connect(self.on_fw_ok)
        w.fail.connect(self.on_fail)
        w.log.connect(self.log.emit)
        w.start()
        self._w_fw = w

    def on_fw_ok(self, firmwares: list[dict[str, Any]]) -> None:
        self._clear_loader()
        self.firmwares = firmwares or []
        self.cb_fw.clear()
        for fw in self.firmwares:
            label = fw.get("version") or "unknown"
            self.cb_fw.addItem(label, fw)
        self.set_loading(f"{len(self.firmwares)} firmware(s) loaded")
        if self.firmwares:
            self.cb_fw.setCurrentIndex(0)
            self.on_fw_changed()

    def on_fw_changed(self) -> None:
        fw = self.cb_fw.currentData()
        self.notes.setPlainText("" if not fw else (fw.get("notes") or ""))

    # ===== Download and request flash =====
    def download_selected_fw(self) -> None:
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
        self._arm_loader("download", self.download_selected_fw)
        # Firmware download keeps the historic 30s timeout — payloads are
        # under 64 KiB but the per-CDN handshake can drag.
        w = HttpWorker(url, stream_to_temp_bin=True, timeout=30.0)
        w.progress.connect(lambda p: self.set_loading(f"Downloading… {p}%"))
        w.ok.connect(self.on_download_ok_then_flash)
        w.fail.connect(self.on_fail)
        w.log.connect(self.log.emit)
        w.start()
        self._w_dl = w

    def on_download_ok_then_flash(self, local_path: str) -> None:
        self._clear_loader()
        self.firmwareSelected.emit(local_path)
        self.status_append(f"Downloaded: {local_path}")
        self.set_phase("Wait - Prepare firmware")
        self.flashRequested.emit(local_path, self.cb_autobackup.isChecked())
