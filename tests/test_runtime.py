from datetime import datetime, timezone
from pathlib import Path
import unittest
import struct
import tempfile
from unittest.mock import patch

from fuji_recipe_lab.runtime import calendar_regions, sparse_page
from fuji_recipe_lab.synchronization import object_addresses
from fuji_recipe_lab.requests_runtime import snapshot_native_ram
from fuji_recipe_lab.raf_metadata import metadata_entries, read_metadata
from fuji_recipe_lab.resources import resource_inputs


class RuntimeInputTests(unittest.TestCase):
    def test_resource_probe_rejects_changed_metadata_before_reuse(self):
        with patch("fuji_recipe_lab.resources.metadata_probe", return_value={"passed": True, "source": {"metadata_sha256": "before"}}), \
             patch("fuji_recipe_lab.resources.read_metadata", return_value=(b"", [], {"metadata_sha256": "after"})):
            with self.assertRaisesRegex(ValueError, "changed"):
                resource_inputs(Path("unused"), Path("unused.RAF"), [])

    def test_calendar_rejects_unrepresentable_dates_before_firmware_access(self):
        for date in [datetime(1999, 12, 31), datetime(2100, 1, 1),
                     datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, microsecond=1)]:
            with self.subTest(date=date), self.assertRaisesRegex(ValueError, "whole-second naive"):
                calendar_regions(Path("does-not-exist"), date)

    def test_sparse_fields_reject_overlap_and_page_overflow(self):
        for fields in [[(0, b"")], [(-1, b"a")], [(4095, b"aa")], [(1, b"aa"), (2, b"b")]]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                sparse_page(0x10000, fields)

    def test_synchronization_ids_cannot_escape_native_table(self):
        for identifier in [0, -1, 251, True, 1.0]:
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                object_addresses(identifier)

    def test_snapshot_preserves_unknown_holes(self):
        execution = {"reached_stop": True,
                     "regions": [{"address": "0x10000", "size": 4096,
                                  "final_valid_ranges": [{"address": "0x10002", "size": 2}]}],
                     "outputs": [{"address": "0x10000", "hex": "01"*4096}]}
        region = snapshot_native_ram(execution, [0x10000])[0]
        self.assertEqual(region["valid_ranges"], [{"offset": 2, "size": 2}])
        self.assertEqual(bytes.fromhex(region["hex"])[:6], b"\xcc\xcc\1\1\xcc\xcc")
        self.assertFalse(region["write_initializes"])

    def test_snapshot_rejects_incomplete_execution(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            snapshot_native_ram({"reached_stop": False}, [0x10000])

    def test_raf_metadata_rejects_truncation_and_excess_entries(self):
        for block in [b"", struct.pack(">I", 256), struct.pack(">I", 1),
                      struct.pack(">IHH", 1, 0x100, 4)+b"\0\0"]:
            with self.subTest(block=block), self.assertRaises(ValueError):
                metadata_entries(block)

    def test_raf_metadata_range_checked_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"synthetic.RAF"
            header = bytearray(108)
            header[:16] = b"FUJIFILMCCD-RAW "
            for offset, size in [(0, 4), (108, 0), (108, 100), (108, 1048577)]:
                struct.pack_into(">II", header, 92, offset, size)
                path.write_bytes(header)
                with self.subTest(offset=offset, size=size), self.assertRaises(ValueError):
                    read_metadata(path)

    def test_raf_metadata_extracts_exact_declared_bytes_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"synthetic.RAF"
            header = bytearray(108)
            header[:16] = b"FUJIFILMCCD-RAW "
            block = struct.pack(">IHHHH", 1, 0x100, 4, 5196, 7872)
            struct.pack_into(">II", header, 92, 108, len(block))
            source = bytes(header)+block+b"not-pixel-data"
            path.write_bytes(source)
            observed, entries, provenance = read_metadata(path)
            self.assertEqual(observed, block)
            self.assertEqual(entries, [(0x100, struct.pack(">HH", 5196, 7872))])
            self.assertEqual(provenance["metadata_offset"], 108)
            self.assertEqual(path.read_bytes(), source)


if __name__ == "__main__":
    unittest.main()
