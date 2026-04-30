# Hardware CI runner setup

The default Forgejo Actions runner (`lab01-hdzero`) advertises only the
`ubuntu-22.04` label. The `hw-test` workflow
([`.forgejo/workflows/hw-test.yml`](../.forgejo/workflows/hw-test.yml))
gates on `[ubuntu-22.04, hdzero-hw]`, so without a runner that
advertises `hdzero-hw` the job sits unclaimed forever — which is the
right default. Adding a hardware runner is opt-in, host-specific work.

This doc captures the steps for the maintainer (or anyone replicating
the lab setup) to bring an `hdzero-hw` runner online.

## Hardware

- **CH341A USB SPI programmer** wired to the W25Q80 chip on an HDZero
  VTX via a SOIC-8 clip. The udev rule at
  [`packaging/99-ch341a.rules`](../packaging/99-ch341a.rules) grants
  `uaccess` + `plugdev` group access so the runner can talk to the
  device without `sudo`.
- **HDZero VTX** wired permanently to the programmer. The workflow
  re-flashes the production firmware on every run (idempotent
  teardown), so the VTX stays bootable across runs.
- **Host** running Linux with USB pass-through (or a bare-metal lab
  box). Tested on Fedora 43 + Ubuntu 22.04. The runner image itself
  is `catthehacker/ubuntu:act-22.04` so the kernel underneath only
  needs to expose `/dev/bus/usb/...` to the container.

## Software

```bash
# Install flashrom on the host (the act_runner container shares
# /dev/bus/usb but the binary lives in the runner image — see below).
sudo dnf install flashrom        # Fedora
sudo apt install flashrom        # Debian/Ubuntu

# Install the udev rule + reload so the runner user can access the
# CH341A without root.
sudo install -m 0644 packaging/99-ch341a.rules \
  /etc/udev/rules.d/99-ch341a.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# unplug + replug the CH341A

# Verify the rule took effect — uaccess group should be present.
ls -l /dev/bus/usb/*/$(lsusb | awk '/1a86:5512/ {print $4}' | tr -d :)
```

## Stage the known-good firmware

The hw-test workflow re-flashes the production firmware on every run
so the VTX is left in a known state. Stage the blob *on the runner
host* — NOT in the repo (binary blobs don't belong in git):

```bash
sudo mkdir -p /var/lib/hdzero-hw
sudo cp /path/to/hdzero-production-firmware.bin \
  /var/lib/hdzero-hw/known-good-firmware.bin
sudo chmod 0644 /var/lib/hdzero-hw/known-good-firmware.bin
```

The workflow padding step (`make_padded_image_1mib`) handles the
1 MiB target, so the blob can be the raw firmware binary — anything
≤ 64 KiB will work.

## Register the runner

The default Quadlet at
`~/.config/containers/systemd/act_runner.container` (see
[`docs/HARDWARE-CI-RUNNER-QUADLET.md`](HARDWARE-CI-RUNNER-QUADLET.md)
when written) advertises one label. Either add a second runner that
advertises `hdzero-hw`, OR replace the existing runner's labels.

For a dedicated hardware runner, register a fresh one:

```bash
TOKEN=$(cat ~/.forgejo-token)
REG_TOKEN=$(curl -s -H "Authorization: token $TOKEN" \
  "https://forgejo.squatch.lab/api/v1/repos/bmags/hdzero-programmer-linux/actions/runners/registration-token" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")

# In a separate data dir so the hw runner can be torn down
# independently of the everyday runner.
mkdir -p ~/.local/share/act_runner-hw

# Auto-register via env vars (same env-var auto-flow as the default
# runner). Note the labels: matches the workflow's `runs-on:` matrix.
cat > ~/.local/share/act_runner-hw/registration.env <<EOF
GITEA_INSTANCE_URL=https://forgejo.squatch.lab
GITEA_RUNNER_REGISTRATION_TOKEN=$REG_TOKEN
GITEA_RUNNER_NAME=$(hostname)-hdzero-hw
GITEA_RUNNER_LABELS=ubuntu-22.04:docker://catthehacker/ubuntu:act-22.04,hdzero-hw:docker://catthehacker/ubuntu:act-22.04
EOF
chmod 0600 ~/.local/share/act_runner-hw/registration.env
```

Then create a second Quadlet (`act_runner-hw.container`) following
the same pattern as `act_runner.container`, pointing at the new data
dir. Mount `/dev/bus/usb` into the container so the spawned job
container can see the CH341A:

```ini
[Container]
ContainerName=act_runner-hw
Image=docker.io/gitea/act_runner:latest
SecurityLabelDisable=true
Volume=%t/podman/podman.sock:/podman.sock
Volume=%h/.local/share/act_runner-hw:/data
Volume=/dev/bus/usb:/dev/bus/usb        # USB pass-through for the spawned job container
Volume=/var/lib/hdzero-hw:/var/lib/hdzero-hw:ro
EnvironmentFile=%h/.local/share/act_runner-hw/registration.env
```

Plus a corresponding stanza in the workflow's `runs-on` matrix so
podman knows to pass-through `/dev/bus/usb` and the firmware blob to
the inner container — the simplest route is `container.options:` in
`config.yaml`:

```yaml
container:
  options: --device=/dev/bus/usb:/dev/bus/usb -v /var/lib/hdzero-hw:/var/lib/hdzero-hw:ro
```

## Verify

After the runner is up:

1. Visit
   `https://forgejo.squatch.lab/bmags/hdzero-programmer-linux/settings/actions/runners`
   and confirm both runners show online with the right labels.
2. Trigger the workflow manually:
   `https://forgejo.squatch.lab/bmags/hdzero-programmer-linux/actions`
   → "hw-test" → "Run workflow".
3. The job should run the read → pad → write → verify → restore
   sequence, upload the four flashrom transcripts as
   `hw-test-transcripts.zip`.

## Tearing down / disabling

Remove or stop the `act_runner-hw` Quadlet. The workflow will sit
unclaimed but won't fail anything — `ci.yml` (smoke + appimage) is
unaffected.

## Why this isn't gated on PRs

Pull-request workflows can ship arbitrary changes to
`packaging/build-appimage.sh`, `flash_ops.py`, the workflow YAML
itself. Running those against real silicon on every contributor PR is
a bricking-foot-gun. The workflow runs only on push to `main` (i.e.,
after merge) and on explicit `workflow_dispatch` from a maintainer.
