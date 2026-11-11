# PyInstaller spec for Inkstone.
#
# Build (run on the TARGET OS — PyInstaller does not cross-compile):
#   pyinstaller pdf/packaging/inkstone.spec
#
# Windows  -> dist/Inkstone/      (one-dir bundle, what the installer installs)
#             dist/Inkstone.exe   (portable single file, double-click to run)
# Linux    -> dist/Inkstone/      (one-dir bundle, wrapped into an AppImage / .deb)
#
# Why two Windows builds: a one-file exe is a self-extracting archive. Every
# launch unpacks the whole Qt + PDF runtime to a temp folder (and the virus
# scanner reads it all again) before a line of Python runs — that, not the
# app, is what makes startup slow, and it happens even when the launch only
# hands a PDF to an already-running window. The one-dir bundle has nothing to
# unpack, so the installed app starts from its own folder. The single file is
# kept for people who want one thing to download and run.
#
# On Windows the icon is icon.ico; on Linux PyInstaller ignores .ico so we pass None.

import sys
from pathlib import Path

spec_dir = Path(SPECPATH)
pdf_dir = spec_dir.parent

is_windows = sys.platform.startswith("win")
icon = str(spec_dir / "icon.ico") if is_windows else None

block_cipher = None

# build_info.json is written by packaging/stamp_build.py during CI; bundle it when
# present so the app can report its commit/tag/build date. Absent in dev builds.
datas = [(str(spec_dir / "icon.png"), ".")]
build_info = pdf_dir / "build_info.json"
if build_info.exists():
    datas.append((str(build_info), "."))

a = Analysis(
    [str(pdf_dir / "main.py")],
    pathex=[str(pdf_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim unused (large) Qt modules to keep the bundle smaller.
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if is_windows:
    # One-file portable .exe -> dist/Inkstone.exe
    portable = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="Inkstone",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        icon=icon,
    )

# One-dir bundle -> dist/Inkstone/ (Windows installer payload; Linux AppImage / .deb).
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Inkstone",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Inkstone",
)
