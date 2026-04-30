import os
from pathlib import Path

from app_logging import open_flash_log, state_dir

# ---------- state_dir resolution ----------

def test_state_dir_uses_hdzero_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HDZERO_STATE_DIR", str(tmp_path / "custom"))
    assert state_dir() == tmp_path / "custom"


def test_state_dir_falls_back_to_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("HDZERO_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert state_dir() == tmp_path / "xdg" / "hdzero-programmer"


def test_state_dir_default_when_no_env(monkeypatch):
    monkeypatch.delenv("HDZERO_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    expected = Path(os.path.expanduser("~/.local/state")) / "hdzero-programmer"
    assert state_dir() == expected


# ---------- open_flash_log ----------

def test_open_flash_log_creates_dir_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HDZERO_STATE_DIR", str(tmp_path / "state"))
    path, fh = open_flash_log("flash", "9.9.9")
    try:
        assert path.parent == tmp_path / "state"
        assert path.exists()
        assert path.name.startswith("flash-")
        assert path.name.endswith(".log")
    finally:
        fh.close()


def test_open_flash_log_writes_header(monkeypatch, tmp_path):
    monkeypatch.setenv("HDZERO_STATE_DIR", str(tmp_path / "state"))
    path, fh = open_flash_log("backup", "1.2.3")
    fh.close()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("=== backup ")
    assert "(hdzero-programmer 1.2.3)" in content


def test_open_flash_log_is_line_buffered(monkeypatch, tmp_path):
    monkeypatch.setenv("HDZERO_STATE_DIR", str(tmp_path / "state"))
    path, fh = open_flash_log("flash", "0.0.0")
    try:
        fh.write("partial line without newline")
        # Without newline, buffer keeps it. Confirms buffering=1 (line)
        # rather than 0 (unbuffered).
        first_read = path.read_text(encoding="utf-8")
        assert "partial line" not in first_read
        fh.write("\n")
        # Now the buffer flushed on the newline.
        second_read = path.read_text(encoding="utf-8")
        assert "partial line without newline" in second_read
    finally:
        fh.close()
