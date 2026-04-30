# app_settings.py
"""Reverse-DNS QSettings scope + one-shot legacy migration.

The macOS upstream and pre-v0.3 Linux fork both wrote QSettings under
the bare brand `HDZero/Programmer`. On a host that runs both, one tool
overwrites the other's `autobackup` toggle. New scope is reverse-DNS
under the maintainer's domain so the two stores never collide.
`migrate_settings_once()` copies the legacy keys forward exactly once;
the legacy file is left intact so a downgrade still finds its data.
"""
from PyQt6.QtCore import QSettings

LEGACY_SETTINGS_ORG = "HDZero"
LEGACY_SETTINGS_APP = "Programmer"

SETTINGS_ORG = "lab.squatch"
SETTINGS_APP = "hdzero-programmer-linux"

SETTINGS_KEY_AUTOBACKUP = "autobackup"

# Sentinel written into the new scope after the first successful migration.
# Idempotent — a second call sees the sentinel and short-circuits.
_KEY_MIGRATED = "_migrated_from_legacy_org"


def settings() -> QSettings:
    """Construct a QSettings handle in the canonical reverse-DNS scope."""
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def migrate_settings_once() -> None:
    """Copy legacy `HDZero/Programmer` keys into the new scope on first run.

    Skipped if the sentinel `_migrated_from_legacy_org` is already set in
    the new scope, so reruns are free. Existing keys in the new scope are
    not overwritten — if a user sets a value under the new scope before
    migration runs (unlikely but possible across versions), their choice
    wins.
    """
    new = settings()
    if new.value(_KEY_MIGRATED, False, type=bool):
        return
    old = QSettings(LEGACY_SETTINGS_ORG, LEGACY_SETTINGS_APP)
    for key in old.allKeys():
        if not new.contains(key):
            new.setValue(key, old.value(key))
    new.setValue(_KEY_MIGRATED, True)
    # Force flush. QSettings auto-syncs on a timer / on destruction, but a
    # crash in the same launch — or another QSettings instance reading the
    # new scope before the timer fires — would miss the migrated keys
    # otherwise. Explicit sync also makes the test suite hermetic.
    new.sync()
