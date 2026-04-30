import os
import subprocess
from pathlib import Path

import pytest

from flash_ops import (
    FLASH_SIZE_BYTES,
    HDZERO_MAX,
    _build_admin_argv,
    find_flashrom,
    make_padded_image_1mib,
    run_admin,
)


# ---------- make_padded_image_1mib ----------

def test_padded_image_pads_to_1mib_with_ff(tmp_path):
    src = tmp_path / "fw.bin"
    payload = b"\x00\x11\x22\x33" * 256  # 1 KiB of non-FF
    src.write_bytes(payload)

    out_path = make_padded_image_1mib(str(src))
    try:
        data = Path(out_path).read_bytes()
        assert len(data) == FLASH_SIZE_BYTES
        assert data[: len(payload)] == payload
        # Tail must be 0xFF (mandatory for W25Q80 — chip ships erased).
        assert data[len(payload):] == b"\xFF" * (FLASH_SIZE_BYTES - len(payload))
    finally:
        os.unlink(out_path)


def test_padded_image_rejects_oversize(tmp_path):
    src = tmp_path / "fw.bin"
    src.write_bytes(b"\x00" * (FLASH_SIZE_BYTES + 1))
    with pytest.raises(RuntimeError, match="larger than 1 MiB"):
        make_padded_image_1mib(str(src))


def test_padded_image_accepts_exact_1mib(tmp_path):
    src = tmp_path / "fw.bin"
    src.write_bytes(b"\xAB" * FLASH_SIZE_BYTES)
    out_path = make_padded_image_1mib(str(src))
    try:
        assert Path(out_path).stat().st_size == FLASH_SIZE_BYTES
    finally:
        os.unlink(out_path)


# ---------- HDZERO_MAX is a UI gate, not a flash-time constraint ----------

def test_hdzero_max_constant():
    # 64 KiB ceiling on user-facing .bin selection; the padded image is
    # always 1 MiB regardless of input size.
    assert HDZERO_MAX == 64 * 1024


# ---------- find_flashrom ----------

def test_find_flashrom_returns_first_existing(monkeypatch, tmp_path):
    fake = tmp_path / "flashrom"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setattr("flash_ops.FLASHROM_PATHS", [str(fake)])
    assert find_flashrom() == str(fake)


def test_find_flashrom_falls_back_to_which(monkeypatch):
    monkeypatch.setattr("flash_ops.FLASHROM_PATHS", ["/nonexistent/flashrom"])
    monkeypatch.setattr("shutil.which", lambda name: "/from/which/" + name)
    assert find_flashrom() == "/from/which/flashrom"


def test_find_flashrom_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr("flash_ops.FLASHROM_PATHS", ["/nonexistent/flashrom"])
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert find_flashrom() is None


# ---------- _build_admin_argv ----------

def test_admin_argv_root_skips_escalation(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    assert _build_admin_argv("flashrom -V") == ["/bin/sh", "-c", "flashrom -V"]


def test_admin_argv_no_escalate_env_skips_escalation(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("HDZERO_NO_ESCALATE", "1")
    assert _build_admin_argv("flashrom -V") == ["/bin/sh", "-c", "flashrom -V"]


def test_admin_argv_prefers_pkexec(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}" if name == "pkexec" else None)
    argv = _build_admin_argv("cmd")
    assert argv == ["/usr/bin/pkexec", "/bin/sh", "-c", "cmd"]


def test_admin_argv_uses_sudo_askpass_when_set(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    monkeypatch.setenv("SUDO_ASKPASS", "/usr/bin/ssh-askpass")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "sudo" else None,
    )
    argv = _build_admin_argv("cmd")
    assert argv == ["/usr/bin/sudo", "-A", "/bin/sh", "-c", "cmd"]


def test_admin_argv_falls_back_to_sudo_n(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    monkeypatch.delenv("SUDO_ASKPASS", raising=False)
    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "sudo" else None,
    )
    argv = _build_admin_argv("cmd")
    assert argv == ["/usr/bin/sudo", "-n", "/bin/sh", "-c", "cmd"]


def test_admin_argv_returns_none_when_nothing_available(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    monkeypatch.delenv("SUDO_ASKPASS", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert _build_admin_argv("cmd") is None


# ---------- run_admin clear-error fallback ----------

def test_run_admin_returns_127_when_no_escalation_tool(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    monkeypatch.delenv("SUDO_ASKPASS", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    r = run_admin("flashrom -V")
    assert isinstance(r, subprocess.CompletedProcess)
    assert r.returncode == 127
    assert "No privilege escalation tool" in r.stderr
