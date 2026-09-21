"""Bounded RAF metadata extraction and native geometry-reader probe.

No pixel decoding, demosaicing or RAW payload is supplied to the firmware.
"""
import hashlib
from pathlib import Path
import struct

from .emulation import run_function
from .pipeline import modules
from .raw import local_file
from .synchronization import STACK, STOP

METADATA_ENTRY = 0x1171388


def metadata_entries(block):
    if len(block) < 4:
        raise ValueError("Truncated RAF metadata count")
    count = struct.unpack_from(">I", block)[0]
    if not 1 <= count <= 255:
        raise ValueError("Unsupported RAF metadata entry count")
    entries, offset = [], 4
    for _ in range(count):
        if offset+4 > len(block):
            raise ValueError("Truncated RAF metadata tag")
        tag, length = struct.unpack_from(">HH", block, offset)
        if offset+4+length > len(block):
            raise ValueError("RAF metadata value exceeds block")
        entries.append((tag, block[offset+4:offset+4+length]))
        offset += 4+length
    return entries


def read_metadata(path: Path):
    if not local_file(path):
        raise ValueError("RAF must be local; iCloud placeholders are not read")
    before = path.stat()
    with path.open("rb") as stream:
        header = stream.read(108)
        if len(header) < 108 or not header.startswith(b"FUJIFILMCCD-RAW "):
            raise ValueError("Not a supported RAF header")
        offset, length = struct.unpack_from(">II", header, 92)
        if offset < 108 or not 4 <= length <= 1024*1024 or offset+length > before.st_size:
            raise ValueError("RAF metadata range is outside the file or exceeds 1 MiB")
        stream.seek(offset)
        block = stream.read(length)
    after = path.stat()
    if len(block) != length or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("RAF changed while reading metadata")
    entries = metadata_entries(block)
    return block, entries, {"path": str(path.resolve()), "size": before.st_size,
                            "model_header": header[28:60].split(b"\0")[0].decode("ascii", errors="replace"),
                            "metadata_offset": offset, "metadata_length": length,
                            "metadata_sha256": hashlib.sha256(block).hexdigest(),
                            "header_sha256": hashlib.sha256(header).hexdigest(), "opened_read_only": True}


def metadata_probe(directory: Path, source: Path):
    block, entries, provenance = read_metadata(source)
    tags = dict(entries)
    required = [0x100, 0x110, 0x111, 0x113, 0x141]
    # Keep the verified branch explicit. Other RAF generations need their own
    # expected-output model; do not silently report them compatible.
    if any(len(tags.get(tag, b"")) != 4 for tag in required):
        raise ValueError("Probe requires the five verified four-byte geometry tags")
    if any(sum(t == tag for t, _ in entries) != 1 for tag in required):
        raise ValueError("Duplicate geometry tags require a separate native-path analysis")
    expected = [value for tag in required for value in struct.unpack(">HH", tags[tag])]
    execution = run_function({
        "architecture": "arm", "entry": METADATA_ENTRY, "stop": STOP,
        "regions": [*modules(directory),
                    {"address": 0x6900000, "size": (len(block)+4095)//4096*4096, "permissions": "r",
                     "hex": block.hex(), "initialized_only": True, "expected_sha256": provenance["metadata_sha256"]},
                    {"address": 0x6a00000, "size": 4096, "permissions": "rw", "hex": "a5"*4096},
                    {"address": 0x7000000, "size": 65536, "permissions": "rw"}],
        "registers": {"R0": 0x6900000, "R1": 0x6a00000, "SP": STACK, "LR": STOP, "CPSR": 0x13},
        "outputs": [{"address": 0x6a00000, "size": 4096}],
        "memory_trace": [{"address": 0x6900000, "size": len(block)}, {"address": 0x6a00000, "size": 4096}],
        "instruction_limit": 10000, "provenance": {**provenance, "scope": "Native X-T4 metadata reader only; source camera may differ", "stubs": [], "patched_instructions": False}})
    output = bytes.fromhex(execution["outputs"][0]["hex"])
    observed = list(struct.unpack("<10H", output[:20]))
    passed = (execution["reached_stop"] and execution["registers"]["R0"] == "0x0" and
              execution["registers"]["SP"] == hex(STACK) and observed == expected and
              output[20:] == b"\xa5"*(4096-20) and not execution["memory_trace_truncated"])
    execution["outputs"][0].pop("hex")
    execution["outputs"][0]["metadata_prefix_hex"] = output[:20].hex()
    return {"passed": passed, "target_reader": "X-T4 2.12", "source": provenance,
            "raw_width": observed[1], "raw_height": observed[0],
            "crop_top_left": observed[2:4], "crop_height_width": observed[4:6],
            "tag_0113_pair": observed[6:8], "tag_0141_pair": observed[8:10],
            "expected_words": expected, "observed_words": observed,
            "firmware_executed": True, "image_pipeline_executed": False,
            "source_pixel_compatibility_validated": False, "execution": execution}
