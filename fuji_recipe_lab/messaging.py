"""Native, nonblocking message transport; explicit cold-start fixtures.

The queue and block pool are built by unchanged Fuji instructions. Four slots
and 80-byte blocks are test inputs, not recovered camera boot configuration.
No scheduler, waiting thread or image processor is supplied.
"""
from pathlib import Path
import hashlib
import struct

from .emulation import run_function
from .pipeline import modules, compact_execution
from .requests_runtime import snapshot_native_ram
from .runtime import sparse_page
from .synchronization import system_runtime_regions, STACK, STOP

QUEUE_ID = 9
CAPACITY = 4
BLOCK_SIZE = 80
QUEUE_OBJECT = 0x7ad2c + 36*(QUEUE_ID-1)
POOL_OBJECT = 0x5d9a0 + 84*(QUEUE_ID-1)
QUEUE_BUFFER = 0x6a00000
POOL_BUFFER = 0x6a01000
RAM_PAGES = [0x5b000, 0x5d000, 0x7a000, QUEUE_BUFFER, POOL_BUFFER,
             0x1731000, 0x18ea000, 0x1b9d000, 0x6a03000, 0x6a04000, 0x3678000]


def merge_sparse_regions(regions):
    """Combine guarded pages only when every overlapping known byte agrees."""
    pages, other = {}, []
    for region in regions:
        if region.get("size") != 4096 or "valid_ranges" not in region:
            other.append(region)
            continue
        address = region["address"]
        known, permissions, dynamic = pages.setdefault(address, ({}, set(), [False]))
        permissions.update(region["permissions"])
        dynamic[0] |= region.get("write_initializes", False)
        data = bytes.fromhex(region["hex"])
        for valid in region["valid_ranges"]:
            for offset in range(valid["offset"], valid["offset"]+valid["size"]):
                if offset in known and known[offset] != data[offset]:
                    raise ValueError(f"Conflicting initialized RAM at {address+offset:#x}")
                known[offset] = data[offset]
    for address, (known, permissions, dynamic) in pages.items():
        fields = []
        for offset in sorted(known):
            if fields and fields[-1][0]+len(fields[-1][1]) == offset:
                fields[-1][1].append(known[offset])
            else:
                fields.append((offset, bytearray([known[offset]])))
        other.append(sparse_page(address, fields, ''.join(p for p in 'rwx' if p in permissions), dynamic[0]))
    return other


def execute(directory, entry, ram, inputs=(), registers=None):
    code = [r for r in system_runtime_regions(directory) if r["address"] != 0x5b000]
    return run_function({
        "architecture": "arm", "entry": entry, "stop": STOP,
        "regions": [*message_code(directory), *code, *ram, *inputs,
                    {"address": 0x7000000, "size": 65536, "permissions": "rw"}],
        "registers": {"SP": STACK, "LR": STOP, "CPSR": 0x13, **(registers or {})},
        "outputs": [{"address": address, "size": 4096} for address in RAM_PAGES]
                   + [{'address': r['address'], 'size': r['size']} for r in inputs if 'w' in r['permissions']],
        "memory_trace": [{"address": address, "size": 4096} for address in RAM_PAGES],
        "memory_trace_limit": 10000, "instruction_limit": 30000,
        "provenance": {"scope": "Native queue and block-pool transport, chosen cold-start core-0 state",
                       "capacity": CAPACITY, "block_size": BLOCK_SIZE,
                       "stubs": [], "patched_instructions": False, "image_pipeline_executed": False}})


def completed(result, expected_return='0x0'):
    lock = bytes.fromhex(result["outputs"][0]["hex"])[0x580:0x590]
    return (result["reached_stop"] and not result["faults"] and result["registers"]["R0"] == expected_return
            and result["registers"]["SP"] == hex(STACK)
            and int(result["registers"]["CPSR"], 16) & 255 == 0x13
            and lock[:4] == bytes(4) and lock[8:] == struct.pack("<II", 0xffffffff, 0)
            and not result["memory_trace_truncated"])


def output_bytes(result, address, size):
    if size <= 0:
        raise ValueError('Output read size must be positive')
    for output in result['outputs']:
        start = int(output['address'], 16)
        if 'hex' in output and start <= address and address+size <= start+output.get('size', 0):
            data = bytes.fromhex(output['hex'])[address-start:address-start+size]
            if len(data) == size:
                return data
    raise ValueError(f'No complete output covers {address:#x}+{size:#x}')


