"""Pin main.__version__ to the pyproject [project].version field.

The version is hard-coded in main.py so AppImage runs (which graft source
into site-packages without dist-info) can still report it. This test
catches the inevitable "bumped one but not the other" mistake on release.
"""
from pathlib import Path

import tomllib

import main


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    cfg = tomllib.loads(pyproject.read_text())
    assert main.__version__ == cfg["project"]["version"], (
        f"main.__version__={main.__version__!r} but "
        f"pyproject [project].version={cfg['project']['version']!r}. "
        "Bump both."
    )


def test_check_rule_returns_zero_when_no_escalate(monkeypatch, capsys):
    """`--check-rule` short-circuits to rc=0 when escalation is opted out,
    even on a host without /etc/udev/rules.d/99-ch341a.rules.
    """
    monkeypatch.setenv("HDZERO_NO_ESCALATE", "1")
    rc = main._run_check_rule()
    assert rc == 0
    out = capsys.readouterr().out
    assert "rule_installed:" in out
    assert "escalation_disabled: True" in out


def test_check_rule_returns_one_when_neither(monkeypatch, capsys):
    monkeypatch.delenv("HDZERO_NO_ESCALATE", raising=False)
    # Force rule_installed() to False without touching the real filesystem.
    import udev_check
    monkeypatch.setattr(udev_check, "RULE_DIRS", ["/nonexistent/path"])
    rc = main._run_check_rule()
    assert rc == 1
    out = capsys.readouterr().out
    assert "rule_installed: False" in out
    assert "escalation_disabled: False" in out
