# 1. Single-prompt sh -c chain for safe-flash pipeline

Date: 2026-04-29

## Status

Accepted.

## Context

`flashrom` driving the CH341A USB SPI programmer requires raw USB access,
which means the user is either:

1. Running the tool as root (unusual on a Linux desktop), OR
2. Has the bundled `99-ch341a.rules` udev rule installed and exports
   `HDZERO_NO_ESCALATE=1` (the documented happy path), OR
3. Has neither — in which case the tool escalates per-invocation via
   `pkexec` (polkit GUI prompt) → `sudo -A` (askpass-driven) → `sudo -n`
   (non-interactive last resort).

The "safe flash" pipeline performs three flashrom invocations in sequence:

- Optional pre-flash chip read (`-r`) — produces a rollback image.
- Padded firmware write (`-w`) — the actual flash.
- Explicit re-verify (`-v`) — diff the chip against the padded image.

If each invocation went through `run_admin()` separately, a user without
the udev rule installed would see THREE polkit prompts per flash. That's
unacceptable UX: users either get prompt fatigue (and start dismissing
prompts mid-flash) or stop using the safe-flash mode entirely and lose
the rollback image.

The alternative is to chain the three invocations into one privileged
shell command, escalate once, and let the chain run under that single
escalation.

## Decision

`FlashWorker.run()` builds a single `sh -c '<cmd1> && <cmd2> && <cmd3>'`
string with each `<cmdN>` shell-escaped via `shlex.quote()`. The whole
chain is passed to `run_admin_streaming()`, which prefixes it with
whatever escalation mechanism is available (`pkexec`, `sudo -A`,
`sudo -n`, or no-op when `HDZERO_NO_ESCALATE=1`). The user sees ONE
prompt for the entire backup → write → verify pipeline.

`shlex.quote()` is mandatory because the user's `XDG_STATE_HOME` or
`tempfile`-resolved `/tmp` dir might contain whitespace, single quotes,
or shell metacharacters. Without `shlex.quote()`, an XDG dir set to
`$HOME/odd dir` would break out of the chain with predictable
consequences.

The `&&` join is deliberate. It short-circuits on the first failure,
which means:
- Backup failed → write doesn't run; chip is untouched.
- Write failed → verify doesn't run; the rollback image still exists
  on disk.
- Verify failed → the chain ends; the user has the rollback image AND
  knows verification mismatched.

## Consequences

**Easier:**
- One privilege prompt covers the full pipeline. Reasonable UX even on
  systems without the udev rule.
- Failure short-circuit semantics are simple to reason about.
- The transcript file (`~/.local/state/hdzero-programmer/flash-*.log`)
  captures all three phases in one stream.

**Harder:**
- Phase tracking is best-effort string-matching against flashrom stdout
  (`reading flash` / `erasing and writing` / `verifying flash`). A
  flashrom version that changes those markers breaks GUI phase reporting
  but does NOT break the flash itself.
- Switching to `argv` lists (canonical Python advice for shell safety)
  would split the chain into multiple privileged calls — `pkexec` and
  `sudo` each run a single program. That would re-introduce the
  multi-prompt problem we're solving here.
- New flashrom invocations added to the chain must also use
  `shlex.quote()`. Linting won't catch this; reviewers must.

## Alternatives considered

1. **Three separate `run_admin()` calls.** Rejected: three polkit prompts
   per flash. Unacceptable UX.
2. **A small setuid helper that the GUI invokes.** Rejected: setuid
   binaries are a security footgun and a packaging burden (signed AppImage
   + setuid is contradictory). The udev-rule path already provides a
   no-prompt option for users who want one.
3. **Background daemon with a Unix socket.** Rejected: vastly more
   surface area than a desktop tool warrants. A polkit prompt per
   user-initiated flash session is fine; the daemon would only eliminate
   prompts entirely, which the udev rule already does.

## References

- `flash_ops.py:113-260` — `FlashWorker` implementation.
- `CLAUDE.md` Gotchas section — preserved as a working-context summary.
- Audit ticket `#19` — supersedes the trust model layer (firmware
  verification at download time), but does NOT change this ADR's
  decision; #19 sits upstream of the chain.