def message_code(directory):
    """Split out the firmware data page containing the registered observer.

    modules() first verifies each entire pinned file. The two code slices keep
    their own hashes; no byte of their instructions is changed.
    """
    original = modules(directory)
    first = original[0]
    data = Path(first['file']).read_bytes()
    if hashlib.sha256(data).hexdigest() != first['expected_sha256']:
        raise ValueError('Pinned message module changed before slicing')
    split = 0x1731000-first['address']
    regions = []
    for offset, chunk in [(0, data[:split]), (split+4096, data[split+4096:])]:
        regions.append({'address': first['address']+offset, 'size': (len(chunk)+4095)//4096*4096,
                        'hex': chunk.hex(), 'permissions': 'rx', 'initialized_only': True,
                        'expected_sha256': hashlib.sha256(chunk).hexdigest()})
    return [*regions, *original[1:]]


def message_runtime(directory: Path):
    system = [r for r in system_runtime_regions(directory) if r["address"] == 0x5b000]
    module = modules(directory)[0]  # Verify before making the data page writable.
    data = Path(module['file']).read_bytes()
    if hashlib.sha256(data).hexdigest() != module['expected_sha256']:
        raise ValueError('Pinned message module changed before data initialization')
    offset = 0x1731000-module['address']
    ram = merge_sparse_regions([
        *system, sparse_page(0x5b000, [(0xd8, bytes(4))], write_initializes=True),
        sparse_page(0x5d000, [(offset+4*(identifier-1), bytes(4))
                            for identifier in (9, 7) for offset in (0x1c8, 0x5b0)], write_initializes=True),
        sparse_page(0x7a000, [], write_initializes=True),
        sparse_page(QUEUE_BUFFER, [], write_initializes=True),
        sparse_page(POOL_BUFFER, [], write_initializes=True),
        sparse_page(0x6a03000, [], write_initializes=True),
        sparse_page(0x6a04000, [], write_initializes=True),
        sparse_page(0x3678000, [], write_initializes=True),
        sparse_page(0x1731000, [(0, data[offset:offset+4096])]),
        sparse_page(0x18ea000, [(0xd04+4*(identifier-1), struct.pack('<I', BLOCK_SIZE)) for identifier in (9, 7)], 'r'),
        sparse_page(0x1b9d000, [(0xfdc, bytes(4))], 'r')])
    stages = []
    for name, entry, config, registers in [
        ('queue_constructor', 0x4af4c, struct.pack('<III', 0, CAPACITY, QUEUE_BUFFER), {'R0': QUEUE_ID, 'R1': 0x6b00000}),
        ('pool_constructor', 0x4b830, struct.pack('<IIII', 0, CAPACITY, BLOCK_SIZE, POOL_BUFFER), {'R0': QUEUE_ID, 'R1': 0x6b00000}),
        ('queue_constructor_7', 0x4af4c, struct.pack('<III', 0, CAPACITY, 0x6a03000), {'R0': 7, 'R1': 0x6b00000}),
        ('pool_constructor_7', 0x4b830, struct.pack('<IIII', 0, CAPACITY, BLOCK_SIZE, 0x6a04000), {'R0': 7, 'R1': 0x6b00000}),
        ('message_observer_registration', 0x127e40c, b'', {'R0': 0x128fa38}),
        ('coordinator_destination_registration', 0x21ee4f8, b'', {'R0': 7})]:
        inputs = [sparse_page(0x6b00000, [(0, config)], 'r')] if config else []
        result = execute(directory, entry, ram, inputs, registers)
        # Registration preserves its callback argument in R0, not a status code.
        expected_return = {'message_observer_registration': '0x128fa38', 'coordinator_destination_registration': '0x7'}.get(name, '0x0')
        ok = completed(result, expected_return)
        if not ok:
            return None, {'passed': False, 'failed_stage': name, 'execution': result, 'stages': stages}
        ram = snapshot_native_ram(result, RAM_PAGES, write_initializes=True)
        if name.startswith('pool_constructor'):
            pool = output_bytes(result, 0x5d9a0+84*(registers['R0']-1), 0x30)
            buffer = POOL_BUFFER if registers['R0'] == 9 else 0x6a04000
            ok = (struct.unpack_from('<I', pool)[0] == 0x424c4f43
                  and struct.unpack_from('<II', pool, 8) == (CAPACITY, CAPACITY)
                  and struct.unpack_from('<I', pool, 0x10)[0] == buffer)
        elif name.startswith('queue_constructor'):
            buffer = QUEUE_BUFFER if registers['R0'] == 9 else 0x6a03000
            ok = output_bytes(result, 0x7ad2c+36*(registers['R0']-1), 36) == struct.pack('<9I', 0, CAPACITY, buffer, buffer, 0, 0, 0, 0, 0)
        elif name == 'message_observer_registration':
            ok = output_bytes(result, 0x17314a0, 4) == struct.pack('<I', 0x128fa38)
        else:
            ok = output_bytes(result, 0x3678e30, 1) == b'\7'
        result['passed'] = ok
        compact_execution(result, 0)
        stages.append({'name': name, 'execution': result})
        if not ok:
            return None, {'passed': False, 'failed_stage': name, 'stages': stages}
    return ram, {'passed': True, 'queue_id': QUEUE_ID, 'capacity': CAPACITY, 'block_size': BLOCK_SIZE,
                 'scope': 'Native constructors, supplied buffer addresses, cold-start pool list, no scheduler', 'stages': stages}


