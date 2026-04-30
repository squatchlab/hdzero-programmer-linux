# 3. pkexec/sudo escalation over a setuid helper

Date: 2026-04-30

## Status

Accepted. Cross-references ADR-0001 (the chain that the escalation wraps).

## Context

`flashrom` driving the CH341A needs raw USB access, which on a normal
Linux desktop means root. Three escalation models were on the table:

1. **Per-invocation escalation** through `pkexec` (polkit GUI prompt),
   falling back to `sudo -A` (askpass) or non-interactive `sudo -n`.
2. **A small setuid helper** binary shipped alongside the AppImage that
   wraps `flashrom -p ch341a_spi …` and is the only path the GUI takes.
3. **A long-running root daemon** with a Unix socket protocol the GUI
   speaks to.

The audit explicitly asked why we picked option 1 — engineers coming
from server contexts often default to option 2 because "sudo prompts
are annoying."

## Decision

The application does not ship a setuid helper, a daemon, or any binary
that runs with elevated privileges by default. Privilege escalation is
per-flashrom-invocation, performed through whichever mechanism the host
provides:

1. `pkexec` (polkit GUI prompt) — preferred; it works without a TTY,
   integrates with the desktop's session, and fails closed if no agent
   is running.
2. `sudo -A` — used only when `SUDO_ASKPASS` is set; lets a user with a
   custom askpass program drive sudo from a desktop session.
3. `sudo -n` — non-interactive; the last-resort path that succeeds only
   if the user has a recent sudo timestamp or NOPASSWD configured.

The single-prompt chain (ADR-0001) keeps the UX cost of this choice down
to one prompt per flash. The udev-rule path
(`packaging/99-ch341a.rules` + `HDZERO_NO_ESCALATE=1`) eliminates the
prompt entirely for users who want zero friction.

## Consequences

**Easier:**

- No persistent attack surface. A vulnerability in the GUI cannot grant
  root access outside the moment a flashrom invocation is running.
- AppImage packaging stays trivial — just a relocatable Python and a
  squashfs. No setuid bit to maintain across rebuilds, no
  `cap_dac_override` capabilities to negotiate with distros that
  sandbox AppImages.
- Distro-agnostic. polkit and sudo are both ubiquitous on Linux
  desktops; the udev-rule fallback works on systems that have neither.

**Harder:**

- Users without a polkit agent (some i3 / sway / lxqt setups out of the
  box) get a degraded fallback that often fails under a GUI session
  with no TTY. The startup banner from `udev_check.should_show_hint()`
  steers them toward the udev-rule path, which is friendlier anyway.
- Each flash op pays the prompt latency. ADR-0001 keeps it to one
  prompt; without ADR-0001 this would be three.
- Per-invocation escalation is incompatible with running flash ops in
  the background (e.g. a queue of devices). The application doesn't do
  that today; if it ever does, this ADR may need to be revisited
  alongside the daemon option.

## Alternatives considered

1. **Setuid helper.** Rejected. Setuid binaries are a well-known
   footgun: every environment-variable handling mistake becomes a
   privilege-escalation bug. They also conflict with signed-AppImage
   distribution (`#21`) — the AppImage runtime extracts the squashfs
   into a temp dir on each launch where setuid bits are typically
   stripped. Even when the bits survive, distros increasingly mount
   AppImage extract dirs `nosuid`. The udev-rule path already provides
   a no-prompt option for users who want one without the security
   trade-off.
2. **Long-running root daemon with a Unix socket.** Rejected. Vastly
   more surface area than a desktop tool warrants. The GUI is invoked
   on demand, not continuously; a daemon would idle with root forever
   to save a prompt during occasional flash sessions. Polkit
   integration is also weaker for daemons than for direct `pkexec`
   calls.
3. **doas instead of sudo.** Rejected. doas isn't on enough distros
   yet to be a credible fallback; pkexec covers the GUI-session case
   that doas was designed to avoid.

## References

- `flash_ops.py` — `_build_admin_argv()` implements the
  pkexec → sudo -A → sudo -n → clear-error fallback.
- `udev_check.py` — `should_show_hint()` and `install_command()` drive
  the friendlier udev-rule path so users don't have to tolerate the
  prompt long-term.
- ADR-0001 — single-prompt chain that this ADR depends on for
  acceptable UX.
