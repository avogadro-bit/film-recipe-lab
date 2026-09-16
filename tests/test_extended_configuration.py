from pathlib import Path
import tempfile
import unittest

from fuji_recipe_lab.configuration import CFG, install_configuration_prefix
from fuji_recipe_lab.extended_configuration import verified_default_block
from fuji_recipe_lab.orchestration import orchestrator_probe
from fuji_recipe_lab.runtime import sparse_page


class ExtendedConfigurationTests(unittest.TestCase):
    def test_changed_firmware_is_rejected_before_extended_read(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'main.bin').write_bytes(b'FLSNW001DEFAULT')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                verified_default_block(Path(directory))

    def test_conflicting_fixture_is_not_silently_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            install_configuration_prefix([sparse_page(CFG, [(3, b'\x01')], 'r')], bytes(4096))
        with self.assertRaisesRegex(ValueError, 'Unverifiable'):
            install_configuration_prefix([sparse_page(CFG, [(3, b'\0')], 'rw')], bytes(4096))

    def test_verified_page_replaces_only_compatible_fixture(self):
        other = sparse_page(CFG+0x2000, [(0, b'x')], 'r')
        result = install_configuration_prefix([sparse_page(CFG, [(3, b'\0')], 'r'), other], bytes(4096))
        self.assertEqual(result[0], other)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]['hex'], '00'*4096)
        self.assertEqual(result[1]['permissions'], 'r')

    def test_extended_mode_requires_native_boot_preparation(self):
        with self.assertRaisesRegex(ValueError, 'WB boot'):
            orchestrator_probe(Path('unused'), with_extended_config=True)