def message_probe(directory: Path):
    ram, preparation = message_runtime(directory)
    if ram is None:
        return preparation
    payload = bytes((i*37+11) % 256 for i in range(68))
    header = struct.pack('<HBBII', 0x1219, 1, QUEUE_ID, len(payload), 0x6b00100)
    inputs = [sparse_page(0x6b00000, [(0, header), (0x100, payload)], 'r')]
    sent = execute(directory, 0x127e784, ram, inputs, {'R0': QUEUE_ID, 'R1': 0x6b00000})
    report = {'passed': False, 'preparation': preparation, 'send': sent,
              'image_pipeline_executed': False, 'scope': 'Synthetic 68-byte payload transported by unmodified Fuji code'}
    if not completed(sent):
        return report
    send_checks = {
        'message_copied_to_allocated_block': output_bytes(sent, POOL_BUFFER+4, 76) == header[:8]+payload,
        'queued_block_pointer': output_bytes(sent, QUEUE_BUFFER, 4) == struct.pack('<I', POOL_BUFFER+4),
        'one_queued_message': output_bytes(sent, QUEUE_OBJECT+24, 4) == struct.pack('<I', 1),
        'one_block_allocated': output_bytes(sent, POOL_OBJECT+8, 4) == struct.pack('<I', CAPACITY-1)}
    ram = snapshot_native_ram(sent, RAM_PAGES, write_initializes=True)
    # Receive into a caller-owned buffer, exactly as the native API requests.
    received = execute(directory, 0x127e914, ram,
                       [sparse_page(0x6b00000, [(8, struct.pack('<I', POOL_BUFFER+0x800))], write_initializes=True)],
                       {'R0': QUEUE_ID, 'R1': 0x6b00000})
    # The payload destination is within our snapshotted pool page but outside
    # its 336-byte block storage, so roundtrip bytes can be checked directly.
    report['receive'] = received
    report['checks'] = {**send_checks,
        'receive_completed': completed(received),
        'payload_roundtrip': output_bytes(received, POOL_BUFFER+0x800, len(payload)) == payload,
        'header_roundtrip': output_bytes(received, 0x6b00000, 12) == header[:8]+struct.pack('<I', POOL_BUFFER+0x800),
        'queue_drained': output_bytes(received, QUEUE_OBJECT+24, 4) == bytes(4),
        'block_returned_to_pool': output_bytes(received, POOL_OBJECT+8, 4) == struct.pack('<I', CAPACITY)}
    report['passed'] = all(report['checks'].values())
    compact_execution(sent, 0)
    compact_execution(received, 0)
    return report


def resume_regions(config, execution):
    if not execution['reached_stop'] or execution['faults']:
        raise ValueError('Cannot resume a receiver from incomplete orchestration')
    regions = []
    for original in config['regions']:
        region = dict(original)
        address = region['address']
        if 'w' in region['permissions'] and address != 0x7000000:
            output = next(o for o in execution['outputs'] if int(o['address'], 16) == address and o['size'] == region['size'])
            mapped = next(r for r in execution['regions'] if int(r['address'], 16) == address)
            region.pop('file', None)
            region.pop('expected_sha256', None)
            region['hex'] = output['hex']
            ranges = mapped.get('final_valid_ranges', mapped.get('valid_ranges'))
            if ranges is not None:
                region.pop('initialized_only', None)
                region['valid_ranges'] = [{'offset': int(r['address'], 16)-address, 'size': r['size']} for r in ranges]
        regions.append(region)
    return regions


