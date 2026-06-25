# Beeran's calculator_suite.spec
# PyInstaller spec file for Beeran's Calculator Suite
#
# MODE: onedir  — produces a folder rather than a single exe.
#                 No extraction on every launch → significantly faster startup.
#
# Build:    pyinstaller --clean calculator_suite.spec
# Output:   dist\BeeransCalculatorSuite\BeeransCalculatorSuite.exe
#
# To distribute: zip the entire  dist\BeeransCalculatorSuite\  folder.

import sys, os
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo,
    StringTable, StringStruct, VarFileInfo, VarStruct,
)

block_cipher = None

a = Analysis(
    ['calculator_suite.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'customtkinter',
        'numpy_financial',
        'dateutil',
        'dateutil.relativedelta',
        'PIL',
        'PIL._tkinter_finder',
        'tkinter',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Windows version / metadata ────────────────────────────────────────────────
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 0, 0, 0),
        prodvers=(1, 0, 0, 0),
        mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
        subtype=0x0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName',      'Beeran'),
            StringStruct('FileDescription',  "Beeran's Calculator Suite"),
            StringStruct('FileVersion',      '1.0.0.0'),
            StringStruct('InternalName',     'BeeransCalculatorSuite'),
            StringStruct('LegalCopyright',   'Copyright \u00a9 2026 Beeran. All rights reserved.'),
            StringStruct('OriginalFilename', 'BeeransCalculatorSuite.exe'),
            StringStruct('ProductName',      "Beeran's Calculator Suite"),
            StringStruct('ProductVersion',   '1.0.0.0'),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
    ]
)
# ─────────────────────────────────────────────────────────────────────────────

# ── EXE: launcher only — files go into COLLECT ───────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    name='BeeransCalculatorSuite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='calculator.ico',
    version=version_info,
)

# ── COLLECT: assemble the output folder ──────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BeeransCalculatorSuite',
    contents_directory='.',   # flat layout — all files beside the exe
)

# ── Post-build cleanup ────────────────────────────────────────────────────────
# PyInstaller also writes a standalone EXE directly to dist\ before COLLECT
# runs. That copy has no dependencies and doesn't work — remove it so users
# don't accidentally run the wrong file.
_extra = os.path.join(DISTPATH, 'BeeransCalculatorSuite.exe')
if os.path.exists(_extra):
    os.remove(_extra)
    print(f'[spec] Removed standalone stub: {_extra}')
