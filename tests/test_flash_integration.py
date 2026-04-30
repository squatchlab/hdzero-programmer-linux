"""End-to-end FlashWorker tests against a fake flashrom binary.

We drive `FlashWorker.run()` synchronously (calling the method, not
`start()`) so the test stays single-threaded — signal slots fire inline,
which lets us collect emissions into plain lists without a Qt event loop.

HDZERO_NO_ESCALATE=1 short-circuits run_admin_streaming so it executes
the fake binary via `sh -c` as the current user, no pkexec/sudo. The
fake flashrom (tests/fixtures/fake_flashrom.sh) emits stdout markers
matching the patterns FlashWorker.run() greps for live phase status.
"""
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


# ---------- shell-quoting hardening ----------

def test_safe_flash_handles_path_with_spaces(qt_app, fake_flashrom, small_firmware, tmp_path):
    """Backup path containing a space and a single quote must round-trip
    through the shlex.quote'd `sh -c '... && ...'` chain unscathed.
    """
    from flash_ops import FlashWorker

    weird_dir = tmp_path / "dir with space and 'quote"
    weird_dir.mkdir()
    backup_path = weird_dir / "backup.bin"

    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=str(backup_path))
    result = _run_worker(qt_app, worker)

    assert result["fails"] == [], result["fails"]
    assert result["ok"] == [True]
    assert backup_path.exists()
    assert backup_path.stat().st_size == 1024 * 1024


# ---------- tempfile cleanup ----------

def test_flash_unlinks_padded_image_after_success(qt_app, fake_flashrom, small_firmware, tmp_path):
    """The padded-1MiB tempfile is always owned by FlashWorker; it must
    be unlinked on the success path so /tmp doesn't accumulate stale
    1MiB blobs across repeated flashes.
    """
    import glob

    from flash_ops import FlashWorker

    before = set(glob.glob("/tmp/hdzero_*.bin"))
    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=None)
    result = _run_worker(qt_app, worker)
    assert result["ok"] == [True], result["fails"]

    after = set(glob.glob("/tmp/hdzero_*.bin"))
    leaked = after - before
    # Only the download-shaped tempfiles (hdzero_dl_*) are owned elsewhere.
    leaked_padded = [p for p in leaked if "hdzero_dl_" not in p]
    assert leaked_padded == [], f"padded image not unlinked: {leaked_padded}"


def test_flash_unlinks_padded_image_after_failure(monkeypatch, qt_app, fake_flashrom, small_firmware):
    """Cleanup runs even when the flash fails — the finally clause covers
    both branches.
    """
    import glob

    from flash_ops import FlashWorker

    monkeypatch.setenv("FAKE_FLASHROM_FAIL", "write")
    before = set(glob.glob("/tmp/hdzero_*.bin"))
    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=None)
    _ = _run_worker(qt_app, worker)

    after = set(glob.glob("/tmp/hdzero_*.bin"))
    leaked_padded = [p for p in (after - before) if "hdzero_dl_" not in p]
    assert leaked_padded == [], f"padded image not unlinked on failure: {leaked_padded}"


def test_flash_unlinks_source_fw_when_cleanup_flag_set(qt_app, fake_flashrom, tmp_path):
    """When cleanup_fw=True (InternetPanel-download path), the source
    firmware tempfile is unlinked too. LocalPanel's user-selected file
    must NOT be unlinked — separate test below.
    """
    from flash_ops import FlashWorker

    fw = tmp_path / "downloaded.bin"
    fw.write_bytes(b"\x42" * 4096)
    assert fw.exists()

    worker = FlashWorker(fake_flashrom, str(fw), backup_path=None, cleanup_fw=True)
    result = _run_worker(qt_app, worker)
    assert result["ok"] == [True]
    assert not fw.exists(), "source fw should be unlinked when cleanup_fw=True"


def test_flash_preserves_source_fw_when_cleanup_flag_unset(qt_app, fake_flashrom, small_firmware):
    """The default (cleanup_fw=False) leaves the user's .bin alone. This
    is the LocalPanel path — the firmware is not the worker's to delete.
    """
    import os

    from flash_ops import FlashWorker

    assert os.path.exists(small_firmware)
    worker = FlashWorker(fake_flashrom, small_firmware, backup_path=None)
    result = _run_worker(qt_app, worker)
    assert result["ok"] == [True]
    assert os.path.exists(small_firmware), "user-selected .bin must not be unlinked"


def test_backup_worker_handles_path_with_spaces(qt_app, fake_flashrom, tmp_path):
    from flash_ops import BackupWorker

    weird_dir = tmp_path / "weird dir"
    weird_dir.mkdir()
    out = weird_dir / "out.bin"

    worker = BackupWorker(fake_flashrom, str(out))
    oks = []
    fails = []
    worker.ok.connect(oks.append)
    worker.fail.connect(fails.append)
    worker.run()

    assert fails == []
    assert oks == [str(out)]
    assert out.exists()
    assert out.stat().st_size == 1024 * 1024
