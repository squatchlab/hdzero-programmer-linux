# 6. Hard-coded `__version__` in `main.py` instead of `importlib.metadata`

Date: 2026-04-30

## Status

Accepted. Strongly tied to the AppImage distribution model — would
revisit if AppImage is ever dropped.

## Context

Idiomatic Python advice for "where does the version string live?" is:

```python
from importlib.metadata import version
__version__ = version("hdzero-programmer")
```

This works for any package installed with a `dist-info` directory
(pip, poetry, pdm, system packagers). The reader's first reaction to
seeing `__version__ = "0.2.0"` hard-coded in `main.py` is therefore
"why aren't we doing the idiomatic thing?"

The reason is the AppImage build (`packaging/build-appimage.sh`):

1. `python-appimage` produces a base AppImage containing a relocatable
   Python 3.12 plus the pip dependencies (PyQt6, requests).
2. The base AppImage is extracted, and our application source is
   **grafted** into
   `opt/python$PY_VER/lib/python$PY_VER/site-packages/_hdzero_app/`
   alongside the deps. The graft is a plain `cp`, not a pip install.
3. The squashfs is repackaged.

Because the graft skips pip, no `dist-info` directory exists for the
`hdzero-programmer` distribution inside the AppImage. At runtime,
`importlib.metadata.version("hdzero-programmer")` raises
`PackageNotFoundError`. This is reproducible by running the AppImage
with `--version`:

```
hdzero-programmer 0.2.0   # works because __version__ is hard-coded
```

vs. the hypothetical `importlib.metadata` form:

```
PackageNotFoundError: No package metadata was found for hdzero-programmer
```

`__version__` also feeds the per-flash transcript header
(`open_flash_log` writes the app version into the file's first line),
the GUI title bar, and the `--version` CLI flag. All three need a
working source of truth on every distribution channel.

## Decision

`main.__version__` is a string literal. `tests/test_version_consistency.py`
reads `pyproject.toml` and asserts that
`main.__version__ == cfg["project"]["version"]`. CI runs this test,
so a release that bumps one without the other fails before tag.

Bumping is documented in `CLAUDE.md`'s "Hard-coded version" gotcha:
update both `main.__version__` and `[project].version` in the same PR.

## Consequences

**Easier:**

- AppImage `--version` works. Pip-installed `hdzero-programmer`
  `--version` also works (the dist-info exists in that path, but we
  don't read it — we use the same hard-coded string everywhere).
- `open_flash_log` can write the version into the transcript header
  without conditional logic per distribution channel.
- The test enforces consistency, so the human cost of "two places"
  is bounded to "remember to update both, or CI yells."

**Harder:**

- One mechanical step on every release that a `dist-info`-driven
  approach wouldn't need.
- A reader new to the codebase wonders why we're not using
  `importlib.metadata`. This ADR is the answer; the gotcha in
  `CLAUDE.md` is the in-workflow reminder.
- If we ever drop the AppImage build (unlikely; it's the primary
  distribution channel), this ADR can be revisited and `__version__`
  collapsed to `importlib.metadata.version(__package__ or "hdzero-programmer")`.

## Alternatives considered

1. **`importlib.metadata.version("hdzero-programmer")` with a
   try/except fallback to `"0.0.0+unknown"` for AppImage runs.**
   Rejected: silent fallback hides bugs. A version string of
   `0.0.0+unknown` in a flash transcript is worse than a hard-coded
   one because it tells the user nothing about which build they were
   running when the chip got bricked.
2. **Inject `dist-info` into the AppImage during the graft step.**
   Rejected: would require teaching `build-appimage.sh` to fabricate
   a METADATA file, a RECORD file, and a name-version-info structure
   that pip would accept. Material complexity for no real win — the
   hard-coded string with a pinning test is simpler and equivalently
   correct.
3. **Read version from a `VERSION` file at the application root.**
   Rejected: same number of files to keep in sync (VERSION +
   pyproject), but adds a runtime file-read on every `--version`
   call and another asset to bundle into the AppImage.

## References

- `main.py:43` — `__version__` literal.
- `pyproject.toml` `[project].version` — second source of truth.
- `tests/test_version_consistency.py` — pin check.
- `app_logging.py:62` — version is written into the transcript header.
- `packaging/build-appimage.sh:75-103` — the graft step that bypasses
  pip and explains why dist-info isn't there.
