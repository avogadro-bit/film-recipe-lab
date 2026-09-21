import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np
import tifffile
from pydantic import ValidationError

from kora.compare import compare
from kora.engine import ExactEngineUnavailable, render_exact
from kora.firmware import inspect_firmware
from kora.recipe import Recipe
from kora.emulation import run_function, self_test


class WorkbenchTests(unittest.TestCase):
    def test_exact_engine_does_not_write_a_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "result.jpg"
            with self.assertRaises(ExactEngineUnavailable):
                render_exact(Path(d) / "source.raf", Recipe(), out)
            self.assertFalse(out.exists())

    def test_recipe_rejects_unknown_and_nonfinite(self):
        for data in [{"film": "invented"}, {"exposure": float("nan")}, {"wb_red": 10}, {"highlights": 0.3}, {"unknown": 1}]:
            with self.assertRaises(ValidationError):
                Recipe(**data)
        self.assertTrue(Recipe(film="reala_ace").unsupported())
        self.assertEqual(Recipe.model_validate_json(Recipe().model_dump_json()), Recipe())

    def test_uint16_comparison_preserves_one_code_difference(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.tiff", Path(d) / "b.tiff"
            data = np.full((4, 4, 3), 40000, dtype=np.uint16)
            tifffile.imwrite(a, data, photometric="rgb")
            self.assertTrue(compare(a, a)["pixel_identical"])
            data[1, 1, 0] += 1
            tifffile.imwrite(b, data, photometric="rgb")
            result = compare(a, b)
            self.assertFalse(result["pixel_identical"])
            self.assertEqual(result["changed_samples"], 1)
            self.assertEqual(result["max_abs_error"], 1)

    def test_shape_mismatch_is_not_resized(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.npy", Path(d) / "b.npy"
            np.save(a, np.zeros((2, 2, 3)))
            np.save(b, np.zeros((3, 3, 3)))
            self.assertFalse(compare(a, b)["comparable"])

    def test_firmware_reconnaissance_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "synthetic.dat"
            data = bytearray(1024)
            struct.pack_into("<I", data, 0, 6)
            struct.pack_into("<II", data, 516, 2, 0x12)
            text = b"CLASSICNEGA"
            data[700:710] = bytes(255 - x for x in text)
            p.write_bytes(data)
            result = inspect_firmware(p)
            self.assertEqual(result["version_display_candidate"], "2.12")
            self.assertEqual(result["keyword_matches"][0]["file_offset"], "0x2bc")
            self.assertEqual(p.read_bytes(), data)

    def test_all_emulator_architectures(self):
        self.assertTrue(self_test()["passed"])

    def test_unknown_hardware_memory_is_a_fault(self):
        # ARM LDR r0,[r1]; BX lr. r1 points outside all declared regions.
        result = run_function({"architecture": "arm", "entry": "0x10000", "stop": "0x20000", "regions": [{"address": "0x10000", "size": 4096, "permissions": "rx", "hex": "000091e51eff2fe1"}], "registers": {"R1": "0x40000000", "LR": "0x20000"}})
        self.assertFalse(result["reached_stop"])
        self.assertEqual(result["faults"][0]["address"], "0x40000000")

    def test_infinite_loop_stops_at_budget(self):
        result = run_function({"architecture": "arm", "entry": "0x10000", "stop": "0x20000", "regions": [{"address": "0x10000", "size": 4096, "permissions": "rx", "hex": "feffffea"}], "instruction_limit": 12})
        self.assertFalse(result["reached_stop"])
        self.assertEqual(result["instructions"], 12)


if __name__ == "__main__":
    unittest.main()
