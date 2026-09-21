"""Isolated X-T4 WB arithmetic and calibration dependencies, never an image renderer.

Calibration numbers in this probe are distinguishable synthetic test inputs.
They must not be installed in the exact engine or used as camera defaults.
"""
import struct

from .emulation import run_function
from .pipeline import modules, compact_execution
from .runtime import sparse_page
from .synchronization import STACK, STOP

INPUT = 0x6000000
OUTPUT = 0x6100000
CFG = 0x6800000


def shift_offset(axis, shift):
    if axis not in (0, 1):
        raise ValueError('axis must be 0 or 1')
    if not -9 <= shift <= 9 or shift == 0:
        return None  # Native default is Q10 unity, including out-of-range values.
    return ((0xf55d, 0xf581)[axis] + 2*(shift-1) if shift > 0
            else (0xf56d, 0xf591)[axis] - 2*shift)


def selector_offset(selector):
    if not 1 <= selector <= 13:
        return None
    return 0xf700 + 4*(selector-1 if selector <= 5 else
                       5 if selector <= 11 else selector-6)


def fixture_value(offset):
    """Unique little-endian values; intentionally NOT recovered calibration."""
    return 700 + offset - 0xf55d


def _execute(code, entry, packet, registers, fields=(), include_count=False, provenance=None):
    regions = [*code, sparse_page(INPUT, [(0, packet)] if packet else [], 'r'),
               sparse_page(OUTPUT, [], write_initializes=True),
               sparse_page(0x17b2000, [(0x764, struct.pack('<I', CFG))], 'r'),
               sparse_page(CFG+0xf000, fields, 'r'),
               sparse_page(0x700f000, [], write_initializes=True)]
    if include_count:
        regions.extend([sparse_page(0x190d000, [(0x784, b'\0')], 'r'),
                        sparse_page(CFG+0x420000, [(0xf82, b'\x1f')], 'r')])
    return run_function({
        'architecture': 'arm', 'entry': entry, 'stop': STOP, 'regions': regions,
        'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13, **registers},
        'outputs': [{'address': OUTPUT, 'size': 6}],
        'memory_trace': [{'address': INPUT, 'size': 4096}, {'address': OUTPUT, 'size': 4096},
                         {'address': CFG, 'size': 0x430000}],
        'instruction_limit': 3000,
        'provenance': {'scope': 'Isolated native WB, synthetic gains and calibration fixtures',
                       'calibration_recovered': False, 'image_pipeline_executed': False,
                       'patched_instructions': False, 'stubs': [],
                       'configuration_fields': {hex(0xf000+o): v.hex() for o, v in fields},
                       'preset_count_fixture': 31 if include_count else None,
                       **(provenance or {})}})


def _returned(result, expected):
    return (result['reached_stop'] and not result['faults']
            and result['registers']['SP'] == hex(STACK)
            and bytes.fromhex(result['outputs'][0]['hex']) == struct.pack('<3H', *expected)
            and not result['memory_trace_truncated'])


def white_balance_probe(directory):
    code = modules(directory)  # Reject a different firmware before any execution.
    cases = []
    # First prove the address dependencies with absent calibration, not fake zeros.
    for axis in (0, 1):
        for shift in range(-9, 10):
            offsets = shift_offset(axis, shift)
            args = [0, 0]
            args[axis] = shift
            execution = _execute(code, 0x22a7cf4, b'', {'R0': args[0] & 0xffffffff,
                                  'R1': args[1] & 0xffffffff, 'R2': OUTPUT})
            if offsets is None:
                ok = _returned(execution, (1024, 1024, 1024))
            else:
                faults = execution['faults']
                ok = (not execution['reached_stop'] and len(faults) == 1
                      and faults[0]['address'] == hex(CFG+offsets)
                      and faults[0]['pc'] == '0x126396c' and faults[0]['size'] == 1)
            cases.append({'kind': 'calibration_dependency', 'axis': axis, 'shift': shift,
                          'expected_offset': hex(offsets) if offsets else None,
                          'passed': ok, 'execution': compact_execution(execution, 6)})

    # Exercise both active branches and the native bypass branch, with padding
    # byte +11 UNREADABLE in every case. No global BSS zeroing is assumed.
    vectors = [(r, 0, 0, 0) for r in range(-9, 10)]
    vectors += [(0, b, 0, 0) for b in range(-9, 10) if b]
    vectors += [(3, -7, preset, selector) for preset in (0, 15, 30, 255)
                for selector in (0, 1, 5, 6, 11, 12, 13, 255)]
    vectors += [(-10, 10, 0, 0), (-128, 127, 0, 0)]
    for mode in (0, 1, 2):
        for red, blue, preset, selector in vectors:
            gains = (1024, 1733, 2981)
            packet = struct.pack('<bbBB3HB', red, blue, preset, selector, *gains, mode)
            offsets = [shift_offset(0, red), shift_offset(1, blue)]
            preset_base = 0xf5a6+4*min(preset, 30)
            other = selector_offset(selector)
            needed = {o for o in [*offsets, preset_base, preset_base+2,
                                  other, other+2 if other else None] if o is not None}
            fields = [(o-0xf000, struct.pack('<H', fixture_value(o))) for o in sorted(needed)] if mode != 1 else []
            result = _execute(code, 0x22a830c, packet,
                              {'R0': INPUT, 'R1': OUTPUT, 'R2': 0, 'R3': 0}, fields,
                              include_count=mode != 1)
            expected = [gains[0]]
            for axis in (0, 1):
                factor = 1024
                if mode != 1:
                    factor = (fixture_value(offsets[axis]) if offsets[axis] else 1024)
                    factor *= fixture_value(preset_base+2*axis)
                    factor *= fixture_value(other+2*axis) if other else 1024
                    factor = (factor >> 20) & 0xffff
                expected.append((((factor*gains[axis+1]+512) & 0xffffffff) >> 10) & 0xffff)
            reads = {int(a['address'], 16)+i for a in result['memory_trace']
                     if a['access'] == 'read' for i in range(a['size'])}
            writes = {int(a['address'], 16)+i for a in result['memory_trace']
                      if a['access'] == 'write' for i in range(a['size'])}
            ok = (_returned(result, expected) and INPUT+11 not in reads
                  and writes == set(range(OUTPUT, OUTPUT+6)))
            cases.append({'kind': 'gain_arithmetic', 'red': red, 'blue': blue, 'preset': preset,
                          'selector': selector, 'mode': mode, 'input_hex': packet.hex(),
                          'expected_gains': expected, 'padding_unmapped': True,
                          'passed': ok, 'execution': compact_execution(result, 6)})
    return {'passed': all(c['passed'] for c in cases), 'cases': cases,
            'scope': 'Native isolated WB dependency and arithmetic tests, no image rendering',
            'camera_emulated': False, 'image_pipeline_validated': False,
            'calibration_recovered': False,
            'padding_scope': 'Byte +11 is unreadable for these calls to 0x22a830c with R2=0; global initialization is not recovered'}
