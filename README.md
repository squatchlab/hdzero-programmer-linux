# HDZero Programmer (Linux)

A PyQt6 desktop GUI for flashing HDZero VTX firmware on Linux. Wraps the
`flashrom` CLI driving a CH341A USB SPI programmer against the W25Q80 chip
on HDZero video transmitters.

## Status

**Linux port in progress.** The code currently in this repository is a direct
import of the upstream macOS tool and has not yet been adapted for Linux —
notably `flash_ops.run_admin()` shells out to `osascript`, which does not
exist on Linux. Expect this to be replaced with `pkexec` (or `sudo` fallback)
in the next pass.

## Credits

This project is a Linux port of the
[HDZero Programmer Tool for Mac](https://github.com/gvotteler) by
**Gunther Votteler** (Gunther_FPV).

- Original author: Gunther Votteler — [@gunther_fpv](https://www.instagram.com/gunther_fpv) ·
  [YouTube: FPVecinos](https://www.youtube.com/@FPVecinos)
- Original license: MIT (see `LICENSE`)

All credit for the original design, UI, and flashing pipeline belongs to
Gunther. This fork only adapts it for Linux.

## Requirements (Linux)

- Python 3.10+
- PyQt6 (`pip install PyQt6`)
- `requests` (`pip install requests`)
- `flashrom` (`sudo apt install flashrom` / `sudo dnf install flashrom` /
  `sudo pacman -S flashrom`)
- A CH341A USB SPI programmer + a wired connection to the HDZero VTX's
  W25Q80 flash chip
- A polkit agent (for the `pkexec` GUI password prompt) — present by default
  on most desktop distros

## Run

```bash
pip install PyQt6 requests
python3 main.py
```

Override the firmware index API base if needed:

```bash
HDZERO_API_BASE=https://your-mirror.example python3 main.py
```

## Skip the password prompt (optional, recommended)

By default each flash and backup triggers a polkit (`pkexec`) password
prompt because `flashrom` needs raw USB access to the CH341A. You can
grant that access to your user via a udev rule and skip the prompt
entirely:

```bash
sudo cp packaging/99-ch341a.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# unplug and replug the CH341A
```

Then launch the app with the bypass env var set:

```bash
HDZERO_NO_ESCALATE=1 python3 main.py
```

The rule grants access to the local-seat user (`uaccess`) and the
`plugdev` group. Without the rule (or without the env var), the app
falls back to the default `pkexec → sudo` escalation chain.

## Desktop integration (optional)

Install a launcher entry into your application menu and a 256×256 icon
into the hicolor icon theme:

```bash
./packaging/install-desktop.sh                # per-user (~/.local/share)
sudo PREFIX=/usr ./packaging/install-desktop.sh   # system-wide
```

Until the `hdzero-programmer` console entrypoint ships (issue #7), edit
the installed `.desktop` file's `Exec=` line to point at
`python3 /absolute/path/to/main.py` so the menu launcher works.

## Usage

1. **Internet tab** — pick a device from the dropdown, pick a firmware
   version, click **FLASH**. The app downloads the `.bin`, pads it to 1 MiB
   (W25Q80 size), and writes it via `flashrom -p ch341a_spi -w`.
2. **Local tab** — browse to a `.bin` you already have, optionally **BACKUP**
   the current chip contents to `~/HDZero_backup_<timestamp>.bin` first,
   then **FLASH**.
3. **Help tab** — shows this README at runtime.

Firmware files larger than 64 KB are rejected by the UI as invalid for
HDZero hardware.

## How it works

Three Python modules, one Qt event loop, blocking I/O isolated to QThread
workers:

- `main.py` — `MainWindow` owns the three tabs and routes signals.
- `internet_panel.py` — fetches device + firmware lists from
  `HDZERO_API_BASE`, downloads selected firmware to a temp file.
- `flash_ops.py` — `flashrom` discovery, 1 MiB padding, and the
  `FlashWorker` / `BackupWorker` QThreads that invoke `flashrom` with
  privilege escalation.

See `CLAUDE.md` for deeper architecture notes.

## License

MIT — see [`LICENSE`](LICENSE). Copyright remains with the original
author Gunther Votteler (2025); this Linux port preserves the upstream
license per its terms.

## Disclaimer

Flashing firmware can brick hardware. Always **BACKUP** before **FLASH**.
Use at your own risk.
