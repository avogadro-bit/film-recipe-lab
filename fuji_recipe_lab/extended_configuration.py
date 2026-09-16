"""Native loading primitives for the DEFAULT block stored in the pinned DAT.

Storage hardware is not emulated. The real native memcpy loads the verified
ROM bytes into guarded RAM; the address-selection path is tested separately.
"""
import hashlib
import struct

from .emulation import run_function
from .pipeline import MAIN_SHA256, modules, compact_execution
from .runtime import sparse_page
from .requests_runtime import snapshot_native_ram
from .synchronization import STACK, STOP

FILE_OFFSET = 0x1837300
BLOCK_SIZE = 0x2000
BLOCK_SHA256 = '6d960689ca466293128590e92b9dd2ad407e7b051f88c5adaf44749d200f3a29'
DESTINATION = 0x6c20000
FLASH_ADDRESS = 0xf0000000+FILE_OFFSET


def verified_default_block(directory):
    main = (directory / 'main.bin').read_bytes()
    if hashlib.sha256(main).hexdigest() != MAIN_SHA256:
        raise ValueError('Pinned main hash mismatch; extended configuration unavailable')
    descriptor = struct.unpack_from('<9I', main, 0x140184)
    if descriptor != (8, 0, 0, 0, 0, 0x1820000, 0x20000, 0, 0):
        raise ValueError('Unexpected DEFAULT block descriptor')
    data = main[FILE_OFFSET:FILE_OFFSET+BLOCK_SIZE]
    if hashlib.sha256(data).hexdigest() != BLOCK_SHA256 or data[:8] != b'FLSNW001':
        raise ValueError('Pinned DEFAULT block hash or signature mismatch')
    provenance = {'scope': 'X-T4 DAT DEFAULT block; native primitives, no complete storage initialization',
                  'source': str((directory / 'main.bin').resolve()), 'source_sha256': MAIN_SHA256,
                  'file_offset': hex(FILE_OFFSET), 'size': BLOCK_SIZE, 'sha256': BLOCK_SHA256,
                  'configuration_offset': '0x420000', 'flash_address': hex(FLASH_ADDRESS),
                  'access_mode': 'Explicit mode 0, set by native setter; not a recovered live mode',
                  'live_camera_dump': False, 'storage_hardware_emulated': False,
                  'patched_instructions': False, 'stubs': [], 'image_pipeline_executed': False}
    return data, main[0x140000:0x140400], provenance


def extended_configuration_runtime(directory):
    data, header, provenance = verified_default_block(directory)
    code = modules(directory)
    common = {'architecture': 'arm', 'stop': STOP, 'instruction_limit': 20000,
              'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13}, 'provenance': provenance}
    stack = sparse_page(0x700f000, [], write_initializes=True)
    # Native descriptor lookup and address arithmetic to the storage callee.
    address = run_function({**common, 'entry': 0x1265520, 'stop': 0x11a6c7c,
                            'regions': [*code, stack, sparse_page(0xe20000, [(0, header)], 'r')],
                            'registers': {**common['registers'], 'R0': 1, 'R1': DESTINATION, 'R2': BLOCK_SIZE}})
    expected = {'R0': DESTINATION, 'R1': FLASH_ADDRESS, 'R2': BLOCK_SIZE, 'R3': 1}
    if not address['reached_stop'] or any(address['registers'][r] != hex(v) for r, v in expected.items()):
        raise ValueError('Native DEFAULT address selection failed')
    source = []
    for page in range(FLASH_ADDRESS & ~4095, FLASH_ADDRESS+BLOCK_SIZE, 4096):
        first, last = max(page, FLASH_ADDRESS), min(page+4096, FLASH_ADDRESS+BLOCK_SIZE)
        source.append(sparse_page(page, [(first-page, data[first-FLASH_ADDRESS:last-FLASH_ADDRESS])], 'r'))
    pages = [DESTINATION, DESTINATION+4096]
    copied = run_function({**common, 'entry': 0x1281848,
                           'regions': [*code, stack, *source, *[sparse_page(p, [], write_initializes=True) for p in pages]],
                           'registers': {**common['registers'], 'R0': DESTINATION, 'R1': FLASH_ADDRESS, 'R2': BLOCK_SIZE},
                           'outputs': [{'address': p, 'size': 4096} for p in pages],
                           'memory_trace': [{'address': DESTINATION, 'size': BLOCK_SIZE}, {'address': FLASH_ADDRESS, 'size': BLOCK_SIZE}],
                           'memory_trace_limit': 10000})
    if (not copied['reached_stop'] or copied['registers']['SP'] != hex(STACK)
            or b''.join(bytes.fromhex(o['hex']) for o in copied['outputs']) != data
            or copied['memory_trace_truncated']):
        raise ValueError('Native DEFAULT copy failed')
    ram = snapshot_native_ram(copied, pages)
    # Verify all three modes emitted by the observed native callers. The
    # configuration translator reads this state but preserves the offset.
    modes = []
    selected = None
    for mode in (0, 1, 2):
        initialized = run_function({**common, 'entry': 0x1294d90,
                                    'regions': [*code, stack, sparse_page(0x190d000, [], write_initializes=True)],
                                    'registers': {**common['registers'], 'R0': mode},
                                    'outputs': [{'address': 0x190d000, 'size': 4096}]})
        if not initialized['reached_stop'] or initialized['registers']['SP'] != hex(STACK):
            raise ValueError('Native access-mode setter failed')
        state = snapshot_native_ram(initialized, [0x190d000])[0]
        reader = run_function({**common, 'entry': 0x12f20d8,
                               'regions': [*code, stack, *ram, state,
                                           sparse_page(0x17b2000, [(0x764, struct.pack('<I', 0x6800000))], 'r')],
                               'outputs': [], 'memory_trace': [{'address': DESTINATION, 'size': BLOCK_SIZE}]})
        passed = (reader['reached_stop'] and reader['registers']['R0'] == '0x1'
                  and reader['registers']['SP'] == hex(STACK)
                  and any(a['address'] == hex(DESTINATION+0xf82) and a['access'] == 'read' for a in reader['memory_trace']))
        if not passed:
            raise ValueError('Native DEFAULT count reader failed')
        if mode == 0:
            selected = state
        modes.append({'mode': mode, 'passed': passed, 'setter': compact_execution(initialized, 0), 'reader': reader})
    for region in [*ram, selected]:
        region['permissions'] = 'r'
        region.pop('write_initializes', None)
    return [*ram, selected], {'passed': True, 'provenance': provenance, 'address_selection': address,
                              'native_copy': compact_execution(copied, 0), 'modes': modes,
                              'count': data[0xf82], 'configuration_end': '0x422000',
                              'remaining_extended_configuration_loaded': False}
