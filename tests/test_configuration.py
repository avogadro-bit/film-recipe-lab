from pathlib import Path
import hashlib
import tempfile
import unittest

from kora.bootstrap import wb_boot_padding
from kora.configuration import configuration_page, firmware_configuration, CFG
from kora.orchestration import orchestrator_probe


class ConfigurationProvenanceTests(unittest.TestCase):
    def test_marker_alone_does_not_authorize_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            data = bytearray(0x132000)
            data[0xc0202:0xc0204] = b'\x55\xaa'
            Path(directory, 'main.bin').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                firmware_configuration(Path(directory))

    def test_boot_descriptor_requires_pinned_source(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'main.bin').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                wb_boot_padding(Path(directory))

    def test_configuration_page_does_not_extend_recovered_data(self):
        for offset in (-4096, 1, 4096, True):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'aligned'):
                configuration_page(bytes(4096), offset)

    def test_configuration_page_is_exact_and_read_only(self):
        prefix = bytes(range(256))*32
        page = configuration_page(prefix, 4096)
        self.assertEqual(page['address'], CFG+4096)
        self.assertEqual(bytes.fromhex(page['hex']), prefix[4096:])
        self.assertEqual(page['permissions'], 'r')
        self.assertEqual(page['expected_sha256'], hashlib.sha256(prefix[4096:]).hexdigest())

    def test_conflicting_modes_rejected_before_firmware_access(self):
        for args in ({'with_firmware_config': True},
                     {'with_firmware_config': True, 'with_receiver': True, 'cfg_feb0': 0},
                     {'with_boot_wb': True}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                orchestrator_probe(Path('unused'), **args)
