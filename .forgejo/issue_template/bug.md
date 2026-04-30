---
name: Bug report
about: Flash failed, GUI crashed, something obviously wrong
title: "[BUG] "
labels: ["bug"]
---

## Environment

- **Distro / version**: (e.g. Fedora 43, Ubuntu 24.04)
- **Python version**: `python3 --version` →
- **flashrom version**: `flashrom --version` →
- **Install method**: AppImage / `pip install --user .` / checkout
- **CH341A udev rule installed?**: `ls /etc/udev/rules.d/99-ch341a.rules` →
- **HDZERO_NO_ESCALATE set?**: yes / no

## What you did

Steps to reproduce. Be literal — "clicked FLASH" not "tried to flash".

1.
2.
3.

## What you expected

## What happened

## Transcript

The per-flash transcript file under `~/.local/state/hdzero-programmer/`
(or `$XDG_STATE_HOME/hdzero-programmer/`). Paste the contents in a code
block, or attach the file.

```
(paste here)
```

## Screenshots / logs (optional)

Anything else that helps. For UI weirdness, the output of running with
`QT_LOGGING_RULES="*=true"` is often useful.
