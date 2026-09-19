#!/usr/bin/env bash
# ============================================================
#  MediFlow - start the web server and open it in the browser
#  (the macOS counterpart of start.bat)
# ============================================================
set -uo pipefail

# Paths are derived from THIS file's folder, so the project can be moved or
# copied to another clinic Mac without editing anything here. Double-clicking a
# .command in Finder starts the shell in the home folder, so this is not
# optional tidiness.
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL="http://127.0.0.1:8000"

# Must run FROM the project folder: the package is not pip-installed, so
# "python -m mediflow.web" only resolves when it is on the current path.
cd "$PROJECT" || { echo "  [خطا] پوشه پروژه پیدا نشد."; exit 1; }

# No MEDIFLOW_DATA_DIR override here, unlike start.bat. That override exists to
# dodge the Microsoft Store (MSIX) redirection of %APPDATA%; macOS has no such
# redirection, so the app's own ~/Library/Application Support/MediFlow is both
# correct and what Time Machine already backs up.
DATA_DIR="${MEDIFLOW_DATA_DIR:-$HOME/Library/Application Support/MediFlow}"
LOG_DIR="$HOME/Library/Logs/MediFlow"

PY="$PROJECT/.venv-mac/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || true)"

echo
echo "  MediFlow"
echo "  --------"
echo "  پوشه داده : $DATA_DIR"
echo "  آدرس      : $URL"
echo

if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    echo "  [خطا] پایتون پیدا نشد:"
    echo "        $PROJECT/.venv-mac/bin/python"
    echo
    echo "  محیط مجازی ساخته نشده است."
    echo
    read -r -p "  Enter " _
    exit 1
fi

# Already up? Then just open the browser - never start a second copy, which
# would fail on the port and leave a confusing error window.
if curl --silent --fail --max-time 2 "$URL/healthz" >/dev/null 2>&1; then
    echo "  سرور از قبل در حال اجراست."
else
    echo "  در حال راه‌اندازی سرور..."
    mkdir -p "$LOG_DIR"
    nohup "$PY" -m mediflow.web >>"$LOG_DIR/server-console.log" 2>&1 &

    # Wait for it to answer before opening the browser, otherwise the first
    # page load races the server and shows "cannot connect".
    tries=0
    until curl --silent --fail --max-time 2 "$URL/healthz" >/dev/null 2>&1; do
        tries=$((tries + 1))
        if [ "$tries" -gt 40 ]; then
            echo
            echo "  [خطا] سرور در ۴۰ ثانیه بالا نیامد."
            echo "  گزارش خطا: $LOG_DIR/server-console.log"
            echo
            read -r -p "  Enter " _
            exit 1
        fi
        sleep 1
    done
fi

echo "  باز کردن مرورگر..."
open "$URL"
echo
echo "  آماده است. برای توقف سرور، stop.command را اجرا کنید."
echo
sleep 3
