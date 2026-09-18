#!/usr/bin/env bash
# Build the MediFlow macOS app and disk image.
# Run from anywhere:  bash packaging/build-macos.sh
#
# The macOS counterpart of build.ps1, and it drives the same PyInstaller spec.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Mirrors .venv-win on the Windows side; falls back to whatever python3 is on
# PATH so a fresh clone builds without ceremony.
PY="$ROOT/.venv-mac/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' mediflow/__init__.py)"
APP="dist/MediFlow.app"
DMG="dist_installer/MediFlow-$VERSION.dmg"

echo "==> Generating application icon"
"$PY" packaging/make_icns.py

echo "==> Ensuring PyInstaller is installed"
"$PY" -m pip install --quiet pyinstaller

echo "==> Building the app with PyInstaller (one-dir, windowed)"
"$PY" -m PyInstaller packaging/mediflow.spec \
    --noconfirm --clean --distpath dist --workpath build

[ -d "$APP" ] || { echo "PyInstaller did not produce $APP" >&2; exit 1; }
echo "==> App built: $APP"

# Apple Silicon refuses to launch an unsigned bundle outright, so even a
# throwaway ad-hoc signature is not optional. PyInstaller signs the executable;
# this signs the .app around it. (--deep is discouraged by Apple for real
# distribution builds, but it is the correct tool for an ad-hoc bundle.)
IDENTITY="${MEDIFLOW_CODESIGN_IDENTITY:--}"
echo "==> Signing with identity: $IDENTITY"
if [ "$IDENTITY" = "-" ]; then
    codesign --force --deep --sign - "$APP"
else
    # A real Developer ID: harden the runtime and timestamp it, which is what
    # notarisation requires.
    codesign --force --deep --sign "$IDENTITY" --options runtime --timestamp "$APP"
fi
codesign --verify --deep --strict "$APP"
echo "==> Signature verified"

echo "==> Building the disk image"
mkdir -p dist_installer
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"      # the drag-to-install target
rm -f "$DMG"
hdiutil create -volname "MediFlow $VERSION" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG" >/dev/null
echo "==> Installer written to $DMG"

if [ "$IDENTITY" = "-" ]; then
    echo
    echo "NOTE: this build is ad-hoc signed, not notarised. A Mac that"
    echo "      DOWNLOADS the .dmg will quarantine it; copying it by USB will"
    echo "      not. To clear quarantine on the receiving Mac:"
    echo "        xattr -dr com.apple.quarantine /Applications/MediFlow.app"
fi
