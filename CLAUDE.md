# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PyQt6 desktop GUI (Linux) for flashing HDZero VTX firmware. Wraps the `flashrom` CLI driving a CH341A USB SPI programmer against a 1 MiB W25Q80 chip. Forked from [Gunther Votteler's macOS tool](https://github.com/gvotteler) under MIT.

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

- **smoke** — installs `PyQt6` + `requests`, runs `py_compile`, then boots `MainWindow` headlessly under `QT_QPA_PLATFORM=offscreen` against an unroutable `HDZERO_API_BASE` so the device-loader worker fails fast instead of hitting the live API.
- **appimage** — installs `pipx` → `python-appimage`, runs `packaging/build-appimage.sh` with `APPIMAGE_EXTRACT_AND_RUN=1` (CI runners lack `/dev/fuse`), and uploads `dist/HDZeroProgrammer-x86_64.AppImage` as a build artifact.

`.forgejo/workflows/release.yml` triggers on `v*` tag pushes: builds the AppImage, generates `SHA256SUMS`, creates a Forgejo release for the tag (or reuses one if it already exists), and uploads both files as release assets via the repo-scoped `${{ secrets.GITHUB_TOKEN }}`. To cut a release: `git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0`.

Requires a registered Forgejo Actions runner labeled `ubuntu-22.04`. With no runner, jobs queue indefinitely — visible in the Actions tab on the repo.

## Architecture

Three files, one Qt event loop, worker threads for blocking I/O.

- `main.py` — `MainWindow` owns the three tabs and the high-level `start_backup` / `start_flash` orchestration. Owns `FlashWorker` / `BackupWorker` lifetimes (assigned to `self.worker` / `self.bkw` to keep QThreads alive).
- `internet_panel.py` — `InternetPanel` tab + four `QThread` HTTP workers (`LoadDevicesWorker`, `LoadFirmwaresWorker`, `LoadImageWorker`, `DownloadFirmwareWorker`) hitting `HDZERO_API_BASE` (default `https://hdzero.go-next.co`, override via env var). Endpoints: `/api/devices`, `/api/firmwares/{device_id}`. Selecting a firmware downloads to a temp `.bin`, then emits `flashRequested`. Two status surfaces in this panel are easy to confuse: `lbl_state` is the short single-line status above the phase line; `lbl_phase` is the "Wait - …" phase indicator written by `set_phase()` and driven by `FlashWorker.status`. The `status_box` `QTextEdit` is the verbose log mirror.
- `flash_ops.py` — `flashrom` discovery, `make_padded_image_1mib` (pads firmware to 1 MiB with `0xFF`, mandatory for W25Q80), and the `FlashWorker` / `BackupWorker` QThreads. Privileged `flashrom` invocation goes through `run_admin()` (buffered) or `run_admin_streaming()` (line callback for live phase updates); both share `_build_admin_argv()` (pkexec → sudo -A → sudo -n → clear-error fallback). `FlashWorker` runs a single-prompt `sh -c` chain — optional pre-flash backup (`-r`) → write (`-w`) → explicit re-verify (`-v`) — joined with `&&` so a failure short-circuits and the user sees one polkit prompt for the whole sequence (deliberate UX choice; do not split a flash into multiple privileged calls).

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
- `flashrom -p ch341a_spi -r` is the backup command. Manual backups land at `~/HDZero_backup_<timestamp>.bin`; pre-flash auto-backups (when the "Backup chip before flashing" checkbox is on, default) land at `~/HDZero_pre-flash_<timestamp>.bin` and are produced by the same chained `flashrom -r` step inside `FlashWorker`.

## Gotchas

- Anything blocking (HTTP, `flashrom`, file I/O > a few KB) must run in a `QThread`, not on the main thread — every existing worker follows the `QThread` + `pyqtSignal` pattern.
- `run_admin()` wraps the command in `sh -c` and passes it to `pkexec` / `sudo`. Arguments are still built as shell strings by `FlashWorker` and `BackupWorker`; if you ever take untrusted input into one of those strings, switch to argv-list construction first. Current inputs (temp file paths, timestamped backup names) are controlled and safe.
- Without a polkit agent installed, `pkexec` falls through to `sudo` paths which will likely fail under a GUI session that has no TTY. The CH341A udev rule in `packaging/99-ch341a.rules` avoids the prompt entirely by granting non-root USB access; combine with `HDZERO_NO_ESCALATE=1` to short-circuit `run_admin()` and execute `flashrom` directly as the user. `udev_check.should_show_hint()` drives a startup banner in `MainWindow` that surfaces a copy-paste install command (`udev_check.install_command(...)`) when the rule is missing and `HDZERO_NO_ESCALATE` is unset; `packaging/install-udev.sh` runs the same steps non-interactively. The banner is skipped silently if `bundled_rule_path()` cannot locate the rule (e.g. a stripped install missing the bundled file).
- `resource_path()` lives in `internet_panel.py` and is imported by `main.py`; reuse it for any new bundled asset so frozen builds keep working.
- README is loaded at runtime by `HelpPanel` — it tries `README.md`, then `Readme.md`. Don't rename the file without updating that list.
- Spanish comments are scattered through the code; preserve them when editing nearby lines.
- `MainWindow._confirm_ch341a_present()` runs a non-blocking soft-check before flash and backup ops via `udev_check.ch341a_present()`. Missing device → Yes/No dialog (default No). Set `HDZERO_SKIP_CH341A_CHECK=1` to bypass entirely (sandboxes without `/sys/bus/usb`, or non-CH341A programmers exposed via the same flashrom interface).
- `tests/fixtures/fake_flashrom.sh` is a drop-in stand-in for the real binary: emits the same stdout markers FlashWorker greps for phase status and supports targeted failure via `FAKE_FLASHROM_FAIL=read|write|verify`. `tests/test_flash_integration.py` calls `FlashWorker.run()` synchronously (not via `start()`) under `HDZERO_NO_ESCALATE=1` so signal slots fire inline and assertions stay simple.
