#!/bin/bash
# Install the CH341A udev rule so flashrom can talk to the programmer
# without root. After this runs (and you re-plug the device), set
# HDZERO_NO_ESCALATE=1 in the app's environment to skip the polkit prompt.
#
# Usage:
#   ./packaging/install-udev.sh
# or, when invoked from the AppImage / wherever this script + the rule
# happen to live in the same directory.
#
# Requires sudo for the install + udevadm reload.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RULE_SRC="$SCRIPT_DIR/99-ch341a.rules"
RULE_DST="/etc/udev/rules.d/99-ch341a.rules"

if [ ! -f "$RULE_SRC" ]; then
    echo "Rule file not found at $RULE_SRC" >&2
    exit 1
fi

echo "Installing $RULE_SRC -> $RULE_DST"
sudo install -m 0644 "$RULE_SRC" "$RULE_DST"

echo "Reloading udev rules and re-triggering devices"
sudo udevadm control --reload-rules
sudo udevadm trigger

cat <<'NOTE'

Done. Unplug and replug the CH341A so the new rule binds.
To skip the polkit prompt on each flash, export:

    HDZERO_NO_ESCALATE=1

(add it to ~/.profile or your desktop entry's Exec= line for persistence.)
NOTE
