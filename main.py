# main.py
import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from flash_ops import HDZERO_MAX, BackupWorker, FlashWorker, find_flashrom
from internet_panel import InternetPanel, resource_path
from udev_check import (
    bundled_rule_path,
    ch341a_present,
    escalation_disabled,
    install_command,
    rule_installed,
    should_show_hint,
)

# Hard-coded so AppImage runs (which graft source into site-packages
# without dist-info) can still report a version. Kept in sync with
# pyproject.toml by tests/test_version_consistency.py.
__version__ = "0.2.0"

SETTINGS_ORG = "HDZero"
SETTINGS_APP = "Programmer"
SETTINGS_KEY_AUTOBACKUP = "autobackup"

APP_TITLE = "HDZero Programmer Tool – by Gunther_FPV"
APP_HEADER_TITLE = "HDZero Programmer (Linux)"

FLASHROM_INSTALL_HINT = (
    "flashrom not found. Install via your distro's package manager:\n"
    "  Debian/Ubuntu: sudo apt install flashrom\n"
    "  Fedora/RHEL:   sudo dnf install flashrom\n"
    "  Arch:          sudo pacman -S flashrom\n"
)

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

        self.cb_autobackup = QCheckBox("Backup chip before flashing (rollback image in ~)")
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.cb_autobackup.setChecked(
            settings.value(SETTINGS_KEY_AUTOBACKUP, True, type=bool)
        )
        self.cb_autobackup.toggled.connect(self._persist_autobackup)
        layout.addWidget(self.cb_autobackup)

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
            self.append_log(FLASHROM_INSTALL_HINT)

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

    @staticmethod
    def _persist_autobackup(checked: bool) -> None:
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(
            SETTINGS_KEY_AUTOBACKUP, checked
        )

    def on_backup_pressed(self): self.start_backup_cb()
    def on_flash_pressed(self):
        if not self.fw_path or not self.fw_path.exists():
            QMessageBox.critical(self, "Error", "Select or download a .bin file first."); return
        self.start_flash_cb(str(self.fw_path), self.cb_autobackup.isChecked())

class HelpPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(10,10,10,10); layout.setSpacing(10)

        # Cargar README
        readme_text = "README not found."
        for p in ("README.md", "Readme.md"):
            rp = resource_path(p)
            if Path(rp).exists():
                try:
                    readme_text = Path(rp).read_text(encoding="utf-8"); break
                except Exception: pass

        md = QTextEdit(); md.setReadOnly(True); md.setMarkdown(readme_text); md.setMinimumHeight(260)
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
        self.panel_internet.flashRequested.connect(self.start_flash)  # (path, autobackup)

        # Tabs con íconos
        icon_internet = QIcon(resource_path("internet.png")) if Path(resource_path("internet.png")).exists() else QIcon()
        icon_pc       = QIcon(resource_path("pc.png"))       if Path(resource_path("pc.png")).exists()       else QIcon()
        icon_info     = QIcon(resource_path("info.png"))     if Path(resource_path("info.png")).exists()     else QIcon()

        self.tabs.addTab(self.panel_internet, icon_internet, "Internet")
        self.tabs.addTab(self.panel_local, icon_pc, "Local")
        self.tabs.addTab(self.panel_help, icon_info, "Help")

        layout.addWidget(self.tabs, 1)

        if not self.flashrom:
            self.panel_local.append_log(FLASHROM_INSTALL_HINT)

        self._maybe_install_udev_banner(layout)

    def _maybe_install_udev_banner(self, layout: QVBoxLayout) -> None:
        """Insert a dismissible banner above the tabs when the CH341A udev
        rule is missing. Suppressed if HDZERO_NO_ESCALATE is set or the rule
        is already in place — see udev_check.should_show_hint.
        """
        if not should_show_hint():
            return

        rule_src = bundled_rule_path()
        if not rule_src:
            # No bundled rule to point at — silent skip rather than a broken
            # copy-paste line.
            return

        cmd = install_command(rule_src)
        banner = QWidget()
        banner.setStyleSheet(
            "background:#3a2a00; border:1px solid #6a4a00; border-radius:6px;"
        )
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(6)

        msg = QLabel(
            "CH341A udev rule not installed. Each flash will pop a polkit "
            "prompt. Run this once to flash without root:"
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("background: transparent; border: none; color:#ffe6a0;")

        cmd_box = QLineEdit(cmd)
        cmd_box.setReadOnly(True)
        cmd_box.setStyleSheet(
            "background:#1a1200; color:#ffeec0; border:1px solid #5a3e00; "
            "font-family: monospace;"
        )

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        btn_dismiss = QPushButton("Dismiss")
        btn_dismiss.setStyleSheet(
            "background:#1f1f1f; color:#fff; border:1px solid #3a3a3a; "
            "padding:4px 10px; border-radius:4px;"
        )
        btn_dismiss.clicked.connect(banner.hide)
        row.addStretch(1)
        row.addWidget(btn_dismiss)

        bl.addWidget(msg)
        bl.addWidget(cmd_box)
        bl.addLayout(row)

        # Insert above the tabs (index 2: header layout, spacing, then tabs).
        # insertWidget at index 2 keeps the header on top and pushes tabs down.
        layout.insertWidget(2, banner)

    def _confirm_ch341a_present(self) -> bool:
        """Soft-check that a CH341A is enumerated before launching a worker.

        Skipped entirely if HDZERO_SKIP_CH341A_CHECK is set in the env (escape
        hatch for sandboxed runs without a readable /sys, or for hardware
        variants we don't recognise yet). When the device is missing we ask
        rather than block — the user might have a non-CH341A programmer wired
        through a passthrough flashrom does recognise.
        """
        if os.environ.get("HDZERO_SKIP_CH341A_CHECK"):
            return True
        if ch341a_present():
            return True

        reply = QMessageBox.question(
            self,
            "No CH341A detected",
            "No CH341A USB SPI programmer is currently enumerated by the "
            "kernel.\n\nFlashing now will almost certainly fail at the "
            "flashrom step. Continue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    # ==== Handlers de alto nivel (reutilizados por ambos tabs) ====
    def on_fw_downloaded_set_local(self, path: str):
        self.fw_path = Path(path)
        self.panel_local.set_fw_path(path)
        self.panel_local.append_log(f"Downloaded from Internet → {path}\n")

    def start_backup(self):
        if not self.flashrom or not os.path.exists(self.flashrom):
            QMessageBox.critical(self, "Error", FLASHROM_INSTALL_HINT)
            return
        if not self._confirm_ch341a_present():
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

    def start_flash(self, fw_path: str, autobackup: bool = True):
        if not fw_path or not Path(fw_path).exists():
            QMessageBox.critical(self, "Error", "Select a .bin file.")
            return
        if not self.flashrom or not os.path.exists(self.flashrom):
            QMessageBox.critical(self, "Error", FLASHROM_INSTALL_HINT)
            return
        if not self._confirm_ch341a_present():
            return

        self.panel_local.flash_btn.setEnabled(False)
        self.panel_local.btn_backup.setEnabled(False)
        self.panel_local.pb.setRange(0, 100)
        self.panel_local.pb.setValue(0)
        self.panel_local.status.setText("Flashing…")

        backup_path: Optional[str] = None
        if autobackup:
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup_path = os.path.expanduser(f"~/HDZero_pre-flash_{ts}.bin")

        self.worker = FlashWorker(self.flashrom, fw_path, backup_path=backup_path)

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

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hdzero-programmer",
        description="Linux desktop GUI for flashing HDZero VTX firmware "
                    "via a CH341A USB SPI programmer.",
    )
    p.add_argument("--version", action="version", version=f"hdzero-programmer {__version__}")
    p.add_argument(
        "--check-rule",
        action="store_true",
        help="Print udev rule status and exit. rc=0 if the rule is installed "
             "or HDZERO_NO_ESCALATE is set; rc=1 otherwise.",
    )
    return p


def _run_check_rule() -> int:
    installed = rule_installed()
    no_escalate = escalation_disabled()
    print(f"rule_installed: {installed}")
    print(f"escalation_disabled: {no_escalate}")
    return 0 if (installed or no_escalate) else 1


def main(argv=None) -> int:
    parser = _build_argparser()
    # argparse splits its own flags off; everything else is forwarded to
    # QApplication so platform plugin args (-style, -platform, …) still work.
    args, qt_argv = parser.parse_known_args(argv)
    if args.check_rule:
        return _run_check_rule()

    app = QApplication([sys.argv[0], *qt_argv])
    app_icon_path = resource_path("icon256.png")
    if Path(app_icon_path).exists():
        app.setWindowIcon(QIcon(app_icon_path))
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
