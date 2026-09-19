#!/usr/bin/env bash
# One command that takes a bare Mac to a finished MediFlow build.
#
#   bash packaging/setup-macos.sh
#
# It checks the toolchain, installs Python if it can, creates the virtual
# environment, installs dependencies, proves the app runs, and then builds it.
# Re-running it is safe and cheap: every step is skipped when already done.
#
# What it deliberately does NOT do: create the Developer ID certificate or the
# app-specific password. Both need an interactive Apple ID sign-in with
# two-factor approval on your own phone, so no script and no assistant can do
# them for you. It tells you when you have reached that point.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_TESTS="${MEDIFLOW_SETUP_TESTS:-1}"
BUILD="1"
BUILD_ARGS=""
for arg in "$@"; do
    case "$arg" in
        --no-build) BUILD="0" ;;
        --no-tests) RUN_TESTS="0" ;;
        --no-notarize) BUILD_ARGS="--no-notarize" ;;
        -h|--help)
            echo "usage: bash packaging/setup-macos.sh [--no-build] [--no-tests] [--no-notarize]"
            exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

step()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()    { printf '    \033[32m✓\033[0m %s\n' "$1"; }
warn()  { printf '    \033[33m!\033[0m %s\n' "$1"; }
die()   { printf '\n\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

# ── 0. The right kind of machine ─────────────────────────────────────────────
step "Checking this machine"
[ "$(uname -s)" = "Darwin" ] || die "This script only runs on macOS. This is $(uname -s)."
ARCH="$(uname -m)"
ok "macOS $(sw_vers -productVersion) on $ARCH"
case "$ARCH" in
    arm64)  ok "Apple Silicon — the build will run on Apple Silicon Macs only" ;;
    x86_64) warn "Intel — the build needs Rosetta 2 on Apple Silicon Macs," ;
            warn "  which is a one-time download an offline clinic cannot make" ;;
esac

# ── 1. Apple's command line tools ────────────────────────────────────────────
step "Checking Apple's command line tools"
if xcode-select -p >/dev/null 2>&1; then
    ok "installed at $(xcode-select -p)"
else
    warn "not installed — opening Apple's installer now"
    xcode-select --install 2>/dev/null || true
    die "Finish the installer window that just opened, then run this script again."
fi
for tool in codesign xcrun hdiutil iconutil security; do
    command -v "$tool" >/dev/null 2>&1 || die "'$tool' is missing even though the tools are installed."
done
ok "codesign, xcrun, hdiutil, iconutil, security all present"

# ── 2. Python 3.11 or newer ──────────────────────────────────────────────────
step "Looking for Python 3.11 or newer"
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$(command -v "$candidate")"
        break
    fi
done

if [ -z "$PY" ]; then
    if command -v brew >/dev/null 2>&1; then
        warn "none found — installing python@3.13 with Homebrew (a few minutes)"
        brew install python@3.13 || die "Homebrew could not install Python."
        PY="$(brew --prefix)/opt/python@3.13/bin/python3.13"
        [ -x "$PY" ] || die "Homebrew finished but $PY is not there."
    else
        die "No Python 3.11+ and no Homebrew.
    Download Python 3.13 from https://www.python.org/downloads/macos/
    install the .pkg, then run this script again."
    fi
fi
ok "using $("$PY" --version) at $PY"

# ── 3. Virtual environment and dependencies ──────────────────────────────────
step "Setting up the virtual environment (.venv-mac)"
VENV_PY="$ROOT/.venv-mac/bin/python"
if [ ! -x "$VENV_PY" ]; then
    "$PY" -m venv .venv-mac || die "Could not create .venv-mac"
    ok "created"
else
    ok "already there"
fi

step "Installing dependencies (this is the slow part — PySide6 is large)"
"$VENV_PY" -m pip install --quiet --upgrade pip || die "pip could not update itself"
"$VENV_PY" -m pip install --quiet -e ".[dev]" || die "Dependency install failed. The output above says why."
ok "installed"

