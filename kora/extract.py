"""Validated outer container extraction, initially pinned to X-T4 2.12."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct

from .fflz import PackedHeader, DecodeError, decompress

XT4_SHA256 = "853d273b5603d3a2b93493f0ebd6a762b0b4b6bdc70317777775ae5f8ed93bc5"
PAYLOAD_BASE = 0x274


@dataclass(frozen=True)
class Segment:
    name: str
    offset: int
    size: int
    encoded: bool
    checksum: int


def checksum(data: bytes) -> int:
    return (~sum(data)) & 0xffffffff


def segments(data: bytes, *, require_known_hash: bool = True) -> list[Segment]:
    if len(data) < PAYLOAD_BASE or struct.unpack_from("<I", data)[0] != 6:
        raise ValueError("Unsupported or truncated X6 container")
    if require_known_hash and hashlib.sha256(data).hexdigest() != XT4_SHA256:
        raise ValueError("This layout has only been validated for the pinned X-T4 2.12 DAT")
    def word(offset):
        return struct.unpack_from("<I", data, offset)[0]
    # Names deliberately avoid guessing the purpose of unidentified regions.
    table = [
        Segment("main", 0, word(0x248), True, word(0x20c)),
        Segment("region_1", word(0x24c), word(0x250), True, word(0x210)),
        Segment("region_2", word(0x254), word(0x258), True, word(0x214)),
        Segment("table_0", word(0x25c), word(0x260), False, word(0x264)),
        Segment("table_1", word(0x268), word(0x26c), False, word(0x270)),
        Segment("region_3", word(0x220), word(0x224), True, word(0x21c)),
        Segment("region_4", word(0x22c), word(0x230), True, word(0x228)),
    ]
    cursor = 0
    for s in table:
        if s.size <= 0 or s.offset != cursor or PAYLOAD_BASE + s.offset + s.size > len(data):
            raise ValueError(f"Segment bounds/continuity violation: {s.name}")
        block = data[PAYLOAD_BASE+s.offset:PAYLOAD_BASE+s.offset+s.size]
        decoded = invert(block) if s.encoded else block
        if checksum(decoded) != s.checksum:
            raise ValueError(f"Segment checksum mismatch: {s.name}")
        cursor += s.size
    if PAYLOAD_BASE + cursor != len(data):
        raise ValueError("Trailing bytes outside validated segments")
    return table


def invert(data: bytes) -> bytes:
    return data.translate(bytes(255-i for i in range(256)))


def packed_objects(main: bytes) -> list[tuple[int, PackedHeader]]:
    """Candidates require full header consistency; decompression validates more."""
    found = []
    start = 0
    marker = struct.pack("<II", 16384, 4)
    while True:
        hit = main.find(marker, start)
        if hit < 0:
            break
        start = hit + 1
        offset = hit - 12
        if offset < 0 or offset % 4:
            continue
        try:
            h = PackedHeader.read(main, offset)
            if h.packed_size < h.unpacked_size:
                found.append((offset, h))
        except DecodeError:
            continue
    return found


def extract(path: Path, destination: Path) -> dict:
    data = path.read_bytes()
    table = segments(data)
    # No files written before all outer checksums and bounds have passed.
    destination.mkdir(parents=True, exist_ok=False)
    report = {"source_sha256": hashlib.sha256(data).hexdigest(), "payload_base": PAYLOAD_BASE,
              "target": "X-T4 2.12", "outer_checksums_valid": True,
              "segments": [], "packed_objects": [], "image_pipeline_executed": False}
    main = None
    for s in table:
        block = data[PAYLOAD_BASE+s.offset:PAYLOAD_BASE+s.offset+s.size]
        decoded = invert(block) if s.encoded else block
        (destination / f"{s.name}.bin").write_bytes(decoded)
        report["segments"].append({**asdict(s), "file_offset": PAYLOAD_BASE+s.offset,
                                   "sha256": hashlib.sha256(decoded).hexdigest(), "checksum_valid": True})
        if s.name == "main":
            main = decoded
    for offset, h in packed_objects(main):
        entry = {"main_offset": offset, "dat_offset": PAYLOAD_BASE+offset, "header": asdict(h)}
        try:
            unpacked = decompress(main, offset)
            name = f"unpacked_{offset:08x}.bin"
            (destination / name).write_bytes(unpacked)
            entry.update(file=name, sha256=hashlib.sha256(unpacked).hexdigest(), decoded=True,
                         validation="Exact declared output size and token bounds; hardware output equivalence not yet established")
        except DecodeError as exc:
            entry.update(decoded=False, error=str(exc))
        report["packed_objects"].append(entry)
    (destination / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
