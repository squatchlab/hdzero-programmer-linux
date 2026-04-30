# 2. 1 MiB padded image with 0xFF for W25Q80 writes

Date: 2026-04-29

## Status

Accepted.

## Context

HDZero VTX hardware uses a Winbond W25Q80 SPI flash chip, capacity 1 MiB
(1024 KiB / 1,048,576 bytes). flashrom's `-w` operation expects an image
exactly the size of the target chip — partial-image writes are not
supported by the `ch341a_spi` programmer.

HDZero firmware blobs distributed via the firmware index API (or selected
locally by the user) are typically much smaller than 1 MiB — current
firmware fits within ~64 KiB, and the UI rejects anything above
`HDZERO_MAX = 64 * 1024` as not-valid-for-HDZero. The remaining ~960 KiB
of the chip is unused storage that the firmware never reads from.

Two options for filling the unused range:

1. Write `0x00` bytes for the unused range.
2. Write `0xFF` bytes for the unused range.

NOR flash (which W25Q80 is) erases to `0xFF`. A sector containing all
`0xFF` is identical to an erased sector. A sector containing all `0x00`
is a written sector and counts toward the chip's erase/write endurance
budget.

## Decision

`flash_ops.make_padded_image_1mib()` produces a 1 MiB temp file by
writing `b"\xFF" * FLASH_SIZE_BYTES` first, then seeking to offset 0 and
overwriting with the firmware bytes. The result:

- Bytes 0 to `len(firmware) - 1` contain the firmware image.
- Bytes `len(firmware)` to `1048575` contain `0xFF`.

The temp file is consumed by `flashrom -p ch341a_spi -w <path>` in the
safe-flash chain (see ADR-0001).

## Consequences

**Easier:**
- The "unused" tail of the chip remains in its erased state from
  flashrom's perspective. Subsequent `-r` reads return the same
  `0xFF`-padded image we wrote, which simplifies verify-pass diff logic.
- Erase/write endurance is preserved for the firmware region only —
  the tail isn't being unnecessarily cycled with `0x00` writes.
- A future firmware that grows beyond the current ~64 KiB ceiling
  doesn't need image-format changes; the pad is a no-op for the
  bytes the firmware does occupy.

**Harder:**
- A future firmware that uses the tail of the chip for non-firmware data
  (config, calibration, logs) would conflict with the unconditional
  `0xFF` pad — the pad would overwrite that data on every flash. No
  such firmware variant exists today, but if HDZero introduces one,
  this ADR must be revisited and the pad strategy made conditional.
- The padded image is held in `/tmp` for the duration of the flash.
  At 1 MiB it's not a memory burden, but it IS a surface for the
  tempfile-leak class of bug — addressed in PR #50 (issue #24) by
  unlinking in the FlashWorker's `finally` block.

## Alternatives considered

1. **Pad with `0x00`.** Rejected: needlessly cycles the chip's
   write endurance and produces a chip state that diverges from
   flashrom's "erased" assumption. Verify-pass diffs would have to
   ignore the tail explicitly.
2. **Read the chip first, splice the firmware into bytes 0..N, write
   back.** Rejected: defeats the rollback-image purpose of the
   pre-flash backup (the backup would already incorporate the new
   firmware's first N bytes if the splice happened before the backup
   step). Also adds a dependency: a working `-r` must succeed before
   the write can even be attempted.
3. **Skip the pad and hope flashrom accepts a partial image.** Rejected:
   `ch341a_spi` does not support partial writes.

## References

- `flash_ops.py:9-11` — `FLASH_SIZE_BYTES = 1024 * 1024` constant.
- `flash_ops.py:98-110` — `make_padded_image_1mib()` implementation.
- `tests/test_flash_ops.py:18-50` — pad invariant tests
  (size, fill byte, oversize rejection).
