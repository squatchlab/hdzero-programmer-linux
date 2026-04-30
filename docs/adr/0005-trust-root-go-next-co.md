# 5. Firmware trust root is hdzero.go-next.co (provisional)

Date: 2026-04-30

## Status

**Accepted, but explicitly provisional.** This ADR captures *what is
true today* and *why no better alternative was workable at fork time*.
It will be **superseded** when tickets `#19` (firmware authenticity
check) and `#20` (trust-root hardening) land.

## Context

`internet_panel.py` resolves the firmware index API base from:

```
HDZERO_API_BASE  (env override)
└── default: https://hdzero.go-next.co
```

The default points at a third-party host the maintainer of this fork
does **not** control. The host returns a JSON manifest of devices and
firmwares; the GUI downloads the selected `.bin` and runs the safe-flash
chain (ADR-0001) against it. **No authenticity check** is performed
between download and flash.

This is the single largest open security issue in the project, captured
verbatim in the 2026-04-29 audit and in tickets `#19`, `#20`. An
acquirer's diligence team treats it as a class-action waiting to be
filed. The audit's recommendation — close `#19/#20/#21` before the next
minor release — is the maintainer's plan.

So why did the fork ship with this trust model in the first place? And
why hasn't it changed yet?

## Decision

For v0.2.x, the firmware index trust root remains
`https://hdzero.go-next.co` with no authenticity verification. This is
the upstream macOS fork's behaviour and the only API this fork knows
how to talk to — the project does not run its own firmware index.

The decision is provisional in three senses:

1. **The default URL** can be replaced by the user via
   `HDZERO_API_BASE`. A user who runs their own mirror or pins to a
   different URL can do so without code changes.
2. **The authenticity gap** (no signature on the firmware blob) is a
   hard blocker on the next minor release. ADR replacement sequencing:
   when `#19` ships, this ADR moves to `Status: Superseded by ADR-NNNN`.
3. **The trust-root identity** (who controls `go-next.co`) is itself
   tracked in `#20`. SECURITY.md notes the gap publicly.

Until `#19` lands, the safest practice for a security-conscious user
is the **Local tab** path: download the `.bin` out-of-band (e.g. from
the official HDZero firmware repository on GitHub), verify it however
they choose, then flash via Local rather than Internet.

## Consequences

**Easier:**

- The fork is operationally compatible with the macOS upstream and the
  community's existing firmware-distribution practices. Users who
  already trust `go-next.co` for the macOS tool aren't asked to change
  workflow.
- No key custody to maintain. Adding signed firmware (the `#19` plan)
  introduces a public verification key in the application binary AND a
  signing key on whoever runs the firmware index — neither has been
  designed yet.

**Harder:**

- A compromise of `go-next.co` (or DNS, or a CA, or the maintainer's
  TLS termination) means tampered firmware reaches `flashrom -w` with
  no countermeasure. The audit's verdict (`docs/audits/2026-04-29.md`)
  treats this as a `BLOCKER` for acquisition.
- Documentation has to keep the trust gap loud. SECURITY.md lists `#19`
  / `#20` under Known Open Security Issues; README does not (yet)
  document the Local-tab safer-path advice but should before the next
  minor release.
- A user who flips `HDZERO_API_BASE` to an attacker-controlled mirror
  via a `.desktop` file or shell alias is *also* a path to tampered
  firmware. The signed-firmware design must remain effective regardless
  of the URL — i.e. the verification key must be embedded in the app
  and not derived from the URL or the manifest itself.

## Alternatives considered

1. **Block flashing entirely until `#19` ships.** Rejected: the tool
   becomes useless for v0.2.x, but the underlying risk is no different
   from the macOS upstream that users have been running for two years.
   Documenting the gap publicly is more honest than gating a
   community fork on a security feature its upstream doesn't have.
2. **Ship a hardcoded list of known-good firmware SHA-256 hashes.**
   Rejected: doesn't scale (every release needs a code change), and
   the list itself becomes a trust root the maintainer has to defend
   manually. Signed manifests (`#19`) are strictly better.
3. **Run our own firmware mirror.** Rejected: same trust model
   problem, just under a different domain — and would also fragment
   the user base from the upstream macOS distribution.

## References

- `internet_panel.py` — `API_BASE` resolution.
- `SECURITY.md` Known Open Security Issues — public-facing version
  of this gap.
- `docs/audits/2026-04-29.md` — audit verdict and remediation timeline.
- Tickets `#19`, `#20`, `#21` — block the next minor release.
