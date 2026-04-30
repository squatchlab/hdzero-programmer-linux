# CLAUDE.md

Onboarding doc for Claude Code. Day-to-day usage lives in `README.md`;
this file covers what's *non-obvious* from reading the code.

## Project

PyQt6 desktop GUI (Linux) for flashing HDZero VTX firmware via `flashrom` +
CH341A USB SPI programmer against a 1 MiB W25Q80 chip. Forked from
[Gunther Votteler's macOS tool](https://github.com/gvotteler/HDZero-Programmer-Tool-Mac)
under MIT.

## Architecture

Six top-level Python modules (all listed in `[tool.setuptools].py-modules`;
the AppImage build copies them into `_hdzero_app/`), one Qt event loop,
worker threads for blocking I/O. ADRs for non-trivial decisions live in
[`docs/adr/`](docs/adr/); the 2026-04-29 acquisition audit and its
remaining firmware-trust blockers (`#19`–`#21`) are under
[`docs/audits/`](docs/audits/). `#22` (HW-CI gate) and `#23` (SECURITY.md)
were closed in the post-audit batch — see `docs/HARDWARE-CI.md` and
`SECURITY.md`.

- `main.py` — `MainWindow` owns the three tabs and routes flash signals.
  Holds `FlashWorker` / `BackupWorker` references on `self.worker` /
  `self.bkw` so QThreads stay alive.
- `internet_panel.py` — `InternetPanel` + four HTTP `QThread` workers
  hitting `HDZERO_API_BASE` (default `https://hdzero.go-next.co`).
  Endpoints `/api/devices`, `/api/firmwares/{id}`. Selecting a firmware
  downloads to a temp `.bin` then emits `flashRequested(path, autobackup)`.
  Two status surfaces: `lbl_state` (one-line above) vs `lbl_phase`
  ("Wait - …", driven by `FlashWorker.status`); `status_box` is the
  verbose log mirror.
- `flash_ops.py` — `find_flashrom()` (probes `/usr/{bin,sbin}`,
  `/usr/local/{bin,sbin}`, Linuxbrew, Homebrew, then `shutil.which`),
  `make_padded_image_1mib` (pads with `0xFF` — see ADR-0002), and the
  `FlashWorker` / `BackupWorker` QThreads. `run_admin()` (buffered) and
  `run_admin_streaming()` (line callback) share `_build_admin_argv()`:
  pkexec → sudo -A (needs `SUDO_ASKPASS`) → sudo -n → clear-error fallback.
- `udev_check.py` — `99-ch341a.rules` install state, CH341A vendor/product
  walk of `/sys/bus/usb/devices`, reads `HDZERO_NO_ESCALATE`. Drives the
  install banner and the `--check-rule` CLI flag.
- `app_settings.py` — `settings()` (reverse-DNS QSettings scope
  `lab.squatch / hdzero-programmer-linux`) and `migrate_settings_once()`
  (one-shot copy of the legacy `HDZero/Programmer` scope into the new one).
- `app_logging.py` — `state_dir()` (`HDZERO_STATE_DIR` >
  `$XDG_STATE_HOME/hdzero-programmer` > `~/.local/state/hdzero-programmer`)
  and `backup_dir()` (`HDZERO_BACKUP_DIR` > `state_dir()/backups/`).
  `open_flash_log(prefix, version)` returns a line-buffered `(path, fh)`.

### Signal wiring (`MainWindow.__init__`)

`InternetPanel` is decoupled from flash logic — emits, `MainWindow` routes:

- `firmwareSelected` → `on_fw_downloaded_set_local` (populates `LocalPanel`)
- `flashRequested(str, bool)` → `start_flash(fw_path, autobackup)`
- `log` → `panel_local.append_log`
- `FlashWorker.status` / `.log` connect to **both** panels.

When adding a flash trigger: emit a request signal from the panel, wire
in `MainWindow`. Do not call `flash_ops` from panels directly.

### Constants

- `HDZERO_MAX = 64 KiB` — UI rejects oversized `.bin`.
- `FLASH_SIZE_BYTES = 1 MiB` — chip size; padded write target. ADR-0002.
- Backups land at `backup_dir()/HDZero_backup_<ts>.bin` (manual) or
  `HDZero_pre-flash_<ts>.bin` (auto, when "Backup chip before flashing"
  is on — default).

## Gotchas

- **QThread-or-bust.** Anything blocking (HTTP, `flashrom`, multi-KB I/O)
  runs on a `QThread` with `pyqtSignal`s. No exceptions on the main thread.
- **Single-prompt flash chain.** `FlashWorker` runs backup → write →
  verify as one `sh -c` chain joined with `&&`, passed through `run_admin()`
  once. **Never split into multiple privileged calls.** Paths interpolated
  via `shlex.quote()` — never f-string raw paths into the chain. ADR-0001.
- **Two paths to `flashrom`.** Default: pkexec/sudo. Friendly: install
  `packaging/99-ch341a.rules` (or run `packaging/install-udev.sh`) and
  set `HDZERO_NO_ESCALATE=1` to short-circuit `run_admin()`. Without a
  polkit agent, pkexec falls through to sudo paths that fail under a
  GUI session with no TTY. `udev_check.should_show_hint()` drives the
  startup install banner; silently skipped if `bundled_rule_path()` can't
  locate the rule.
- **Pre-flash CH341A presence check.** `MainWindow._confirm_ch341a_present()`
  pops a Yes/No dialog (default No) when no device is enumerated. Bypass
  with `HDZERO_SKIP_CH341A_CHECK=1` (test sandboxes, non-CH341A programmers).
- **`resource_path()`** lives in `internet_panel.py`. It checks
  `HDZERO_APP_DIR` (AppImage), then `sys._MEIPASS` (PyInstaller-compat,
  unused), then the module dir. Reuse for any new bundled asset.
- **README at runtime.** `HelpPanel` tries `README.md` then `Readme.md`
  and renders via `setMarkdown()`. Don't rename without updating the list.
- **Excepthook.** `main._install_excepthook()` (after `QApplication`
  construction) catches uncaught exceptions, pops `QMessageBox.critical`
  with traceback + transcript-dir hint, and keeps the app alive so a
  half-written chip isn't abandoned. Reentrancy-guarded.
- **`InternetPanel` retry.** Loaders call `_arm_loader(label, fn)`;
  `on_fail` reveals a `Retry <label>` button; success paths call
  `_clear_loader()`. Lets users recover from transient API failures.
- **Persistent transcripts.** `MainWindow._open_flash_log` /
  `_flash_log_write` / `_close_flash_log` mirror worker emissions to a
  line-buffered file under `state_dir()`, ending with `=== OK: … ===` or
  `=== FAIL: … ===`. Crash mid-flash leaves a partial transcript on disk;
  `OSError` on open degrades silently so the flash itself isn't blocked.
- **English only.** Upstream fork shipped Spanish section markers; future
  imports from upstream must translate before merging.
- **Hard-coded version.** `main.__version__` is pinned to
  `[project].version` by `tests/test_version_consistency.py`. Necessary
  because the AppImage grafts source into `_hdzero_app/` *without*
  dist-info, so `importlib.metadata.version()` fails at runtime there.
  Bump both fields in the same PR.
- **CLI flags.** `main()` runs `argparse` for `--version` / `--check-rule`
  before constructing `QApplication`; `parse_known_args` lets Qt's
  platform flags pass through. CI `appimage` job execs both flags as a
  launch smoke test.
- **Autobackup persistence.** `app_settings.settings()` returns a
  `QSettings` handle in the reverse-DNS scope `lab.squatch /
  hdzero-programmer-linux` (file `~/.config/lab.squatch/hdzero-programmer-linux.conf`).
  Key `autobackup` is shared between Local and Internet panels — last
  toggle on either becomes the next-launch default.
  `app_settings.migrate_settings_once()` runs in `main()` after
  `_install_excepthook()` and copies the legacy `HDZero/Programmer` keys
  forward exactly once (sentinel `_migrated_from_legacy_org`); the legacy
  file is left intact so a downgrade still finds its data.
- **Test harness.** `tests/fixtures/fake_flashrom.sh` is a drop-in
  stand-in: emits the same stdout markers `FlashWorker` greps and supports
  `FAKE_FLASHROM_FAIL=read|write|verify`. Integration tests call
  `worker.run()` synchronously under `HDZERO_NO_ESCALATE=1` so signal
  slots fire inline.
- **Lint + secrets.** `ruff check .` in CI gates merges; deliberate
  ignores are in `pyproject.toml` (legacy upstream style — `E401/E701/
  E702/E501/W293`). `.pre-commit-config.yaml` runs ruff (`--fix`),
  ruff-format (`--check` only, no bulk reformat yet), and `gitleaks` on
  every commit; CI re-runs ruff + gitleaks as the gate.

## CI / release

`.forgejo/workflows/ci.yml` (push to `main` + PRs):

- **smoke** — `pip install -e ".[dev]"`, `ruff check`, `mypy` (strict on
  `flash_ops` / `udev_check` / `app_logging` / `app_settings`;
  `disallow_untyped_defs` on `main` / `internet_panel` — see
  `[tool.mypy]` overrides in `pyproject.toml`), `gitleaks detect`,
  `py_compile` the six modules, `pytest --cov` (no fail-under yet),
  headless `MainWindow` boot under `QT_QPA_PLATFORM=offscreen` against an
  unroutable `HDZERO_API_BASE`.
- **appimage** — `python-appimage` (pinned), runs
  `packaging/build-appimage.sh` with `APPIMAGE_EXTRACT_AND_RUN=1` (CI
  lacks `/dev/fuse`), uploads the artifact, smoke-execs `--version` and
  `--check-rule` (with `HDZERO_NO_ESCALATE=1`).

`.forgejo/workflows/hw-test.yml` (manual / `workflow_dispatch`): real-HW
flash regression gated on `[ubuntu-22.04, hdzero-hw]`. Runner setup
is host-specific opt-in work; see `docs/HARDWARE-CI.md`. Without an
`hdzero-hw`-labeled runner the job sits unclaimed forever, which is the
intended default.

`.forgejo/workflows/release.yml` triggers on `v*` tags: builds the
AppImage, generates `SHA256SUMS`, creates/updates a Forgejo release with
both files attached. Cut a release: `git tag -a vX.Y.Z -m "vX.Y.Z" &&
git push origin vX.Y.Z`. Requires a Forgejo Actions runner labeled
`ubuntu-22.04` — without one, jobs queue forever.
