# 4. CH341A USB vendor:product IDs hardcoded, not configurable

Date: 2026-04-30

## Status

Accepted.

## Context

`udev_check.py` and the bundled `packaging/99-ch341a.rules` both encode
the CH341A USB IDs as constants:

```python
CH341A_VENDOR  = "1a86"
CH341A_PRODUCT = "5512"
```

Reviewers occasionally ask: why isn't this read from a config file,
parsed from the udev rule at runtime, or made user-overridable via an
env var?

The reasons aren't obvious from the code alone — the constants look
arbitrary to a reader who doesn't know that this app exists *only* to
flash HDZero VTXes via *this exact* programmer.

## Decision

The vendor and product IDs stay hardcoded in `udev_check.py`. The same
values are baked into the bundled udev rule. There is no env-var
override, no config file, no UI element that lets the user retarget the
presence-check at a different USB device.

## Consequences

**Easier:**

- The presence check (`ch341a_present()`) is one read of `idVendor` and
  `idProduct` per `/sys/bus/usb/devices/*` entry. Fast, side-effect-free,
  no config to validate.
- The udev rule is a single file users can `sudo install` without
  templating. If we made the IDs configurable, the rule would need to
  be generated per-user, which complicates the AppImage distribution
  story and the `packaging/install-udev.sh` helper.
- The "non-CH341A programmer" case is rare in this user base. HDZero
  Goggles ship with a CH341A in the official flash kit; community
  kits use the same chip because that's what flashrom's `ch341a_spi`
  driver targets.

**Harder:**

- Users with a *clone* programmer that exposes itself with a different
  VID/PID get a false-negative on the presence check. They can bypass
  it with `HDZERO_SKIP_CH341A_CHECK=1`, but the udev rule won't grant
  them non-root access — they'll fall back to pkexec.
- Future hardware revisions (e.g. CH341B with different IDs) would
  require a code change rather than a config update. Acceptable
  trade-off; flashrom itself would need updating in that case anyway.
- Adding support for additional programmers (FT232H, the audit's
  example) requires either expanding the constants to a list or
  refactoring the check to accept multiple (vendor, product) pairs.
  The CONTRIBUTING.md scope statement already calls this out — new
  programmer support warrants a discussion issue first.

## Alternatives considered

1. **Env-var override** (`HDZERO_PROGRAMMER_VID` /
   `HDZERO_PROGRAMMER_PID`). Rejected for now: zero real demand, and
   the udev rule would still hardcode 1a86:5512 — so the override would
   only affect the presence-check half of the path, leaving the
   permissions half broken and confusing to debug.
2. **Read the IDs out of the udev rule at runtime.** Rejected: the
   rule isn't always installed (that's the point of the install
   banner), and parsing udev syntax just to learn two constants is
   over-engineered.
3. **Config file under `~/.config/hdzero-programmer/`.** Rejected for
   now: same critique as the env-var option, plus it adds a config
   format to support and a config-discovery code path. If FT232H
   support lands, revisit this ADR.

## References

- `udev_check.py:14-15` — the constants.
- `packaging/99-ch341a.rules` — the rule that grants
  `uaccess`/`plugdev` access to the same VID:PID.
- `CONTRIBUTING.md` "What's in scope" — non-CH341A programmer support
  requires a discussion issue.
- The "Set `HDZERO_SKIP_CH341A_CHECK=1`" gotcha in `CLAUDE.md` for
  users running clone programmers.
