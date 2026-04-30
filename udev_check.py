# udev_check.py
"""First-run sanity checks for CH341A USB access.

The app can run flashrom without root if the user has installed the
packaged udev rule (`packaging/99-ch341a.rules`) and exported
HDZERO_NO_ESCALATE=1. When the rule is missing, every flash op pops a
polkit/sudo prompt — surface a one-time hint to nudge the user toward
the friendlier path.
"""
import os
from pathlib import Path
from typing import List

CH341A_VENDOR = "1a86"
CH341A_PRODUCT = "5512"
RULE_FILENAME = "99-ch341a.rules"

# Both system rule dirs udev consults. /etc takes precedence per udev docs.
RULE_DIRS: List[str] = [
    "/etc/udev/rules.d",
    "/usr/lib/udev/rules.d",
    "/run/udev/rules.d",
]


def rule_installed() -> bool:
    """True if 99-ch341a.rules exists in any standard udev rule directory."""
    for d in RULE_DIRS:
        if Path(d, RULE_FILENAME).is_file():
            return True
    return False


def ch341a_present() -> bool:
    """True if a CH341A USB device is currently enumerated by the kernel.

    Walks /sys/bus/usb/devices/* and matches idVendor/idProduct against the
    CH341A IDs. Returns False on any I/O error so the caller can degrade
    gracefully (e.g. on systems without /sys mounted).
    """
    base = Path("/sys/bus/usb/devices")
    try:
        entries = list(base.iterdir())
    except OSError:
        return False
    for entry in entries:
        try:
            vendor = (entry / "idVendor").read_text().strip()
            product = (entry / "idProduct").read_text().strip()
        except OSError:
            continue
        if vendor == CH341A_VENDOR and product == CH341A_PRODUCT:
            return True
    return False


def escalation_disabled() -> bool:
    """True when the user has opted out of pkexec/sudo escalation, signalling
    they expect the udev rule path to be working.
    """
    return bool(os.environ.get("HDZERO_NO_ESCALATE"))


def should_show_hint() -> bool:
    """Whether to surface the first-run install hint.

    Show when:
      - the rule is not installed, AND
      - the user has not opted out of escalation (otherwise the hint is noise
        for someone who has already chosen their path).

    Presence of the device itself is informational, not gating — a user might
    plug the CH341A in after launching the app, and the hint should still be
    visible so they can act on it.
    """
    return not rule_installed() and not escalation_disabled()


def bundled_rule_path() -> str:
    """Locate the bundled 99-ch341a.rules across layouts.

    AppImage build copies the rule next to the .py modules (so resource_path
    finds it via HDZERO_APP_DIR). In a plain checkout the rule lives under
    packaging/. Returns the first hit or an empty string if neither layout
    matches — caller can degrade the hint accordingly.
    """
    # Lazy import so the module stays usable in test environments that have
    # not configured resource discovery.
    try:
        from internet_panel import resource_path
        cand = resource_path(RULE_FILENAME)
        if Path(cand).is_file():
            return cand
    except Exception:
        pass

    checkout = Path(__file__).resolve().parent / "packaging" / RULE_FILENAME
    if checkout.is_file():
        return str(checkout)
    return ""


def install_command(rule_src: str) -> str:
    """Return the shell snippet the user should run to install the rule.

    `rule_src` is the absolute path to the bundled 99-ch341a.rules (resolved
    by the caller via resource_path()).
    """
    return (
        f"sudo install -m 0644 {rule_src} /etc/udev/rules.d/{RULE_FILENAME} && "
        "sudo udevadm control --reload-rules && sudo udevadm trigger"
    )
