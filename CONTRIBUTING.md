# Contributing to HDZero Programmer (Linux)

Thanks for considering a contribution. This file documents how the project
is structured for contributors and what patterns the maintainer expects.

## Reporting bugs

File issues at https://forgejo.squatch.lab/bmags/hdzero-programmer-linux/issues
using the **Bug report** template. Please include:

- Distro + version (`/etc/os-release` first 5 lines)
- Python version (`python3 --version`)
- `flashrom` version (`flashrom --version`)
- Whether you're running from the AppImage, a `pip install`, or a checkout
- The transcript file from `~/.local/state/hdzero-programmer/` (or
  `$XDG_STATE_HOME/hdzero-programmer/`) for the failed flash, if applicable
- For UI-related bugs, the output of running with `QT_LOGGING_RULES="*=true"`

**For security issues, do NOT file a public issue.** See
[`SECURITY.md`](SECURITY.md) for the disclosure path (when that file
lands per ticket #23 — until then, email the maintainer directly).

## Proposing changes

1. Fork the repo or create a branch (`git checkout -b feature/short-name`).
2. Run the dev setup (below) before your first commit.
3. Keep PRs focused — one logical change per PR. Mixing license cleanup
   with a new feature makes review harder than necessary.
4. Reference the issue number in your commit message (`Closes #N`) and the
   PR description.
5. Update tests, docs, and `CHANGELOG.md` as part of the same PR.

## Dev setup

```bash
git clone https://forgejo.squatch.lab/bmags/hdzero-programmer-linux.git
cd hdzero-programmer-linux

# Editable install with dev tools (pytest, ruff)
pip install --user -e ".[dev]"

# Pre-commit hooks (ruff on every commit)
pip install --user pre-commit
pre-commit install
```

Run the suite before pushing:

```bash
ruff check .
pytest
```

For UI changes, boot the GUI headlessly to confirm import + construction:

```bash
QT_QPA_PLATFORM=offscreen HDZERO_API_BASE=http://127.0.0.1:1 python3 -c "
from PyQt6.QtWidgets import QApplication
import sys, main
app = QApplication(sys.argv); w = main.MainWindow(); w.show()
print('boot ok')
"
```

If you have a CH341A and an HDZero VTX, real-hardware testing is welcome —
ticket #22 tracks the formal CI gate.

## Conventions

- **Commit messages**: imperative mood, lower-case subject, optional body.
  Reference issues with `Closes #N` / `Refs #N` so Forgejo auto-links.
- **Branch names**: `feature/short-name`, `fix/short-name`, `docs/short-name`.
  Prefix `batch-x-` for grouped low-risk PRs (see recent merge history).
- **Code style**: ruff with the project's `pyproject.toml` config. Some
  upstream-fork patterns (multi-statement lines, mixed imports) are
  deliberately preserved via E401/E701/E702/W293 ignores. New code should
  still aim for one statement per line.
- **Comments**: write WHY, not WHAT. The diff shows what changed; the
  comment should explain the reason a reader can't derive from the code.
- **ADRs**: non-trivial design decisions get an ADR under `docs/adr/`.
  Use the Nygard template in [`docs/adr/README.md`](docs/adr/README.md).
  Tick the "ADR added or referenced" item in the PR template when your
  change qualifies (criteria in the ADR README).

## Architecture overview

See [`CLAUDE.md`](CLAUDE.md) for the architecture document. It's named
that way because it doubles as the AI assistant's working context, but
the content is a normal architecture/onboarding doc — read it on day one.

## What's in scope

- Linux desktop GUI for flashing HDZero VTX firmware via CH341A.
- Bug fixes, test additions, documentation, accessibility improvements.
- New flashrom programmer support (e.g., FT232H) is welcome but warrants
  a discussion issue first — udev rule + worker subclass implications.

## What's out of scope (currently)

- Windows / macOS support. The upstream tool covers macOS; a Windows port
  would be a separate fork.
- Replacing PyQt6 with another GUI framework. PyQt6 is locked in by the
  upstream design and the AppImage build.
- Hardware programmers other than CH341A without a discussion issue first.

## License

By contributing, you agree your work is licensed under the project's
[MIT License](LICENSE), with the binary distribution implications
documented in [`LICENSE-NOTES.md`](LICENSE-NOTES.md).
