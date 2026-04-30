import os
from pathlib import Path

import pytest

import udev_check
from udev_check import (
    RULE_FILENAME,
    ch341a_present,
    escalation_disabled,
    install_command,
    rule_installed,
    should_show_hint,
)


# ---------- rule_installed ----------

def test_rule_installed_finds_etc(monkeypatch, tmp_path):
    etc = tmp_path / "etc-udev"
    etc.mkdir()
    (etc / RULE_FILENAME).write_text("")
    monkeypatch.setattr(udev_check, "RULE_DIRS", [str(etc)])
    assert rule_installed() is True


def test_rule_installed_returns_false_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(udev_check, "RULE_DIRS", [str(tmp_path / "nope")])
    assert rule_installed() is False


def test_rule_installed_scans_all_dirs(monkeypatch, tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    (b / RULE_FILENAME).write_text("")
    monkeypatch.setattr(udev_check, "RULE_DIRS", [str(a), str(b)])
    assert rule_installed() is True


# ---------- ch341a_present ----------

def test_ch341a_present_matches_vendor_product(monkeypatch, tmp_path):
    base = tmp_path / "sys-usb"
    base.mkdir()
    dev = base / "1-1"
    dev.mkdir()
    (dev / "idVendor").write_text("1a86\n")
    (dev / "idProduct").write_text("5512\n")
    # Patch the literal Path constructor inside udev_check so it walks our
    # tmp tree instead of the real /sys.
    real_path = udev_check.Path

    def fake_path(arg):
        if arg == "/sys/bus/usb/devices":
            return real_path(str(base))
        return real_path(arg)

    monkeypatch.setattr(udev_check, "Path", fake_path)
    assert ch341a_present() is True


def test_ch341a_present_false_when_no_match(monkeypatch, tmp_path):
    base = tmp_path / "sys-usb"
    base.mkdir()
    dev = base / "1-1"
    dev.mkdir()
    (dev / "idVendor").write_text("dead\n")
    (dev / "idProduct").write_text("beef\n")
    real_path = udev_check.Path
    monkeypatch.setattr(udev_check, "Path", lambda a: real_path(str(base)) if a == "/sys/bus/usb/devices" else real_path(a))
    assert ch341a_present() is False


def test_ch341a_present_false_when_sysfs_missing(monkeypatch, tmp_path):
    real_path = udev_check.Path
    monkeypatch.setattr(udev_check, "Path", lambda a: real_path(str(tmp_path / "nonexistent")) if a == "/sys/bus/usb/devices" else real_path(a))
    assert ch341a_present() is False


# ---------- escalation_disabled ----------

def test_escalation_disabled_reads_env(monkeypatch):
    monkeypatch.setenv("HDZERO_NO_ESCALATE", "1")
    assert escalation_disabled() is True
    monkeypatch.delenv("HDZERO_NO_ESCALATE")
    assert escalation_disabled() is False


# ---------- should_show_hint ----------

def test_should_show_hint_when_rule_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(udev_check, "RULE_DIRS", [str(tmp_path / "nope")])
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    assert should_show_hint() is True


def test_should_show_hint_suppressed_when_rule_present(monkeypatch, tmp_path):
    d = tmp_path / "rules"; d.mkdir()
    (d / RULE_FILENAME).write_text("")
    monkeypatch.setattr(udev_check, "RULE_DIRS", [str(d)])
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    assert should_show_hint() is False


def test_should_show_hint_suppressed_when_no_escalate(monkeypatch, tmp_path):
    monkeypatch.setattr(udev_check, "RULE_DIRS", [str(tmp_path / "nope")])
    monkeypatch.setenv("HDZERO_NO_ESCALATE", "1")
    assert should_show_hint() is False


# ---------- install_command ----------

def test_install_command_includes_src_and_reload():
    cmd = install_command("/opt/app/99-ch341a.rules")
    assert "/opt/app/99-ch341a.rules" in cmd
    assert "udevadm control --reload-rules" in cmd
    assert "udevadm trigger" in cmd
    assert f"/etc/udev/rules.d/{RULE_FILENAME}" in cmd
