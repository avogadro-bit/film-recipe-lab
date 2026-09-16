"""Pinned configuration supplied in the X-T4 DAT, not a live camera dump.

The native loader reads 0x72000 bytes starting at flash block 6 (128 KiB
blocks). main.bin contains the expected AA55 marker and WB tables there.
Only this prefix is available; do not zero-fill the rest of cfgdata.
"""
import hashlib
import struct

from .emulation import run_function
from .pipeline import MAIN_SHA256, modules, compact_execution
from .runtime import sparse_page
from .synchronization import STACK, STOP

FLASH_OFFSET = 0xc0000
PREFIX_SIZE = 0x72000
PREFIX_SHA256 = '4b9d1113af1fc914fa2055df1087ffc665585aecf27116c50debd47eee56e643'
CFG = 0x6800000


def firmware_configuration(directory):
    main = (directory / 'main.bin').read_bytes()
    if hashlib.sha256(main).hexdigest() != MAIN_SHA256:
        raise ValueError('Pinned main segment hash mismatch; configuration not loaded')
    prefix = main[FLASH_OFFSET:FLASH_OFFSET+PREFIX_SIZE]
    if (len(prefix) != PREFIX_SIZE or hashlib.sha256(prefix).hexdigest() != PREFIX_SHA256
            or prefix[0x202:0x204] != b'\x55\xaa'):
        raise ValueError('Pinned firmware configuration range or marker mismatch')
    provenance = {
        'source': str((directory / 'main.bin').resolve()), 'source_sha256': MAIN_SHA256,
        'file_offset': hex(FLASH_OFFSET), 'size': PREFIX_SIZE, 'sha256': PREFIX_SHA256,
        'scope': 'Configuration prefix supplied in X-T4 2.12 DAT; not live unit calibration',
        'native_loader': '0x1263f40 -> 0x1264db8, start block 6, size 0x72000',
        'flash_address': '0xf00c0000', 'live_camera_dump': False,
        'x100vi_compatibility_validated': False,
        'unknown_configuration_range': '0x72000..0x4bffff remains unavailable'}
    return prefix, provenance


def configuration_page(prefix, page_offset):
    if (type(page_offset) is not int or page_offset < 0 or page_offset % 4096
            or page_offset+4096 > len(prefix)):
        raise ValueError('Configuration page must be aligned and inside recovered prefix')
    data = prefix[page_offset:page_offset+4096]
    return {'address': CFG+page_offset, 'size': 4096, 'permissions': 'r',
            'hex': data.hex(), 'initialized_only': True,
            'expected_sha256': hashlib.sha256(data).hexdigest()}


def install_configuration_prefix(regions, prefix):
    """Replace compatible sparse read-only fixtures with verified DAT pages."""
    retained = []
    for region in regions:
        address, size = region['address'], region['size']
        if address < CFG+len(prefix) and CFG < address+size:
            if (address < CFG or address+size > CFG+len(prefix) or region['permissions'] != 'r'
                    or 'valid_ranges' not in region or 'hex' not in region):
                raise ValueError('Unverifiable configuration overlap')
            before = bytes.fromhex(region['hex'])
            for valid in region['valid_ranges']:
                start, count = valid['offset'], valid['size']
                if before[start:start+count] != prefix[address-CFG+start:address-CFG+start+count]:
                    raise ValueError('Conflicting configuration fixture and DAT bytes')
        else:
            retained.append(region)
    return [*retained, *[configuration_page(prefix, p) for p in range(0, len(prefix), 4096)]]


