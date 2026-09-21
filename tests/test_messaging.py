from pathlib import Path
import tempfile
import unittest

from kora.messaging import merge_sparse_regions, message_runtime, resume_regions
from kora.runtime import sparse_page
from kora.orchestration import orchestrator_probe


class MessageStateTests(unittest.TestCase):
    def test_merging_native_tables_preserves_holes(self):
        merged = merge_sparse_regions([sparse_page(0x1000, [(4, b'ab')], 'r'),
                                       sparse_page(0x1000, [(5, b'bc'), (20, b'x')], write_initializes=True)])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['valid_ranges'], [{'offset': 4, 'size': 3}, {'offset': 20, 'size': 1}])
        self.assertEqual(bytes.fromhex(merged[0]['hex'])[7:20], b'\xcc'*13)
        self.assertTrue(merged[0]['write_initializes'])

    def test_conflicting_native_snapshots_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            merge_sparse_regions([sparse_page(0x1000, [(4, b'ab')]), sparse_page(0x1000, [(5, b'z')])])

    def test_incomplete_orchestration_cannot_feed_receiver(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            resume_regions({}, {'reached_stop': False, 'faults': []})

    def test_message_constructors_require_pinned_firmware(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'main.bin').write_bytes(b'not the Fuji firmware')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                message_runtime(Path(directory))

    def test_configuration_variants_require_explicit_bounded_exploration(self):
        for value, receiver in [(-1, True), (256, True), (True, True), (0, False)]:
            with self.subTest(value=value, receiver=receiver), self.assertRaisesRegex(ValueError, 'cfg_feb0'):
                orchestrator_probe(Path('unused'), with_receiver=receiver, cfg_feb0=value)
