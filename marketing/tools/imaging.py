"""Writing PNGs that are small enough to keep in the repository.

Interface screenshots and flat typographic cards are the ideal case for an
indexed palette: they are large areas of a handful of brand colours, with
anti-aliased type over them. Quantising to 256 colours takes a 2880x1800 grab
from about 400 KB to about 150 KB with no visible difference — the chart's
anti-aliased line and 20-pixel Dari text come out pixel-for-pixel the same at
100%. Plain ``optimize=True`` saves almost nothing on the same file.

Dithering is off deliberately. It would add noise to the flat fills to fight
banding that is not there, and cost most of the saving back.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

PALETTE_SIZE = 256


def save_png(image: Image.Image, path: Path) -> None:
    quantized = image.convert("RGB").quantize(
        colors=PALETTE_SIZE,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    quantized.save(path, "PNG", optimize=True)
