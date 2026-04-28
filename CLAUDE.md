# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PyQt6 desktop GUI (Linux) for flashing HDZero VTX firmware. Wraps the `flashrom` CLI driving a CH341A USB SPI programmer against a 1 MiB W25Q80 chip. Forked from [Gunther Votteler's macOS tool](https://github.com/gvotteler) under MIT.

## Run / Build

No `requirements.txt` or `pyproject.toml` is checked in yet (see issue #7). Manual setup:

```bash
pip install PyQt6 requests
python3 main.py
```

Runtime dep on the `flashrom` CLI:

```bash
sudo apt install flashrom    # Debian/Ubuntu
sudo dnf install flashrom    # Fedora/RHEL
sudo pacman -S flashrom      # Arch
```

`flash_ops.find_flashrom()` probes `/usr/{bin,sbin}`, `/usr/local/{bin,sbin}`, Linuxbrew, then macOS Homebrew, falling back to `shutil.which`. Privileged invocation goes through `run_admin()` which prefers `pkexec` (polkit GUI prompt), then `sudo -A` if `SUDO_ASKPASS` is set, then non-interactive `sudo` as a last resort. A polkit agent (gnome-shell, plasma, lxpolkit, etc.) is required for the standard GUI flow.

Distribution target is an **AppImage** (planned, issue #8). The repository still contains macOS bundle leftovers (`app_icon.icns`, `AppIcon.iconset/`, `qt.conf`, `qt_plugin_path_hook.py`, `HDZeroProgrammerTool_v2.zip`); see issue #9 for cleanup. `resource_path()` and `qt_plugin_path_hook.py` use `sys._MEIPASS`, which works for both PyInstaller and AppImage's python-appimage builds.

## Architecture

Three files, one Qt event loop, worker threads for blocking I/O.

- `main.py` — `MainWindow` owns the three tabs and the high-level `start_backup` / `start_flash` orchestration. Owns `FlashWorker` / `BackupWorker` lifetimes (assigned to `self.worker` / `self.bkw` to keep QThreads alive).
- `internet_panel.py` — `InternetPanel` tab + four `QThread` HTTP workers (`LoadDevicesWorker`, `LoadFirmwaresWorker`, `LoadImageWorker`, `DownloadFirmwareWorker`) hitting `HDZERO_API_BASE` (default `https://hdzero.go-next.co`, override via env var). Endpoints: `/api/devices`, `/api/firmwares/{device_id}`. Selecting a firmware downloads to a temp `.bin`, then emits `flashRequested`. Two status surfaces in this panel are easy to confuse: `lbl_state` is the short single-line status above the phase line; `lbl_phase` is the "Wait - …" phase indicator written by `set_phase()` and driven by `FlashWorker.status`. The `status_box` `QTextEdit` is the verbose log mirror.
- `flash_ops.py` — `flashrom` discovery, `make_padded_image_1mib` (pads firmware to 1 MiB with `0xFF`, mandatory for W25Q80), and the `FlashWorker` / `BackupWorker` QThreads. Privileged `flashrom` invocation goes through `run_admin()` (pkexec → sudo -A → sudo -n → clear-error fallback) — single GUI password prompt per op (deliberate UX choice; do not split a flash into multiple privileged calls).

### Cross-panel signal wiring (`MainWindow.__init__`)

`InternetPanel` is decoupled from flash logic — it emits, `MainWindow` routes:

- `panel_internet.firmwareSelected` → `on_fw_downloaded_set_local` (populates `LocalPanel` path)
- `panel_internet.flashRequested` → `start_flash`
- `panel_internet.log` → `panel_local.append_log`
- `FlashWorker.status` / `.log` are connected to **both** `panel_local` and `panel_internet` so progress shows on whichever tab the user is viewing.

When adding a new flash trigger, follow this pattern: emit a request signal from the panel, wire it in `MainWindow`, do not call `flash_ops` from panels directly.

### Constants that matter

- `HDZERO_MAX = 64 * 1024` — UI rejects `.bin` larger than 64 KB (HDZero firmware ceiling).
- `FLASH_SIZE_BYTES = 1 MiB` — chip size; the padded image written via `flashrom -p ch341a_spi -w` must be exactly this.
- `flashrom -p ch341a_spi -r` is the backup command (full chip read to `~/HDZero_backup_<timestamp>.bin`).

## Gotchas

- Anything blocking (HTTP, `flashrom`, file I/O > a few KB) must run in a `QThread`, not on the main thread — every existing worker follows the `QThread` + `pyqtSignal` pattern.
- `run_admin()` wraps the command in `sh -c` and passes it to `pkexec` / `sudo`. Arguments are still built as shell strings by `FlashWorker` and `BackupWorker`; if you ever take untrusted input into one of those strings, switch to argv-list construction first. Current inputs (temp file paths, timestamped backup names) are controlled and safe.
- Without a polkit agent installed, `pkexec` falls through to `sudo` paths which will likely fail under a GUI session that has no TTY. CH341A udev rules (issue #6) avoid the prompt entirely by granting non-root USB access.
- `resource_path()` lives in `internet_panel.py` and is imported by `main.py`; reuse it for any new bundled asset so frozen builds keep working.
- README is loaded at runtime by `HelpPanel` — it tries `Readme.md`, `README.md`, `Readme,md` in order. Don't rename the file without updating that list.
- Spanish comments are scattered through the code; preserve them when editing nearby lines.
