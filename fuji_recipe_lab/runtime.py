"""Explicit RAM fixtures for the native cached-calendar metadata path.

These are chosen runtime inputs, not recovered camera RAM or ISP calibration.
All unspecified bytes stay inaccessible. Native code performs locking,
calendar adjustment and formatting without callbacks or instruction patches.
"""
from datetime import datetime
from pathlib import Path

from .pipeline import system_module, SYSTEM_SHA256

DEFAULT_CALENDAR = datetime(2026, 9, 11, 12, 34, 56)


def sparse_page(address: int, fields: list[tuple[int, bytes]], permissions="rw", write_initializes=False):
    data = bytearray(b"\xcc"*4096)
    occupied = set()
    ranges = []
    for offset, value in fields:
        indexes = set(range(offset, offset+len(value)))
        if not value or offset < 0 or offset+len(value) > 4096 or occupied & indexes:
            raise ValueError("Sparse fields must be nonempty, disjoint and within one page")
        data[offset:offset+len(value)] = value
        occupied.update(indexes)
        ranges.append({"offset": offset, "size": len(value)})
    return {"address": address, "size": 4096, "permissions": permissions, "hex": data.hex(),
            "valid_ranges": ranges, "write_initializes": write_initializes}


def calendar_regions(directory: Path, date: datetime = DEFAULT_CALENDAR):
    if not 2000 <= date.year <= 2099 or date.tzinfo is not None or date.microsecond:
        raise ValueError("Calendar fixture requires a whole-second naive date in 2000..2099; UTC offset is explicitly zero")
    system = system_module(directory)
    encoded = bytes([date.year-2000, date.month, date.day, date.hour, date.minute, date.second])
    return [
        {"address": 0x40000, "size": 0x1c000, "permissions": "rx", "hex": system.hex(),
         "expected_sha256": SYSTEM_SHA256, "initialized_only": True},
        sparse_page(0x01791000, [(0x688, bytes(4)), (0x6b0, encoded)]),
        sparse_page(0x01b84000, [(0x41c, b"\0"), (0xff0, b"\0"), (0xff2, b"\0"),
                               (0xff4, b"\0"), (0xff6, b"\1")], "r")]
