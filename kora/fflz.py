"""Fuji DAT LZ stream reconstructed from the X-T4 2.12 image.

Header: unpacked length, total packed length INCLUDING 20-byte header,
ceil(packed_length / page_size), page_size (16 KiB), codec word (4).
Literal: 1..127 followed by that many bytes.
Reference: two bytes, high bit set; distance=((a&127)<<4)|(b>>4),
length=b&15. Overlapping copies are intentional.

This codec is for firmware objects, not RAF image compression.
"""
from dataclasses import dataclass
import struct


class DecodeError(ValueError):
    pass


@dataclass(frozen=True)
class PackedHeader:
    unpacked_size: int
    packed_size: int
    page_count: int
    page_size: int
    codec: int

    @classmethod
    def read(cls, data: bytes, offset: int = 0, max_output: int = 128 * 1024 * 1024):
        if offset < 0 or offset + 20 > len(data):
            raise DecodeError("Truncated packed header")
        h = cls(*struct.unpack_from("<5I", data, offset))
        if not 0 < h.unpacked_size <= max_output:
            raise DecodeError("Unpacked size outside configured limit")
        if h.packed_size < 20 or offset + h.packed_size > len(data):
            raise DecodeError("Packed size outside input")
        if h.codec != 4 or h.page_size != 16384:
            raise DecodeError("Unsupported codec or DMA page size")
        if h.page_count != (h.packed_size + h.page_size - 1) // h.page_size:
            raise DecodeError("Inconsistent page count")
        return h


def decompress(data: bytes, offset: int = 0, max_output: int = 128 * 1024 * 1024) -> bytes:
    h = PackedHeader.read(data, offset, max_output)
    pos, end = offset + 20, offset + h.packed_size
    out = bytearray()
    while pos < end:
        token = data[pos]
        pos += 1
        if token < 128:
            if token == 0:
                raise DecodeError(f"Zero literal at {pos-1:#x}")
            if pos + token > end or len(out) + token > h.unpacked_size:
                raise DecodeError(f"Literal outside input/output at {pos-1:#x}")
            out.extend(data[pos:pos+token])
            pos += token
        else:
            if pos >= end:
                raise DecodeError("Truncated reference")
            value = data[pos]
            pos += 1
            distance = ((token & 127) << 4) | (value >> 4)
            length = value & 15
            if distance == 0 or distance > len(out) or length == 0:
                raise DecodeError(f"Invalid reference at {pos-2:#x}: distance={distance}, length={length}, written={len(out)}")
            if len(out) + length > h.unpacked_size:
                raise DecodeError("Reference exceeds declared output")
            # Repeat a period for overlap; never slice beyond initialized bytes.
            pattern = out[-distance:]
            out.extend((pattern * ((length + distance - 1) // distance))[:length])
    if len(out) != h.unpacked_size:
        raise DecodeError(f"Output size mismatch: {len(out)} != {h.unpacked_size}")
    return bytes(out)
