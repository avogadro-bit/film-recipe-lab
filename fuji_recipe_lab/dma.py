"""Native DMA descriptor encoding with write capture, never DMA completion.

Registers are write-only observation pages. Their status is unavailable, and
the firmware must stop on the first status read. Pixel addresses stay unmapped.
"""
import struct

from .emulation import run_function
from .pipeline import modules, compact_execution
from .runtime import sparse_page
from .synchronization import STACK, STOP, system_runtime_regions

ENTRY = 0x11ae2b0
PARAMETERS = 0x6d00000
DESCRIPTORS = 0x6d01000


def control_probe(directory):
    """Native status/launch functions against static, synthetic register inputs.

    This is a truth-table test, not a device model. No state is transferred to
    the RAW receiver, and no status is changed during an execution.
    """
    code = modules(directory)
    system = system_runtime_regions(directory)
    cases = []
    words = [0, *[1 << bit for bit in range(32)], 0xffffffff, 0xa5a5a5a5]
    for channel in (1, 9):
        for status in words:
            cases.append(_control_case(code, system, channel, 'status', status, None))
        for status, control in [(0, 0), (0x80000001, 0xa5a5a5a5), (0, 0xffffffff),
                                (0x10000, None), (None, None), (0, None)]:
            cases.append(_control_case(code, system, channel, 'launch', status, control))
    for operation in ('status', 'launch'):
        cases.append(_control_case(code, system, 16, operation, None, None))
    callbacks = [callback_probe(directory, attribute) for attribute in (0, 4)]
    attributes = task_flag_attribute_frontier(directory)
    from .task_initialization import task_initialization_probe
    initialization = task_initialization_probe(directory)
    startup = task_initialization_probe(directory, startup=True)
    from .boot_task import boot_task_probe
    boot_task = boot_task_probe(directory)
    return {'target': 'X-T4 2.12', 'passed': all(c['passed'] for c in cases)
            and all(c['passed'] for c in callbacks) and attributes['passed'] and initialization['passed'] and startup['passed'] and boot_task['passed'],
            'case_count': len(cases), 'firmware_executed': True,
            'image_pipeline_executed': False, 'hardware_emulated': False,
            'ram_transferred': False,
            'scope': 'Native DMA status decoding and launch conditions on explicit static test inputs; no device completion',
            'cases': cases, 'callback_cases': callbacks, 'task_flag_attribute': attributes,
            'task_initialization': initialization, 'startup_initialization': startup, 'boot_task': boot_task}


