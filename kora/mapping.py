"""Static corroboration of two X-T4 module bases, not a whole-camera memory map."""
import hashlib
from pathlib import Path
import re
import struct

from .xt4 import MODULE_BASE, MODULE_SHA256, DEVELOP_MODULE_BASE, DEVELOP_MODULE_SHA256, DEVELOP_ENTRY


def analyze_xt4(directory: Path) -> dict:
    report = {"method": "Adjacent ARM MOVW/MOVT, same register and condition; pointers to NUL-delimited ASCII string starts. Bases from module headers.",
              "whole_system_mapping_validated": False, "modules": []}
    for name, base, digest in [
        ("unpacked_00260000.bin", MODULE_BASE, MODULE_SHA256),
        ("unpacked_005c0000.bin", DEVELOP_MODULE_BASE, DEVELOP_MODULE_SHA256)]:
        data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Pinned module hash mismatch: {name}")
        counts = {hex(base+delta): 0 for delta in [-32, 0, 32]}
        references, calls = [], []
        for offset in range(32, len(data)-8, 4):
            a, b = struct.unpack_from("<II", data, offset)
            if (a & 0x0ff00000 == 0x03000000 and b & 0x0ff00000 == 0x03400000 and
                    a & 0xf000f000 == b & 0xf000f000 and a >> 28 != 15):
                pointer = (a & 4095) | ((a >> 4) & 0xf000) | (((b & 4095) | ((b >> 4) & 0xf000)) << 16)
                for delta in [-32, 0, 32]:
                    target = pointer-base-delta
                    if (0 < target < len(data) and data[target-1] == 0 and
                            re.match(rb"[\x20-\x7e]{8,}\x00", data[target:target+256])):
                        counts[hex(base+delta)] += 1
                        text = data[target:target+256].split(b"\0")[0].decode()
                        if delta == 0 and text.startswith(("MODE_FSIM_", "reccfSetDevelopPara")):
                            references.append({"instruction": hex(base+offset), "pointer": hex(pointer), "string": text})
            if a & 0x0f000000 == 0x0b000000 and a >> 28 != 15:
                relative = a & 0xffffff
                if relative & 0x800000:
                    relative -= 1 << 24
                if base+offset+8+relative*4 == DEVELOP_ENTRY:
                    calls.append(hex(base+offset))
        report["modules"].append({"file": name, "sha256": digest, "base": hex(base),
                                  "header_words": [hex(x) for x in struct.unpack_from("<8I", data)],
                                  "string_start_reference_counts": counts,
                                  "relevant_references": references, "builder_call_candidates": calls})
    return report
