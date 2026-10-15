# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for SpeakSync on Windows."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None
project_root = Path.cwd().resolve()

# Collect dynamic libraries, modules, and data for wx and prism
prism_datas, prism_binaries, prism_hidden = collect_all("prism")
wx_datas, wx_binaries, wx_hidden = collect_all("wx")

datas = [
    (str(project_root / "assets"), "assets"),
] + prism_datas + wx_datas

binaries = prism_binaries + wx_binaries

hiddenimports = [
    "soundobj",
    "_c_miniaudio",
    "prism",
    "prism._native",
    "prism.common",
    "prism.core",
    "prism.custom",
    "prism._dispatch",
    "pynput",
    "pynput.keyboard",
    "pynput.keyboard._win32",
    "pynput.mouse",
    "pynput.mouse._win32",
    "comtypes",
    "comtypes.client",
    "comtypes.stream",
    "win32gui",
    "win32con",
    "win32process",
    "win32api",
    "win32event",
    "pkg_resources",
] + prism_hidden + wx_hidden

ico_path = project_root / "assets" / "speaksync.ico"
app_icon = str(ico_path) if ico_path.is_file() else None

a = Analysis(
    [str(project_root / "src" / "speak_sync" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pytest", "PIL._imagingtk", "PIL.ImageTk"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="speaksync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="speaksync",
)
