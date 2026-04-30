# Architecture Decision Records

This directory tracks the non-trivial design decisions of the project.
Each ADR follows Michael Nygard's template:

```
# N. Short title

Date: YYYY-MM-DD

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-NNNN

## Context
What's the situation that's forcing a decision?

## Decision
What's the decision we made?

## Consequences
What becomes easier? What becomes harder?
```

## Index

- [ADR-0001 — Single-prompt sh -c chain for safe-flash pipeline](0001-single-prompt-flash-chain.md)
- [ADR-0002 — 1 MiB padded image with 0xFF for W25Q80 writes](0002-1mib-pad-invariant.md)
- [ADR-0003 — pkexec/sudo escalation over a setuid helper](0003-pkexec-over-setuid.md)
- [ADR-0004 — CH341A USB vendor:product hardcoded, not configurable](0004-ch341a-vendor-product-hardcoded.md)
- [ADR-0005 — Firmware trust root is hdzero.go-next.co (provisional)](0005-trust-root-go-next-co.md)
- [ADR-0006 — Hard-coded `__version__` in `main.py`](0006-hardcoded-version.md)
- [ADR-0007 — MIT source / GPL-v3 binary distribution position](0007-mit-source-gpl-binary.md)

## When to write a new ADR

A decision warrants an ADR when:

- It's not derivable from reading the code
- A reasonable engineer would want to know *why* in addition to *what*
- Changing the decision would have non-trivial blast radius

The PR template (`.forgejo/PULL_REQUEST_TEMPLATE.md`) has an "ADR
added or referenced" checkbox in the Test plan section; tick it when
the PR introduces a non-trivial decision.
