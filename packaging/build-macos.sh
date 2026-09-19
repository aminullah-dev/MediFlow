#!/usr/bin/env bash
# Build, sign, notarise and package MediFlow for macOS.
# Run from anywhere:  bash packaging/build-macos.sh
#
# The macOS counterpart of build.ps1, driving the same PyInstaller spec.
#
# With a Developer ID certificate in the login keychain this produces a
# notarised, stapled .dmg ready to hand to a clinic. Without one it produces an
# ad-hoc signed build that runs on the build Mac and nowhere else comfortably.
# Nothing has to be configured for the first case beyond installing the
# certificate and storing notarytool credentials once — see packaging/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Mirrors .venv-win on the Windows side; falls back to whatever python3 is on
# PATH so a fresh clone builds without ceremony.
PY="$ROOT/.venv-mac/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' mediflow/__init__.py)"
# PySide6 publishes no universal2 wheel, so this build runs on one architecture
# only. The name has to say which: two .dmg files of the same version are not
# interchangeable, and handing a clinic the wrong one costs a site visit.
ARCH="$(uname -m)"
APP="dist/MediFlow.app"
DMG="dist_installer/MediFlow-$VERSION-$ARCH.dmg"
ENTITLEMENTS="packaging/entitlements.plist"

# The Apple Developer team this product ships under. Not a secret: it is
# embedded in every signed binary and `codesign -dv` prints it. Override for a
# different team; never put an Apple ID or password in this file.
TEAM_ID="${MEDIFLOW_TEAM_ID:-27RXPRW77S}"

# A notarytool keychain profile created once with `store-credentials` (see the
# README). Credentials therefore live in the build Mac's keychain, never in the
# repository, the environment, or CI logs.
NOTARY_PROFILE="${MEDIFLOW_NOTARY_PROFILE:-MediFlow}"

# Set to 0 (or pass --no-notarize) to sign but skip the trip to Apple. The
# result is valid over USB and refused on download, so this is for iterating on
# the build, not for shipping.
NOTARIZE="${MEDIFLOW_NOTARIZE:-1}"
for arg in "$@"; do
    case "$arg" in
        --no-notarize) NOTARIZE="0" ;;
        -h|--help) echo "usage: bash packaging/build-macos.sh [--no-notarize]"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

_store_credentials_hint() {
    cat >&2 <<HINT

The notarytool credential profile "$NOTARY_PROFILE" does not exist on this Mac.
Create it once — it is the only step no script can do for you, because it needs
your Apple ID:

  1. Make an app-specific password at https://account.apple.com
     (Sign-In and Security > App-Specific Passwords). It looks like
     abcd-efgh-ijkl-mnop and is shown only once.

  2. Run, with your own Apple ID and that password:

     xcrun notarytool store-credentials "$NOTARY_PROFILE" \
         --apple-id "YOUR-APPLE-ID" \
         --team-id $TEAM_ID \
         --password "abcd-efgh-ijkl-mnop"

Then run this build again. To build without notarising in the meantime:

     bash packaging/setup-macos.sh --no-notarize
HINT
}

# ── Identity ──────────────────────────────────────────────────────────────────
# Resolve the Developer ID from the keychain rather than making the operator
# paste an exact certificate name. An Individual account's certificate is named
# after the person, so that string is neither guessable nor stable enough to
# hardcode; the team id is.
IDENTITY="${MEDIFLOW_CODESIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
    IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
        | grep "Developer ID Application" | grep "$TEAM_ID" \
        | head -1 | sed 's/.*"\(.*\)".*/\1/')" || true
fi

if [ -n "$IDENTITY" ]; then
    echo "==> Signing identity: $IDENTITY"
    export MEDIFLOW_CODESIGN_IDENTITY="$IDENTITY"   # the spec signs with it too
else
    echo "==> No Developer ID for team $TEAM_ID in the keychain — ad-hoc build"
fi

# Check the notarisation credentials up front. store-credentials writes a
# generic-password item; the service name is an implementation detail, so a
# miss here is reported as a warning and the build continues rather than
# refusing on a guess. The real check is the submission itself.
if [ -n "$IDENTITY" ] && [ "$NOTARIZE" = "1" ]; then
    if security find-generic-password -s "com.apple.gke.notary.tool" \
            -a "$NOTARY_PROFILE" >/dev/null 2>&1 \
       || security find-generic-password -a "$NOTARY_PROFILE" >/dev/null 2>&1; then
        echo "==> Notarisation profile \"$NOTARY_PROFILE\" found"
    else
        echo "==> WARNING: no notarisation profile \"$NOTARY_PROFILE\" found."
        echo "    Building anyway; if the submission fails, the fix is printed."
    fi
fi

# Report the shipped constraints from the artifact itself, not from what the
# build intended. LSMinimumSystemVersion is derived from the bundled Qt, so it
# moves on its own when PySide6 raises its floor — the operator needs to see the
# number that actually ended up in the bundle.
_summarise() {
    local min_os
    min_os="$(/usr/libexec/PlistBuddy -c "Print :LSMinimumSystemVersion" \
        "$APP/Contents/Info.plist" 2>/dev/null || echo "unknown")"
    echo "  Architecture : $ARCH"
    echo "  Requires     : macOS $min_os or later"
    if [ "$ARCH" = "x86_64" ]; then
        echo "                 (an Apple Silicon Mac needs Rosetta 2, which is a"
        echo "                  one-time download — see packaging/README.md)"
    fi
}

