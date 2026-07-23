"""Frozen-app entry point used by PyInstaller.

Kept tiny and free of side effects; delegates straight to the package's
console entry point so the packaged build and ``python -m mediflow`` behave
identically.
"""
from mediflow.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
