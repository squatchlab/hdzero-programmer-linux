# tests/test_app_settings.py
"""Reverse-DNS QSettings scope + one-shot legacy migration."""
import os

import pytest

# QSettings on Linux honours XDG_CONFIG_HOME; pointing it at a tmp_path
# keeps tests hermetic. Set BEFORE the QSettings module is touched —
# QSettings caches the resolved path on first construction in some
# binding versions.


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Pin QSettings to write under tmp_path for the lifetime of the test.

    `XDG_CONFIG_HOME` alone is not enough: PyQt6's `QStandardPaths` caches
    the resolved config dir per QCoreApplication, so an env var set by
    monkeypatch.setenv doesn't always reach a QSettings instance
    constructed later. `QSettings.setPath` overrides the cache directly
    for IniFormat / UserScope; we restore Qt's defaults at teardown so
    one test can't bleed into the next.
    """
    from PyQt6.QtCore import QSettings

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    yield tmp_path
    # Reset so a subsequent test that doesn't take this fixture (or runs
    # later) sees fresh path resolution. setPath with an empty string
    # restores the platform default.
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "",
    )


def test_settings_uses_reverse_dns_scope(isolated_config):
    from PyQt6.QtCore import QSettings

    import app_settings

    assert app_settings.SETTINGS_ORG == "lab.squatch"
    assert app_settings.SETTINGS_APP == "hdzero-programmer-linux"

    s = app_settings.settings()
    s.setValue("autobackup", True)
    s.sync()

    expected = isolated_config / "lab.squatch" / "hdzero-programmer-linux.conf"
    assert expected.exists(), (
        f"QSettings did not write to reverse-DNS path. Looked under "
        f"{isolated_config}: {list(isolated_config.rglob('*'))}"
    )

    # Direct construction with the same scope reads back the value.
    s2 = QSettings(app_settings.SETTINGS_ORG, app_settings.SETTINGS_APP)
    assert s2.value("autobackup", False, type=bool) is True


def test_migrate_copies_legacy_keys_once(isolated_config):
    from PyQt6.QtCore import QSettings

    import app_settings

    legacy = QSettings("HDZero", "Programmer")
    legacy.setValue("autobackup", False)
    legacy.setValue("some_other_key", "preserved")
    legacy.sync()

    app_settings.migrate_settings_once()

    new = app_settings.settings()
    assert new.value("autobackup", True, type=bool) is False
    assert new.value("some_other_key") == "preserved"
    assert new.value("_migrated_from_legacy_org", False, type=bool) is True

    legacy_path = isolated_config / "HDZero" / "Programmer.conf"
    assert legacy_path.exists(), "legacy file should be left intact"


def test_migrate_is_idempotent(isolated_config):
    import app_settings

    new = app_settings.settings()
    new.setValue("autobackup", True)
    new.setValue("_migrated_from_legacy_org", True)
    new.sync()

    # Now plant a legacy file with a contradicting value. A second call
    # to migrate must NOT clobber the new scope's value.
    from PyQt6.QtCore import QSettings

    legacy = QSettings("HDZero", "Programmer")
    legacy.setValue("autobackup", False)
    legacy.sync()

    app_settings.migrate_settings_once()

    new2 = app_settings.settings()
    assert new2.value("autobackup", False, type=bool) is True


def test_migrate_skips_keys_already_in_new_scope(isolated_config):
    from PyQt6.QtCore import QSettings

    import app_settings

    # User set the new scope (somehow — e.g. opened a build, toggled
    # checkbox, then a later build added migration). Migration must not
    # overwrite their explicit choice.
    new = app_settings.settings()
    new.setValue("autobackup", True)
    new.sync()

    legacy = QSettings("HDZero", "Programmer")
    legacy.setValue("autobackup", False)
    legacy.sync()

    app_settings.migrate_settings_once()

    assert app_settings.settings().value("autobackup", False, type=bool) is True


def test_migrate_no_legacy_data_is_noop(isolated_config):
    import app_settings

    # No legacy file at all. Migration should run cleanly and write the
    # sentinel (so a future legacy file doesn't accidentally migrate later).
    app_settings.migrate_settings_once()

    new = app_settings.settings()
    assert new.value("_migrated_from_legacy_org", False, type=bool) is True


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
