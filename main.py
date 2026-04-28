# main.py
import os, sys, time
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog,
    QProgressBar, QTextEdit, QMessageBox, QTabWidget
)
from PyQt6.QtGui import QPixmap, QIcon, QTextCursor
from PyQt6 import QtCore
from PyQt6.QtCore import Qt

from internet_panel import InternetPanel, resource_path
from flash_ops import find_flashrom, FlashWorker, BackupWorker, HDZERO_MAX

APP_TITLE = "HDZero Programmer Tool – by Gunther_FPV"
APP_HEADER_TITLE = "HDzero Programmer for MAC"

class LocalPanel(QWidget):
    def __init__(self, start_backup_cb, start_flash_cb):
        super().__init__()
        self.start_backup_cb = start_backup_cb
        self.start_flash_cb = start_flash_cb
        self.flashrom = find_flashrom() or ""
        self.fw_path: Optional[Path] = None

        layout = QVBoxLayout(self); layout.setContentsMargins(10,10,10,10); layout.setSpacing(10)

        row = QHBoxLayout()
        lbl = QLabel("Select BIN file:")
        self.path_edit = QLineEdit(); self.path_edit.setReadOnly(True)
        browse = QPushButton("Browse"); browse.clicked.connect(self.pick_bin)
        row.addWidget(lbl); row.addWidget(self.path_edit, 1); row.addWidget(browse)
        layout.addLayout(row)

        self.status = QLabel("Waiting for file…"); layout.addWidget(self.status)
        self.pb = QProgressBar(); self.pb.setRange(0, 100); self.pb.setValue(0); layout.addWidget(self.pb)

        self.log = QTextEdit(); self.log.setReadOnly(True); layout.addWidget(self.log, 1)

        bottom = QHBoxLayout()
        backup_icon = QIcon(resource_path("backup.png")) if Path(resource_path("backup.png")).exists() else QIcon()
        flash_icon  = QIcon(resource_path("flash.png"))  if Path(resource_path("flash.png")).exists()  else QIcon()

        self.btn_backup = QPushButton("BACKUP")
        if not backup_icon.isNull(): self.btn_backup.setIcon(backup_icon); self.btn_backup.setIconSize(QtCore.QSize(22, 22))
        self.btn_backup.setStyleSheet("font-size:16px; font-weight:600; height:36px;")
        self.btn_backup.clicked.connect(self.on_backup_pressed)
        bottom.addWidget(self.btn_backup)

        self.flash_btn = QPushButton("FLASH")
        if not flash_icon.isNull(): self.flash_btn.setIcon(flash_icon); self.flash_btn.setIconSize(QtCore.QSize(22, 22))
        self.flash_btn.setStyleSheet("font-size:16px; font-weight:600; height:36px;")
        self.flash_btn.clicked.connect(self.on_flash_pressed)
        bottom.addWidget(self.flash_btn)

        layout.addLayout(bottom)

        if not self.flashrom:
            self.append_log("flashrom not found. Install with Homebrew: brew install flashrom\n")

    def set_fw_path(self, path: str):
        self.fw_path = Path(path); self.path_edit.setText(path)
        self.status.setText("Ready to flash (from Internet).")

    def append_log(self, text: str):
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log.setTextCursor(cursor)
        self.log.insertPlainText(text)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def pick_bin(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select firmware .bin", "", "BIN (*.bin)")
        if not path: return
        if not path.lower().endswith(".bin"):
            QMessageBox.critical(self, "Error", "Please select a valid .bin file."); return
        size = os.path.getsize(path)
        if size > HDZERO_MAX:
            QMessageBox.critical(self, "Error", "Firmware > 64KB; not valid for HDZero."); return
        self.set_fw_path(path); self.status.setText("Ready to flash.")

    def on_backup_pressed(self): self.start_backup_cb()
    def on_flash_pressed(self):
        if not self.fw_path or not self.fw_path.exists():
            QMessageBox.critical(self, "Error", "Select or download a .bin file first."); return
        self.start_flash_cb(str(self.fw_path))

class HelpPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(10,10,10,10); layout.setSpacing(10)

        # Cargar README
        readme_text = "README not found."
        for p in ("Readme.md", "README.md", "Readme,md"):
            rp = resource_path(p)
            if Path(rp).exists():
                try:
                    readme_text = Path(rp).read_text(encoding="utf-8"); break
                except Exception: pass

        md = QTextEdit(); md.setReadOnly(True); md.setPlainText(readme_text); md.setMinimumHeight(260)
        layout.addWidget(md, 1)

        # Logo Next al 50%
        next_path = resource_path("next.png")
        logo = QLabel(); logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        if Path(next_path).exists():
            pix = QPixmap(next_path)
            if not pix.isNull():
                w = max(1, pix.width() // 2); h = max(1, pix.height() // 2)
                scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo.setPixmap(scaled)
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(700, 620)
        self.setMinimumSize(680, 600)

        self.flashrom = find_flashrom() or ""
        self.fw_path: Optional[Path] = None

        # Estilo oscuro + tabs gris
        self.setStyleSheet("""
            QWidget { background: #000; color: #fff; }
            QTabWidget::pane { border: 1px solid #2a2a2a; background: #1a1a1a; }
            QTabBar::tab { background: #262626; color: #fff; padding: 8px 14px; border: 1px solid #333; border-bottom: none; }
            QTabBar::tab:selected { background: #333333; }
            QLineEdit, QTextEdit, QComboBox, QProgressBar { background: #121212; color: #fff; border: 1px solid #333; }
            QPushButton { background: #1f1f1f; color: #fff; border: 1px solid #3a3a3a; padding: 8px 12px; border-radius: 6px; }
            QPushButton:hover { background: #2a2a2a; }
            QLabel { color: #fff; }
        """)

        layout = QVBoxLayout(self); layout.setContentsMargins(12,12,12,12); layout.setSpacing(10)

        # Header
        header = QHBoxLayout(); header.setSpacing(12)
        icon_path = resource_path("icon256.png")
        if Path(icon_path).exists():
            pix = QPixmap(icon_path).scaledToHeight(64, Qt.TransformationMode.SmoothTransformation)
            icon_lbl = QLabel(); icon_lbl.setPixmap(pix); header.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        title_lbl = QLabel(APP_HEADER_TITLE); title_lbl.setStyleSheet("font-size:22px; font-weight:700;")
        header.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addStretch(1)
        layout.addLayout(header)
        layout.addSpacing(14)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setMovable(False)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #2a2a2a; background: #1a1a1a; }
            QTabBar::tab { background:#262626; color:#fff; padding:8px 14px; padding-left:26px;
                           border:1px solid #333; border-bottom:none; text-align:left; min-width:120px; }
            QTabBar::tab:selected { background:#333333; }
        """)

        # Instancias de paneles
        self.panel_internet = InternetPanel()
        self.panel_local = LocalPanel(start_backup_cb=self.start_backup, start_flash_cb=self.start_flash)
        self.panel_help = HelpPanel()

        # Conexiones entre paneles
        self.panel_internet.firmwareSelected.connect(self.on_fw_downloaded_set_local)
        self.panel_internet.log.connect(self.panel_local.append_log)
        self.panel_internet.flashRequested.connect(self.start_flash)

        # Tabs con íconos
        icon_internet = QIcon(resource_path("internet.png")) if Path(resource_path("internet.png")).exists() else QIcon()
        icon_pc       = QIcon(resource_path("pc.png"))       if Path(resource_path("pc.png")).exists()       else QIcon()
        icon_info     = QIcon(resource_path("info.png"))     if Path(resource_path("info.png")).exists()     else QIcon()

        self.tabs.addTab(self.panel_internet, icon_internet, "Internet")
        self.tabs.addTab(self.panel_local, icon_pc, "Local")
        self.tabs.addTab(self.panel_help, icon_info, "Help")

        layout.addWidget(self.tabs, 1)

        if not self.flashrom:
            self.panel_local.append_log("flashrom not found. Install with Homebrew: brew install flashrom\n")

    # ==== Handlers de alto nivel (reutilizados por ambos tabs) ====
    def on_fw_downloaded_set_local(self, path: str):
        self.fw_path = Path(path)
        self.panel_local.set_fw_path(path)
        self.panel_local.append_log(f"Downloaded from Internet → {path}\n")

    def start_backup(self):
        if not self.flashrom or not os.path.exists(self.flashrom):
            QMessageBox.critical(self, "Error", "flashrom not found. Install: brew install flashrom")
            return
        ts = time.strftime("%Y%m%d-%H%M%S")
        out = os.path.expanduser(f"~/HDZero_backup_{ts}.bin")
        self.panel_local.btn_backup.setEnabled(False)
        self.panel_local.flash_btn.setEnabled(False)
        self.panel_local.status.setText("Backing up…")
        self.panel_local.pb.setRange(0, 0)

        self.bkw = BackupWorker(self.flashrom, out)
        self.bkw.log.connect(self.panel_local.append_log)
        self.bkw.ok.connect(self.on_backup_ok)
        self.bkw.fail.connect(self.on_backup_fail)
        self.bkw.start()

    def on_backup_ok(self, out_path: str):
        self.panel_local.status.setText("✅ Backup done")
        self.panel_local.pb.setRange(0, 100)
        self.panel_local.pb.setValue(100)
        self.panel_local.append_log(f"Backup saved: {out_path}\n")
        QMessageBox.information(self, "Backup", f"Backup saved at:\n{out_path}")
        self.panel_local.btn_backup.setEnabled(True)
        self.panel_local.flash_btn.setEnabled(True)

    def on_backup_fail(self, msg: str):
        self.panel_local.status.setText("❌ Backup error")
        self.panel_local.pb.setRange(0, 100)
        self.panel_local.pb.setValue(100)
        self.panel_local.append_log(f"\nERROR: {msg}\n")
        QMessageBox.critical(self, "Error", msg)
        self.panel_local.btn_backup.setEnabled(True)
        self.panel_local.flash_btn.setEnabled(True)

    def start_flash(self, fw_path: str):
        if not fw_path or not Path(fw_path).exists():
            QMessageBox.critical(self, "Error", "Select a .bin file.")
            return
        if not self.flashrom or not os.path.exists(self.flashrom):
            QMessageBox.critical(self, "Error", "flashrom not found. Install: brew install flashrom")
            return

        self.panel_local.flash_btn.setEnabled(False)
        self.panel_local.btn_backup.setEnabled(False)
        self.panel_local.pb.setRange(0, 100)
        self.panel_local.pb.setValue(0)
        self.panel_local.status.setText("Flashing…")

     
        self.worker = FlashWorker(self.flashrom, fw_path)

        self.worker.progress.connect(self.panel_local.pb.setValue)
        self.worker.status.connect(self.panel_local.status.setText)
        self.worker.log.connect(self.panel_local.append_log)
        self.worker.ok.connect(self.on_flash_ok)
        self.worker.fail.connect(self.on_flash_fail)

        self.worker.status.connect(self.panel_internet.set_phase)

        self.worker.log.connect(self.panel_internet.status_append)

        self.worker.start()

    def on_flash_ok(self):
        self.panel_local.status.setText("✅ Done")
        self.panel_local.pb.setValue(100)
        self.panel_internet.status_append("Finished.")
        QMessageBox.information(self, "Success", "Flash completed and verified.")
        self.panel_local.flash_btn.setEnabled(True)
        self.panel_local.btn_backup.setEnabled(True)

    def on_flash_fail(self, msg: str):
        self.panel_local.status.setText("❌ Error")
        self.panel_local.pb.setValue(100)
        self.panel_internet.status_append(f"ERROR: {msg}")
        self.panel_local.append_log(f"\nERROR: {msg}\n")
        QMessageBox.critical(self, "Error", msg)
        self.panel_local.flash_btn.setEnabled(True)
        self.panel_local.btn_backup.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app_icon_path = resource_path("icon256.png")
    if Path(app_icon_path).exists():
        app.setWindowIcon(QIcon(app_icon_path))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
