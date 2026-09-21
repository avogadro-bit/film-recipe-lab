"""Native module descriptor and bounded BSS-clear slice; not a full boot."""
import hashlib
import struct

from .emulation import run_function
from .pipeline import MAIN_SHA256, modules, compact_execution
from .runtime import sparse_page
from .synchronization import STACK, STOP


def wb_boot_padding(directory):
    main = (directory / 'main.bin').read_bytes()
    if hashlib.sha256(main).hexdigest() != MAIN_SHA256:
        raise ValueError('Pinned main segment hash mismatch; boot descriptor not loaded')
    header = main[0x140000:0x140400]
    code = modules(directory)
    descriptor = struct.unpack_from('<9I', header, 0x13c)
    if descriptor != (6, 0x1e0f000, 0x900000, 0x270f000, 0x126a000, 0x5c0000, 0x520000, 0x20, 1):
        raise ValueError('Unexpected module-6 boot descriptor')
    common = {'architecture': 'arm', 'stop': STOP,
              'regions': [*code, sparse_page(0xe20000, [(0, header)], 'r'),
                          sparse_page(0x700f000, [], write_initializes=True)],
              'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13}, 'instruction_limit': 3000,
              'provenance': {'scope': 'Native module lookup and BSS fallback; selected WB page only',
                             'source_main_sha256': MAIN_SHA256, 'descriptor_file_offset': '0x14013c',
                             'descriptor_hex': header[0x13c:0x160].hex(),
                             'full_boot_executed': False, 'dma_emulated': False,
                             'patched_instructions': False, 'stubs': []}}
    lookup = run_function({**common, 'entry': 0x1290fb8,
                           'registers': {**common['registers'], 'R0': 6}})
    if not lookup['reached_stop'] or lookup['registers']['R0'] != '0xe2013c':
        raise ValueError('Native module lookup failed')
    # Observe the real software fallback's complete BSS range BEFORE memset.
    setup = run_function({**common, 'entry': 0x1264a90, 'stop': 0x1281a40,
                          'registers': {**common['registers'], 'R4': 0xe2013c}})
    if (not setup['reached_stop'] or [setup['registers'][r] for r in ('R0', 'R1', 'R2')]
            != ['0x270f000', '0x0', '0x126a000']):
        raise ValueError('Native BSS fallback arguments differ')
    page = 0x288d000
    if not descriptor[3] <= page < page+4096 <= descriptor[3]+descriptor[4]:
        raise ValueError('WB page outside native clear range')
    # Bound the large BSS clear to this 4 KiB subrange. This is an
    # explicitly narrowed call to the SAME native byte-fill function, not
    # an assertion that the complete boot sequence ran in the emulator.
    result = run_function({**common, 'entry': 0x1281a40,
                           'regions': [*common['regions'], sparse_page(page, [], write_initializes=True)],
                           'registers': {**common['registers'], 'R0': page, 'R1': 0, 'R2': 4096},
                           'outputs': [{'address': page, 'size': 4096}],
                           'memory_trace': [{'address': page, 'size': 4096}],
                           'memory_trace_limit': 10000, 'instruction_limit': 10000})
    writes = {int(a['address'], 16)+i for a in result['memory_trace']
              if a['access'] == 'write' for i in range(a['size'])}
    if (not result['reached_stop'] or result['registers']['SP'] != hex(STACK)
            or result['outputs'][0]['hex'] != '00'*4096
            or result['memory_trace_truncated'] or writes != set(range(page, page+4096))):
        raise ValueError('Native bounded BSS clear failed')
    padding = bytes.fromhex(result['outputs'][0]['hex'])[0x207:0x208]
    report = {'passed': True, 'full_boot_executed': False,
              'scope': 'Padding cold-state derived from real BSS fallback; only selected page fill executed',
              'native_clear_range': {'address': hex(descriptor[3]), 'size': descriptor[4]},
              'executed_clear_range': {'address': hex(page), 'size': 4096},
              'transferred_range': {'address': '0x288d207', 'size': 1},
              'lookup': lookup, 'fallback_arguments': setup, 'page_clear': compact_execution(result, 0)}
    return padding, report
