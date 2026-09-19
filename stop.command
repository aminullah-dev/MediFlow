#!/usr/bin/env bash
# ============================================================
#  MediFlow - stop the running web server
#  (the macOS counterpart of stop.bat)
# ============================================================
set -uo pipefail

echo
echo "  در حال توقف سرور مدی‌فلو..."

# Match the full command line rather than the interpreter name: python3 is
# shared with every other Python tool on the Mac, so killing them all would be
# reckless. Only a process actually running "-m mediflow.web" matches.
PIDS="$(pgrep -f 'mediflow\.web' || true)"

if [ -z "$PIDS" ]; then
    echo "  سروری در حال اجرا نبود."
else
    COUNT="$(printf '%s\n' "$PIDS" | wc -l | tr -d ' ')"
    # shellcheck disable=SC2086
    kill $PIDS 2>/dev/null

    # Give it a moment to shut down cleanly; a SQLite write mid-flight is worth
    # waiting out rather than tearing down.
    for _ in 1 2 3 4 5; do
        pgrep -f 'mediflow\.web' >/dev/null 2>&1 || break
        sleep 1
    done
    REMAINING="$(pgrep -f 'mediflow\.web' || true)"
    if [ -n "$REMAINING" ]; then
        # shellcheck disable=SC2086
        kill -9 $REMAINING 2>/dev/null
    fi
    echo "  متوقف شد: $COUNT پروسه"
fi

echo
sleep 3
