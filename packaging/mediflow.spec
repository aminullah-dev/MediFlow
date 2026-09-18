# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MediFlow (one-dir, windowed GUI) — Windows and macOS.

Run from the project root:

    pyinstaller packaging/mediflow.spec --noconfirm --clean

One spec, both platforms, deliberately. The Analysis block is the part that is
easy to get subtly wrong (see the hidden-imports note below), so it exists once
rather than once per OS where the two copies would quietly drift apart. Only
the icon and the macOS ``.app`` wrapper differ, and both are derived below.

Notes
* ``collect_submodules('mediflow')`` is essential: models are imported
  dynamically via importlib (``data/models/__init__.py``), so static analysis
  alone would miss them.
* The compiled ``.qm`` translations are bundled as data next to their package
  so the runtime ``Path(__file__).parent`` lookup keeps working when frozen.
* macOS builds are single-architecture — whatever the build Mac is. An Apple
  Silicon build will not start on an Intel Mac; build on each, or ship arm64
  only and let Intel machines fall out of scope explicitly.
"""
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

IS_MACOS = sys.platform == "darwin"

# Read the version rather than restating it: pyproject.toml, mediflow.iss and
# this file would otherwise be three places to forget on a release.
_ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is injected by PyInstaller
VERSION = re.search(
    r'__version__ = "([^"]+)"',
    (_ROOT / "mediflow" / "__init__.py").read_text(encoding="utf-8"),
).group(1)

ICON = "../assets/mediflow.icns" if IS_MACOS else "../assets/mediflow.ico"

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
    icon=ICON,              # relative to this spec file (packaging/)
    # Apple Silicon refuses to run an unsigned binary at all, so leaving this
    # empty still gets an ad-hoc signature from PyInstaller. Export a Developer
    # ID here to produce something that can be notarised and distributed.
    codesign_identity=os.environ.get("MEDIFLOW_CODESIGN_IDENTITY") or None,
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

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="MediFlow.app",
        icon=ICON,
        bundle_identifier="com.mediflow.mediflow",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            # Without this macOS renders the whole app at 1x on a Retina
            # display — every icon and every Dari glyph blurred.
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.medical",
            # Declared so macOS offers the app its own languages when the
            # system is set to Dari or Pashto, matching i18n/translations/.
            "CFBundleDevelopmentRegion": "en",
            "CFBundleLocalizations": ["en", "fa-AF", "ps-AF"],
            "NSHumanReadableCopyright": "MediFlow",
        },
    )
