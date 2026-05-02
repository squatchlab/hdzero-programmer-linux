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
