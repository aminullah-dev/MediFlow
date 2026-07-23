"""Console entry point: ``python -m mediflow`` / ``mediflow``."""
from __future__ import annotations

import sys


def main() -> int:
    from mediflow.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
