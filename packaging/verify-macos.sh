#!/usr/bin/env bash
# Answer one question about a finished build: can this file be handed to a
# clinic?
#
#   bash packaging/verify-macos.sh                       # newest .dmg built here
#   bash packaging/verify-macos.sh path/to/MediFlow.dmg
#   bash packaging/verify-macos.sh dist/MediFlow.app
#
# There are now three things build-macos.sh can produce — notarised, signed but
# not notarised, and ad-hoc — and they are indistinguishable by filename. Giving
# a clinic the wrong one is a site visit, so this asks the system rather than
# trusting what the build printed at the time.
#
# The check that matters most is the last one: the app INSIDE the disk image has
# to carry its own stapled ticket, because that is the copy that ends up in
# /Applications. A stapled .dmg holding an unstapled .app looks fine here and
# fails on a Mac with no internet.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    TARGET="$(ls -t dist_installer/MediFlow-*.dmg 2>/dev/null | head -1)"
    [ -n "$TARGET" ] || TARGET="dist/MediFlow.app"
fi
[ -e "$TARGET" ] || { echo "Nothing to check at: $TARGET" >&2; exit 2; }

FAILED=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=1; }
note() { printf '    %s\n' "$1"; }

MOUNT=""
cleanup() { [ -n "$MOUNT" ] && hdiutil detach "$MOUNT" -quiet 2>/dev/null; }
trap cleanup EXIT

echo
echo "Checking: $TARGET"
echo

# ── Signature ────────────────────────────────────────────────────────────────
if codesign --verify --deep --strict "$TARGET" 2>/dev/null; then
    ok "signature is valid"
else
    bad "signature is broken or missing"
fi

AUTHORITY="$(codesign -dv --verbose=4 "$TARGET" 2>&1 \
    | grep '^Authority=' | head -1 | cut -d= -f2-)"
case "$AUTHORITY" in
    "Developer ID Application"*)
        ok "signed by: $AUTHORITY" ;;
    "")
        bad "ad-hoc signed — no certificate at all"
        note "runs on the Mac that built it and nowhere else" ;;
    *)
        bad "signed by '$AUTHORITY', which is not a Developer ID"
        note "only a Developer ID certificate can be notarised" ;;
esac

# ── Notarisation, as Gatekeeper itself reports it ────────────────────────────
case "$TARGET" in
    *.dmg) ASSESS=(spctl --assess --type open
                   --context context:primary-signature -vv "$TARGET") ;;
    *)     ASSESS=(spctl --assess --type exec -vv "$TARGET") ;;
esac
VERDICT="$("${ASSESS[@]}" 2>&1)"
if printf '%s' "$VERDICT" | grep -q "source=Notarized Developer ID"; then
    ok "Gatekeeper accepts it as notarised"
elif printf '%s' "$VERDICT" | grep -q "accepted"; then
    bad "accepted, but NOT as notarised"
    note "$(printf '%s' "$VERDICT" | grep '^source=' || echo 'no source reported')"
else
    bad "Gatekeeper rejects it"
    note "$(printf '%s' "$VERDICT" | head -2 | tr '\n' ' ')"
fi

# ── The stapled ticket — the whole point for an offline clinic ───────────────
if xcrun stapler validate "$TARGET" >/dev/null 2>&1; then
    ok "notarisation ticket is stapled"
else
    bad "no stapled ticket"
    note "Gatekeeper would have to ask Apple over the network on first launch,"
    note "which a clinic Mac with no internet cannot do"
fi

# ── For a disk image: the app inside it, which is the copy that gets used ────
if [ "${TARGET##*.}" = "dmg" ]; then
    MOUNT="$(hdiutil attach "$TARGET" -nobrowse -readonly -mountrandom /tmp \
        2>/dev/null | grep -o '/tmp/[^ ]*' | tail -1)"
    if [ -z "$MOUNT" ]; then
        bad "could not open the disk image to look inside it"
    else
        INNER="$MOUNT/MediFlow.app"
        if [ ! -d "$INNER" ]; then
            bad "no MediFlow.app inside the disk image"
        elif xcrun stapler validate "$INNER" >/dev/null 2>&1; then
            ok "the app inside carries its own stapled ticket"
        else
            bad "the app inside is NOT stapled"
            note "the .dmg opens, then the installed app is refused offline"
        fi
        [ -d "$INNER" ] && TARGET="$INNER"
    fi
fi

# ── What it will and will not run on ─────────────────────────────────────────
PLIST="$TARGET/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    echo
    echo "  Requires : macOS $(/usr/libexec/PlistBuddy -c \
        'Print :LSMinimumSystemVersion' "$PLIST" 2>/dev/null || echo '?') or later"
    ARCHS="$(lipo -archs "$TARGET/Contents/MacOS/MediFlow" 2>/dev/null || echo '?')"
    echo "  Runs on  : $ARCHS"
    case "$ARCHS" in
        arm64) note "Apple Silicon only — an Intel Mac cannot run this" ;;
        x86_64) note "Intel natively; Apple Silicon needs Rosetta 2, a download" ;;
    esac
fi

echo
if [ "$FAILED" = "0" ]; then
    printf '\033[32mSafe to hand to a clinic.\033[0m Copy it to a USB stick.\n\n'
else
    printf '\033[31mDo NOT hand this to a clinic.\033[0m Rebuild with:\n'
    printf '  bash packaging/setup-macos.sh\n\n'
    exit 1
fi
