"""Cover MainWindow's unhandled-exception hook.

We don't actually raise inside a Qt slot — we install the hook and then
call sys.excepthook directly with a fabricated traceback. That keeps the
test single-threaded, no event loop required.
"""
import sys

import main


def _fabricated_traceback():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        return sys.exc_info()


def test_excepthook_pops_dialog_and_writes_stderr(monkeypatch, capsys):
    captured = []

    def fake_critical(parent, title, text):
        captured.append((title, text))

    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", fake_critical)

    main._install_excepthook()
    try:
        et, e, tb = _fabricated_traceback()
        sys.excepthook(et, e, tb)

        # stderr got the formatted traceback.
        err = capsys.readouterr().err
        assert "RuntimeError: boom" in err

        # Dialog was invoked exactly once.
        assert len(captured) == 1
        title, text = captured[0]
        assert title == "HDZero Programmer crashed"
        assert "RuntimeError: boom" in text
        # The hint about the transcript dir is included on a successful
        # state_dir() resolve.
        assert "transcripts" in text or "/hdzero-programmer" in text
    finally:
        sys.excepthook = sys.__excepthook__


def test_excepthook_keyboardinterrupt_quits_without_dialog(monkeypatch, capsys):
    """Ctrl-C on the terminal must quit cleanly, not pop the crash dialog."""
    dialog_calls = []
    quit_calls = []

    def fake_critical(parent, title, text):
        dialog_calls.append((title, text))

    def fake_quit():
        quit_calls.append(True)

    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", fake_critical)
    monkeypatch.setattr(QtWidgets.QApplication, "quit", staticmethod(fake_quit))

    main._install_excepthook()
    try:
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            et, e, tb = sys.exc_info()
        sys.excepthook(et, e, tb)

        assert dialog_calls == [], "crash dialog must not pop on Ctrl-C"
        assert quit_calls == [True], "QApplication.quit() must be called"
        assert capsys.readouterr().err == ""
    finally:
        sys.excepthook = sys.__excepthook__


def test_excepthook_reentrancy_falls_back(monkeypatch):
    """If the hook is invoked while already running (e.g. its own
    QMessageBox somehow re-enters), the second call must not loop."""
    calls = []
    original = sys.excepthook

    def fake_critical(parent, title, text):
        # Simulate a Qt error during the hook by calling the hook again.
        et, e, tb = _fabricated_traceback()
        sys.excepthook(et, e, tb)

    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", fake_critical)

    def _capture_original(*args):
        calls.append(args)

    monkeypatch.setattr(sys, "excepthook", original)  # baseline
    main._install_excepthook()
    monkeypatch.setattr(sys, "__excepthook__", _capture_original, raising=False)

    try:
        et, e, tb = _fabricated_traceback()
        # The original handler we want the fallback to land on is whatever
        # was set before _install_excepthook patched sys.excepthook. The
        # hook captured that as its `original`. We can't easily inspect
        # closure state, so instead we just assert no recursion blew the
        # stack — the test completing is the assertion.
        sys.excepthook(et, e, tb)
    finally:
        sys.excepthook = sys.__excepthook__


def test_excepthook_state_dir_failure_still_pops_dialog(monkeypatch, capsys):
    """#82: if state_dir() raises while building the transcript hint, the
    crash dialog must still appear — just without the hint line. Covers the
    last-resort `except Exception` around the state_dir() import (main.py:553)."""
    captured = []

    def fake_critical(parent, title, text):
        captured.append((title, text))

    def boom_state_dir():
        raise RuntimeError("state_dir exploded")

    from PyQt6 import QtWidgets

    import app_logging
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", fake_critical)
    # The hook does `from app_logging import state_dir` at call time, so
    # patching the attribute on the module is what the import resolves to.
    monkeypatch.setattr(app_logging, "state_dir", boom_state_dir)

    main._install_excepthook()
    try:
        et, e, tb = _fabricated_traceback()
        sys.excepthook(et, e, tb)

        # Dialog still popped exactly once with the traceback...
        assert len(captured) == 1
        title, text = captured[0]
        assert title == "HDZero Programmer crashed"
        assert "RuntimeError: boom" in text
        # ...but the transcript-dir hint was swallowed, so it is absent.
        assert "transcripts" not in text
        # stderr still got the traceback regardless.
        assert "RuntimeError: boom" in capsys.readouterr().err
    finally:
        sys.excepthook = sys.__excepthook__


def test_excepthook_messagebox_failure_falls_back_to_original(monkeypatch, capsys):
    """#82: if QMessageBox.critical itself raises (Qt wedged), the hook must
    fall back to the original excepthook rather than vanish. Covers the
    last-resort `except Exception` around the dialog (main.py:564)."""
    fallback_calls = []

    def fake_original(exc_type, exc, tb):
        fallback_calls.append((exc_type, exc, tb))

    def wedged_critical(parent, title, text):
        raise RuntimeError("Qt is wedged")

    from PyQt6 import QtWidgets

    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", wedged_critical)
    # Install our sentinel as the *current* excepthook so the hook captures
    # it as `original` when _install_excepthook runs.
    monkeypatch.setattr(sys, "excepthook", fake_original)

    main._install_excepthook()
    try:
        et, e, tb = _fabricated_traceback()
        sys.excepthook(et, e, tb)

        # Dialog raised → fell back to the original handler exactly once.
        assert len(fallback_calls) == 1
        assert fallback_calls[0][0] is RuntimeError
        # stderr still carried the traceback before the dialog was attempted.
        assert "RuntimeError: boom" in capsys.readouterr().err
    finally:
        sys.excepthook = sys.__excepthook__