def configuration_probe(directory):
    from .white_balance import _execute, _returned, shift_offset, OUTPUT
    prefix, provenance = firmware_configuration(directory)
    code = modules(directory)
    cases = []
    # Stop BEFORE storage hardware calls. These are address/ABI observations,
    # not successful flash reads and not stubbed calls.
    for entry, boundary, registers, expected in [
        (0x1264db8, 0x1264250, {'R0': CFG, 'R1': 0, 'R2': PREFIX_SIZE},
         {'R0': 6, 'R1': 3, 'R2': CFG, 'R3': 0}),
        (0x126420c, 0x11a6c7c, {'R0': FLASH_OFFSET, 'R1': CFG, 'R2': 0x60000},
         {'R0': CFG, 'R1': 0xf0000000+FLASH_OFFSET, 'R2': 0x60000, 'R3': 1})]:
        result = run_function({'architecture': 'arm', 'entry': entry, 'stop': boundary,
                               'regions': [*code, sparse_page(0x700f000, [], write_initializes=True)],
                               'registers': {'SP': STACK, 'LR': STOP, 'CPSR': 0x13, **registers},
                               'instruction_limit': 500,
                               'provenance': {**provenance, 'scope': 'Native address calculation to explicit callee boundary; no storage read',
                                              'patched_instructions': False, 'stubs': []}})
        ok = result['reached_stop'] and all(result['registers'][r] == hex(v) for r, v in expected.items())
        cases.append({'kind': 'flash_address_boundary', 'passed': ok, 'execution': result})

    # Run the real little-endian reader on firmware bytes, including marker and
    # the configuration byte that blocked the RAW receiver.
    for offset, size in [(0x202, 2), (0xfeb0, 1), (0xa8, 1), (0x5e8c, 1)]:
        result = run_function({'architecture': 'arm', 'entry': 0x1263bf4 if size == 2 else 0x1263954,
                               'stop': STOP, 'regions': [*code, configuration_page(prefix, offset & ~4095),
                                   sparse_page(0x17b2000, [(0x764, struct.pack('<I', CFG))], 'r'),
                                   sparse_page(0x700f000, [], write_initializes=True)],
                               'registers': {'R0': offset, 'SP': STACK, 'LR': STOP, 'CPSR': 0x13},
                               'memory_trace': [{'address': CFG+offset, 'size': size}],
                               'instruction_limit': 500, 'provenance': provenance})
        expected = int.from_bytes(prefix[offset:offset+size], 'little')
        ok = (result['reached_stop'] and result['registers']['R0'] == hex(expected)
              and result['registers']['SP'] == hex(STACK))
        cases.append({'kind': 'native_configuration_read', 'offset': hex(offset), 'value': expected,
                      'passed': ok, 'execution': result})

    # Every pair of WB shifts uses the actual DAT coefficients. Neither preset
    # count nor any unobserved high configuration page is supplied here.
    for red in range(-9, 10):
        for blue in range(-9, 10):
            offsets = [shift_offset(0, red), shift_offset(1, blue)]
            fields = [(offset-0xf000, prefix[offset:offset+2]) for offset in offsets if offset is not None]
            result = _execute(code, 0x22a7cf4, b'',
                              {'R0': red & 0xffffffff, 'R1': blue & 0xffffffff, 'R2': OUTPUT}, fields,
                              provenance=provenance)
            expected = [struct.unpack_from('<H', prefix, offset)[0] if offset is not None else 1024 for offset in offsets]+[1024]
            observed = {int(a['address'], 16)+i-CFG for a in result['memory_trace']
                        if a['access'] == 'read' and CFG <= int(a['address'], 16) < CFG+PREFIX_SIZE
                        for i in range(a['size'])}
            required = {offset+i for offset in offsets if offset is not None for i in (0, 1)}
            ok = _returned(result, expected) and observed == required
            cases.append({'kind': 'firmware_wb_shifts', 'red': red, 'blue': blue,
                          'coefficients': expected, 'passed': ok, 'execution': compact_execution(result, 6)})
    from .bootstrap import wb_boot_padding
    _, bootstrap = wb_boot_padding(directory)
    from .extended_configuration import extended_configuration_runtime
    _, extended = extended_configuration_runtime(directory)
    return {'passed': all(c['passed'] for c in cases) and bootstrap['passed'] and extended['passed'], 'provenance': provenance, 'cases': cases,
            'wb_boot_padding': bootstrap,
            'extended_configuration': extended,
            'firmware_configuration_recovered': True, 'live_calibration_recovered': False,
            'image_pipeline_validated': False, 'camera_emulated': False}