def receiver_frontier(config, execution, cfg_feb0=None, firmware_config=None, boot_wb=None, extended_config=None, resource_plan=None):
    """Enter the real task loop with RAM from completed RAW orchestration.

    Direct entry with an explicit current-thread ID=9, not a scheduler switch.
    Its event-flag object is initialized by the native constructor.
    """
    if cfg_feb0 is not None and (type(cfg_feb0) is not int or not 0 <= cfg_feb0 <= 255):
        raise ValueError('Exploratory configuration byte must be 0..255')
    if firmware_config is not None and cfg_feb0 is not None:
        raise ValueError('Firmware configuration cannot be mixed with cfg_feb0 hypotheses')
    if boot_wb is not None and firmware_config is None:
        raise ValueError('Boot WB padding requires verified configuration')
    if extended_config is not None and boot_wb is None:
        raise ValueError('Extended configuration requires WB boot state')
    if resource_plan is not None and extended_config is None:
        raise ValueError('RAW resource plan requires extended configuration')
    regions = resume_regions(config, execution)
    if extended_config is not None:
        regions.extend(extended_config[0])
        regions.append(sparse_page(0x3374000, [], write_initializes=True))
    if firmware_config is not None:
        from .configuration import configuration_page, install_configuration_prefix
        if extended_config is not None:
            regions = install_configuration_prefix(regions, firmware_config[0])
        else:
            regions.append(configuration_page(firmware_config[0], 0xf000))
            if boot_wb is not None:
                regions.append(configuration_page(firmware_config[0], 0))
    if cfg_feb0 is not None:
        regions.append(sparse_page(0x680f000, [(0xeb0, bytes([cfg_feb0]))], 'r'))
    thread = next(r for r in regions if r['address'] == 0x6600000)
    data = bytearray.fromhex(thread['hex'])
    struct.pack_into('<I', data, 0xcc, QUEUE_ID)
    thread['hex'] = data.hex()
    regions = merge_sparse_regions([*regions,
        sparse_page(0x7a000, [(0x55c+4*(QUEUE_ID-1), struct.pack('<I', 0x6600000))]),
        sparse_page(0x62000, [(0xc50+4*(QUEUE_ID-1), bytes(4))], write_initializes=True),
        sparse_page(0x64000, [], write_initializes=True),
        sparse_page(0x288d000, [(0x207, boot_wb[0])] if boot_wb else [], write_initializes=True),
        sparse_page(0x288c000, [], write_initializes=True),
        # Explicit disabled event-trace configuration and its unlocked spinlock.
        # The native mask check and atomic lock/unlock still execute.
        sparse_page(0x1add000, [(0xcc4, bytes(4))]),
        sparse_page(0x190b000, [(0xbf0, bytes(4))], 'r')])
    prepared_config = {**config, 'regions': [*regions, sparse_page(0x6b00000, [(0, bytes(8))], 'r')],
                       'entry': 0x4b0c4, 'registers': {'R0': QUEUE_ID, 'R1': 0x6b00000, 'SP': STACK, 'LR': STOP, 'CPSR': 0x13},
                       'outputs': [*config['outputs'], {'address': 0x62000, 'size': 4096}, {'address': 0x64000, 'size': 4096}, {'address': 0x1add000, 'size': 4096}, {'address': 0x288d000, 'size': 4096}, {'address': 0x288c000, 'size': 4096}],
                       'provenance': {**config['provenance'], 'scope': 'Native receiver event-flag constructor, flags initially zero',
                                      'current_thread': 'Explicit ID=9 at 0x66000cc and matching table slot; direct entry, no scheduler'}}
    if extended_config is not None:
        prepared_config['outputs'].append({'address': 0x3374000, 'size': 4096})
        prepared_config['memory_trace'] = [*config.get('memory_trace', []), {'address': 0x3374000, 'size': 4096},
                                           {'address': 0x6c20000, 'size': 0x2000}, {'address': 0x190d784, 'size': 1}]
    initialized = run_function(prepared_config)
    object_address = 0x64554+16*(QUEUE_ID-1)
    ok = (initialized['reached_stop'] and not initialized['faults'] and initialized['registers']['R0'] == '0x0'
          and output_bytes(initialized, object_address, 16) == bytes(16)
          and output_bytes(initialized, 0x62c50+4*(QUEUE_ID-1), 4) == struct.pack('<I', object_address))
    if not ok:
        compact_execution(initialized, 0)
        return {'preparation_passed': False, 'event_flag_constructor': initialized}
    regions = [r for r in resume_regions(prepared_config, initialized) if r['address'] != 0x6b00000]
    result = run_function({**prepared_config, 'entry': 0x221a290, 'regions': regions,
                           'outputs': [*prepared_config['outputs'], {'address': 0x7000000, 'size': 65536}],
                           'memory_trace': [*prepared_config.get('memory_trace', []), {'address': 0x288d000, 'size': 4096},
                                            {'address': 0x680f000, 'size': 4096}, {'address': 0x288c000, 'size': 4096},
                                            {'address': 0x6800000, 'size': 4096}],
                           'registers': {'R0': QUEUE_ID, 'SP': STACK, 'LR': STOP, 'CPSR': 0x13},
                           'instruction_limit': 50000,
                           'register_trace': [0x21ae6fc, 0x21aee14, 0x2207464, 0x21d28e4, 0x2218a80, 0x2205944,
                                              0x2199240, 0x2199744, 0x2218af8,
                                              0x22054a0, 0x22053c0, 0x22055ec, 0x2205924,
                                              0x219eb88, 0x21ca300, 0x11ac6b8, 0x11ac76c] if extended_config else [],
                           'provenance': {**prepared_config['provenance'], 'scope': 'Native receiver task loop, explicit ID=9, direct core-0 entry, no scheduler',
                                          'cfg_feb0': cfg_feb0, 'cfg_feb0_recovered_from_camera': False,
                                          'firmware_configuration': firmware_config[1] if firmware_config else None,
                                          'wb_padding_provenance': boot_wb[1]['scope'] if boot_wb else None,
                                          'extended_configuration': extended_config[1]['provenance'] if extended_config else None,
                                          'configuration_page_offset': '0xf000' if firmware_config and not extended_config else None,
                                          'configuration_prefix_loaded': extended_config is not None,
                                          'raw_resource_plan': resource_plan}})
    result['scope'] = 'Receiver frontier; a memory fault is not a completed image operation'
    wb_page = next(r for r in result['regions'] if int(r['address'], 16) == 0x288d000)
    known = {int(r['address'], 16)+i for r in wb_page.get('final_valid_ranges', []) for i in range(r['size'])}
    result['white_balance_structure'] = {
        'address': '0x288d1fc', 'size': 12,
        'known_offsets': [i for i in range(12) if 0x288d1fc+i in known],
        'unknown_offsets': [i for i in range(12) if 0x288d1fc+i not in known],
        'global_initialization_recovered': False}
    notification = output_bytes(result, 0x6a04004, 24)
    result['notification_hex'] = notification.hex()
    result['checks'] = {
        'expected_configuration_frontier': len(result['faults']) == 1
            and result['faults'][0]['address'] == '0x680feb0' and result['faults'][0]['pc'] == '0x126396c',
        'raw_queue_drained': output_bytes(result, QUEUE_OBJECT+24, 4) == bytes(4),
        'raw_message_block_released': output_bytes(result, POOL_OBJECT+8, 4) == struct.pack('<I', CAPACITY),
        'wrapper_operation_installed': output_bytes(result, 0x6500004, 1) == b'\x23',
        'wrapper_callback_installed': output_bytes(result, 0x6500008, 4) == struct.pack('<I', 0x21d28e4),
        'wrapper_type_installed': output_bytes(result, 0x650000c, 1) == b'\5',
        'coordinator_message_enqueued': output_bytes(result, 0x7ad2c+36*6+24, 4) == struct.pack('<I', 1),
        'native_notification_header': struct.unpack('<HBBI', notification[:8]) == (0x923c, 9, 7, 16),
        'native_notification_context': notification[8:16] == struct.pack('<II', 0x6500000, 0x6000000),
        'native_notification_operation': notification[20] == 0x23,
        'diagnostic_lock_released': output_bytes(result, 0x1addcc4, 4) == bytes(4)}
    if firmware_config is not None:
        result['checks']['expected_configuration_frontier'] = (
            len(result['faults']) == 1 and result['faults'][0]['address'] == '0x288d204'
            and result['faults'][0]['pc'] == '0x21ae880' and result['faults'][0]['size'] == 4)
        result['checks']['wb_fields_written_padding_unknown'] = (
            result['white_balance_structure']['known_offsets'] == list(range(11))
            and result['white_balance_structure']['unknown_offsets'] == [11])
        result['checks']['firmware_configuration_byte_read'] = any(
            a['access'] == 'read' and a['address'] == '0x680feb0' and a['pc'] == '0x126396c'
            for a in result['memory_trace'])
    if boot_wb is not None:
        result['checks']['expected_configuration_frontier'] = (
            len(result['faults']) == 1 and result['faults'][0]['address'] == '0x190d784'
            and result['faults'][0]['pc'] == '0x1294d80' and result['faults'][0]['size'] == 1)
        result['checks'].pop('wb_fields_written_padding_unknown')
        result['checks']['wb_structure_fully_defined'] = (
            result['white_balance_structure']['known_offsets'] == list(range(12)))
        result['checks']['native_wb_copy_completed'] = all(
            any(a['access'] == 'write' and a['address'] == hex(address) and a['size'] == 4
                and a['pc'] == '0x21ae884' for a in result['memory_trace'])
            for address in (0x288cec8, 0x288cecc, 0x288ced0))
        result['checks']['native_gain_function_reached'] = '0x22a830c' in result['trace_tail']
    if extended_config is not None:
        samples = result['register_trace']
        calls = {s['pc']: s['registers'] for s in samples}
        progress = [int(s['registers']['R1'], 16) for s in samples if s['pc'] == '0x21d28e4']
        result['native_progress_codes'] = progress
        result['wb_parameter_words'] = list(struct.unpack('<3H', output_bytes(result, 0x3374016, 6)))
        result['resource_frontier'] = {'owner_context': '0x600003c', 'request_type': '0x2f', 'index': 0,
                                       'lookup_result': calls.get('0x2199744', {}).get('R0'),
                                       'scope': 'No matching owner/type/index lease; no pixel buffer supplied'}
        result['checks']['expected_configuration_frontier'] = (
            len(result['faults']) == 1 and result['faults'][0]['address'] == '0x0'
            and result['faults'][0]['pc'] == '0x2218b04' and result['faults'][0]['size'] == 4)
        result['checks']['coordinator_message_enqueued'] = output_bytes(result, 0x7ad2c+36*6+24, 4) == struct.pack('<I', 3)
        result['checks']['native_gain_function_reached'] = '0x21aee14' in calls
        result['checks']['native_wb_handler_returned'] = '0x2207464' in calls
        result['checks']['native_progress_sequence'] = progress == [8, 9, 0x28]
        result['checks']['missing_intermediate_resource_identified'] = (
            all(calls.get('0x2199240', {}).get(k) == v for k, v in
                {'R0': '0x600003c', 'R1': '0x2f', 'R2': '0x0'}.items())
            and calls.get('0x2199744', {}).get('R0') == '0x0'
            and calls.get('0x2218af8', {}).get('R0') == '0x0')
        result['checks']['register_observations_complete'] = not result['register_trace_truncated']
    if resource_plan is not None:
        mode = config['provenance']['request_mode']
        descriptor_address, descriptor = {
            2: (0x25d8cec, [0, 0x34983c00, 0xc80000, 0x1400, 0x1400, 0xa00, 2]),
            6: (0x25d6ddc, [1, 0x65a00000, 55464192, 12768, 12768, 4344, 1]),
            7: (0x25e3efc, [1, 0x65a00000, 55464192, 12768, 12768, 4344, 1])}[mode]
        lease = output_bytes(result, 0x3731220, 36)
        transfer = calls.get('0x219eb88', {}).get('R1')
        geometry = list(struct.unpack('<6I', output_bytes(result, int(transfer, 16), 24))) if transfer else None
        result['resource_frontier'] = {
            'owner_context': '0x600003c', 'request_type': '0x2f', 'index': 0,
            'lease_address': '0x3731220', 'slot': 1, 'descriptor_address': hex(descriptor_address),
            'request_mode': mode,
            'descriptor_words': descriptor, 'lookup_result': calls.get('0x2218af8', {}).get('R0'),
            'transfer_words': geometry,
            'transfer_layout': ['source', 'source_stride', 'destination', 'destination_stride', 'width_bytes', 'rows'],
            'scope': 'Native lease and transfer setup; source pixels absent, destination not mapped'}
        if geometry:
            required = geometry[2] - descriptor[1] + (geometry[5]-1)*geometry[3] + geometry[4]
            result['resource_frontier']['destination_required_extent'] = required
            result['resource_frontier']['destination_static_capacity'] = descriptor[2]
            result['resource_frontier']['fits_static_capacity'] = 0 <= geometry[2]-descriptor[1] and required <= descriptor[2]
        result['checks'].pop('missing_intermediate_resource_identified')
        result['checks']['expected_configuration_frontier'] = (
            len(result['faults']) == 1 and result['faults'][0]['address'] == '0x7acd0'
            and result['faults'][0]['pc'] == '0x5500c' and result['faults'][0]['size'] == 4)
        result['checks']['native_raw_plan_preserved'] = output_bytes(result, 0x600003b, 1) == b'\6'
        result['checks']['native_intermediate_lease_created'] = (
            lease[:6] == struct.pack('<hBBh', 1, 0x2f, 0, 1)
            and lease[8:] == struct.pack('<7I', *descriptor)
            and any(s['pc'] == '0x22053c0' and s['registers']['R1'] == '0x2f'
                    and s['registers']['R2'] == '0x0' for s in samples))
        result['checks']['native_descriptor_lookup_succeeded'] = (
            calls.get('0x2199744', {}).get('R0') == '0x1'
            and calls.get('0x2218af8', {}).get('R0') == hex(descriptor_address))
        result['checks']['native_transfer_setup_reached'] = all(
            address in calls for address in ('0x219eb88', '0x21ca300', '0x11ac6b8', '0x11ac76c'))
    result['passed'] = all(result['checks'].values())
    stack = bytes.fromhex(next(o['hex'] for o in result['outputs'] if int(o['address'], 16) == 0x7000000))
    # The harness does not export FP. Frame pointers are discovered only when
    # their previous-frame/return pair fits the observed GCC ARM stack layout.
    frames = []
    for offset in range(int(result['registers']['SP'], 16)-0x7000000, len(stack)-4, 4):
        previous, returned = struct.unpack_from('<II', stack, offset)
        if 0x7000000+offset < previous < STACK and (0x1021000 <= returned < 0x1735000 or 0x1e0f000 <= returned < 0x270f000):
            frames.append({'address': hex(0x7000000+offset), 'previous_fp': hex(previous), 'return_candidate': hex(returned)})
    result['stack_frame_candidates'] = frames
    result['preparation_passed'] = True
    compact_execution(initialized, 0)
    result['event_flag_constructor'] = initialized
    compact_execution(result, 0)
    return result


