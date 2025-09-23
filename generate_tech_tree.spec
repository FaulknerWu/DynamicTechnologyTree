# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DynamicTechnologyTree generator.
- Does NOT bundle external config.ini (user editable next to exe)
- Includes package dtt and localisation resources
"""

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

def collect_localisation_datas():
    datas = []
    loc_root = os.path.join(os.path.abspath('.'), 'localisation')
    if os.path.isdir(loc_root):
        for root, dirs, files in os.walk(loc_root):
            for f in files:
                # Include all localisation yml files
                if f.lower().endswith(('.yml', '.yaml')):
                    full_path = os.path.join(root, f)
                    rel_root = os.path.relpath(root, os.path.abspath('.'))
                    datas.append((full_path, rel_root))
    return datas

# Collect all dtt submodules (mixins etc.)
hiddenimports = collect_submodules('dtt')

a = Analysis(
    ['generate_tech_tree.py'],
    pathex=[],
    binaries=[],
    datas=collect_localisation_datas(),
    hiddenimports=hiddenimports,
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='generate_tech_tree',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # show console for logging output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# No COLLECT step needed for onefile; EXE above is sufficient.
