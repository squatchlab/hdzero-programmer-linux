# License Notes

The HDZero Programmer (Linux) project source code is distributed under the
[MIT License](LICENSE). The notes below clarify how that license interacts
with the project's runtime dependencies and distribution artifacts, since
those interactions matter for redistribution and downstream packaging.

## Source vs. binary distribution

| Artifact | License terms |
|---|---|
| Source code in this repository (`*.py`, `pyproject.toml`, `tests/`, `packaging/`, etc.) | MIT (see `LICENSE`). |
| The `dist/HDZeroProgrammer-x86_64.AppImage` distributed via Forgejo / Codeberg releases | GPL-v3 by virtue of bundling PyQt6. See "PyQt6 dependency" below. |
| `.desktop` entries, icons, udev rule, `install-*.sh` scripts shipped under `packaging/` | MIT (same as source). |

The MIT-licensed source remains MIT-licensed. The AppImage as a combined
distribution work inherits the GPL-v3 obligations of the bundled PyQt6
runtime — anyone redistributing the AppImage must respect those terms.

## PyQt6 dependency

PyQt6 is dual-licensed by Riverbank Computing under:

- **GNU GPL v3**, OR
- **A commercial Riverbank License** for use cases incompatible with GPL v3.

This project does not hold the commercial license. Therefore, when the
project is distributed *as a binary that includes PyQt6* (the AppImage), the
combined work is distributed under GPL-v3 terms. MIT is one-way compatible
with GPL — MIT-licensed code can be incorporated into a GPL distribution
without re-licensing the source — so the source remains MIT and only the
specific binary artifact is GPL-v3-bound.

If you want to redistribute this project's source under MIT, you can do so
freely. If you want to redistribute the AppImage, you must comply with
GPL-v3 (provide source, preserve license notices, etc. — see
https://www.gnu.org/licenses/gpl-3.0.html).

If you want to ship a non-GPL binary, you have two options:

1. Acquire a commercial PyQt6 license from Riverbank Computing and rebuild
   the AppImage; or
2. Replace PyQt6 with a non-copyleft Qt binding (PySide6 is LGPL, which has
   different but less restrictive terms).

Neither path is currently exercised by this project.

## Upstream attribution

This project is a Linux port of the [HDZero Programmer Tool for Mac]
(https://github.com/gvotteler/HDZero-Programmer-Tool-Mac) by Gunther
Votteler, originally distributed under MIT. The original copyright and
permission notice is preserved verbatim in `LICENSE`.

## Trademark

"HDZero" is a product name owned by Divimath. This project is not
affiliated with, endorsed by, or sponsored by Divimath. The brand name
appears here only to identify the hardware target.

See ticket `#43` for the open trademark-policy investigation; the project
may rename to a non-brand identifier if the policy is restrictive.

## Contact

For license questions about distribution scenarios not covered above,
see [`SECURITY.md`](SECURITY.md) for the maintainer contact path (when
that file lands per ticket `#23`).