# ── Build ─────────────────────────────────────────────────────────────────────
echo "==> Generating application icon"
"$PY" packaging/make_icns.py

echo "==> Ensuring PyInstaller is installed"
"$PY" -m pip install --quiet pyinstaller

echo "==> Building the app with PyInstaller (one-dir, windowed)"
"$PY" -m PyInstaller packaging/mediflow.spec \
    --noconfirm --clean --distpath dist --workpath build

[ -d "$APP" ] || { echo "PyInstaller did not produce $APP" >&2; exit 1; }
echo "==> App built: $APP"

# ── Sign ──────────────────────────────────────────────────────────────────────
if [ -z "$IDENTITY" ]; then
    # Ad-hoc. --deep is the right tool here and only here: there is no
    # certificate, so re-signing nested code costs nothing.
    codesign --force --deep --sign - "$APP"
else
    # NOT --deep. PyInstaller has already signed every nested framework and .so
    # with this identity and these entitlements, inside-out, which is the only
    # ordering notarisation accepts. --deep would re-sign all of it with the
    # OUTER entitlements and get the submission rejected.
    codesign --force --sign "$IDENTITY" --options runtime --timestamp \
        --entitlements "$ENTITLEMENTS" "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"
echo "==> Signature verified"

# ── Notarise the app, then staple it BEFORE it goes into the disk image ──────
# Order matters. Stapling writes Apple's ticket into the bundle, and a bundle
# copied out of a .dmg keeps whatever was stapled at the time the image was
# built. Notarising only the .dmg would leave the installed app relying on a
# network check — which is the one thing an offline clinic cannot do.
if [ -n "$IDENTITY" ] && [ "$NOTARIZE" = "1" ]; then
    echo "==> Notarising the app (team $TEAM_ID, profile $NOTARY_PROFILE)"
    mkdir -p build
    ZIP="build/MediFlow-$VERSION.zip"        # beside the other build artifacts
    # ditto, not zip: it preserves the symlinks and extended attributes inside a
    # .app, which a plain zip silently flattens into an invalid bundle.
    rm -f "$ZIP"
    ditto -c -k --keepParent "$APP" "$ZIP"
    # The keychain profile already carries the Apple ID and team, so --team-id
    # is not passed again here.
    NOTARY_LOG="build/notarytool-app.log"
    if xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait \
            2>&1 | tee "$NOTARY_LOG"; then
        :
    elif grep -q "No Keychain password item found" "$NOTARY_LOG"; then
        # Nothing was ever submitted, so there is no log to fetch. Different
        # problem, different instruction.
        _store_credentials_hint
        exit 1
    else
        echo >&2
        echo "Apple rejected the submission. The signed app is still at $APP." >&2
        echo "For the per-file reasons, take the id printed above and run:" >&2
        echo "  xcrun notarytool log <submission-id> --keychain-profile $NOTARY_PROFILE" >&2
        exit 1
    fi
    xcrun stapler staple "$APP"
    echo "==> App notarised and stapled"
fi

# ── Disk image ────────────────────────────────────────────────────────────────
echo "==> Building the disk image"
mkdir -p dist_installer
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/MediFlow.app"
ln -s /Applications "$STAGE/Applications"      # the drag-to-install target
rm -f "$DMG"
hdiutil create -volname "MediFlow $VERSION" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG" >/dev/null
echo "==> Installer written to $DMG"

if [ -n "$IDENTITY" ] && [ "$NOTARIZE" = "1" ]; then
    echo "==> Signing and notarising the disk image"
    codesign --force --sign "$IDENTITY" --timestamp "$DMG"
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"

    echo "==> Gatekeeper assessment"
    spctl --assess --type open --context context:primary-signature -vv "$DMG"
    spctl --assess --type exec -vv "$APP"
    echo
    echo "Ready to ship: $DMG"
    echo "  Notarised and stapled — it opens on a clinic Mac with no internet."
    _summarise
elif [ -n "$IDENTITY" ]; then
    # Signed with a real Developer ID, but --no-notarize was asked for.
    codesign --force --sign "$IDENTITY" --timestamp "$DMG"
    echo
    echo "Built and signed, NOT notarised (--no-notarize): $DMG"
    echo "  Copied by USB it installs and runs anywhere."
    echo "  DOWNLOADED it is quarantined and refused, because Gatekeeper checks"
    echo "  notarisation, not just the signature. Do not ship this by email or"
    echo "  a download link — re-run without --no-notarize for that."
    echo
    _summarise
else
    echo
    echo "NOTE: this build is ad-hoc signed and NOT notarised. It runs on this"
    echo "      Mac; on any other it will be refused, and a downloaded copy is"
    echo "      quarantined outright. To clear quarantine on a receiving Mac:"
    echo "        xattr -dr com.apple.quarantine /Applications/MediFlow.app"
    echo "      For a real build, install the Developer ID certificate for team"
    echo "      $TEAM_ID and see packaging/README.md."
    echo
    _summarise
fi
