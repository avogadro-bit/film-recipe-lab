"""Native heap and RAW task construction on explicit cold-start fixtures.

Allocated addresses are produced by firmware, never supplied as call results.
Heap contents and the caller's previous stack remain unknown until written.
"""
import struct

from .emulation import run_function
from .messaging import merge_sparse_regions, output_bytes
from .pipeline import modules, compact_execution
from .requests_runtime import snapshot_native_ram
from .runtime import sparse_page
from .synchronization import system_runtime_regions, STACK, STOP

HEAP = 0x6a00000
HEAP_SIZE = 0x10000
PARAMETERS = 0x6e00000


def task_initialization_probe(directory, *, startup=False):
    if type(startup) is not bool:
        raise ValueError('startup must be a boolean')
    identifier = 26 if startup else 9
    slot = identifier-1
    entry_point = 0x2120c20 if startup else 0x21cb604
    code = modules(directory)
    system = system_runtime_regions(directory)
    ram = merge_sparse_regions([
        system[1], sparse_page(0x5b000, [(0xec, bytes(4)), (0xd8, bytes(4))], write_initializes=True),
        sparse_page(0x79000, [(0xfd8, bytes(4))], write_initializes=True),
        sparse_page(0x7a000, [], write_initializes=True),
        sparse_page(0x5d000, [(0x1c8+4*slot, bytes(4)), (0x5b0+4*slot, bytes(4))], write_initializes=True),
        *([sparse_page(0x5e000, [], write_initializes=True),
           sparse_page(0x7b000, [], write_initializes=True)] if startup else []),
        sparse_page(0x1b67000, [(0x6ec, struct.pack('<I', 1))], write_initializes=True),
        sparse_page(0x1a22000, [(0x8d0, struct.pack('<I', 1)), (0x8d4+8*slot, bytes(8))], write_initializes=True),
        sparse_page(0x18ea000, [], write_initializes=True),
        *[sparse_page(a, [], write_initializes=True) for a in
          (0x2d1d000, 0x31d4000, 0x336b000, 0x3678000, 0x367c000, 0x3726000)],
        *[sparse_page(a, [], write_initializes=True) for a in range(HEAP, HEAP+HEAP_SIZE, 4096)]])
    pages = [r['address'] for r in ram]
    stages = []
    checks = {}
    allocations = []
    for name, entry, stop, registers, config in [
        ('heap_constructor', 0x4ba4c, STOP, {'R0': 1, 'R1': PARAMETERS}, struct.pack('<III', 0, HEAP_SIZE, HEAP)),
        ('startup_constructor' if startup else 'raw_task_constructor', entry_point, STOP,
         {} if startup else {'R0': 7}, None),
    ]:
        result = run_function({
            'architecture': 'arm', 'entry': entry, 'stop': stop,
            'regions': [*code, system[0], *ram,
                        *([sparse_page(PARAMETERS, [(0, config)], 'r')] if config else []),
                        sparse_page(0x700f000, [], write_initializes=True)],
            'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13, **registers},
            'outputs': [{'address': a, 'size': 4096} for a in [*pages, 0x700f000]],
            'register_trace': [0x2246f7c, 0x21d4050, 0x21cf870, 0x21f2b48, 0x21d4064,
                               0x21ee4f8, 0x21ef6e4, 0x21ef1e8, 0x21ee538,
                               0x21f096c, 0x21f08ac, 0x22047c0,
                               0x4f4d8, 0x4af4c, 0x4b830, 0x127d76c, 0x127d7c0],
            'memory_trace': [{'address': 0x700f000, 'size': 4096}],
            'memory_trace_limit': 10000, 'instruction_limit': 50000,
            'provenance': {'scope': 'Native constructor with explicit empty heap/queue registries and synthetic arena',
                           'heap_id_fixture': 1, 'heap_base_fixture': hex(HEAP), 'heap_size_fixture': HEAP_SIZE,
                           'task_arguments_source': 'Native caller 0x2120c20' if startup else 'Native table 0x25eb468 read by caller 0x21f08ac',
                           'coordinator_id_fixture': None if startup else 7,
                           'earlier_task_7_creation_executed': False,
                           'caller_stack_seeded': False,
                           'allocated_pointers_stubbed': False, 'patched_instructions': False, 'stubs': [],
                           'state_transferred_to_raw_receiver': False, 'image_pipeline_executed': False}})
        if name == 'heap_constructor':
            valid = (result['reached_stop'] and not result['faults']
                     and result['registers']['R0'] == '0x0'
                     and result['registers']['SP'] == hex(STACK)
                     and output_bytes(result, 0x79fd8, 4) == struct.pack('<I', 0x7a01c))
            if not valid:
                stages.append({'name': name, 'execution': compact_execution(result, 0)})
                return {'passed': False, 'failed_stage': name, 'stages': stages}
            ram = snapshot_native_ram(result, pages, write_initializes=True)
            checks['native_heap_registered'] = valid
        elif startup:
            descriptor = STACK-0x74
            missing = descriptor+24
            calls = [t['registers'] for t in result['register_trace'] if t['pc'] == '0x4f4d8']
            writes = [t for t in result['memory_trace'] if t['access'] == 'write']
            pool = output_bytes(result, 0x5e1d4, 0x30)
            checks.update({
                'first_task_arguments_native': [(t['registers']['R0'], t['registers']['R1'], t['registers']['R2'])
                    for t in result['register_trace'] if t['pc'] == '0x2246f7c'] == [('0x1a', '0x25bd09c', '0x3')],
                'native_allocations_requested': [(r['R0'], r['R1']) for r in calls]
                    == [('0x1', '0xc0'), ('0x1', '0x6c0'), ('0x1', '0x1400')],
                'native_queue_created': output_bytes(result, 0x7b0b0, 36)
                    == struct.pack('<9I', 0, 48, HEAP+8, HEAP+8, 0, 0, 0, 0, 0),
                'native_pool_created': struct.unpack_from('<I', pool)[0] == 0x424c4f43
                    and struct.unpack_from('<II', pool, 8) == (48, 48)
                    and struct.unpack_from('<I', pool, 0x10)[0] == HEAP+0xd0,
                'native_block_size_32': output_bytes(result, 0x18ead68, 4) == struct.pack('<I', 32),
                'native_stack_allocated': output_bytes(result, 0x1a2299c, 8) == struct.pack('<II', HEAP+0x798, 0x1400),
                'native_descriptor_created': output_bytes(result, descriptor, 24)
                    == struct.pack('<6I', 26, 0x25bd09c, 3, 0x1400, 0x22491fc, 26),
                'missing_word_never_written': not any(int(t['address'], 16) < missing+4
                    and int(t['address'], 16)+t['size'] > missing for t in writes),
                'first_task_attribute_unknown': not result['reached_stop'] and len(result['faults']) == 1
                    and result['faults'][0]['address'] == hex(missing)
                    and result['faults'][0]['pc'] == '0x127d7c0'
                    and result['faults'][0]['access'] == 'read',
                'observations_complete': not result['memory_trace_truncated'] and not result['register_trace_truncated'],
            })
            allocations = [{'purpose': purpose, 'address': hex(address), 'size': size}
                           for purpose, address, size in [('queue', HEAP+8, 192),
                               ('message_blocks', HEAP+0xd0, 1728), ('task_stack', HEAP+0x798, 5120)]]
        else:
            allocation_calls = [t['registers'] for t in result['register_trace'] if t['pc'] == '0x4f4d8']
            descriptor = STACK-0x7c
            missing = descriptor+24
            queue_buffer, pool_buffer, task_stack = HEAP+8, HEAP+0xd0, HEAP+0x1518
            pool = output_bytes(result, 0x5dc40, 0x30)
            writes = [t for t in result['memory_trace'] if t['access'] == 'write']
            checks.update({
                'predecessors_executed_in_order': [t['pc'] for t in result['register_trace'][:10]] == [
                    '0x21d4050', '0x21cf870', '0x21f2b48', '0x21d4064',
                    '0x21ee4f8', '0x21ef6e4', '0x21ef1e8', '0x21ee538', '0x21f096c', '0x21f08ac'],
                'native_status_array_cleared': output_bytes(result, 0x2d1d1f8, 16) == bytes(16),
                'native_secondary_array_cleared': output_bytes(result, 0x31d4070, 0x300) == bytes(0x300)
                    and output_bytes(result, 0x336b31c, 2) == bytes(2),
                'native_coordinator_registered': output_bytes(result, 0x3678e30, 1) == bytes([7]),
                'native_request_state_initialized': output_bytes(result, 0x3678e34, 1) == bytes(1)
                    and output_bytes(result, 0x3678e38, 4) == struct.pack('<I', 0xffffffff)
                    and output_bytes(result, 0x3678e40, 16) == struct.pack('<4I', 0, 0xffffffff, 0, 0xffffffff),
                'native_state_initialized': output_bytes(result, 0x367cfdc, 3) == bytes([0, 4, 0])
                    and output_bytes(result, 0x367cfe0, 20) == struct.pack('<5I', 0, 0xffffffff, 0, 0, 0),
                'native_buffer_pointer_initialized': output_bytes(result, 0x3726ff0, 4) == struct.pack('<I', 0x3726ff4),
                'task_arguments_read_from_rom': [(t['registers']['R0'], t['registers']['R1'], t['registers']['R2'])
                    for t in result['register_trace'] if t['pc'] == '0x22047c0'] == [('0x9', '0x251b754', '0x6')],
                'three_native_allocations_requested': [(r['R0'], r['R1']) for r in allocation_calls]
                    == [('0x1', '0xc0'), ('0x1', '0x1440'), ('0x1', '0x1400')],
                'native_queue_has_48_slots': output_bytes(result, 0x7ae4c, 36)
                    == struct.pack('<9I', 0, 48, queue_buffer, queue_buffer, 0, 0, 0, 0, 0),
                'native_pool_has_48_blocks': struct.unpack_from('<I', pool)[0] == 0x424c4f43
                    and struct.unpack_from('<II', pool, 8) == (48, 48)
                    and struct.unpack_from('<I', pool, 0x10)[0] == pool_buffer,
                'native_block_size_104': output_bytes(result, 0x18ead24, 4) == struct.pack('<I', 104),
                'queue_pool_allocation_registry': output_bytes(result, 0x1b67750, 12)
                    == struct.pack('<III', pool_buffer, queue_buffer, 0x1440),
                'task_stack_allocation_registry': output_bytes(result, 0x1a22914, 8)
                    == struct.pack('<II', task_stack, 0x1400),
                'six_native_descriptor_words': output_bytes(result, descriptor, 24)
                    == struct.pack('<6I', 9, 0x251b754, 6, 0x1400, 0x221a290, 9),
                'unknown_word_never_written': not any(int(t['address'], 16) < missing+4
                    and int(t['address'], 16)+t['size'] > missing for t in writes),
                'guard_stops_attribute_read': not result['reached_stop'] and len(result['faults']) == 1
                    and result['faults'][0]['address'] == hex(missing)
                    and result['faults'][0]['pc'] == '0x127d7c0'
                    and result['faults'][0]['access'] == 'read',
                'observations_complete': not result['memory_trace_truncated'] and not result['register_trace_truncated'],
            })
            allocations = [{'purpose': purpose, 'address': hex(address), 'size': size}
                           for purpose, address, size in [('queue', queue_buffer, 192),
                               ('message_blocks', pool_buffer, 5184), ('task_stack', task_stack, 5120)]]
        stages.append({'name': name, 'execution': compact_execution(result, 0)})
    return {'passed': all(checks.values()), 'checks': checks, 'allocations': allocations,
            'entry': hex(entry_point), 'missing_stack_word': hex(STACK-(0x5c if startup else 0x64)),
            'scope': 'Native startup to first task (26); prior stack unknown' if startup else
                     'Native heap and coordinator initialization through RAW task allocations; blocked by stack state predating 0x21cb604',
            'task_constructor_completed': False, 'live_event_attribute_recovered': False,
            'state_transferred_to_raw_receiver': False, 'image_pipeline_executed': False,
            'stages': stages}