def _control_case(code, system, channel, operation, status, control):
    base = 0xfffe0000 + min(channel, 15)*4096
    fields = []
    if status is not None:
        fields.append((0x30, struct.pack('<I', status)))
    if control is not None:
        fields.append((0x28, struct.pack('<I', control)))
    if operation == 'status':
        fields.extend([(0x14, struct.pack('<I', 0x12345678)), (0x18, struct.pack('<I', 0x89abcdef))])
    result = run_function({
        'architecture': 'arm', 'entry': 0x11adbe4 if operation == 'status' else 0x11adb34, 'stop': STOP,
        'regions': [*code, *system, sparse_page(base, fields),
                    sparse_page(PARAMETERS, [(0, b'\xa5'*16)]),
                    sparse_page(0x700f000, [], write_initializes=True)],
        'registers': {'R0': channel, 'R1': PARAMETERS, 'SP': STACK, 'LR': STOP, 'CPSR': 0x13},
        'outputs': [{'address': PARAMETERS, 'size': 16}],
        'memory_trace': [{'address': base, 'size': 4096}],
        'instruction_limit': 256,
        'provenance': {'scope': 'Static synthetic register words; not a recovered hardware state or device model',
                       'status_word': status, 'control_word': control,
                       'external_register_updates': False,
                       'ram_transferred_to_receiver': False, 'pixel_addresses_mapped': False,
                       'patched_instructions': False, 'stubs': []}})
    observed = result['memory_trace']
    reads = [int(a['address'], 16) for a in observed if a['access'] == 'read']
    writes = [(int(a['address'], 16), int(a['write_value'], 16))
              for a in observed if a['access'] == 'write']
    expected = bytearray(b'\xa5'*16)
    checks = {'observations_complete': not result['memory_trace_truncated']}
    if channel == 16:
        checks.update(native_invalid_channel_rejected=result['reached_stop'] and not result['faults']
                      and result['registers']['R0'] == '0xffffffe2', no_register_access=not observed)
    elif operation == 'status':
        expected[0] = (status >> 16) & 1
        struct.pack_into('<II', expected, 4, 0x12345678, 0x89abcdef)
        checks.update(native_status_returned=result['reached_stop'] and not result['faults']
                      and result['registers']['R0'] == '0x0',
                      exact_register_reads=reads == [base+0x30, base+0x14, base+0x18],
                      no_register_writes=not writes)
    elif status is None or (not status & 0x10000 and control is None):
        missing = base+0x30 if status is None else base+0x28
        checks.update(stopped_on_unknown_register=not result['reached_stop'] and len(result['faults']) == 1
                      and result['faults'][0]['address'] == hex(missing)
                      and result['faults'][0]['pc'] == '0x5aa40', no_command_written=not writes)
    elif status & 0x10000:
        checks.update(busy_channel_remains_waiting=not result['reached_stop'] and not result['faults']
                      and result['error'] is None and result['instructions'] == 256,
                      only_busy_status_polled=len(reads) > 1 and set(reads) == {base+0x30},
                      no_command_written=not writes)
    else:
        checks.update(native_launch_function_returned=result['reached_stop'] and not result['faults']
                      and result['registers']['R0'] == '0x0',
                      exact_register_reads=reads == [base+0x30, base+0x28],
                      native_enable_bit_preserves_other_bits=writes == [(base+0x28, control | 0x10000000)])
    checks['output_bytes_and_padding'] = result['outputs'][0]['hex'] == expected.hex()
    if result['reached_stop']:
        checks['stack_restored'] = result['registers']['SP'] == hex(STACK)
    return {'passed': all(checks.values()), 'checks': checks,
            'input': {'channel': channel, 'operation': operation, 'status': status, 'control': control},
            'decoded_status': bytes.fromhex(result['outputs'][0]['hex'])[0]
                if operation == 'status' and channel < 16 else None,
            'execution': compact_execution(result, 0)}


