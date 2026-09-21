from pathlib import Path
import tempfile
import unittest

from kora.messaging import output_bytes
from kora.orchestration import orchestrator_probe
from kora.resource_plan import raw_resource_plan, dma_initialization_frontier
from kora.requests_runtime import request_runtime
from kora.dma import descriptor_probe, control_probe, callback_probe, task_flag_attribute_frontier
from kora.task_initialization import task_initialization_probe
from kora.boot_task import boot_task_probe, boot_lock_initialization_probe


class ResourcePlanTests(unittest.TestCase):
    def test_plan_requires_full_configuration_preconditions(self):
        with self.assertRaisesRegex(ValueError, 'extended configuration'):
            orchestrator_probe(Path('unused'), with_raw_resource_plan=True)

    def test_changed_native_code_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'unpacked_00260000.bin').write_bytes(b'changed firmware')
            for probe in (raw_resource_plan, dma_initialization_frontier, descriptor_probe, control_probe,
                          callback_probe, task_flag_attribute_frontier, task_initialization_probe,
                          boot_task_probe, boot_lock_initialization_probe):
                with self.subTest(probe=probe.__name__):
                    with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                        probe(Path(directory))

    def test_callback_probe_rejects_unstudied_attributes(self):
        for attribute in (True, -1, 1, 8, '4'):
            with self.subTest(attribute=attribute):
                with self.assertRaisesRegex(ValueError, 'Event flag attribute'):
                    callback_probe(Path('unused'), attribute)

    def test_startup_selector_is_strict_and_firmware_is_pinned(self):
        for value in (0, 1, None, 'startup'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'startup must be a boolean'):
                    task_initialization_probe(Path('unused'), startup=value)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'unpacked_00260000.bin').write_bytes(b'changed firmware')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                task_initialization_probe(Path(directory), startup=True)

    def test_request_modes_cannot_escape_the_studied_tables(self):
        for mode in (-1, 8, 256, True, '7', 3):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, 'Request mode'):
                    request_runtime(Path('unused'), mode)
                with self.assertRaisesRegex(ValueError, 'Request mode'):
                    orchestrator_probe(Path('unused'), request_mode=mode)
        with self.assertRaisesRegex(ValueError, 'request initialization'):
            orchestrator_probe(Path('unused'), request_mode=7)

    def test_stack_observation_can_cross_page_inside_one_output(self):
        raw = bytes(range(256))*32
        result = {'outputs': [{'address': '0x7000000', 'size': len(raw), 'hex': raw.hex()}]}
        self.assertEqual(output_bytes(result, 0x7000ff8, 24), raw[0xff8:0x1010])
        self.assertEqual(output_bytes(result, 0x7001ff0, 16), raw[-16:])

    def test_incomplete_output_is_never_returned_as_a_short_read(self):
        for output in [
            {'address': '0x1000', 'size': 4, 'hex': '01020304'},
            {'address': '0x1000', 'size': 4096, 'hex': '01'},
            {'address': '0x1000', 'error': 'unmapped'}]:
            with self.subTest(output=output):
                with self.assertRaisesRegex(ValueError, 'No complete output'):
                    output_bytes({'outputs': [output]}, 0x1002, 4)
