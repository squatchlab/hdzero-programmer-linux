# Trademark exposure: "HDZero"

Status: **OPEN — research in progress.** The audit (`docs/audits/2026-04-29.md`)
flagged this as a MINOR ACQUISITION concern. This file captures the
current state, the open questions, and the contingency plan so a buyer's
diligence team finds an answer rather than a gap.

## What "HDZero" refers to

"HDZero" is the product name of Divimath Inc.'s digital FPV video
transmitter line. The maintainer of this fork is not affiliated with
Divimath; the project exists because the upstream macOS tool by Gunther
Votteler shipped under MIT and the Linux community wanted a port.

## Where the brand appears in this repo

- `pyproject.toml` — `name = "hdzero-programmer"`, plus the `keywords`
  list, the `Homepage` URL, and the `gui-scripts` entry point.
- `main.py:49` — `APP_TITLE = "HDZero Programmer Tool – by Gunther_FPV"`,
  `APP_HEADER_TITLE = "HDZero Programmer (Linux)"`.
- `README.md` — "HDZero Programmer (Linux)" headline, "HDZero VTX",
  numerous mentions in usage instructions.
- `app_settings.py` — `SETTINGS_APP = "hdzero-programmer-linux"` (the
  reverse-DNS scope's `lab.squatch / hdzero-programmer-linux`).
- AppImage filename: `dist/HDZeroProgrammer-x86_64.AppImage`.
- Forgejo repository slug: `bmags/hdzero-programmer-linux`.

## Open research questions

These are listed so a future contributor (or the maintainer when time
opens up) can pick up where the audit left off. None blocks shipping —
the project has been operating under this name for the duration of the
upstream macOS fork's existence — but each is part of the answer to
"is this name choice durable?"

### 1. USPTO TESS lookup

[`tmsearch.uspto.gov`](https://tmsearch.uspto.gov) for the literal mark
"HDZERO" or "HD ZERO" in the goods/services classes covering radio
transmitting apparatus (Class 9) and broadcasting (Class 38).

Outcome to capture here:
- Registration number(s), if any.
- Owner of record (presumably Divimath; confirm).
- Goods/services scope.
- Live vs. dead status.

### 2. Divimath trademark policy

Many hardware vendors publish a *trademark usage policy* for third-party
tools, drivers, and educational material. The policy typically permits
"factual references" (e.g., "tool for flashing HDZero VTXes") and bars
implied endorsement.

Outcome to capture here: link to the policy, OR the result of contacting
Divimath via their published support / legal channel.

### 3. Maintainer's risk tolerance

The audit's filing recommendation was `MINOR` because:
- The upstream macOS tool has used the name for ~2 years without issue.
- The brand usage here is *factual reference* — the tool exists *to
  flash HDZero VTXes*; it isn't claiming to be an HDZero-branded
  product.
- The README and `LICENSE-NOTES.md` make the unaffiliated status clear.

A risk-averse maintainer (or one preparing for acquisition) may still
want to seek written clarification from Divimath before the next
version bump.

## Contingency: name pivot

If the answer to (1) or (2) above is restrictive — i.e., Divimath asserts
that any use of "HDZero" in a tool name requires a license — the
project can pivot to a generic name:

- New name candidate: **`vtx-programmer-linux`** (descriptive, no brand).
- `pyproject.toml [project].name`: rename to `vtx-programmer`.
- AppImage filename: `dist/VtxProgrammer-x86_64.AppImage`.
- Repo slug: rename via Forgejo (auto-redirects from old URL for ~30 days
  on Forgejo defaults; check current behaviour at rename time).
- README headline + APP_TITLE / APP_HEADER_TITLE: update.
- `app_settings.py`: `SETTINGS_APP = "vtx-programmer-linux"`. The
  existing `migrate_settings_once()` already handles legacy-scope
  migration (currently `HDZero/Programmer` → `lab.squatch /
  hdzero-programmer-linux`), so a second migration to a `vtx` scope is
  the same shape.
- README "How it works" section retains *factual references* to "HDZero
  VTX" (cannot be avoided — the tool exists to flash that hardware) but
  the *project's own* name no longer collides.

The rename is mechanical (one PR, ~10 file edits) and reversible.

## Disposition

- **Today:** the name stays. We document the gap rather than pretend it
  doesn't exist.
- **Acquisition diligence:** point this file at the diligence team.
  Honest "open question with a contingency plan" beats silent ambiguity.
- **Cease-and-desist trigger:** execute the contingency plan above
  (one PR), publish a CHANGELOG entry referencing the rename, and
  announce in the release notes for the new version.

## References

- `LICENSE-NOTES.md` — fork attribution + GPL-binary disclosure.
- `README.md` License section — credits Divimath's product implicitly via
  Gunther Votteler's upstream tool, not via direct affiliation.
- ADR-0007 (`docs/adr/0007-mit-source-gpl-binary.md`) — distribution
  position. Independent of the trademark question but referenced
  together by acquisition reviewers.
- Audit ticket `#43` — the source filing.