def callback_probe(directory, attribute=0):
    """Signal the native event flag through the real callback, without an IRQ.

    Polling is nonblocking, before and after an explicit callback invocation.
    This does not manufacture a DMA completion inside the RAW receiver.
    """
    from .requests_runtime import snapshot_native_ram
    if type(attribute) is not int or attribute not in (0, 4):
        raise ValueError('Event flag attribute must be 0 or 4 in this bounded probe')
    code, system = modules(directory), system_runtime_regions(directory)
    pages = [0x62000, 0x64000, PARAMETERS]
    ram = [sparse_page(0x62000, [(0xc70, bytes(4))], write_initializes=True),
           sparse_page(0x64000, [], write_initializes=True),
           sparse_page(PARAMETERS, [], write_initializes=True)]
    thread = [sparse_page(0x6600000, [(0xcc, struct.pack('<I', 9))], 'r'),
              sparse_page(0x7a000, [(0x57c, struct.pack('<I', 0x6600000))], 'r')]
    stages = []
    steps = [('constructor', 0x4b0c4, {'R0': 9, 'R1': 0x6e00000}, None, '0x0'),
             ('poll_before', 0x127dfd8, {'R0': 0x10, 'R1': PARAMETERS, 'R2': 0}, None, '0xffffffce'),
             ('callback_without_target', 0x21c702c, {}, 0, '0x0'),
             ('callback_to_thread_9', 0x21c702c, {}, 9, '0x0'),
             ('poll_after', 0x127dfd8, {'R0': 0x10, 'R1': PARAMETERS, 'R2': 0}, None, '0x0'),
             ('poll_again', 0x127dfd8, {'R0': 0x10, 'R1': PARAMETERS, 'R2': 0}, None,
              '0xffffffce' if attribute == 4 else '0x0')]
    for name, entry, registers, target, expected_return in steps:
        result = run_function({
            'architecture': 'arm', 'entry': entry, 'stop': STOP,
            'regions': [*code, *system, *thread, *ram,
                        sparse_page(0x6e00000, [(0, struct.pack('<II', attribute, 0))], 'r'),
                        *([sparse_page(0x3735000, [(0xba9, bytes([target]))], 'r')] if target is not None else []),
                        sparse_page(0x700f000, [], write_initializes=True)],
            'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13, **registers},
            'outputs': [{'address': p, 'size': 4096} for p in pages],
            'memory_trace': [{'address': 0x64000, 'size': 4096}, {'address': PARAMETERS, 'size': 4}],
            'register_trace': [0x127e0c8], 'instruction_limit': 3000,
            'provenance': {'scope': 'Native flag constructor, explicit callback and nonblocking polls; no scheduler or IRQ',
                           'thread_fixture': 9, 'callback_target_fixture': target,
                           'event_attribute_fixture': attribute, 'live_task_attributes_recovered': False,
                           'dma_completion_emulated': False, 'state_transferred_to_raw_receiver': False,
                           'patched_instructions': False, 'stubs': []}})
        flags = bytes.fromhex(result['outputs'][1]['hex'])[0x5d4:0x5e4]
        checks = {'native_return': result['reached_stop'] and not result['faults']
                  and result['registers']['R0'] == expected_return,
                  'stack_restored': result['registers']['SP'] == hex(STACK),
                  'observations_complete': not result['memory_trace_truncated'] and not result['register_trace_truncated']}
        if name in ('constructor', 'poll_before', 'callback_without_target'):
            checks['no_event_pending'] = flags == struct.pack('<4I', attribute, 0, 0, 0)
        if name == 'callback_to_thread_9':
            checks['correct_callback_arguments'] = len(result['register_trace']) == 1 and all(
                result['register_trace'][0]['registers'][k] == v for k, v in {'R0': '0x9', 'R1': '0x10'}.items())
        if name == 'poll_after':
            checks['native_event_observed'] = result['outputs'][2]['hex'][:8] == '10000000'
        if name in ('poll_after', 'poll_again'):
            checks['event_retention_matches_attribute'] = flags == struct.pack('<4I', attribute, 0, 0 if attribute else 0x10, 0)
        ok = all(checks.values())
        if ok:
            ram = snapshot_native_ram(result, pages, write_initializes=True)
        stages.append({'name': name, 'passed': ok, 'checks': checks, 'flag_object_hex': flags.hex(),
                       'execution': compact_execution(result, 0)})
        if not ok:
            break
    return {'passed': len(stages) == len(steps) and all(s['passed'] for s in stages), 'attribute': attribute,
            'scope': 'Isolated event notification, not evidence of DMA or image completion',
            'stages': stages}


