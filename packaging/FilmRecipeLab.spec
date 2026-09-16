# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from fuji_recipe_lab import __version__


project_root = Path(SPEC).resolve().parent.parent
datas = collect_data_files(
    "fuji_recipe_lab",
    includes=["static/*", "luts/*.json"],
)
datas += [
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "THIRD_PARTY.md"), "."),
]
notices = project_root / "build" / "release-notices"
if not (notices / "inventory.json").is_file():
    raise RuntimeError("Run scripts/prepare_release_notices.py before packaging")
datas.append((str(notices), "Third-Party-Notices"))

a = Analysis(
    [str(project_root / "fuji_recipe_lab" / "desktop.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["capstone", "unicorn"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Film Recipe Lab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Film Recipe Lab",
)
app = BUNDLE(
    coll,
    name="Film Recipe Lab.app",
    icon=None,
    bundle_identifier="com.avogadrobit.film-recipe-lab",
    version=__version__,
    info_plist={
        "CFBundleDisplayName": "Film Recipe Lab",
        "CFBundleName": "Film Recipe Lab",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 Paul Wellenreiter",
    },
)
