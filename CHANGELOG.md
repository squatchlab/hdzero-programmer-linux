# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Post-`v0.3.0` audit-remediation batch (workflow-driven review of the six
modules, docs, CI, and tests). No version bump yet.

### Added
- `tests/test_error_paths.py`: coverage for previously-untested defensive
  paths — `run_admin_streaming` no-escalation-tool (127) + non-UTF-8 decode
  + SIGKILL-after-SIGTERM, and `FlashWorker` padded-image cleanup `OSError`.
  (#90)
- Tests for the excepthook `state_dir()` / `QMessageBox` fallbacks and the
  backup-dir `mkdir` `OSError` handlers in `start_backup` / `start_flash`.
  (#82)
- `_SIGTERM_GRACE_SECS` constant in `flash_ops` (named so the SIGKILL test
  can shrink it). (#90)

### Changed
- `_build_admin_argv` docstring now states the `shlex.quote()` caller
  contract (the function applies no escaping; unquoted input is a
  shell-injection surface). (#80)
- PyQt6 dependency ceiling `<6.9` → `<7`; `build-appimage.sh` requirements
  gain matching `<7` / `<3` bounds so the AppImage resolves the same wheel
  range as a source install. (#85)
- Removed the dead PyInstaller `_MEIPASS` branch from
  `internet_panel.resource_path` (AppImage-only build); dropped the now-unused
  `import sys`. (#88)
- `main.py` tidy: `_load_icon()` helper for the repeated icon-load pattern,
  direct `QSize` import, `os.path` → `pathlib`, dropped needless `getattr`
  in the flash-log helpers. (#89)
- PEP 585/604 type hints across `flash_ops`, `main`, `udev_check`,
  `app_logging` (`Tuple[Path, IO[str]]` → `tuple[Path, TextIO]`),
  `app_settings`. (#92)
- `_no_escalate` test fixture is no longer `autouse` — requested explicitly
  so a future test can exercise a real escalation path. (#91)
- conftest `qt_app` upgraded from `QCoreApplication` to a headless offscreen
  `QApplication` so widget-level tests can construct `MainWindow`. (#82)
- Removal-criteria note added to the legacy `QSettings` migration shim. (#86)
- CI tool pins refreshed: ruff-pre-commit `v0.5.7` → `v0.15.15`, gitleaks
  `v8.18.4` → `v8.30.1` (pre-commit + `ci.yml`), `actions/checkout` v4 → v6.
  `actions/upload-artifact` kept at v3 with a do-not-bump guard comment;
  `actions/setup-python` kept at v5 with the v6 blocker documented. (#83, #84)
- Doc drift: dropped the stale "when SECURITY.md lands per #23" conditional
  from `CONTRIBUTING.md` / `LICENSE-NOTES.md`; corrected the
  `build-appimage.sh` README-fallback comment; `CLAUDE.md` now describes the
  unified `HttpWorker` and the two-path `resource_path`. (#87)

### Fixed
- `HttpWorker._stream_download` no longer crashes on a non-numeric
  `Content-Length` header (`ValueError` escaped the worker's failure
  handler); falls back to unknown-size streaming. (#81)

## [0.3.0] - 2026-04-30

Post-acquisition-audit batch. Closes the audit's documentation and
operational blockers (`#22` HW-CI gate, `#23` SECURITY.md), lands the
ADR corpus, the mypy gate, the legacy-settings migration, and the
HTTP-worker refactor. Firmware-trust trio (`#19`/`#20`/`#21`) remains
open and is the gating set for `v0.4.0`.

### Added
- ADR scaffolding under `docs/adr/` with template + index; ADR-0001
  through ADR-0007 covering single-prompt sh -c chain, 1 MiB padded
  image, pkexec-over-setuid, hardcoded CH341A vendor:product, the
  provisional `hdzero.go-next.co` trust root, hard-coded `__version__`,
  and the MIT-source / GPL-binary distribution position. (#31)
- PR template now has an "ADR added or referenced" checkbox so
  non-trivial design decisions don't slip through unmarked.
- `SECURITY.md` with disclosure policy, response timelines, supported
  versions, and known open security tickets. README links it from a
  new "Reporting a Vulnerability" section. (#23)
- Hard timeout on `flashrom` invocations in `FlashWorker` / `BackupWorker`
  so a hung CH341A doesn't block the GUI indefinitely.
- gitleaks secret scan in CI and as a pre-commit hook.
- pytest-cov coverage measurement in CI (no fail-under threshold yet).
- Contributing guide, code of conduct, issue + PR templates.
- 2026-04-29 acquisition audit report archived under `docs/audits/`.
- `app_settings.py`: `QSettings` reverse-DNS scope
  (`lab.squatch / hdzero-programmer-linux`) plus a one-shot migration
  from the legacy `HDZero/Programmer` scope, sentinel-guarded so a
  downgrade still finds its data. (#33)
- mypy gate in CI: strict on safety-critical modules (`flash_ops`,
  `udev_check`, `app_logging`, `app_settings`); `disallow_untyped_defs`
  + `check_untyped_defs` on UI plumbing (`main`, `internet_panel`).
  PyQt6 namespace ignored for missing imports — no first-party stubs.
  (#26, #68)
- Real-hardware regression workflow `.forgejo/workflows/hw-test.yml`
  gated on the `hdzero-hw` runner label, plus `docs/HARDWARE-CI.md`
  documenting host-side CH341A pass-through, runner registration, and
  the idempotent restore step. (#22)
- `docs/legal/trademark.md` capturing HDZero brand exposure and a
  `vtx-programmer-linux` rename contingency if the policy turns
  restrictive. (#43)

### Changed
- Chip backups (manual + pre-flash auto) now land in
  `app_logging.backup_dir()` — `HDZERO_BACKUP_DIR` override, else
  `$XDG_STATE_HOME/hdzero-programmer/backups/` (default
  `~/.local/state/hdzero-programmer/backups/`). Pre-existing files at
  `~/HDZero_*.bin` are not auto-migrated.
- Narrowed broad `except Exception` handlers across flash/UI paths.
- LICENSE: SPDX header, dual fork copyright line, PyQt6 GPL-binary
  position documented in `LICENSE-NOTES.md`.
- Collapsed four near-duplicate `InternetPanel` HTTP workers into a
  single `HttpWorker` with retry + exponential backoff (`requests`-based,
  bounded by `timeout` + `retries` kwargs). (#25, #37)
- python-appimage pinned to `>=1.4,<2` — 0.34 imports `distutils` which
  was removed in Python 3.12.
- AppImage + smoke jobs now apt-install the full PyQt6 runtime lib set
  (`libgl1`, `libegl1`, `libxkbcommon0`, `libdbus-1-3`, `libfontconfig1`,
  `libxcb-cursor0`) plus `squashfs-tools` for `appimagetool`.

### Fixed
- Temp firmware files (downloaded `.bin` and 1 MiB padded image) now
  unlinked after flash success and failure.
- `run_admin_streaming` now polls stdout via `select.select()` instead
  of blocking on `for line in proc.stdout:`. The wall-clock deadline
  fires even when a wedged `flashrom` produces no output, so a hung
  CH341A no longer burns the full timeout budget waiting on readline.

### Reverted
- `actions/upload-artifact` rolled back from v4 to v3 — Forgejo's
  Actions implementation does not yet support the v4 upload protocol
  (returns `GHESNotSupportedError`). Bump again once Forgejo lands v4
  compatibility.

## [0.2.0] - 2026-04-29

First Linux-native release. Replaces the macOS escalation path with
`pkexec`/`sudo`, ships a self-contained AppImage, and hardens the flash
pipeline with an opt-in pre-flash backup and a mandatory post-write verify.

### Added
- Safe-flash pipeline: optional pre-flash chip read to
  `~/HDZero_pre-flash_<timestamp>.bin`, write, then explicit re-verify —
  chained under one privilege prompt so a failure short-circuits with the
  rollback image intact. "Backup chip before flashing" checkbox on both
  Local and Internet panels (default on). (#1)
- `run_admin_streaming()` in `flash_ops` for live phase status updates
  parsed from flashrom stdout. (#1)
- Forgejo Actions CI: smoke job (`py_compile` + `pytest` + headless Qt
  `MainWindow` boot under `QT_QPA_PLATFORM=offscreen`) and AppImage build
  job that uploads the artifact. (#2, #3)
- pytest suite covering `make_padded_image_1mib`, `find_flashrom`,
  `_build_admin_argv`, `run_admin` fallback, and all `udev_check` helpers.
  (#3, #4)
- udev install UX: `udev_check` module, dismissible startup banner with a
  copy-paste install command when `99-ch341a.rules` is missing and
  `HDZERO_NO_ESCALATE` is unset, plus `packaging/install-udev.sh` helper.
  Rule + helper now bundled into the AppImage. (#4)
- Release automation: pushing a `v*` tag triggers
  `.forgejo/workflows/release.yml`, which builds the AppImage, generates
  `SHA256SUMS`, and creates a Forgejo release with both files attached.
  (#6)

### Changed
- App header switched from "HDzero Programmer for MAC" to
  "HDZero Programmer (Linux)". (#5)
- `flashrom not found` hints now point at `apt`/`dnf`/`pacman` instead of
  Homebrew. (#5)
- README rewritten: drop the stale "Linux port in progress" status, document
  the safe-flash pipeline, the udev banner, the install helper, the CI
  workflow, and the release flow. (#5, #6)

### Removed
- Stale macOS-only artifacts and references that survived the fork. (#5)

## [0.1.0] - prior

Initial fork of the upstream macOS tool (no Linux adaptations yet).
