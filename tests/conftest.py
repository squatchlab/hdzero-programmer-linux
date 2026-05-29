import os
import sys

import pytest


@pytest.fixture(scope="session")
def qt_app():
    """A single QApplication for the whole session, headless (offscreen).

    FlashWorker is a QThread (QObject), and Qt insists on an application
    instance for signal/slot machinery even when we drive run() directly
    instead of starting the thread. A full QApplication (not just
    QCoreApplication) is used so widget-level tests — e.g. constructing
    MainWindow to exercise its error handlers — can share the same
    instance; Qt permits only one application object per process, and a
    QCoreApplication cannot host QWidgets. QApplication subclasses
    QCoreApplication, so the worker tests are unaffected. The offscreen
    platform mirrors the CI headless boot and needs no display.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    existing = QApplication.instance()
    if existing is not None:
        yield existing
        return
    app = QApplication(sys.argv)
    yield app
