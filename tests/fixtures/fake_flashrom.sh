#!/bin/bash
# Fake flashrom for integration tests. Mimics the stdout markers FlashWorker
# parses for live phase status, and supports targeted failure injection via
# FAKE_FLASHROM_FAIL=read|write|verify. Honors -r <path> by writing a 1 MiB
# image of 0xCC bytes (deterministic, distinct from the real chip backup but
# sized correctly for any post-condition assertions).
#
# Argument shape we care about (the rest is ignored):
#   flashrom -p ch341a_spi -r <path>      (read / backup)
#   flashrom -p ch341a_spi -w <path>      (write)
#   flashrom -p ch341a_spi -v <path>      (verify-only)
#
# All three modes print a short startup banner first so the parser sees a
# realistic stream rather than a single line.

set -u

mode=""
target=""
while [ $# -gt 0 ]; do
    case "$1" in
        -r) mode="read"; target="$2"; shift 2 ;;
        -w) mode="write"; target="$2"; shift 2 ;;
        -v) mode="verify"; target="$2"; shift 2 ;;
        -p) shift 2 ;;            # programmer name — irrelevant to fixture
        *)  shift ;;
    esac
done

cat <<'BANNER'
flashrom v1.3.0 on Linux 6.0.0 (x86_64)
flashrom is free software, get the source code at https://flashrom.org
Using clock_gettime for delay loops (clk_id: 1, resolution: 1ns).
Found Winbond flash chip "W25Q80.V" (1024 kB, SPI) on ch341a_spi.
BANNER

case "$mode" in
    read)
        echo "Reading flash... done."
        if [ "${FAKE_FLASHROM_FAIL:-}" = "read" ]; then
            echo "FAILED at offset 0x12340 — chip not responding" >&2
            exit 1
        fi
        # Produce a deterministic 1 MiB image so callers can stat() and
        # diff against expectations.
        : > "$target"
        head -c 1048576 /dev/zero | tr '\0' '\314' > "$target"
        ;;
    write)
        echo "Erasing and writing flash chip... "
        if [ "${FAKE_FLASHROM_FAIL:-}" = "write" ]; then
            echo "FAILED — sector erase verify mismatch at 0x4000" >&2
            exit 1
        fi
        echo "Erase/write done."
        echo "Verifying flash... VERIFIED."
        ;;
    verify)
        echo "Verifying flash..."
        if [ "${FAKE_FLASHROM_FAIL:-}" = "verify" ]; then
            echo "FAILED — verify mismatch at 0x10000 (got 0xff, expected 0x42)" >&2
            exit 1
        fi
        echo "VERIFIED."
        ;;
    *)
        echo "fake_flashrom: unsupported mode (no -r/-w/-v)" >&2
        exit 2
        ;;
esac

exit 0