def task_flag_attribute_frontier(directory):
    """The RAW task builder writes 24 bytes; flag selection reads a word at +24.

    Execute the two isolated native blocks without supplying the missing word.
    This is not the complete queue/task constructor or its registry checks.
    """
    from .requests_runtime import snapshot_native_ram
    code = modules(directory)
    descriptor = STACK-0x38
    built = run_function({
        'architecture': 'arm', 'entry': 0x2204800, 'stop': 0x2204828,
        'regions': [*code, sparse_page(0x700f000, [], write_initializes=True)],
        'registers': {'R4': 9, 'R5': 0, 'R6': 1, 'R11': STACK, 'SP': STACK-0x100, 'CPSR': 0x13},
        'outputs': [{'address': 0x700f000, 'size': 4096}], 'instruction_limit': 30,
        'provenance': {'scope': 'Isolated native RAW task descriptor construction; explicit ID=9, priority/argument fixtures',
                       'full_task_constructor_executed': False, 'patched_instructions': False, 'stubs': []}})
    raw = bytes.fromhex(built['outputs'][0]['hex'])
    expected = struct.pack('<6I', 9, 1, 0, 0x1400, 0x221a290, 9)
    if not built['reached_stop'] or built['faults'] or raw[descriptor-0x700f000:descriptor-0x700f000+24] != expected:
        raise ValueError('Native RAW task descriptor block failed')
    ram = snapshot_native_ram(built, [0x700f000], write_initializes=True)
    selected = run_function({
        'architecture': 'arm', 'entry': 0x127d7b8, 'stop': 0x4b0c4,
        'regions': [*code, *ram],
        'registers': {'R4': descriptor, 'R11': STACK, 'SP': STACK-0x100, 'CPSR': 0x13},
        'instruction_limit': 30,
        'provenance': {'scope': 'Isolated flag-attribute branch after unreconstructed task registry checks',
                       'unknown_stack_word_supplied': False, 'state_transferred_to_receiver': False,
                       'patched_instructions': False, 'stubs': []}})
    checks = {'native_descriptor_pointer': built['registers']['R0'] == hex(descriptor),
              'only_six_words_initialized': ram[0]['valid_ranges'] == [{'offset': descriptor-0x700f000, 'size': 24}],
              'unknown_attribute_word_blocks_selection': not selected['reached_stop'] and len(selected['faults']) == 1
                and selected['faults'][0]['address'] == hex(descriptor+24)
                and selected['faults'][0]['pc'] == '0x127d7c0'}
    return {'passed': all(checks.values()), 'checks': checks,
            'scope': 'RAW task attribute cannot be inferred from these six constructor words; previous stack state unknown',
            'descriptor_words': list(struct.unpack('<6I', expected)), 'missing_offset': '0x18',
            'constructor_block': compact_execution(built, 0), 'attribute_selection': selected}


def descriptor_probe(directory):
    code = modules(directory)
    system = system_runtime_regions(directory)
    # Request 0x20 is used by 0x21ca300. Check the actual pinned ROM entry;
    # the lower encoder receives bytes +1/+2 and the word at +4.
    module = (directory / 'unpacked_00260000.bin').read_bytes()
    request = module[0x1582e80-0x1021000:0x1582e80-0x1021000+12]
    if request != bytes.fromhex('102c03000800000001000000'):
        raise ValueError('Unexpected native DMA request-0x20 descriptor')
    cases = []
    for channel in (1, 9):
        for rows in (1, 3, 31):
            for increment in ((0, 0), (0, 1), (1, 0), (1, 1)):
                for seed in (0, 0xa5):
                    case = _case(code, system, request, channel, rows, increment, seed)
                    cases.append(case)
    for invalid in ('unaligned_list', 'short_list', 'unaligned_width', 'bad_channel'):
        cases.append(_case(code, system, request, 1, 3, (1, 1), 0xa5, invalid))
    return {'target': 'X-T4 2.12', 'passed': all(c['passed'] for c in cases),
            'case_count': len(cases), 'firmware_executed': True,
            'image_pipeline_executed': False, 'hardware_emulated': False,
            'request_descriptor_address': '0x1582e80', 'request_descriptor_hex': request.hex(),
            'scope': 'Native row-list encoding and captured register writes; status reads unavailable, no pixel transfer',
            'cases': cases}


