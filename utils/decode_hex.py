#!/usr/bin/env python3
"""Decode a uads RAW hex line (or the 636-byte flush) into its wire layout.

Usage: python3 utils/decode_hex.py <hexstring or file with hex>
"""
import re
import struct
import sys

import net_messages


def find_ids(buf):
    """Find all plausible UA message ids (0x3e0..0x3ff) and their offsets."""
    hits = []
    for i in range(0, len(buf) - 4, 4):
        v = struct.unpack_from("<I", buf, i)[0]
        if 0x3e0 <= v <= 0x3ff:
            hits.append((i, v))
    return hits


def main():
    arg = sys.argv[1]
    if "/" in arg or arg.endswith(".txt") or arg.endswith(".hex") or arg.endswith(".dat"):
        blob = open(arg, "rb").read()
        try:
            buf = bytes.fromhex(blob.decode("ascii"))
        except ValueError:
            buf = blob  # raw binary dump from _dump_bad_split
    else:
        buf = bytes.fromhex(re.sub(r"[^0-9a-fA-F]", "", arg))

    print("datagram: %d bytes, flags=%#x seq=%d chnl=%d msg=%#x"
          % (len(buf), buf[0],
             struct.unpack_from("<I", buf, 1)[0], buf[5], buf[6]))
    if buf[6] != net_messages.USR_MSG_DATA:
        print("not USR_MSG_DATA, nothing to do")
        return
    sz = struct.unpack_from("<I", buf, 24)[0]
    payload = buf[28:28 + sz]
    print("payload: %d bytes" % len(payload))
    print("  from=%#018x cast=%d to=%#018x sz=%d"
          % (struct.unpack_from("<Q", buf, 7)[0], buf[15],
             struct.unpack_from("<Q", buf, 16)[0],
             struct.unpack_from("<I", buf, 24)[0]))

    # payload IS the UA region (framing lives at raw offsets 7..27)
    ua = payload
    print("UA region: %d bytes" % len(ua))
    for off, mid in find_ids(ua):
        print("  UA msg_id %#05x (=%d) at UA offset %d" % (mid, mid, off))

    # walk with the current size table
    from net_classes import _ua_msg_size
    offset = 0
    print("walk:")
    while offset + 16 <= len(ua):
        mid = struct.unpack_from("<I", ua, offset)[0]
        size = _ua_msg_size(mid, ua, offset)
        if size is None:
            tail = ua[offset:]
            print("  STOP at %d: msg_id=%d, %d bytes left" % (offset, mid, len(tail)))
            # hex dump the tail in 16-byte rows
            for i in range(0, len(tail), 16):
                chunk = tail[i:i + 16]
                hx = " ".join("%02x" % b for b in chunk)
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                print("    %4d: %-47s %s" % (offset + i, hx, asc))
            break
        print("  %4d: msg_id %#05x size %d" % (offset, mid, size))
        offset += size
    if offset == len(ua):
        print("  walk consumed everything")


if __name__ == "__main__":
    main()
