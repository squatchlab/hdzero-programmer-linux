# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PyQt6 desktop GUI (Linux) for flashing HDZero VTX firmware. Wraps the `flashrom` CLI driving a CH341A USB SPI programmer against a 1 MiB W25Q80 chip. Forked from [Gunther Votteler's macOS tool](https://github.com/gvotteler/HDZero-Programmer-Tool-Mac) under MIT.

## Run / Build

Project metadata + pinned dependencies live in `pyproject.toml` (PEP 621). The `hdzero-programmer` GUI entrypoint is wired to `main:main`.

```bash
pip install --user .          # installs the hdzero-programmer launcher
hdzero-programmer
# or run from a checkout without installing
pip install --user PyQt6 requests && python3 main.py
```

Runtime dep on the `flashrom` CLI:

```bash
sudo apt install flashrom    # Debian/Ubuntu
sudo dnf install flashrom    # Fedora/RHEL
sudo pacman -S flashrom      # Arch
```

`flash_ops.find_flashrom()` probes `/usr/{bin,sbin}`, `/usr/local/{bin,sbin}`, Linuxbrew, then macOS Homebrew, falling back to `shutil.which`. Privileged invocation goes through `run_admin()` which prefers `pkexec` (polkit GUI prompt), then `sudo -A` if `SUDO_ASKPASS` is set, then non-interactive `sudo` as a last resort. A polkit agent (gnome-shell, plasma, lxpolkit, etc.) is required for the standard GUI flow.

