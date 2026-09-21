import unittest
from kora.emulation import run_function


class RegisterTraceTests(unittest.TestCase):
    def test_samples_observe_registers_before_instruction(self):
        result = run_function({'architecture': 'arm', 'entry': 0x10000, 'stop': 0x20000,
                               'regions': [{'address': 0x10000, 'size': 4096, 'permissions': 'rx',
                                            'hex': '010080e21eff2fe1'}],
                               'registers': {'R0': 41, 'LR': 0x20000},
                               'register_trace': [0x10000, 0x10004, 0x10004]})
        self.assertTrue(result['reached_stop'])
        self.assertEqual([s['registers']['R0'] for s in result['register_trace']], ['0x29', '0x2a'])
        self.assertEqual(result['register_trace_total'], 2)
        self.assertFalse(result['register_trace_truncated'])

    def test_trace_budget_does_not_stop_execution(self):
        result = run_function({'architecture': 'arm', 'entry': 0x10000, 'stop': 0x20000,
                               'regions': [{'address': 0x10000, 'size': 4096, 'permissions': 'rx', 'hex': 'feffffea'}],
                               'instruction_limit': 12, 'register_trace': [0x10000], 'register_trace_limit': 2})
        self.assertEqual(result['instructions'], 12)
        self.assertEqual(result['register_trace_total'], 12)
        self.assertEqual(len(result['register_trace']), 2)
        self.assertTrue(result['register_trace_truncated'])

    def test_register_trace_has_explicit_bounds(self):
        for extra in ({'register_trace': [-1]}, {'register_trace': list(range(65))},
                      {'register_trace_limit': 0}, {'register_trace_limit': 1025}):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'register_trace'):
                run_function({'architecture': 'arm', 'entry': 0x10000, 'stop': 0x20000, 'regions': [], **extra})