# ── 4. Prove it works before packaging it ────────────────────────────────────
# Separating this from the build is the point: if the app cannot run from
# source, the problem is the install, and hunting it inside a PyInstaller
# bundle wastes an afternoon.
if [ "$RUN_TESTS" = "1" ]; then
    step "Running the test suite (a minute or two)"
    if QT_QPA_PLATFORM=offscreen "$VENV_PY" -m pytest -q; then
        ok "all tests pass"
    else
        die "Tests failed. Do not package this — fix the failure first."
    fi
else
    warn "skipping tests (--no-tests)"
fi

step "Checking the app imports and Qt loads"
QT_QPA_PLATFORM=offscreen "$VENV_PY" -c '
import mediflow
from PySide6 import QtWidgets
from mediflow.core import secret_store
app = QtWidgets.QApplication([])
print(f"    MediFlow {mediflow.__version__}, Qt loaded, secrets sealed with {secret_store.describe()}")
' || die "The app could not start. The traceback above says why."
ok "the app starts"

# ── 5. Build ─────────────────────────────────────────────────────────────────
if [ "$BUILD" = "0" ]; then
    step "Setup complete (build skipped)"
    echo "    Next:  bash packaging/build-macos.sh"
    exit 0
fi

step "Building the app"
# Unquoted on purpose: empty must expand to no argument at all, and the only
# value it ever holds is a single flag with no spaces. macOS ships bash 3.2,
# so the guarded-array idiom buys nothing here.
# shellcheck disable=SC2086
bash packaging/build-macos.sh $BUILD_ARGS \
    || die "The build failed. The output above says where."

# ── 6. Say what is left, based on the artifact — not on what is installed ────
# This used to ask the keychain whether a Developer ID certificate existed and
# conclude from that alone that the build was "notarised and stapled. Ship it."
# It said exactly that after a --no-notarize run, directly under build-macos.sh
# correctly reporting the opposite. A certificate is what makes notarisation
# possible, not evidence that it happened. Ask the file.
TEAM_ID="${MEDIFLOW_TEAM_ID:-27RXPRW77S}"
DMG="$(ls -t dist_installer/MediFlow-*.dmg 2>/dev/null | head -1)"

if [ -n "$DMG" ] && xcrun stapler validate "$DMG" >/dev/null 2>&1; then
    step "Done"
    echo "    $DMG"
    echo "    Notarised and stapled — it opens on a clinic Mac with no internet."
    echo "    Confirm before every handover:  bash packaging/verify-macos.sh"
elif security find-identity -v -p codesigning 2>/dev/null \
        | grep -q "Developer ID Application.*$TEAM_ID"; then
    step "Done — signed, but NOT notarised"
    cat <<TEXT
    ${DMG:-the build} is signed with your Developer ID but carries no
    notarisation ticket, so Gatekeeper refuses it on any Mac that DOWNLOADED
    it. Copied by USB it still installs.

    This is what --no-notarize produces. For a build you can hand over, run
    again without that flag:

      bash packaging/setup-macos.sh

TEXT
else
    step "Done — but this build cannot leave this Mac"
    cat <<TEXT
    dist/MediFlow.app works here. It is ad-hoc signed, so on any other Mac it
    will be refused.

    Two things remain, and both need YOUR Apple ID with two-factor approval on
    your own phone, so no script can do them:

      1. Create a "Developer ID Application" certificate at
         https://developer.apple.com/account/resources/certificates
         Download it, double-click it to install it in your keychain.

      2. Create an app-specific password at https://account.apple.com
         (Sign-In and Security > App-Specific Passwords), then run once:

         xcrun notarytool store-credentials "MediFlow" \\
             --apple-id "YOUR-APPLE-ID" --team-id $TEAM_ID --password "THE-PASSWORD"

    Then run this script again. It will find the certificate on its own and
    produce a .dmg that opens on a clinic Mac with no internet.

    Step by step, in Persian: packaging/QUICKSTART-macOS-fa.md
TEXT
fi
