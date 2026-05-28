"""#82: MainWindow backup-dir creation error handling.

`start_backup` and `start_flash` both create `backup_dir()` before
launching a worker. If the mkdir fails (disk-full, EROFS, a bad
XDG_STATE_HOME), the handler must pop a critical dialog and return
*without* starting a worker — never leave the UI mid-operation against a
directory that doesn't exist.

These construct a real MainWindow under the shared offscreen QApplication
(`qt_app`). MainWindow.__init__ does no network I/O, so construction is
cheap and deterministic.
"""
import pytest


class _BoomDir:
    """Stand-in for backup_dir()'s return: .mkdir always raises OSError."""

    def mkdir(self, *args, **kwargs):
        raise OSError("No space left on device")


@pytest.fixture
def main_window(qt_app, monkeypatch):
    # A real, existing executable so the `os.path.exists(self.flashrom)`
    # guard passes and we reach the backup-dir creation.
    from main import MainWindow

    monkeypatch.setenv("HDZERO_SKIP_CH341A_CHECK", "1")
    w = MainWindow()
    w.flashrom = "/bin/sh"
    yield w
    w.deleteLater()


def _capture_critical(monkeypatch):
    calls = []
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "critical", lambda *a, **k: calls.append(a[1:3])
    )
    return calls


def test_start_backup_mkdir_failure_aborts_with_dialog(main_window, monkeypatch):
    import main

    calls = _capture_critical(monkeypatch)
    monkeypatch.setattr(main, "backup_dir", lambda: _BoomDir())

    main_window.start_backup()

    assert len(calls) == 1
    assert "Cannot create backup dir" in calls[0][1]
    # Returned before constructing/starting the BackupWorker.
    assert not hasattr(main_window, "bkw")


def test_start_flash_autobackup_mkdir_failure_aborts_with_dialog(
    main_window, monkeypatch, tmp_path
):
    import main

    fw = tmp_path / "fw.bin"
    fw.write_bytes(b"\x00" * 1024)

    calls = _capture_critical(monkeypatch)
    monkeypatch.setattr(main, "backup_dir", lambda: _BoomDir())

    main_window.start_flash(str(fw), autobackup=True)

    assert len(calls) == 1
    assert "Cannot create backup dir" in calls[0][1]
    # Returned before constructing/starting the FlashWorker.
    assert not hasattr(main_window, "worker")
