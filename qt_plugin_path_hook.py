# qt_plugin_path_hook.py
import os, sys, pathlib
# Cuando está empaquetado, PyInstaller expone sys._MEIPASS
base = pathlib.Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else pathlib.Path(__file__).parent
qt_plugins = base / "PyQt6" / "Qt6" / "plugins"
os.environ["QT_PLUGIN_PATH"] = str(qt_plugins)
