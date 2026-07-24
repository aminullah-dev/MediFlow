"""Entry point: ``python -m mediflow.web``.

Kept separate from :mod:`mediflow.web.server` so importing the app for tests
never starts a listener. ``start.bat`` invokes this.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    host = os.environ.get("MEDIFLOW_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("MEDIFLOW_PORT", "8000"))
    except ValueError:
        port = 8000

    from mediflow.web.server import run

    try:
        run(host=host, port=port)
    except OSError as exc:
        # Almost always "port already in use" — say so in plain language rather
        # than dumping a winsock error at a receptionist.
        print(f"\nMediFlow could not start on {host}:{port}\n  {exc}\n", file=sys.stderr)
        print("If MediFlow is already running, just open http://127.0.0.1:8000",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
