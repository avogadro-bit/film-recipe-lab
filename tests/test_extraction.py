import random
import struct
from pathlib import Path
import tempfile
import unittest

from kora.fflz import DecodeError, decompress
from kora.extract import PAYLOAD_BASE, checksum, invert, segments, packed_objects, extract


def packed(tokens, size):
    n = len(tokens) + 20
    return struct.pack("<5I", size, n, (n+16383)//16384, 16384, 4) + tokens


def synthetic_container():
    header = bytearray(PAYLOAD_BASE)
    struct.pack_into("<I", header, 0, 6)
    fields = [(None, 0x248, 0x20c, True), (0x24c, 0x250, 0x210, True),
              (0x254, 0x258, 0x214, True), (0x25c, 0x260, 0x264, False),
              (0x268, 0x26c, 0x270, False), (0x220, 0x224, 0x21c, True),
              (0x22c, 0x230, 0x228, True)]
    payload = bytearray()
    for i, (offset_at, size_at, sum_at, encoded) in enumerate(fields):
        block = bytes([i, 255-i, i*3, 17]) * (i+1)
        if offset_at is not None:
            struct.pack_into("<I", header, offset_at, len(payload))
        struct.pack_into("<I", header, size_at, len(block))
        struct.pack_into("<I", header, sum_at, checksum(block))
        payload.extend(invert(block) if encoded else block)
    return bytes(header+payload)


class ExtractionTests(unittest.TestCase):
    def test_literals_and_overlapping_references(self):
        # ABC + distance 3 length 9, then distance 1 length 5.
        self.assertEqual(decompress(packed(b"\x03ABC\x80\x39\x80\x15", 17)), b"ABCABCABCABCCCCCC")

    def test_reference_decoder_against_bytewise_oracle(self):
        rng = random.Random(6714)
        expected, tokens = bytearray(), bytearray()
        for _ in range(500):
            if len(expected) < 2100 or rng.random() < .2:
                block = rng.randbytes(rng.randint(1, 127))
                tokens.extend(bytes([len(block)])+block)
                expected.extend(block)
            else:
                distance, length = rng.randint(1, 2047), rng.randint(1, 15)
                tokens.extend([128 | distance >> 4, (distance & 15) << 4 | length])
                for _ in range(length):
                    expected.append(expected[-distance])
        self.assertEqual(decompress(packed(tokens, len(expected))), expected)

    def test_rejects_invalid_tokens_and_bounds(self):
        for tokens, size in [(b"\0", 1), (b"\x02a", 2), (b"\x01a", 2),
                             (b"\x80", 1), (b"\x80\x11", 1),
                             (b"\x01a\x80\x01", 2), (b"\x01a\x80\x10", 2),
                             (b"\x01a\x80\x1f", 3), (b"\x02ab", 1)]:
            with self.subTest(tokens=tokens), self.assertRaises(DecodeError):
                decompress(packed(tokens, size))

    def test_header_limits_and_embedded_stream(self):
        stream = packed(b"\x01a\x80\x1f\x80\x1f", 31)
        self.assertEqual(decompress(b"junk"+stream+b"padding", 4), b"a"*31)
        self.assertEqual(packed_objects(b"junk"+stream)[0][0], 4)
        for offset, value in [(0, 0), (0, 2**30), (4, 9999), (8, 2), (12, 8192), (16, 5)]:
            data = bytearray(stream)
            struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(DecodeError):
                decompress(data)
        with self.assertRaises(DecodeError):
            decompress(stream, -1)

    def test_outer_mixed_encoding_and_corruption(self):
        data = synthetic_container()
        result = segments(data, require_known_hash=False)
        self.assertEqual(len(result), 7)
        self.assertFalse(result[3].encoded)
        for s in result:
            damaged = bytearray(data)
            damaged[PAYLOAD_BASE+s.offset] ^= 1
            with self.subTest(segment=s.name), self.assertRaisesRegex(ValueError, "checksum"):
                segments(damaged, require_known_hash=False)

    def test_outer_rejects_wrong_version_gaps_and_trailing_data(self):
        data = synthetic_container()
        with self.assertRaisesRegex(ValueError, "pinned"):
            segments(data)
        for offset, value in [(0, 8), (0x24c, 5), (0x248, 2**32-1)]:
            damaged = bytearray(data)
            struct.pack_into("<I", damaged, offset, value)
            with self.assertRaises(ValueError):
                segments(damaged, require_known_hash=False)
        with self.assertRaisesRegex(ValueError, "Trailing"):
            segments(data+b"x", require_known_hash=False)

    def test_wrong_firmware_creates_no_extraction_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory)/"wrong.dat", Path(directory)/"out"
            source.write_bytes(synthetic_container())
            with self.assertRaises(ValueError):
                extract(source, destination)
            self.assertFalse(destination.exists())

    def test_native_probes_reject_unverified_modules_before_execution(self):
        from kora.xt4 import film_probe, parameter_probe
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory)/"unpacked_00260000.bin"
            module.write_bytes(b"unverified")
            with self.assertRaisesRegex(ValueError, "pinned"):
                film_probe(module)
            with self.assertRaisesRegex(ValueError, "Pinned"):
                parameter_probe(Path(directory))
