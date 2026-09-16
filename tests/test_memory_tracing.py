import unittest

from fuji_recipe_lab.emulation import run_function


class MemoryTracingTests(unittest.TestCase):
    def guarded_load(self, pointer):
        return run_function({
            "architecture": "arm", "entry": 0x10000, "stop": 0x20000,
            "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx", "hex": "000091e51eff2fe1", "initialized_only": True},
                        {"address": 0x30000, "size": 4096, "permissions": "r", "hex": "01020304", "initialized_only": True}],
            "registers": {"R1": pointer, "LR": 0x20000}, "instruction_limit": 8})

    def test_guarded_data_is_readable_but_page_padding_is_not(self):
        result = self.guarded_load(0x30000)
        self.assertTrue(result["reached_stop"])
        self.assertEqual(result["registers"]["R0"], "0x4030201")
        for pointer in [0x30002, 0x30004]:
            with self.subTest(pointer=pointer):
                result = self.guarded_load(pointer)
                self.assertFalse(result["reached_stop"])
                self.assertEqual(result["faults"][0]["pc"], "0x10000")
                self.assertIn("initialized", result["faults"][0]["reason"])

    def test_instruction_fetch_into_padding_stops(self):
        result = run_function({
            "architecture": "arm", "entry": 0x10000, "stop": 0x20000,
            "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx", "hex": "0000a0e1", "initialized_only": True}],
            "instruction_limit": 8})
        self.assertFalse(result["reached_stop"])
        self.assertEqual(result["faults"][0]["access"], "fetch")
        self.assertEqual(result["faults"][0]["address"], "0x10004")

    def test_trace_limits_and_overlapping_watch_ranges(self):
        result = run_function({
            "architecture": "arm", "entry": 0x10000, "stop": 0x20000,
            "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx", "hex": "000081e5002091e51eff2fe1"},
                        {"address": 0x30000, "size": 4096, "permissions": "rw"}],
            "registers": {"R0": 0x12345678, "R1": 0x30000, "LR": 0x20000},
            "memory_trace": [{"address": 0x30000, "size": 4}, {"address": 0x30002, "size": 4}],
            "memory_trace_limit": 1, "outputs": [{"address": 0x30000, "size": 4}]})
        self.assertTrue(result["reached_stop"])
        self.assertEqual(result["memory_trace_total"], 2)
        self.assertTrue(result["memory_trace_truncated"])
        self.assertEqual(len(result["memory_trace"]), 1)
        self.assertEqual(result["memory_trace"][0]["write_value"], "0x12345678")
        self.assertEqual(result["outputs"][0]["hex"], "78563412")

    def test_write_to_padding_is_reported(self):
        result = run_function({
            "architecture": "arm", "entry": 0x10000, "stop": 0x20000,
            "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx", "hex": "000081e51eff2fe1"},
                        {"address": 0x30000, "size": 4096, "permissions": "rw", "hex": "00000000", "initialized_only": True}],
            "registers": {"R0": 1, "R1": 0x30004, "LR": 0x20000}})
        self.assertFalse(result["reached_stop"])
        self.assertEqual(result["faults"][0]["access"], "write")

    def test_sparse_ranges_keep_unknown_holes_forbidden(self):
        for pointer, passed in [(0x30000, True), (0x30004, False), (0x30008, True)]:
            with self.subTest(pointer=pointer):
                result = run_function({
                    "architecture": "arm", "entry": 0x10000, "stop": 0x20000,
                    "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx", "hex": "000091e51eff2fe1"},
                                {"address": 0x30000, "size": 4096, "permissions": "r", "hex": "01020304cccccccc05060708",
                                 "valid_ranges": [{"offset": 0, "size": 2}, {"offset": 2, "size": 2}, {"offset": 8, "size": 4}]}],
                    "registers": {"R1": pointer, "LR": 0x20000}})
                self.assertEqual(result["reached_stop"], passed)
                if not passed:
                    self.assertIn("initialized", result["faults"][0]["reason"])

    def test_wrong_code_hash_is_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            run_function({"architecture": "arm", "entry": 0x10000, "stop": 0x20000,
                          "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx",
                                       "hex": "1eff2fe1", "expected_sha256": "0"*64}]})

    def dynamic_ram(self, code, **changes):
        region = {"address": 0x30000, "size": 4096, "permissions": "rw", "hex": "cc"*4096,
                  "valid_ranges": [], "write_initializes": True, **changes}
        return run_function({
            "architecture": "arm", "entry": 0x10000, "stop": 0x20000,
            "regions": [{"address": 0x10000, "size": 4096, "permissions": "rx", "hex": code}, region],
            "registers": {"R0": 0x12345678, "R1": 0x30000, "LR": 0x20000},
            "instruction_limit": 12})

    def test_native_write_initializes_only_written_bytes(self):
        # STRB r0,[r1]; LDRB r2,[r1]; BX lr.
        result = self.dynamic_ram("0000c1e50020d1e51eff2fe1")
        self.assertTrue(result["reached_stop"])
        self.assertEqual(result["registers"]["R2"], "0x78")
        self.assertEqual(result["regions"][1]["final_valid_ranges"], [{"address": "0x30000", "size": 1}])
        # The same byte store does not make a four-byte load valid.
        result = self.dynamic_ram("0000c1e5002091e51eff2fe1")
        self.assertFalse(result["reached_stop"])
        self.assertEqual(result["faults"][0]["access"], "read")
        self.assertEqual(result["faults"][0]["pc"], "0x10004")

    def test_dynamic_ram_rejects_read_before_initialization(self):
        result = self.dynamic_ram("000091e51eff2fe1")
        self.assertFalse(result["reached_stop"])
        self.assertEqual(result["regions"][1]["final_valid_ranges"], [])

    def test_native_writes_merge_with_explicit_initial_bytes(self):
        # Write a word adjacent to an existing word, then read it back.
        result = self.dynamic_ram("000081e5002091e51eff2fe1", valid_ranges=[{"offset": 4, "size": 4}])
        self.assertTrue(result["reached_stop"])
        self.assertEqual(result["registers"]["R2"], "0x12345678")
        self.assertEqual(result["regions"][1]["final_valid_ranges"], [{"address": "0x30000", "size": 8}])

    def test_register_write_capture_cannot_be_read_back_as_hardware_status(self):
        result = self.dynamic_ram('000081e5002091e51eff2fe1', permissions='w')
        self.assertFalse(result['reached_stop'])
        self.assertEqual(result['regions'][1]['final_valid_ranges'], [{'address': '0x30000', 'size': 4}])
        self.assertEqual(result['registers']['R2'], '0x0')
        self.assertTrue(any(f['address'] == '0x30000' and f['access'] == 23 for f in result['faults']))

    def test_dynamic_initialization_requires_writable_guarded_ram(self):
        with self.assertRaisesRegex(ValueError, "guarded writable"):
            self.dynamic_ram("1eff2fe1", permissions="r")
        with self.assertRaisesRegex(ValueError, "guarded writable"):
            run_function({"architecture": "arm", "entry": 0x10000, "stop": 0x20000,
                          "regions": [{"address": 0x10000, "size": 4096, "permissions": "rw",
                                       "write_initializes": True}]})
