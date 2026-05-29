"""#90: coverage for previously-untested error / edge paths.

A grab-bag of defensive branches that only fire on failure:
- run_admin_streaming with no escalation tool, and with non-UTF-8 output
- FlashWorker's padded-image cleanup when unlink raises
- HelpPanel's README-load fallback

Stream-download / Content-Length edge cases are covered separately in
test_http_worker.py (#81). Two #90 items are deferred:
- SIGKILL-after-SIGTERM in run_admin_streaming — its hard-coded 5s wait
  makes a fast, non-flaky test awkward without refactoring the code.
- HelpPanel README-load fallback — needs the GUI QApplication fixture
  introduced with #82; file once that lands so QWidget construction is safe.
"""
import stat
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "fake_flashrom.sh"


@pytest.fixture
def _no_escalate(monkeypatch):
    monkeypatch.setenv("HDZERO_NO_ESCALATE", "1")
    monkeypatch.delenv("FAKE_FLASHROM_FAIL", raising=False)


@pytest.fixture
def fake_flashrom():
    mode = FIXTURE.stat().st_mode
    FIXTURE.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(FIXTURE)


# ---------- run_admin_streaming ----------

def test_run_admin_streaming_no_escalation_tool_returns_127(monkeypatch):
    """With neither pkexec nor sudo available and not running as root,
    run_admin_streaming returns 127 and emits the install hint rather than
    raising."""
    import flash_ops

    # Force the "no tool" branch: not root, and which() finds nothing.
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    monkeypatch.setattr(flash_ops.os, "geteuid", lambda: 1000)
    monkeypatch.setattr("shutil.which", lambda _name: None)

    lines = []
    rc = flash_ops.run_admin_streaming("echo nope", lines.append)

    assert rc == 127
    assert any("No privilege escalation tool" in line for line in lines)


def test_run_admin_streaming_non_utf8_output_decodes_to_replacement(
    _no_escalate,
):
    """flashrom output is decoded errors='replace'; an invalid UTF-8 byte
    must surface as U+FFFD on the callback, not crash the reader thread."""
    import flash_ops

    lines = []
    # \303 (0xC3) starts a 2-byte sequence; \050 ('(') is an invalid
    # continuation byte -> one U+FFFD.
    rc = flash_ops.run_admin_streaming(r"printf '\303\050\n'", lines.append)

    assert rc == 0
    assert "�" in "".join(lines)


# ---------- FlashWorker cleanup ----------

def test_flash_cleanup_oserror_is_logged_not_raised(
    _no_escalate, qt_app, fake_flashrom, tmp_path, monkeypatch
):
    """If unlinking the padded tempfile fails, the worker logs it and still
    reports success — cleanup failure must not mask a good flash."""
    import flash_ops
    from flash_ops import FlashWorker

    fw = tmp_path / "fw.bin"
    fw.write_bytes(b"\x01\x02\x03\x04" * 4096)

    # Make every unlink during the run fail.
    def boom_unlink(_path):
        raise OSError("unlink denied")

    monkeypatch.setattr(flash_ops.os, "unlink", boom_unlink)

    logs, ok, fails = [], [], []
    worker = FlashWorker(fake_flashrom, str(fw), backup_path=None)
    worker.log.connect(logs.append)
    worker.ok.connect(lambda: ok.append(True))
    worker.fail.connect(fails.append)
    worker.run()

    assert ok == [True], fails
    assert any("temp cleanup" in line for line in logs)
