#!/bin/sh
# Install the HDZero Programmer .desktop entry and icon for the current user.
#
# System-wide install: re-run with `sudo PREFIX=/usr ./install-desktop.sh`.
# Default per-user install drops files under $XDG_DATA_HOME (~/.local/share).
#
# This script does NOT install the hdzero-programmer launcher binary itself.
# Until the pyproject.toml entrypoint lands (issue #7), edit the resulting
# .desktop file's Exec= line to point at `python3 /absolute/path/to/main.py`.

set -eu

PREFIX="${PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_DIR="$PREFIX/applications"
ICON_DIR="$PREFIX/icons/hicolor/256x256/apps"

mkdir -p "$APP_DIR" "$ICON_DIR"

install -m 0644 "$SCRIPT_DIR/hdzero-programmer.desktop" "$APP_DIR/hdzero-programmer.desktop"
install -m 0644 "$REPO_ROOT/icon256.png"                "$ICON_DIR/hdzero-programmer.png"

# Refresh caches if the tools are present (silent if not).
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" || true
command -v gtk-update-icon-cache    >/dev/null 2>&1 && gtk-update-icon-cache  -f -t "$PREFIX/icons/hicolor" || true

echo "Installed:"
echo "  $APP_DIR/hdzero-programmer.desktop"
echo "  $ICON_DIR/hdzero-programmer.png"
