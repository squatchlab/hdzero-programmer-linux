# 7. MIT source / GPL-v3 binary distribution position

Date: 2026-04-30

## Status

Accepted. Cross-references `LICENSE-NOTES.md` for the full legal text.

## Context

The application source (Python modules, packaging scripts, docs) is
licensed MIT — inherited from Gunther Votteler's macOS upstream and
preserved in this fork. MIT is a permissive license with minimal
redistribution constraints.

The application *binary* — the AppImage produced by
`packaging/build-appimage.sh` — bundles **PyQt6**, which is licensed
**GPL-v3**. Riverbank Computing also offers PyQt6 under a commercial
license, but this project ships under the GPL-v3 path.

GPL-v3 is *strongly* copyleft: a redistributed binary that includes a
GPL-v3 work must itself be distributed under GPL-v3 terms, with
corresponding source available to recipients. This is independent of
what license the *non-PyQt6* parts of the binary carry.

A naive reading of "the source is MIT" leads a redistributor to treat
the AppImage as MIT, which is wrong. Acquisition diligence will spot
this immediately; the audit (`docs/audits/2026-04-29.md`) flagged the
need for an explicit `LICENSE-NOTES.md` because of it.

The project also can't simply switch the source to GPL-v3 — the
upstream copyright is held by Gunther Votteler under MIT, and a
unilateral relicense would either require his agreement or constitute
a fork relicense that contributors would have to opt into.

## Decision

The project takes the dual position:

- **Source code** is distributed under **MIT** (the upstream license,
  honoured per its terms).
- **The AppImage binary** is distributed under **GPL-v3** because of
  the bundled PyQt6 dependency.
- `LICENSE` contains the verbatim MIT text plus a SPDX header and a
  dual copyright line (upstream maintainer + this fork's contributions).
- `LICENSE-NOTES.md` documents the source-vs-binary split, the GPL-v3
  flow-down from PyQt6, and the redistribution obligations on whoever
  republishes the AppImage.
- `README.md` summarizes the position in its License section and
  links to `LICENSE-NOTES.md`.
- The AppImage build (`packaging/build-appimage.sh`) bundles `LICENSE`
  and `LICENSE-NOTES.md` alongside the source so a recipient of the
  binary has the legal text available locally.

A redistributor of the AppImage who triggers the GPL-v3 obligations
must make the *corresponding source* of the AppImage's contents
available to their recipients. The Forgejo repository at
`https://forgejo.squatch.lab/bmags/hdzero-programmer-linux` is one such
source-availability path; redistributors must verify a permanent URL
or ship source archives themselves if they cannot rely on the public
repo's availability.

## Consequences

**Easier:**

- The *source* is reusable by anyone under MIT. Patches, ports, and
  derivative source-form distributions don't have to take on the GPL.
- The *binary* answer is unambiguous. "AppImage redistribution = GPL-v3
  obligations" is a one-line story; users don't need a lawyer.
- Acquisition diligence sees a documented position rather than an
  implicit one. `LICENSE-NOTES.md` is the artifact a buyer's legal
  team will read.

**Harder:**

- Anyone forking or repackaging the AppImage must understand both
  licenses to do so legally. README + LICENSE-NOTES.md are the
  educational layer; a contributor who skips the docs may ship a
  GPL-v3-violating binary by mistake.
- A future replacement of PyQt6 with a non-copyleft Qt binding
  (PySide6 is LGPL-v3, which is weaker copyleft) would shift this
  position. Such a swap would warrant a new ADR superseding this one.
- The AppImage binary's source-availability obligation requires the
  Forgejo (or a mirror) to remain reachable. If the project ever
  moves repos, redistributors keyed off the old URL get stuck —
  which is one reason `pyproject.toml`'s `[project.urls]` Homepage
  field is the canonical source-availability URL.

## Alternatives considered

1. **Relicense source to GPL-v3.** Rejected: cannot be done
   unilaterally. Upstream copyright is MIT and we honour it. A
   contributor-only relicense of *this fork's* contributions would
   produce a confusing dual-licensed source tree that nobody benefits
   from.
2. **Switch to PySide6 (LGPL).** Considered but deferred. PySide6 has
   subtle API differences that would require porting work, and the
   upstream macOS fork uses PyQt6 — diverging would make merging
   future upstream changes harder. Worth revisiting if the audit's
   licensing concerns ever escalate to a hard blocker.
3. **Document MIT and ignore the GPL implications.** Rejected.
   Audits read the bundled binaries; failure to document creates a
   compliance gap that is much worse than acknowledging the dual
   position up front.

## References

- `LICENSE` — MIT text + SPDX + dual copyright.
- `LICENSE-NOTES.md` — full source-vs-binary breakdown.
- `README.md` — License section summarizes this ADR's outcome for
  end users.
- `packaging/build-appimage.sh` — bundles `LICENSE` and
  `LICENSE-NOTES.md` into the AppImage.
- Audit `docs/audits/2026-04-29.md` — flagged the documentation gap
  that motivated this ADR.
