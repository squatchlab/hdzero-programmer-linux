import sys

import pytest


@pytest.fixture(scope="session")
def qt_app():
    """A single QCoreApplication for the whole session.

    FlashWorker is a QThread (QObject), and Qt insists on an application
    instance for signal/slot machinery even when we drive run() directly
    instead of starting the thread. QCoreApplication is enough — no GUI
    plugin or event loop required.
    """
    from PyQt6.QtCore import QCoreApplication

    existing = QCoreApplication.instance()
    if existing is not None:
        yield existing
        return
    app = QCoreApplication(sys.argv)
    yield app
