# Security Policy

## Reporting a Vulnerability

If you believe you have found a security vulnerability in
`hdzero-programmer-linux` — particularly anything affecting the
firmware-flash path on real HDZero hardware — please report it
**privately** rather than opening a public Forgejo issue.

**Contact:** [bryan.magalski@gmail.com](mailto:bryan.magalski@gmail.com)

Encrypt sensitive details where possible. Once an AppImage signing key is
in place (tracked in `#21`), this section will publish the GPG fingerprint
that signs both releases and incoming reports.

If the Forgejo instance hosting this repository supports private
vulnerability reporting, that channel is also acceptable.

## What to Include

- The affected version (`hdzero-programmer --version`).
- A short description of the issue and its impact (e.g., "tampered
  firmware can reach `flashrom -w` because …").
- Steps to reproduce, or a proof-of-concept if you have one.
- Whether the issue is already public anywhere, and any disclosure
  timeline you intend to follow.

## What to Expect

- **Acknowledgement:** within **5 business days** of report receipt.
- **Initial triage + severity assessment:** within **10 business days**.
- **Fix or mitigation timeline:** shared after triage. Standard
  coordinated-disclosure window is **90 days** from the acknowledgement
  date; we will negotiate longer if a fix requires upstream coordination
  (`flashrom`, the firmware index API, or the Forgejo runner).
- **Credit:** if you wish to be credited in the release notes for the
  fix, say so in your initial report. Default is anonymous unless asked.

## Supported Versions

Only the most recent tagged release receives security fixes. Older
versions are best-effort. The current release is published under
[`Releases`](https://forgejo.squatch.lab/bmags/hdzero-programmer-linux/releases)
with `SHA256SUMS` attached; signed-release support is tracked in `#21`.

| Version | Supported          |
| ------- | ------------------ |
| `0.2.x` | :white_check_mark: |
| `< 0.2` | :x:                |

## Scope

In scope:

- The packaged AppImage and its build pipeline (`packaging/`,
  `.forgejo/workflows/`).
- The Python source modules (`main.py`, `internet_panel.py`,
  `flash_ops.py`, `udev_check.py`, `app_logging.py`).
- The bundled udev rule (`packaging/99-ch341a.rules`) and install
  helpers (`packaging/install-udev.sh`).
- Default trust assumptions about the firmware index API base
  (`https://hdzero.go-next.co`, override `HDZERO_API_BASE`); see also
  `#19`, `#20`.

Out of scope (report upstream instead):

- `flashrom` itself ([flashrom.org](https://www.flashrom.org/)).
- PyQt6 / Qt 6.
- The original macOS upstream
  ([github.com/gvotteler/HDZero-Programmer-Tool-Mac](https://github.com/gvotteler/HDZero-Programmer-Tool-Mac))
  unless the issue is also reachable from this fork.

## Known Open Security Issues

Tracked publicly because the audit that surfaced them is also public:

- `#19` — firmware fetched over the network is flashed to hardware with
  no authenticity check.
- `#20` — trust root is a third-party host (`hdzero.go-next.co`) outside
  the maintainer's control.
- `#21` — AppImage releases ship `SHA256SUMS` but no GPG/sigstore
  signature.

Closing all three is a precondition for the next minor release.
