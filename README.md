# HDZero Programmer (Linux)

A PyQt6 desktop GUI for flashing HDZero VTX firmware on Linux. Wraps the
`flashrom` CLI driving a CH341A USB SPI programmer against the W25Q80 chip
on HDZero video transmitters.

## Status

Linux port is functional. `flash_ops.run_admin()` uses `pkexec` with
`sudo -A` / `sudo -n` fallbacks, the build system produces a self-contained
AppImage, and CI runs a headless smoke test plus the AppImage build on each
push. The default flash pipeline now reads the chip first (rollback image),
writes, then re-verifies — all in a single privilege prompt.

## Credits

This project is a Linux port of the
[HDZero Programmer Tool for Mac](https://github.com/gvotteler/HDZero-Programmer-Tool-Mac)
by **Gunther Votteler** (Gunther_FPV).

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

Install via pip (recommended):

```bash
pip install --user .
hdzero-programmer
```

Or run directly out of a checkout:

```bash
pip install --user PyQt6 requests
python3 main.py
```

Override the firmware index API base if needed:

```bash
HDZERO_API_BASE=https://your-mirror.example hdzero-programmer
```

## Skip the password prompt (optional, recommended)

By default each flash and backup triggers a polkit (`pkexec`) password
prompt because `flashrom` needs raw USB access to the CH341A. The app
detects when this rule is missing and shows a banner with the exact
install command on launch.

Run the bundled helper or the manual sequence:

```bash
./packaging/install-udev.sh
# or, equivalently:
sudo install -m 0644 packaging/99-ch341a.rules /etc/udev/rules.d/99-ch341a.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# unplug and replug the CH341A
```

Then launch with the bypass env var set so the app skips `pkexec` entirely:

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

The `.desktop` `Exec=` line points at the `hdzero-programmer` console
script installed by `pip install`. If you run from a checkout without
installing, edit the installed `.desktop` file's `Exec=` line to
`python3 /absolute/path/to/main.py`.

## Build a self-contained AppImage (optional)

For distribution to users without a Python toolchain, build a single-file
AppImage that bundles a relocatable Python 3.12, PyQt6, `requests`, and
the application source:

```bash
pipx install python-appimage
./packaging/build-appimage.sh
# → dist/HDZeroProgrammer-x86_64.AppImage
```

The resulting AppImage still requires `flashrom` on the host (the AppImage
shells out to it) and the same CH341A access setup described above (udev
rule or polkit agent).

## Usage

1. **Internet tab** — pick a device from the dropdown, pick a firmware
   version, click **FLASH**. The app downloads the `.bin`, pads it to 1 MiB
   (W25Q80 size), and runs the safe-flash pipeline below.
2. **Local tab** — browse to a `.bin` you already have, optionally **BACKUP**
   the current chip contents to
   `~/.local/state/hdzero-programmer/backups/HDZero_backup_<timestamp>.bin`
   on demand, or just hit **FLASH** to run the safe-flash pipeline.
3. **Help tab** — shows this README at runtime.

Each tab has a **Backup chip before flashing** checkbox (on by default).
With it on, FLASH executes a single chained sequence under one privilege
prompt:

1. read the current chip to
   `~/.local/state/hdzero-programmer/backups/HDZero_pre-flash_<timestamp>.bin`
   (rollback image),
2. write the padded firmware,
3. re-verify the chip against the padded image.

If any step fails the chain short-circuits, leaving the rollback image
intact. Uncheck the box to skip step 1 (write + verify only).

Firmware files larger than 64 KB are rejected by the UI as invalid for
HDZero hardware.

Each flash and backup also writes a real-time transcript to
`~/.local/state/hdzero-programmer/flash-<timestamp>.log` (or
`backup-<timestamp>.log`). Useful when something goes wrong on the
flashrom side — the file captures the full pipeline including phase
transitions and the final OK/FAIL summary even if the GUI is closed.
Override the directory with `HDZERO_STATE_DIR=/path/to/dir`.

Chip backups (manual + pre-flash auto) land under
`~/.local/state/hdzero-programmer/backups/`. Override with
`HDZERO_BACKUP_DIR=/path/to/dir` if you prefer a different location.

> **Migration note:** versions ≤0.2.0 dropped backup files at
> `~/HDZero_*.bin` (in the home directory root). Existing files are
> not auto-moved — `mv ~/HDZero_*.bin ~/.local/state/hdzero-programmer/backups/`
> if you want them in the new location.

## Architecture

See [`docs/adr/`](docs/adr/) for the architecture decision records covering
the safe-flash chain, the 1 MiB pad invariant, and other non-trivial design
choices. [`CLAUDE.md`](CLAUDE.md) is the day-one onboarding doc.

## How it works

Six Python modules, one Qt event loop, blocking I/O isolated to QThread
workers:

- `main.py` — `MainWindow` owns the three tabs and routes signals.
- `internet_panel.py` — fetches device + firmware lists from
  `HDZERO_API_BASE`, downloads selected firmware to a temp file.
- `flash_ops.py` — `flashrom` discovery, 1 MiB padding, and the
  `FlashWorker` / `BackupWorker` QThreads that invoke `flashrom` with
  privilege escalation.
- `udev_check.py` — detects whether `99-ch341a.rules` is installed and
  whether the CH341A is currently attached; drives the first-run banner.
- `app_logging.py` — resolves the per-flash transcript dir under
  `$XDG_STATE_HOME/hdzero-programmer/` and opens line-buffered log files.
- `app_settings.py` — `QSettings` reverse-DNS scope
  (`lab.squatch / hdzero-programmer-linux`) plus a one-shot migration
  from the legacy `HDZero/Programmer` scope.

See `CLAUDE.md` for deeper architecture notes.

## CI

`.forgejo/workflows/ci.yml` runs on every push and pull request:

- **smoke** — `ruff check`, `mypy` (strict on the safety-critical
  modules; typed signatures on UI plumbing), `gitleaks`, `py_compile`,
  `pytest --cov` against `tests/`, and a headless `MainWindow` boot
  under `QT_QPA_PLATFORM=offscreen`.
- **appimage** — builds the AppImage and uploads it as a workflow
  artifact (downloadable from the run page). Smoke-execs `--version`
  and `--check-rule` against the built image.

Requires a registered Forgejo Actions runner labeled `ubuntu-22.04`.

## Development

```bash
pip install --user -e ".[dev]"   # pytest + ruff
pip install --user pre-commit && pre-commit install
pytest                           # 64 tests, mostly hardware-mock
ruff check .                     # lint
```

`.pre-commit-config.yaml` runs `ruff` on every commit. CI re-runs the
same checks against the full tree, so a missed hook still gets caught.

## Releases

Pushing a `v*` tag triggers `.forgejo/workflows/release.yml`, which builds
the AppImage, generates `SHA256SUMS`, creates a Forgejo release, and
uploads both files as release assets:

```bash
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

Verify a downloaded AppImage:

```bash
sha256sum -c SHA256SUMS
```

## License

MIT — see [`LICENSE`](LICENSE). Copyright remains with the original author
Gunther Votteler (2025); the Linux port preserves the upstream license per
its terms and adds a fork copyright line for contributions made under it.

The AppImage build bundles PyQt6 (GPL-v3) and is therefore distributed under
GPL-v3 terms even though the source itself is MIT. See
[`LICENSE-NOTES.md`](LICENSE-NOTES.md) for the full source-vs-binary breakdown
and redistribution notes.

## Reporting a Vulnerability

Found something security-relevant? Please report it privately per
[`SECURITY.md`](SECURITY.md) rather than filing a public issue.

## Disclaimer

Flashing firmware can brick hardware. Always **BACKUP** before **FLASH**.
Use at your own risk.
