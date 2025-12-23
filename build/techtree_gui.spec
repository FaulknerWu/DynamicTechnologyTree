# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Stellaris Tech Tree Generator GUI
# Usage: pyinstaller build/techtree_gui.spec

from pathlib import Path
import os

# SPECPATH is provided by PyInstaller
project_root = Path(SPECPATH).parent

block_cipher = None

a = Analysis(
    [str(project_root / 'scripts' / 'generate_tech_tree_gui.py')],
    pathex=[
        str(project_root / 'src'),
        str(project_root / 'scripts'),
    ],
    binaries=[],
    datas=[
        (str(project_root / 'src' / 'gui'), 'gui'),
        (str(project_root / 'src' / 'mixins'), 'mixins'),
    ],
    hiddenimports=[
        'gui',
        'gui.fonts',
        'gui.path_detector',
        'gui.title_bar',
        'gui.config_editor',
        'gui.main_window',
        'gui.generation_worker',
        'generator',
        'config',
        'mixins.config_mixin',
        'mixins.parser_mixin',
        'mixins.render_mixin',
        'mixins.relations_mixin',
        'mixins.output_mixin',
        'mixins.stats_mixin',
        'mixins.cycle_mixin',
        'localization',
        'models',
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TechTreeGeneratorGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if needed: icon='icon.ico'
)