Distribution target is an **AppImage** built via `packaging/build-appimage.sh` (closes #8): uses [`python-appimage`](https://github.com/niess/python-appimage) to graft a relocatable Python 3.12 + PyQt6 + `requests`, then post-injects the application source into `opt/python3.12/lib/python3.12/site-packages/_hdzero_app/`. The generated AppRun (`recipe/entrypoint.sh`) exports `HDZERO_APP_DIR` so `resource_path()` resolves bundled assets out of the inject dir. `resource_path()` checks `HDZERO_APP_DIR` first, then falls back to `sys._MEIPASS` (PyInstaller-compat — no PyInstaller build is currently shipped) and finally the module's directory (pip / checkout).

## CI

`.forgejo/workflows/ci.yml` runs on push to `main` and on pull requests:

- **smoke** — installs `.[dev]` (PyQt6, requests, pytest, pytest-cov, ruff), runs `ruff check .`, downloads + runs `gitleaks detect --source .`, `py_compile`s the five top-level modules, runs `pytest --cov`, then boots `MainWindow` headlessly under `QT_QPA_PLATFORM=offscreen` against an unroutable `HDZERO_API_BASE` so the device-loader worker fails fast instead of hitting the live API. Ruff + pytest are blocking gates; coverage is measured but not yet thresholded (`--cov-fail-under` deliberately omitted).
- **appimage** — installs `pipx` → `python-appimage`, runs `packaging/build-appimage.sh` with `APPIMAGE_EXTRACT_AND_RUN=1` (CI runners lack `/dev/fuse`), and uploads `dist/HDZeroProgrammer-x86_64.AppImage` as a build artifact.

`.forgejo/workflows/release.yml` triggers on `v*` tag pushes: builds the AppImage, generates `SHA256SUMS`, creates a Forgejo release for the tag (or reuses one if it already exists), and uploads both files as release assets via the repo-scoped `${{ secrets.GITHUB_TOKEN }}`. To cut a release: `git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0`.

Requires a registered Forgejo Actions runner labeled `ubuntu-22.04`. With no runner, jobs queue indefinitely — visible in the Actions tab on the repo.

## Architecture

Five Python modules, one Qt event loop, worker threads for blocking I/O. ADRs for non-trivial design decisions live in [`docs/adr/`](docs/adr/) (single-prompt flash chain, 1 MiB pad invariant, more incoming under `#31`); the 2026-04-29 acquisition audit verdict is archived under [`docs/audits/`](docs/audits/) and drives the open-blocker backlog (`#19`–`#23`).

- `main.py` — `MainWindow` owns the three tabs and the high-level `start_backup` / `start_flash` orchestration. Owns `FlashWorker` / `BackupWorker` lifetimes (assigned to `self.worker` / `self.bkw` to keep QThreads alive).
- `internet_panel.py` — `InternetPanel` tab + four `QThread` HTTP workers (`LoadDevicesWorker`, `LoadFirmwaresWorker`, `LoadImageWorker`, `DownloadFirmwareWorker`) hitting `HDZERO_API_BASE` (default `https://hdzero.go-next.co`, override via env var). Endpoints: `/api/devices`, `/api/firmwares/{device_id}`. Selecting a firmware downloads to a temp `.bin`, then emits `flashRequested`. Two status surfaces in this panel are easy to confuse: `lbl_state` is the short single-line status above the phase line; `lbl_phase` is the "Wait - …" phase indicator written by `set_phase()` and driven by `FlashWorker.status`. The `status_box` `QTextEdit` is the verbose log mirror.
- `flash_ops.py` — `flashrom` discovery, `make_padded_image_1mib` (pads firmware to 1 MiB with `0xFF`, mandatory for W25Q80), and the `FlashWorker` / `BackupWorker` QThreads. Privileged `flashrom` invocation goes through `run_admin()` (buffered) or `run_admin_streaming()` (line callback for live phase updates); both share `_build_admin_argv()` (pkexec → sudo -A → sudo -n → clear-error fallback). `FlashWorker` runs a single-prompt `sh -c` chain — optional pre-flash backup (`-r`) → write (`-w`) → explicit re-verify (`-v`) — joined with `&&` so a failure short-circuits and the user sees one polkit prompt for the whole sequence (deliberate UX choice; do not split a flash into multiple privileged calls).
- `udev_check.py` — detects `99-ch341a.rules` install state, walks `/sys/bus/usb/devices` for the CH341A vendor/product, and reads `HDZERO_NO_ESCALATE`. Drives the first-run install banner in `MainWindow` and the `--check-rule` CLI smoke flag.
- `app_logging.py` — resolves the per-flash transcript dir (`HDZERO_STATE_DIR` > `$XDG_STATE_HOME/hdzero-programmer` > `~/.local/state/hdzero-programmer`) and opens line-buffered log files via `open_flash_log(prefix, version)`.

All five modules are top-level (`tool.setuptools.py-modules` lists every one); pip-install must include each or the launcher `ModuleNotFoundError`s on import. AppImage build (`packaging/build-appimage.sh`) copies them explicitly into the inject dir.

### Cross-panel signal wiring (`MainWindow.__init__`)

`InternetPanel` is decoupled from flash logic — it emits, `MainWindow` routes:

- `panel_internet.firmwareSelected` → `on_fw_downloaded_set_local` (populates `LocalPanel` path)
- `panel_internet.flashRequested(str, bool)` → `start_flash(fw_path, autobackup)` — second arg drives the pre-flash backup phase
- `panel_internet.log` → `panel_local.append_log`
- `FlashWorker.status` / `.log` are connected to **both** `panel_local` and `panel_internet` so progress shows on whichever tab the user is viewing.

When adding a new flash trigger, follow this pattern: emit a request signal from the panel, wire it in `MainWindow`, do not call `flash_ops` from panels directly.

### Constants that matter

- `HDZERO_MAX = 64 * 1024` — UI rejects `.bin` larger than 64 KB (HDZero firmware ceiling).
- `FLASH_SIZE_BYTES = 1 MiB` — chip size; the padded image written via `flashrom -p ch341a_spi -w` must be exactly this.
- `flashrom -p ch341a_spi -r` is the backup command. Both manual backups (`HDZero_backup_<timestamp>.bin`) and pre-flash auto-backups (`HDZero_pre-flash_<timestamp>.bin`, on by default via the "Backup chip before flashing" checkbox) land in `app_logging.backup_dir()` — `HDZERO_BACKUP_DIR` env override, else `state_dir()/backups/` (default `~/.local/state/hdzero-programmer/backups/`). Pre-flash auto-backup is the chained `flashrom -r` step inside `FlashWorker`.

## Gotchas

- Anything blocking (HTTP, `flashrom`, file I/O > a few KB) must run in a `QThread`, not on the main thread — every existing worker follows the `QThread` + `pyqtSignal` pattern.
- `run_admin()` wraps the command in `sh -c` and passes it to `pkexec` / `sudo`. `FlashWorker` and `BackupWorker` now build the chain by interpolating `shlex.quote()`'d paths so a path with whitespace, quotes, or shell-meta chars (e.g. `XDG_STATE_HOME` or `tempfile` resolving under `~/odd dir/`) can't break out of the chain. The `&&` join still keeps the whole pipeline under one privilege prompt — switching to argv lists would split it into multiple prompts because pkexec/sudo run a single program. Adding new flashrom invocations: keep this pattern; never f-string a raw path into the chain.
- Without a polkit agent installed, `pkexec` falls through to `sudo` paths which will likely fail under a GUI session that has no TTY. The CH341A udev rule in `packaging/99-ch341a.rules` avoids the prompt entirely by granting non-root USB access; combine with `HDZERO_NO_ESCALATE=1` to short-circuit `run_admin()` and execute `flashrom` directly as the user. `udev_check.should_show_hint()` drives a startup banner in `MainWindow` that surfaces a copy-paste install command (`udev_check.install_command(...)`) when the rule is missing and `HDZERO_NO_ESCALATE` is unset; `packaging/install-udev.sh` runs the same steps non-interactively. The banner is skipped silently if `bundled_rule_path()` cannot locate the rule (e.g. a stripped install missing the bundled file).
- `resource_path()` lives in `internet_panel.py` and is imported by `main.py`; reuse it for any new bundled asset so frozen builds keep working.
- README is loaded at runtime by `HelpPanel` — it tries `README.md`, then `Readme.md`. Don't rename the file without updating that list.
- All comments and UI strings are English. Upstream macOS fork shipped Spanish section markers (`# Cargar README`, `# Columna IZQUIERDA`, etc.); future imports from upstream must translate any Spanish before merging.
- `MainWindow._confirm_ch341a_present()` runs a non-blocking soft-check before flash and backup ops via `udev_check.ch341a_present()`. Missing device → Yes/No dialog (default No). Set `HDZERO_SKIP_CH341A_CHECK=1` to bypass entirely (sandboxes without `/sys/bus/usb`, or non-CH341A programmers exposed via the same flashrom interface).
- `tests/fixtures/fake_flashrom.sh` is a drop-in stand-in for the real binary: emits the same stdout markers FlashWorker greps for phase status and supports targeted failure via `FAKE_FLASHROM_FAIL=read|write|verify`. `tests/test_flash_integration.py` calls `FlashWorker.run()` synchronously (not via `start()`) under `HDZERO_NO_ESCALATE=1` so signal slots fire inline and assertions stay simple. Suite size is 51 tests across `test_flash_ops`, `test_flash_integration`, `test_udev_check`, `test_app_logging`, `test_excepthook`, `test_version_consistency`.
- `main._install_excepthook()` (called once after `QApplication` construction) replaces `sys.excepthook` with a handler that prints the traceback to stderr, pops `QMessageBox.critical` with the traceback + transcript-dir hint, and keeps the app alive — useful for in-flight flashes where dropping the process would leave the chip half-written. Reentrancy-guarded: a buggy hook re-entry falls back to the original handler.
- `InternetPanel` exposes a `Retry` button next to `lbl_state` that re-runs whichever loader most recently failed. Each loader (`load_devices`, `on_device_changed`, `download_selected_fw`) calls `_arm_loader(label, fn)` before kicking; `on_fail` reveals the button labeled `Retry <label>`; success paths call `_clear_loader()` to hide it again. Lets the user recover from transient API failures without remembering which dropdown they were in.
- `app_logging.open_flash_log(prefix, version)` opens a fresh line-buffered file under the app state dir (`HDZERO_STATE_DIR` > `$XDG_STATE_HOME/hdzero-programmer` > `~/.local/state/hdzero-programmer`) and returns `(path, fh)`. `MainWindow._open_flash_log` / `_flash_log_write` / `_close_flash_log` mirror every worker `log` and `status` emission to that file in real time, then write a final `=== OK: … ===` or `=== FAIL: … ===` summary line and append the path to the GUI log so the user can find the transcript. A crash mid-flash leaves the partial transcript on disk because the handle is line-buffered; the open path silently degrades on `OSError` (disk-full, broken XDG dir) so the GUI flash itself isn't blocked.
- Version is hard-coded in `main.__version__` (and pinned to the `[project].version` field in pyproject.toml by `tests/test_version_consistency.py`). The hard-code is necessary because the AppImage build grafts source into `site-packages/_hdzero_app/` *without* dist-info, so `importlib.metadata.version("hdzero-programmer")` would fail at runtime there. Bump both fields in the same PR. The CI `appimage` job execs the built AppImage with `--version` and `--check-rule` (with `HDZERO_NO_ESCALATE=1`) as a launch smoke test.
- `main()` parses `--version` and `--check-rule` via argparse before constructing `QApplication`. `parse_known_args` lets Qt platform flags (`-style`, `-platform`, …) pass through to `QApplication` untouched.
- Lint with `ruff check .` (config in `pyproject.toml`, runs in CI before pytest). Selected rules: pyflakes (F), pycodestyle E/W, isort (I). Deliberate ignores: E401/E701/E702/E501/W293 — the upstream macOS-fork code style packs multiple statements per line and mixes imports, and rewriting it bulk-style would create churn for no real bug protection. New code should still aim for one statement per line; the ignores exist so the lint job stays useful rather than blocked on legacy style.
- `.pre-commit-config.yaml` runs `ruff` (with `--fix`), `ruff-format --check` (stage 1: check-only, no bulk reformat of legacy code), and `gitleaks` on every commit. Install once with `pre-commit install`; CI re-runs ruff and gitleaks against the full tree as the gate. `ruff-format` will flip from `--check` to autoformat once the codebase is fully formatted — not yet.
- Autobackup checkbox state persists via `QSettings("HDZero", "Programmer")` under key `autobackup`. Both `LocalPanel` and `InternetPanel` read on construction and write on toggle; the shared key means the last toggle on either tab becomes the next-launch default. On Linux this lands in `~/.config/HDZero/Programmer.conf`. `HelpPanel` renders `README.md` via `QTextEdit.setMarkdown()` rather than `setPlainText` so headings, code blocks, and lists render correctly in the in-app help.
