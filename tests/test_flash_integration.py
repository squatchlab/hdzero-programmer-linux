"""End-to-end FlashWorker tests against a fake flashrom binary.

We drive `FlashWorker.run()` synchronously (calling the method, not
`start()`) so the test stays single-threaded — signal slots fire inline,
which lets us collect emissions into plain lists without a Qt event loop.

HDZERO_NO_ESCALATE=1 short-circuits run_admin_streaming so it executes
the fake binary via `sh -c` as the current user, no pkexec/sudo. The
fake flashrom (tests/fixtures/fake_flashrom.sh) emits stdout markers
matching the patterns FlashWorker.run() greps for live phase status.
"""
import os
import stat
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "fake_flashrom.sh"


@pytest.fixture(autouse=True)
def _no_escalate(monkeypatch):
    monkeypatch.setenv("HDZERO_NO_ESCALATE", "1")
    monkeypatch.delenv("FAKE_FLASHROM_FAIL", raising=False)


@pytest.fixture
def fake_flashrom():
    # Belt-and-braces: ensure the fixture is executable even if checked
    # out without the +x bit (e.g. some Windows-mediated transfers).
    mode = FIXTURE.stat().st_mode
    FIXTURE.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(FIXTURE)


@pytest.fixture
def small_firmware(tmp_path):
    fw = tmp_path / "fw.bin"
    fw.write_bytes(b"\xAB\xCD\xEF\x01" * 4096)  # 16 KiB, well under HDZERO_MAX
    return str(fw)


def _run_worker(qt_app, worker):
    """Collect signals and run the worker body inline."""
    statuses = []
    logs = []
    ok = []
    fails = []

    worker.status.connect(statuses.append)
    worker.log.connect(logs.append)
    worker.ok.connect(lambda: ok.append(True))
    worker.fail.connect(fails.append)

    # Direct .run() call — synchronous, single-threaded.
    worker.run()
    return {"statuses": statuses, "logs": logs, "ok": ok, "fails": fails}


# ---------- happy path with backup ----------

def test_safe_flash_with_backup_emits_all_phases(qt_app, fake_flashrom, small_firmware, tmp_path):
    from flash_ops import FlashWorker

    backup_path = tmp_path / "backup.bin"
    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=str(backup_path))

    result = _run_worker(qt_app, worker)

    assert result["fails"] == []
    assert result["ok"] == [True]

    joined = "\n".join(result["statuses"])
    # Phase markers in order: prep, safe-flash banner, backup, flash, verify, done.
    assert "Prepare firmware" in joined
    assert "Safe flash (backup → write → verify)" in joined
    assert "Backup (reading chip)" in joined
    assert "Flashing" in joined
    assert "Verifying" in joined
    assert "Done." in joined

    # Backup file produced by the fake harness should be 1 MiB.
    assert backup_path.exists()
    assert backup_path.stat().st_size == 1024 * 1024


# ---------- happy path without backup ----------

def test_safe_flash_no_backup_skips_read_phase(qt_app, fake_flashrom, small_firmware):
    from flash_ops import FlashWorker

    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=None)
    result = _run_worker(qt_app, worker)

    assert result["fails"] == []
    assert result["ok"] == [True]

    joined = "\n".join(result["statuses"])
    assert "Safe flash (write → verify)" in joined
    # No backup phase status when backup_path is None.
    assert "Backup (reading chip)" not in joined
    assert "Flashing" in joined
    assert "Verifying" in joined


# ---------- failure injection ----------

def test_safe_flash_write_failure_short_circuits(monkeypatch, qt_app, fake_flashrom, small_firmware, tmp_path):
    from flash_ops import FlashWorker

    monkeypatch.setenv("FAKE_FLASHROM_FAIL", "write")

    backup_path = tmp_path / "backup.bin"
    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=str(backup_path))
    result = _run_worker(qt_app, worker)

    assert result["ok"] == []
    assert len(result["fails"]) == 1
    assert "Safe flash failed" in result["fails"][0]

    # Backup runs first (and succeeds) under `&&` chaining, so the file
    # should still exist as the rollback image even though the write blew up.
    assert backup_path.exists()


def test_safe_flash_verify_failure_surfaces_in_log(monkeypatch, qt_app, fake_flashrom, small_firmware):
    from flash_ops import FlashWorker

    monkeypatch.setenv("FAKE_FLASHROM_FAIL", "verify")

    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=None)
    result = _run_worker(qt_app, worker)

    assert result["ok"] == []
    assert len(result["fails"]) == 1

    log_blob = "".join(result["logs"])
    # The fake harness emits this exact failure line on stderr (folded into
    # stdout by run_admin_streaming) — confirms the streaming pipeline
    # routes both streams to the GUI log.
    assert "verify mismatch at 0x10000" in log_blob


# ---------- backup_path attribute is preserved ----------

def test_flashworker_records_backup_path(qt_app, fake_flashrom, small_firmware):
    from flash_ops import FlashWorker

    worker = FlashWorker(fake_flashrom, small_firmware, backup_path="/tmp/whatever.bin")
    assert worker.backup_path == "/tmp/whatever.bin"
