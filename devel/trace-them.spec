# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller --onedir build specification for Trace Them."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "trace_them" / "resources" / "*.json"), "trace_them/resources"),
]
datas += collect_data_files("jsonschema_specifications")
datas += collect_data_files("jsonschema")

hiddenimports = [
    "socks",
    "sockshandler",
    "openpyxl",
]
hiddenimports += collect_submodules("jsonschema_specifications")

a = Analysis(
    [str(ROOT / "devel" / "trace-them.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="trace-them",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "docs" / "images" / "trace-them.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="trace-them",
)
