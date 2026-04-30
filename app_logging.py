# app_logging.py
"""Persistent flash/backup log files.

Each flash or backup op opens a timestamped file under the app's state
directory and mirrors the GUI log there in real time. The file remains
on disk after the op completes so the user (or whoever debugs a brick)
has the full flashrom transcript without needing the app open or
scrolling through the GUI log buffer.

State directory resolution (first hit wins):
  1. HDZERO_STATE_DIR env var (test-friendly override)
  2. $XDG_STATE_HOME/hdzero-programmer
  3. ~/.local/state/hdzero-programmer
"""
import os
import time
from pathlib import Path
from typing import IO, Tuple


def state_dir() -> Path:
    override = os.environ.get("HDZERO_STATE_DIR")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path(os.path.expanduser("~/.local/state"))
    return base / "hdzero-programmer"


def open_flash_log(prefix: str, version: str) -> Tuple[Path, IO[str]]:
    """Create a fresh log file under state_dir() and return (path, handle).

    `prefix` is one of "flash" / "backup" — drives the filename. The handle
    is line-buffered (buffering=1) so a crash mid-op still leaves a useful
    transcript on disk; callers don't have to flush after every line.
    The header line records the prefix, timestamp, and app version so a
    file recovered later identifies itself unambiguously.
    """
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = d / f"{prefix}-{ts}.log"
    fh = open(path, "w", buffering=1, encoding="utf-8")
    fh.write(f"=== {prefix} {ts} (hdzero-programmer {version}) ===\n")
    return path, fh
