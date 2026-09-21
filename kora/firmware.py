"""Read-only DAT reconnaissance. No package rewriting or guessed decompression."""
from pathlib import Path
import hashlib
import math
import re
import struct
from collections import Counter


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    return -sum((n / len(data)) * math.log2(n / len(data)) for n in Counter(data).values())


def inspect_firmware(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 532:
        raise ValueError("DAT trop court pour l’inspection X6/X8.")
    fmt = struct.unpack_from("<I", data, 0)[0]
    if fmt not in {6, 8}:
        raise ValueError(f"Unsupported {fmt} format; inspection is limited to X6/X8.")
    major, minor = struct.unpack_from("<II", data, 516)
    keywords = re.compile(rb"classic|chrome|eterna|film.?sim|rawconv|bleach|threadx", re.I)
    matches = []
    for label, view in [("original", data), ("xor_ff_view", data.translate(bytes(255 - i for i in range(256))))]:
        for match in re.finditer(rb"[ -~]{8,}", view):
            if keywords.search(match[0]):
                matches.append({"file_offset": hex(match.start()), "view": label, "text": match[0][:240].decode("ascii")})
    words = [{"file_offset": hex(o), "u32_le": hex(struct.unpack_from("<I", data, o)[0])} for o in range(512, min(640, len(data)), 4)]
    return {
        "file": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "format_word": fmt, "version_words_hex": [hex(major), hex(minor)],
        "version_display_candidate": f"{major:x}.{minor:02x}",
        "header_words": words, "keyword_matches": matches,
        "entropy_windows": [{"offset": hex(o), "entropy_bits_per_byte": round(entropy(data[o:o+65536]), 4)} for o in range(0, len(data), 1048576)],
        "limits": ["Version offsets follow FujiHack public parser; complete X6/X8 manifest is NOT parsed or validated.", "XOR view is only for reconnaissance. Trailer segments may be unencoded; this is not a reconstructed firmware image.", "String hits may be inside compressed streams or UI resources. They do not identify executable image processing or LUTs.", "No checksum, signature, relocation, decompression, DSP or ISP equivalence has been established."],
    }
