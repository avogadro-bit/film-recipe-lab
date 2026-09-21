from pathlib import Path
import tempfile
import unittest

from kora.white_balance import _execute, INPUT, white_balance_probe


class WhiteBalanceGuardTests(unittest.TestCase):
    def execute_read(self, offset):
        # Authored ARM LDRB r0,[r0,#offset]; BX lr. No proprietary code needed.
        code = (0xe5d00000+offset).to_bytes(4, 'little') + bytes.fromhex('1eff2fe1')
        return _execute([{'address': 0x10000, 'size': 4096, 'permissions': 'rx',
                          'hex': code.hex(), 'initialized_only': True}],
                        0x10000, bytes(range(11)), {'R0': INPUT})

    def test_unknown_padding_cannot_be_read(self):
        result = self.execute_read(11)
        self.assertFalse(result['reached_stop'])
        self.assertEqual(result['faults'][0]['address'], hex(INPUT+11))

    def test_last_defined_field_remains_readable(self):
        result = self.execute_read(10)
        self.assertTrue(result['reached_stop'])
        self.assertEqual(result['registers']['R0'], '0xa')

    def test_absent_calibration_cannot_be_read(self):
        code = [{'address': 0x10000, 'size': 4096, 'permissions': 'rx',
                 'hex': '0000d0e51eff2fe1', 'initialized_only': True}]
        result = _execute(code, 0x10000, b'', {'R0': 0x680f55d})
        self.assertFalse(result['reached_stop'])
        self.assertEqual(result['faults'][0]['address'], '0x680f55d')

    def test_wrong_firmware_rejected_before_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'unpacked_00260000.bin').write_bytes(b'wrong firmware')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                white_balance_probe(Path(directory))
