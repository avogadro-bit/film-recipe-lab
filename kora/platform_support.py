"""Small operating-system adapters, kept independent of the desktop toolkit."""
import ctypes
import os
from pathlib import Path
import sys


def windows_data_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Kora'


def physical_memory_bytes():
    try:
        if sys.platform == 'win32':
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in
                    ('total_physical', 'available_physical', 'total_page', 'available_page',
                     'total_virtual', 'available_virtual', 'extended_virtual')]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.total_physical
        else:
            return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (AttributeError, OSError, ValueError):
        pass
    return 8 * 1024**3


def drive_roots():
    if sys.platform != 'win32':
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [Path(f'{chr(65+i)}:/') for i in range(26) if mask & (1 << i)]


def adobe_rgb_profile():
    if sys.platform == 'win32':
        directory = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/spool/drivers/color'
        candidates = [directory / name for name in ('AdobeRGB1998.icc', 'AdobeRGB1998.icm', 'Adobe RGB (1998).icc')]
    else:
        candidates = [Path('/System/Library/ColorSync/Profiles/AdobeRGB1998.icc')]
    return next((path for path in candidates if path.is_file()), None)
