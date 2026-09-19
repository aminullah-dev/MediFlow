"""Generate the MediFlow macOS application icon (assets/mediflow.icns).

Same artwork as the Windows ``.ico`` — :func:`make_icon.render` draws both — so
the two platforms can never drift apart visually. Only the container differs:
macOS wants an ``.icns`` holding the standard iconset sizes up to 1024px for
Retina displays.

``iconutil`` (part of macOS) produces the canonical container and is used when
present. Pillow's ICNS writer is the fallback, so the asset can also be
regenerated on a Linux CI box without a Mac in the loop.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_icon import render  # noqa: E402  (needs the path above)

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "assets" / "mediflow.icns"

# The names Apple's iconset format requires; @2x is the Retina variant of the
# entry above it, so 512x512@2x is the 1024px artwork.
_ICONSET = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def _with_iconutil(out: Path) -> bool:
    if not shutil.which("iconutil"):
        return False
    with tempfile.TemporaryDirectory() as work:
        iconset = Path(work) / "mediflow.iconset"
        iconset.mkdir()
        for name, size in _ICONSET:
            render(size).save(iconset / name, format="PNG")
        subprocess.run(                                     # noqa: S603
            ["iconutil", "--convert", "icns", str(iconset), "--output", str(out)],
            check=True,
        )
    return True


def _with_pillow(out: Path) -> None:
    """Fallback writer. Pillow builds the container from one 1024px source."""
    render(1024).save(out, format="ICNS",
                      sizes=[(size, size) for _, size in _ICONSET])


def main() -> None:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    if not _with_iconutil(_OUT):
        _with_pillow(_OUT)
    print("Wrote", _OUT)


if __name__ == "__main__":
    main()
