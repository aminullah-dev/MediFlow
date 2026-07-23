# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MediFlow (one-dir, windowed GUI).

Run from the project root:

    pyinstaller packaging/mediflow.spec --noconfirm --clean

Notes
* ``collect_submodules('mediflow')`` is essential: models are imported
  dynamically via importlib (``data/models/__init__.py``), so static analysis
  alone would miss them.
* The compiled ``.qm`` translations are bundled as data next to their package
  so the runtime ``Path(__file__).parent`` lookup keeps working when frozen.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("mediflow")
datas = collect_data_files("mediflow", includes=["**/*.qm"])

excludes = [
    "tkinter", "pytest", "black", "mypy", "ruff", "setuptools", "pip",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia",
]

a = Analysis(
    ["mediflow_launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — no console window
    icon="../assets/mediflow.ico",   # relative to this spec file (packaging/)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MediFlow",
)
