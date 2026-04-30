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

## When to write a new ADR

A decision warrants an ADR when:

- It's not derivable from reading the code
- A reasonable engineer would want to know *why* in addition to *what*
- Changing the decision would have non-trivial blast radius

Examples that should become ADRs (tracked under `#31`):
- Why `pkexec` over a setuid wrapper
- Why CH341A vendor:product hardcoded vs configurable
- Why the trust root is `hdzero.go-next.co` (or whatever resolves it,
  pending #20)
- Why hard-coded `__version__` instead of `importlib.metadata`
- Why MIT-source-/-GPL-binary distribution position (cross-refs
  LICENSE-NOTES.md)
