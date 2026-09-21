"""Bounded native RAW resource-plan assignment, not a complete coordinator."""

from .emulation import run_function
from .pipeline import modules, compact_execution
from .runtime import sparse_page
from .synchronization import STACK


def raw_resource_plan(directory):
    # This basic block is in the coordinator that prepares RAW development.
    # Its caller/context acquisition and subsequent file reader are NOT run.
    result = run_function({
        'architecture': 'arm', 'entry': 0x21ed068, 'stop': 0x21ed070,
        'regions': [*modules(directory), sparse_page(0x6000000, [], write_initializes=True)],
        'registers': {'R0': 0x6000000, 'SP': STACK, 'CPSR': 0x13},
        'outputs': [{'address': 0x600003b, 'size': 1}],
        'memory_trace': [{'address': 0x6000000, 'size': 4096}],
        'instruction_limit': 10,
        'provenance': {'scope': 'Isolated native assignment of RAW resource plan 6 to a supplied context',
                       'coordinator_executed': False, 'source_pixel_compatibility_validated': False,
                       'patched_instructions': False, 'stubs': []}})
    writes = [a for a in result['memory_trace'] if a['access'] == 'write']
    if (not result['reached_stop'] or result['faults']
            or result['outputs'][0]['hex'] != '06'
            or len(writes) != 1 or writes[0]['address'] != '0x600003b'
            or writes[0]['size'] != 1 or writes[0]['pc'] != '0x21ed06c'):
        raise ValueError('Native RAW resource-plan assignment failed')
    value = bytes.fromhex(result['outputs'][0]['hex'])
    return value, {'passed': True, 'plan': 6, 'transferred_offset': '0x3b',
                   'scope': 'Explicit partial coordinator preparation; full RAW setup remains unexecuted',
                   'execution': compact_execution(result, 0)}


def dma_initialization_frontier(directory):
    """Run the real DMA initializer to its first unavailable MMIO read.

    This faulted execution is diagnostic only. None of its RAM is resumed.
    """
    import struct
    from .synchronization import system_runtime_regions, STOP

    pages = [0x1788000, 0x1789000, 0x64000, 0x7a000]
    result = run_function({
        'architecture': 'arm', 'entry': 0x11ac684, 'stop': STOP,
        'regions': [*modules(directory), *system_runtime_regions(directory),
                    *[sparse_page(p, [(0xcd0, bytes(4))] if p == 0x7a000 else [],
                                  write_initializes=True) for p in pages],
                    sparse_page(0x700f000, [], write_initializes=True)],
        'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13},
        'outputs': [{'address': p, 'size': 4096} for p in pages],
        'memory_trace': [{'address': p, 'size': 4096} for p in pages],
        'register_trace': [0x11ac6a4, 0x127e1e4, 0x11adacc, 0x5aa38],
        'instruction_limit': 5000,
        'provenance': {'scope': 'Actual DMA initializer, stopped by unmapped hardware; no RAM transferred',
                       'initial_semaphore_slot': 'Explicit unregistered cold-start slot 0x7acd0=0; not a live dump',
                       'hardware_emulated': False, 'patched_instructions': False, 'stubs': []}})
    from .messaging import output_bytes
    calls = {s['pc']: s['registers'] for s in result['register_trace']}
    result['checks'] = {
        'native_channel_count': calls.get('0x11ac6a4', {}).get('R0') == '0x8',
        'native_semaphore_arguments': all(calls.get('0x127e1e4', {}).get(k) == v
                                          for k, v in {'R0': '0xe4', 'R1': '0x8'}.items()),
        'native_software_state_cleared': output_bytes(result, 0x1788fe8, 0x18) == bytes(0x18)
            and output_bytes(result, 0x1789000, 0x2ac) == bytes(0x2ac),
        'native_semaphore_constructed': output_bytes(result, 0x64324, 20) == struct.pack('<5I', 0, 8, 8, 8, 0)
            and output_bytes(result, 0x7acd0, 4) == struct.pack('<I', 0x64324),
        'first_hardware_register_requested': calls.get('0x5aa38', {}).get('R0') == '0xfffe0000',
        'expected_hardware_frontier': len(result['faults']) == 1
            and result['faults'][0]['address'] == '0xfffe0000' and result['faults'][0]['size'] == 4
            and result['faults'][0]['pc'] == '0x5aa40' and not result['reached_stop'],
        'observations_complete': not result['memory_trace_truncated'] and not result['register_trace_truncated']}
    result['passed'] = all(result['checks'].values())
    result['ram_transferred'] = False
    return compact_execution(result, 0)