def wrapper_runtime(directory):
    """Native wrapper defaults, then native binding to our context address."""
    ram = sparse_page(0x6500000, [], write_initializes=True)
    stages = []
    for entry in [0x2204830, 0x2204880]:
        result = run_function({'architecture': 'arm', 'entry': entry, 'stop': STOP,
                               'regions': [*modules(directory), ram, {'address': 0x7000000, 'size': 65536, 'permissions': 'rw'}],
                               'registers': {'R0': 0x6500000, 'R1': 0x6000000, 'SP': STACK, 'LR': STOP},
                               'outputs': [{'address': 0x6500000, 'size': 4096}], 'instruction_limit': 1000,
                               'provenance': {'scope': 'Native wrapper constructor and context binding', 'stubs': [], 'patched_instructions': False}})
        if not result['reached_stop'] or result['faults'] or result['registers']['SP'] != hex(STACK):
            raise ValueError('Native wrapper initialization failed')
        ram = snapshot_native_ram(result, [0x6500000], write_initializes=True)[0]
        compact_execution(result, 0)
        stages.append(result)
    data = bytes.fromhex(ram['hex'])
    if data[:4] != struct.pack('<I', 0x6000000) or data[0x44:0x47] != bytes([0, 3, 1]):
        raise ValueError('Native wrapper fields differ from the observed constructor')
    return ram, {'passed': True, 'stages': stages}
