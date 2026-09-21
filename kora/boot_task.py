"""Task-86 entry experiment with its native stack fill, without a scheduler.

The stack arena and entry SP are relocated test inputs. This is not a recovered
running context, and its RAM is never spliced into a later RAW call.
"""
import struct

from .emulation import run_function
from .messaging import output_bytes
from .pipeline import modules, compact_execution
from .requests_runtime import snapshot_native_ram
from .runtime import sparse_page
from .synchronization import system_runtime_regions, STOP

SCRATCH = 0x700e000
FRAME = SCRATCH+0xff0
TASK_STACK = 0x700f000


def boot_lock_initialization_probe(directory):
    pages = [*range(0x178c000, 0x1790000, 4096), 0x1949000]
    code = modules(directory)
    ram = [sparse_page(p, [], write_initializes=True) for p in pages]
    stages = []
    checks = {}
    for name, entry in [('driver_reset', 0x11a1564), ('driver_initialize', 0x11a1584), ('configuration_initialize', 0x11bf390)]:
        result = run_function({
        'architecture': 'arm', 'entry': entry, 'stop': STOP,
        'regions': [*code, *system_runtime_regions(directory),
                    sparse_page(SCRATCH, [], write_initializes=True), *ram],
        'registers': {'SP': FRAME, 'LR': STOP, 'CPSR': 0x13},
        'outputs': [{'address': p, 'size': 4096} for p in pages]+[{'address': 0x15824a0, 'size': 72}],
        'register_trace': [0x128075c, 0x11bdf18, 0x11be8c4, 0x11bfd44, 0x11bfdfc, 0x11a1634,
                           0x5aa38, 0x5a9f0],
        'instruction_limit': 100000,
        'provenance': {'scope': 'Complete lock/configuration initializer entry on unknown writable RAM',
                       'state_transferred_to_raw_receiver': False, 'patched_instructions': False,
                       'stubs': [], 'image_pipeline_executed': False}})
        if result['reached_stop'] and not result['faults']:
            checks[name+'_stack_restored'] = result['registers']['SP'] == hex(FRAME)
            if name == 'driver_reset':
                checks['native_driver_reset_bytes'] = output_bytes(result, 0x1949b7c, 0x12c) == bytes(0x12c)
            elif name == 'driver_initialize':
                checks['native_driver_values_from_rom'] = output_bytes(result, 0x1949b7c, 72) == output_bytes(result, 0x15824a0, 72)
                checks['native_driver_marker_and_unlocked_state'] = output_bytes(result, 0x1949c9c, 8) == struct.pack('<II', 0x22233344, 0)
            if not all(checks.values()):
                stages.append({'name': name, 'execution': compact_execution(result, 0)})
                return {'passed': False, 'checks': checks, 'failed_stage': name, 'stages': stages}
            ram = snapshot_native_ram(result, pages, write_initializes=True)
            stages.append({'name': name, 'execution': compact_execution(result, 0)})
        else:
            faults = result['faults']
            checks['configuration_initializer_reached_hardware'] = (name == 'configuration_initialize'
                and not result['reached_stop'] and len(faults) == 1
                and faults[0]['address'] == '0xff70f03c' and faults[0]['pc'] == '0x5aa40'
                and faults[0]['access'] == 19 and faults[0]['size'] == 4)
            checks['native_configuration_lock_initialized'] = output_bytes(result, 0x178c5a0, 4) == bytes(4)
            checks['trace_complete'] = not result['register_trace_truncated']
            stages.append({'name': name, 'execution': compact_execution(result, 0)})
            return {'passed': all(checks.values()), 'checks': checks, 'frontier_stage': name, 'stages': stages,
                    'initialization_completed': False, 'completed_stage_ram_reused': True,
                    'faulted_ram_reused': False, 'state_transferred_to_raw_receiver': False}
    return {'passed': False, 'stages': stages, 'unexpected_completion': True,
            'state_transferred_to_raw_receiver': False}


