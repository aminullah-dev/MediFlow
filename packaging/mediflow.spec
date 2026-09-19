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
import subprocess
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

# Apple Silicon refuses to run an unsigned binary at all, so an unset identity
# still gets an ad-hoc signature from PyInstaller — enough to launch, not enough
# to distribute. build-macos.sh resolves the real Developer ID and exports it.
#
# Handing PyInstaller the identity matters more than it looks: it signs every
# collected Qt framework and C extension individually, inside-out, which is the
# only ordering notarisation accepts. Signing the finished bundle with
# `codesign --deep` instead re-signs that nested code with the OUTER
# entitlements and gets the submission rejected.
CODESIGN_IDENTITY = os.environ.get("MEDIFLOW_CODESIGN_IDENTITY") or None
ENTITLEMENTS = (
    str(Path(SPECPATH) / "entitlements.plist")  # noqa: F821 - injected by PyInstaller
    if IS_MACOS and CODESIGN_IDENTITY else None
)

def minimum_macos_version() -> str:
    """The oldest macOS the Qt actually being bundled will start on.

    Hardcoding this is a trap. PySide6 raises its own floor every few releases
    and pyproject.toml pins only ">=6.7", so a fresh build machine installs
    whatever is current — 6.11 at the time of writing, which no longer supports
    macOS 11. An Info.plist that understates the floor does real damage: macOS
    installs the app happily on an older Mac and Qt then fails to load at
    launch, in a clinic, not on the build machine. So read the floor out of the
    framework that imposes it.
    """
    fallback = "12.0"
    try:
        import PySide6

        qt_core = (Path(PySide6.__file__).parent / "Qt" / "lib"
                   / "QtCore.framework" / "Versions" / "A" / "QtCore")
        if not qt_core.exists():
            raise FileNotFoundError(qt_core)
        commands = subprocess.run(["otool", "-l", str(qt_core)],
                                  capture_output=True, text=True,
                                  check=True).stdout
        # LC_BUILD_VERSION on anything current, LC_VERSION_MIN_MACOSX on older
        # binaries. Matching a bare "version" line would also catch
        # LC_SOURCE_VERSION, which reads 0.0 — hence the anchored search.
        found = re.search(r"^\s*minos\s+([0-9][0-9.]*)\s*$", commands, re.M)
        if not found:
            found = re.search(
                r"LC_VERSION_MIN_MACOSX.*?^\s*version\s+([0-9][0-9.]*)\s*$",
                commands, re.M | re.S)
        if not found:
            raise ValueError("no minimum OS load command in the Qt binary")
        return found.group(1)
    except Exception as exc:                        # noqa: BLE001 - build-time
        print(f"WARNING: could not read the bundled Qt's minimum macOS "
              f"({exc}); declaring {fallback}. Verify before shipping.")
        return fallback


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
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=ENTITLEMENTS,
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
            "LSMinimumSystemVersion": minimum_macos_version(),
            "LSApplicationCategoryType": "public.app-category.medical",
            # Declared so macOS offers the app its own languages when the
            # system is set to Dari or Pashto, matching i18n/translations/.
            "CFBundleDevelopmentRegion": "en",
            "CFBundleLocalizations": ["en", "fa-AF", "ps-AF"],
            "NSHumanReadableCopyright": "MediFlow",
        },
    )