def _case(code, system, request, channel, rows, increment, seed, invalid=None):
    width = 64 if channel == 1 else 96
    source, destination = 0x60000000, 0x65000000
    source_stride, destination_stride = width+32, width+64
    channel_base = 0xfffe0000 + channel*0x1000
    argument_channel = 16 if invalid == 'bad_channel' else channel
    argument_list = DESCRIPTORS+4 if invalid == 'unaligned_list' else DESCRIPTORS
    capacity = rows*32 - (1 if invalid == 'short_list' else 0)
    argument_width = width+1 if invalid == 'unaligned_width' else width
    data = bytearray(36)
    data[0:2] = request[1:3]
    data[4:8] = request[4:8]
    data[8:10] = bytes(increment)
    struct.pack_into('<6I', data, 12, source, source_stride, destination, destination_stride, argument_width, rows)
    result = run_function({
        'architecture': 'arm', 'entry': ENTRY, 'stop': STOP,
        'regions': [*code, *system,
                    sparse_page(PARAMETERS, [(0, data)], 'r'),
                    sparse_page(DESCRIPTORS, [(0, bytes([seed])*4096)]),
                    sparse_page(0xfff4a000, [], 'w', write_initializes=True),
                    sparse_page(channel_base, [], 'w', write_initializes=True),
                    sparse_page(0x700f000, [], write_initializes=True)],
        'registers': {'R0': argument_channel, 'R1': PARAMETERS, 'R2': argument_list, 'R3': capacity,
                      'SP': STACK, 'LR': STOP, 'CPSR': 0x13},
        'outputs': [{'address': DESCRIPTORS, 'size': 4096}],
        'memory_trace': [{'address': DESCRIPTORS, 'size': 4096},
                         {'address': 0xfff4a000, 'size': 4096}, {'address': channel_base, 'size': 4096}],
        'register_trace': [0x5a9f0, 0x5aa38], 'register_trace_limit': 32,
        'instruction_limit': 10000,
        'provenance': {'scope': 'Explicit synthetic transfer dimensions, increment flags and descriptor seed; no image data',
                       'descriptor_memory_seed': seed, 'pixel_addresses_mapped': False,
                       'register_scope': 'Write capture only, no peripheral side effects or status values',
                       'patched_instructions': False, 'stubs': []}})
    raw = bytes.fromhex(result['outputs'][0]['hex'])
    writes = [a for a in result['memory_trace'] if a['access'] == 'write']
    mmio_writes = [(int(a['address'], 16), int(a['write_value'], 16))
                   for a in writes if int(a['address'], 16) >= 0xfff00000]
    checks = {'observations_complete': not result['memory_trace_truncated'] and not result['register_trace_truncated']}
    expected = bytearray([seed])*4096
    if invalid:
        checks.update(native_rejection=result['reached_stop'] and not result['faults']
                      and result['registers']['R0'] == '0xffffffe2' and result['registers']['SP'] == hex(STACK),
                      no_descriptor_or_register_writes=not writes,
                      descriptor_memory_preserved=raw == expected)
    else:
        control = ((struct.unpack_from('<I', request, 4)[0]-1)&15)<<8 | (request[2]&3)<<16
        for row in range(rows):
            following = DESCRIPTORS+(row+1)*32 | (seed&0xf) | 1
            if row == rows-1:
                following &= ~1
            struct.pack_into('<6I', expected, row*32, width-1,
                             source+row*source_stride, destination+row*destination_stride,
                             control | (0 if increment[0] else 4),
                             control | (0 if increment[1] else 4), following)
        expected_mmio = [(0xfff4a500+(channel//2)*4, 0x1002c2c),
                         (channel_base+0x14, source), (channel_base+0x18, destination),
                         (channel_base+0x10, 0), (channel_base+0x28, 0x1100001)]
        checks.update(native_descriptors_and_untouched_bytes_match=raw == expected,
                      native_register_write_sequence=mmio_writes == expected_mmio,
                      # The guard and Unicorn's write-only protection may
                      # both report this same access. Neither supplies data.
                      stopped_on_unavailable_status=not result['reached_stop'] and 1 <= len(result['faults']) <= 2
                      and all(f['address'] == hex(channel_base+0x30) and f['pc'] == '0x5aa40'
                              and f['size'] == 4 and f['access'] in ('read', 23) for f in result['faults']),
                      hardware_start_not_claimed=all(address != channel_base+0x24 for address, _ in mmio_writes))
    report = {'passed': all(checks.values()), 'checks': checks,
              'input': {'channel': argument_channel, 'rows': rows, 'width': argument_width,
                        'source_stride': source_stride, 'destination_stride': destination_stride,
                        'increment': list(increment), 'seed': seed, 'invalid': invalid},
              'descriptor_first_hex': raw[:32].hex(), 'descriptor_last_hex': raw[(rows-1)*32:rows*32].hex(),
              'mmio_writes': [{'address': hex(a), 'value': hex(v)} for a, v in mmio_writes],
              'execution': compact_execution(result, 0)}
    return report
