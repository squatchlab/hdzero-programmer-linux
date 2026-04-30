# tests/test_app_settings.py
"""Reverse-DNS QSettings scope + one-shot legacy migration.

QSettings + pytest is finicky: PyQt6's QStandardPaths caches the
config dir per-process, so an `XDG_CONFIG_HOME` set via
`monkeypatch.setenv` after the runtime cache warms up doesn't always
reach a QSettings instance constructed later. To stay hermetic we
construct QSettings with an *explicit file path* (the
`QSettings(filename, IniFormat)` overload) and inject those instances
into `migrate_settings_once()` via its optional kwargs. This bypasses
QStandardPaths entirely and is the same pattern the Qt docs recommend
for tests.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _qapp():
    """QSettings on some bindings needs a QCoreApplication for org/app
    fallbacks. Construct one for the duration of the test if absent."""
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    created = False
    if app is None:
        app = QCoreApplication([os.environ.get("PYTEST_CURRENT_TEST", "test")])
        created = True
    yield
    if created:
        app.quit()


@pytest.fixture
def settings_pair(tmp_path):
    """Return ``(new, old, new_path, old_path)`` — two empty QSettings
    instances backed by explicit IniFormat files under tmp_path."""
    from PyQt6.QtCore import QSettings

    new_path = tmp_path / "new.conf"
    old_path = tmp_path / "legacy.conf"
    new = QSettings(str(new_path), QSettings.Format.IniFormat)
    old = QSettings(str(old_path), QSettings.Format.IniFormat)
    return new, old, new_path, old_path


def test_settings_uses_reverse_dns_scope():
    """Constants pin the reverse-DNS scope so a downgrade or a side-by-
    side macOS install doesn't share QSettings storage."""
    import app_settings

    assert app_settings.SETTINGS_ORG == "lab.squatch"
    assert app_settings.SETTINGS_APP == "hdzero-programmer-linux"


def test_migrate_copies_legacy_keys_once(settings_pair):
    import app_settings

    new, old, new_path, old_path = settings_pair
    old.setValue("autobackup", False)
    old.setValue("some_other_key", "preserved")
    old.sync()

    app_settings.migrate_settings_once(new=new, old=old)

    assert new.value("autobackup", True, type=bool) is False
    assert new.value("some_other_key") == "preserved"
    assert new.value("_migrated_from_legacy_org", False, type=bool) is True
    assert old_path.exists(), "legacy file should be left intact"


def test_migrate_is_idempotent(settings_pair):
    import app_settings

    new, old, _, _ = settings_pair
    new.setValue("autobackup", True)
    new.setValue("_migrated_from_legacy_org", True)
    new.sync()

    # Plant a contradicting legacy value. A second migrate must NOT
    # clobber the new scope's value.
    old.setValue("autobackup", False)
    old.sync()

    app_settings.migrate_settings_once(new=new, old=old)

    assert new.value("autobackup", False, type=bool) is True


def test_migrate_skips_keys_already_in_new_scope(settings_pair):
    import app_settings

    new, old, _, _ = settings_pair
    # User set the new scope (somehow — e.g. opened a build, toggled
    # checkbox, then a later build added migration). Migration must not
    # overwrite their explicit choice.
    new.setValue("autobackup", True)
    new.sync()

    old.setValue("autobackup", False)
    old.sync()

    app_settings.migrate_settings_once(new=new, old=old)

    assert new.value("autobackup", False, type=bool) is True


def test_migrate_no_legacy_data_is_noop(settings_pair):
    import app_settings

    new, old, _, _ = settings_pair
    # No keys in `old` at all. Migration should run cleanly and write
    # the sentinel so a future legacy file doesn't accidentally migrate
    # later.
    app_settings.migrate_settings_once(new=new, old=old)

    assert new.value("_migrated_from_legacy_org", False, type=bool) is True


def test_settings_helper_returns_correct_scope():
    """`settings()` returns a QSettings with the reverse-DNS org/app."""
    import app_settings

    s = app_settings.settings()
    # organizationName + applicationName are the canonical readbacks.
    assert s.organizationName() == app_settings.SETTINGS_ORG
    assert s.applicationName() == app_settings.SETTINGS_APP