def boot_task_probe(directory):
    code = modules(directory)
    descriptor = FRAME-0x28
    common = {'architecture': 'arm', 'instruction_limit': 50000,
              'provenance': {'scope': 'Isolated task-86 descriptor, native stack fill and task entry',
                             'scheduler_executed': False, 'kernel_context_restored': False,
                             'entry_sp_fixture': hex(TASK_STACK+4096),
                             'relocated_stack_arena': hex(TASK_STACK),
                             'state_transferred_to_raw_receiver': False,
                             'patched_instructions': False, 'stubs': [], 'image_pipeline_executed': False}}
    built = run_function({**common, 'entry': 0x12b0c80, 'stop': 0x12b0cbc,
                          'regions': [*code, sparse_page(SCRATCH, [], write_initializes=True)],
                          'registers': {'R11': FRAME, 'SP': FRAME-0x100, 'CPSR': 0x13},
                          'outputs': [{'address': SCRATCH, 'size': 4096}]})
    expected = (86, 0x168ccec, 5, 4096, 0x12b2b00, 0)
    if (not built['reached_stop'] or built['faults']
            or output_bytes(built, descriptor, 24) != struct.pack('<6I', *expected)):
        raise ValueError('Native task-86 descriptor mismatch')
    words = struct.unpack('<6I', output_bytes(built, descriptor, 24))
    # Execute the native size/pointer lookup, UXT B(identifier), and fill call.
    # The arena binding is explicit; no allocator or event-flag call is faked.
    filled = run_function({**common, 'entry': 0x127d8ec, 'stop': 0x127d914,
                           'regions': [*code, sparse_page(SCRATCH, [], write_initializes=True),
                                       sparse_page(TASK_STACK, [], write_initializes=True),
                                       sparse_page(0x1a22000, [(0xb7c, struct.pack('<II', TASK_STACK, words[3]))], 'r')],
                           'registers': {'R1': words[0], 'R2': words[0]-1, 'R11': FRAME,
                                         'SP': FRAME-0x100, 'CPSR': 0x13},
                           'outputs': [{'address': TASK_STACK, 'size': 4096}],
                           'memory_trace': [{'address': TASK_STACK, 'size': 4096}],
                           'memory_trace_limit': 10000})
    writes = {int(t['address'], 16)+i for t in filled['memory_trace'] if t['access'] == 'write'
              for i in range(t['size'])}
    if (not filled['reached_stop'] or filled['faults'] or filled['memory_trace_truncated']
            or output_bytes(filled, TASK_STACK, 4096) != bytes([86])*4096
            or writes != set(range(TASK_STACK, TASK_STACK+4096))):
        raise ValueError('Native task stack fill failed')
    stack = snapshot_native_ram(filled, [TASK_STACK], write_initializes=True)
    result = run_function({**common, 'entry': words[4], 'stop': STOP,
                           'regions': [*code, *system_runtime_regions(directory), *stack,
                                       *[sparse_page(p, [], write_initializes=True) for p in
                                         (0x1af3000, 0x1b68000, 0x1bd5000)]],
                           'registers': {'R0': words[5], 'SP': TASK_STACK+4096, 'LR': STOP, 'CPSR': 0x13},
                           'outputs': [{'address': p, 'size': 4096} for p in
                                       (TASK_STACK, 0x1af3000, 0x1b68000, 0x1bd5000)],
                           'register_trace': [0x12b25f4, 0x12b2674, 0x12b2b68, 0x12b2c08,
                                              0x1291908, 0x1e1de60],
                           'memory_trace': [{'address': TASK_STACK, 'size': 4096}],
                           'memory_trace_limit': 10000})
    faults = result['faults']
    dispatch = [t for t in result['register_trace'] if t['pc'] == '0x12b2674']
    checks = {
        'native_initial_state_zero': output_bytes(result, 0x1af36d8, 10) == bytes(10),
        'native_message_buffer_initialized': output_bytes(result, 0x1b6895c, 0xd8)
            == bytes(8)+struct.pack('<I', 0x1b68968)+bytes(0xd8-12),
        'native_initial_event_zero': output_bytes(result, 0x1bd5670, 2) == bytes(2),
        'rom_selects_module_start_handler': len(dispatch) == 1
            and dispatch[0]['registers']['R2'] == '0x2'
            and dispatch[0]['registers']['R3'] == '0x12b2b68',
        'selected_handler_entered': len([t for t in result['register_trace'] if t['pc'] == '0x12b2b68']) == 1,
        'stopped_on_unavailable_lock': not result['reached_stop'] and len(faults) == 1
            and faults[0]['address'] == '0x178c5a0' and faults[0]['pc'] == '0x12807f8'
            and faults[0]['access'] == 19 and faults[0]['size'] == 4,
        'module_entry_not_reached': not any(t['pc'] in ('0x1291908', '0x1e1de60') for t in result['register_trace']),
        'traces_complete': not result['register_trace_truncated'] and not result['memory_trace_truncated'],
    }
    initialization = boot_lock_initialization_probe(directory)
    return {'passed': all(checks.values()) and initialization['passed'], 'checks': checks, 'descriptor_words': list(words),
            'lock_initialization': initialization,
            'descriptor': compact_execution(built, 0), 'stack_fill': compact_execution(filled, 0),
            'entry_execution': compact_execution(result, 0),
            'full_boot_executed': False, 'state_transferred_to_raw_receiver': False}
