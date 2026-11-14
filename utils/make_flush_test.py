#!/usr/bin/env python3
"""Build a synthetic 636-byte flush datagram for testing split_usr_data:
VIEWER(28) + BUILDINGVHCL(272) + zero padding + SYNCGM(52) + trailing bytes,
matching the layout observed in the real uads log."""
import struct

import net_messages


def ua_msg(msg_id, total, fill=b""):
    body = struct.pack("<I", msg_id) + fill
    assert len(body) <= total
    return body + b"\x00" * (total - len(body))


def main():
    viewer = ua_msg(net_messages.UAMSG_VIEWER, 28, b"\x01\x00\x01\x00\x03\x01")
    bldvhcl = ua_msg(net_messages.UAMSG_BUILDINGVHCL, 528)
    syncgm = ua_msg(net_messages.UAMSG_SYNCGM, 52,
                    b"\x00" * 8 + b"\x01\x00\x00\x00" + b"\x01\x01\x01\x00\x01\x01")

    ua_region = viewer + bldvhcl + syncgm
    assert len(ua_region) == 608, len(ua_region)

    payload = (b"\xbb\xbb\x04\x92\x22\x8e\xaa\xaa"  # from
               + b"\x01"                            # cast
               + b"\xfa\x54\x25\x3f\x29\x01\x00\x00"  # to
               + struct.pack("<I", len(ua_region) + 12))
    hdr = (b"\x02" + struct.pack("<I", 7) + b"\x01"
           + bytes([net_messages.USR_MSG_DATA]))
    raw = hdr + payload + ua_region
    assert len(raw) == 636, len(raw)
    open("/tmp/flush_test.hex", "w").write(raw.hex())
    print("wrote /tmp/flush_test.hex (%d bytes)" % len(raw))


if __name__ == "__main__":
    main()
