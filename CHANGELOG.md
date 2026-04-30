# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Post-`v0.2.0` work on `main` not yet tagged. Bumps the next release; until
then, `__version__` and `pyproject` still read `0.2.0`.

### Added
- ADR scaffolding under `docs/adr/` with template + index; ADR-0001
  (single-prompt sh -c chain) and ADR-0002 (1 MiB padded image with 0xFF).
  (#31 partial)
- Hard timeout on `flashrom` invocations in `FlashWorker` / `BackupWorker`
  so a hung CH341A doesn't block the GUI indefinitely.
- gitleaks secret scan in CI and as a pre-commit hook.
- pytest-cov coverage measurement in CI (no fail-under threshold yet).
- Contributing guide, code of conduct, issue + PR templates.
- 2026-04-29 acquisition audit report archived under `docs/audits/`.

### Changed
- Chip backups (manual + pre-flash auto) now land in
  `app_logging.backup_dir()` — `HDZERO_BACKUP_DIR` override, else
  `$XDG_STATE_HOME/hdzero-programmer/backups/` (default
  `~/.local/state/hdzero-programmer/backups/`). Pre-existing files at
  `~/HDZero_*.bin` are not auto-migrated.
- Narrowed broad `except Exception` handlers across flash/UI paths.
- LICENSE: SPDX header, dual fork copyright line, PyQt6 GPL-binary
  position documented in `LICENSE-NOTES.md`.
- `actions/upload-artifact` bumped to v4.

### Fixed
- Temp firmware files (downloaded `.bin` and 1 MiB padded image) now
  unlinked after flash success and failure.

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
