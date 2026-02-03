# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Stellaris Tech Tree Generator GUI
# Usage: pyinstaller packaging/pyinstaller/techtree_gui.spec

from __future__ import annotations

from pathlib import Path

# SPECPATH is provided by PyInstaller and points to this spec's directory.
spec_dir = Path(SPECPATH).resolve()
project_root = spec_dir.parent.parent

src_dir = project_root / "src"
entry_script = src_dir / "gui" / "__main__.py"
font_file = src_dir / "gui" / "fonts" / "NotoSansSC-Regular.otf"

block_cipher = None

a = Analysis(
    [str(entry_script)],
    pathex=[
        str(src_dir),
    ],
    binaries=[],
    datas=[
        (str(font_file), "gui/fonts"),
    ],
    hiddenimports=[
        "gui",
        "gui.fonts",
        "gui.path_detector",
        "gui.title_bar",
        "gui.config_editor",
        "gui.i18n",
        "gui.main_window",
        "gui.generation_worker",
        "generator",
        "config",
        "dtt_core",
        "dtt_core.config_loader",
        "dtt_core.scan_parse",
        "dtt_core.render",
        "dtt_core.output",
        "dtt_core.relations",
        "dtt_core.cycle",
        "dtt_core.stats",
        "localization",
        "models",
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
    name="TechTreeGeneratorGUI",
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
    icon=None,
)
