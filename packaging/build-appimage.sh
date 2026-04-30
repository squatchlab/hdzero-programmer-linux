#!/bin/bash
# Build a self-contained AppImage of HDZero Programmer.
#
# Strategy: use python-appimage to produce a base AppImage with a
# relocatable Python interpreter plus the pip dependencies (PyQt6,
# requests). Extract that AppImage, inject our application source +
# PNG assets into a known directory inside it, and repackage.
#
# Output:    dist/HDZeroProgrammer-x86_64.AppImage
# Runtime:   AppRun sets HDZERO_APP_DIR so resource_path() resolves
#            assets out of the injected directory.
#
# Prereqs:   pipx install python-appimage
#            (python-appimage downloads appimagetool itself)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_VER="${PYTHON_VERSION:-3.12}"
BUILD_DIR="$REPO_ROOT/dist/build-appimage"
DIST_DIR="$REPO_ROOT/dist"
RECIPE_DIR="$BUILD_DIR/recipe"
INJECT_REL="opt/python$PY_VER/lib/python$PY_VER/site-packages/_hdzero_app"
OUT="$DIST_DIR/HDZeroProgrammer-x86_64.AppImage"

if ! command -v python-appimage >/dev/null 2>&1; then
    echo "python-appimage not found. Install with: pipx install python-appimage" >&2
    exit 1
fi

rm -rf "$BUILD_DIR"
mkdir -p "$RECIPE_DIR" "$DIST_DIR"

# --- recipe: deps only. Application source is grafted in post-build.
cat > "$RECIPE_DIR/requirements.txt" <<EOF
PyQt6>=6.6
requests>=2.31
EOF

# --- entrypoint shell script: invoked as AppRun. Locates the injected
#     source dir, exports HDZERO_APP_DIR for resource_path(), points
#     PYTHONPATH at it, then execs python on main.py.
cat > "$RECIPE_DIR/entrypoint.sh" <<EOF
#!/bin/bash
APPSRC="\$APPDIR/$INJECT_REL"
export HDZERO_APP_DIR="\$APPSRC"
export PYTHONPATH="\$APPSRC:\${PYTHONPATH:-}"
exec "\$APPDIR/opt/python$PY_VER/bin/python$PY_VER" "\$APPSRC/main.py" "\$@"
EOF
chmod +x "$RECIPE_DIR/entrypoint.sh"

# --- desktop + icon (reused from packaging/)
# python-appimage derives the AppImage filename from the desktop Name= field
# and shells the appimagetool invocation with shell=True/' '.join, so a Name
# with whitespace gets word-split. Rewrite Name=HDZeroProgrammer for the
# build-only desktop copy; the XDG-installed entry keeps the human form.
sed 's/^Name=.*/Name=HDZeroProgrammer/' \
    "$REPO_ROOT/packaging/hdzero-programmer.desktop" \
    > "$RECIPE_DIR/hdzero-programmer.desktop"
cp "$REPO_ROOT/icon256.png"                          "$RECIPE_DIR/hdzero-programmer.png"

# --- build base AppImage (python + deps)
cd "$BUILD_DIR"
python-appimage build app -p "$PY_VER" "$RECIPE_DIR"

BASE=$(ls "$BUILD_DIR"/*.AppImage 2>/dev/null | head -1)
if [ -z "$BASE" ]; then
    echo "python-appimage produced no .AppImage" >&2
    exit 1
fi

# --- extract, inject application source + assets, repackage
"$BASE" --appimage-extract >/dev/null
INJECT_ABS="$BUILD_DIR/squashfs-root/$INJECT_REL"
mkdir -p "$INJECT_ABS"

# Application source (top-level .py modules)
cp "$REPO_ROOT/main.py"           "$INJECT_ABS/"
cp "$REPO_ROOT/internet_panel.py" "$INJECT_ABS/"
cp "$REPO_ROOT/flash_ops.py"      "$INJECT_ABS/"
cp "$REPO_ROOT/udev_check.py"     "$INJECT_ABS/"
cp "$REPO_ROOT/app_logging.py"    "$INJECT_ABS/"

# Image assets used by HelpPanel, LocalPanel, InternetPanel, MainWindow
cp "$REPO_ROOT"/*.png "$INJECT_ABS/"

# README is loaded at runtime by HelpPanel (tries Readme.md, README.md, Readme,md)
cp "$REPO_ROOT/README.md" "$INJECT_ABS/README.md"

# udev rule + install helper — udev_check.bundled_rule_path() resolves the
# rule via resource_path() so the in-app banner can show a working
# copy-paste install command on AppImage runs.
cp "$REPO_ROOT/packaging/99-ch341a.rules"  "$INJECT_ABS/"
cp "$REPO_ROOT/packaging/install-udev.sh"  "$INJECT_ABS/"
chmod +x "$INJECT_ABS/install-udev.sh"

# Repackage. python-appimage already cached appimagetool somewhere on PATH;
# fall back to the appimagetool that python-appimage downloaded into ~/.cache.
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [ -z "$APPIMAGETOOL" ]; then
    CACHED=$(find ~/.cache/python_appimage ~/.cache 2>/dev/null -name 'appimagetool*' -type f -executable | head -1 || true)
    APPIMAGETOOL="$CACHED"
fi
if [ -z "$APPIMAGETOOL" ]; then
    echo "appimagetool not found on PATH or in ~/.cache. Install from https://github.com/AppImage/AppImageKit/releases" >&2
    exit 1
fi

ARCH=x86_64 "$APPIMAGETOOL" "$BUILD_DIR/squashfs-root" "$OUT"
echo
echo "Built: $OUT"
ls -lh "$OUT"
