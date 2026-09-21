"""Legacy identifiers retained solely to preserve existing users' data.

New documentation, commands and exports use KŌRA. Do not remove these aliases
without a migration: changing the macOS bundle ID or WebView location can reset
saved recipes and UI preferences.
"""
import os
import sys
from pathlib import Path

MAC_BUNDLE_ID = 'com.avogadrobit.film-recipe-lab'


def lut_override():
    return os.environ.get('KORA_LUT_DIR', os.environ.get('FUJI_RECIPE_LUT_DIR'))


def lut_directory():
    current = Path.home() / '.local/share/kora/luts'
    legacy = Path.home() / '.local/share/fuji-recipe-lab/luts'
    return current if current.exists() or not legacy.exists() else legacy


def mac_webview_directory():
    base = Path.home() / 'Library/Application Support'
    current = base / 'KŌRA/WebView'
    legacy = base / 'Film Recipe Lab/WebView'
    return current if current.exists() or not legacy.exists() else legacy


def browser_disabled():
    return os.environ.get('KORA_NO_BROWSER', os.environ.get('FILM_RECIPE_LAB_NO_BROWSER')) == '1'


def logs_directory():
    if sys.platform == 'darwin':
        base = Path.home() / 'Library/Logs'
        current, legacy = base / 'KŌRA', base / 'Film Recipe Lab'
    else:
        base = Path.home() / '.local/state'
        current, legacy = base / 'kora', base / 'film-recipe-lab'
    return current if current.exists() or not legacy.exists() else legacy
