"""Generate the MediFlow application icon (assets/mediflow.ico).

A teal rounded square with a white medical cross — matches the app's medical
palette. Multi-resolution .ico for the taskbar, Start menu and installer.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

TEAL = (8, 145, 178, 255)      # #0891b2 (matches the app primary)
DEEP = (13, 85, 99, 255)       # #0d5563 (sidebar bottom)
WHITE = (255, 255, 255, 255)

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "assets" / "mediflow.ico"


def _render(size: int) -> Image.Image:
    # Render at 4x then downscale for crisp anti-aliasing.
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    radius = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=TEAL)

    # White cross (rounded), centred.
    arm = int(s * 0.16)          # half-thickness
    ext = int(s * 0.30)          # arm length from centre
    cx = cy = s // 2
    r = arm // 2
    d.rounded_rectangle([cx - arm, cy - ext, cx + arm, cy + ext], radius=r, fill=WHITE)
    d.rounded_rectangle([cx - ext, cy - arm, cx + ext, cy + arm], radius=r, fill=WHITE)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_render(sz) for sz in sizes]
    images[0].save(_OUT, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
    print("Wrote", _OUT)


if __name__ == "__main__":
    main()
