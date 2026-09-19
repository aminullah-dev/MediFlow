"""Render the social cards described by ``marketing/cards.toml``.

Two sizes per card per language: 1080x1080 for a Facebook or Instagram feed and
1080x1920 for a WhatsApp status, which is where most of this audience actually
looks. Nothing is hand-placed — the headline picks its own size until it fits,
so editing a line in the TOML cannot silently push text off the canvas.

Persian and Pashto need real shaping and bidi, not just a right-aligned string.
Pillow gets both from libraqm, which the module refuses to start without: a
build lacking it renders the letters unjoined and in the wrong order, and the
failure looks enough like a design choice that it ships unnoticed.

    python marketing/tools/make_cards.py
"""
from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # so the script runs from anywhere

from marketing.tools.imaging import save_png  # noqa: E402

FONTS = ROOT / "mediflow" / "ui" / "fonts"
CARDS = ROOT / "marketing" / "cards.toml"
OUT = ROOT / "marketing" / "images" / "cards"

# Straight out of mediflow/ui/theme.py, so a card and a screenshot of the
# application sitting side by side in a feed are the same product.
INK_DARK = "#0a3a44"
INK_DARK_FOOT = "#072830"
CYAN = "#22c3c9"
TEAL = "#0e7490"
PAPER = "#eaf0f1"
AMBER = "#f0a83c"
WHITE = "#ffffff"
DIM_ON_DARK = "#aac6cc"
DIM_ON_LIGHT = "#4a6169"


@dataclass(frozen=True)
class Accent:
    ground: str
    footer: str
    headline: str
    support: str
    rule: str
    mark: str


ACCENTS = {
    "brand": Accent(INK_DARK, INK_DARK_FOOT, WHITE, DIM_ON_DARK, CYAN, CYAN),
    "light": Accent(PAPER, "#dbe6e8", "#12252b", DIM_ON_LIGHT, TEAL, TEAL),
    "warn": Accent(INK_DARK, INK_DARK_FOOT, WHITE, DIM_ON_DARK, AMBER, AMBER),
}

# Wordmark and the standing platform line, per language.
WORDMARK = {"dari": "مدی‌فلو", "pashto": "مدي‌فلو"}
FOOTNOTE = {
    "dari": "ویندوز و مک · بدون انترنت",
    "pashto": "وینډوز او مک · بې انټرنیټه",
}

SIZES = {"square": (1080, 1080), "story": (1080, 1920)}

# Where the text block sits in the space above the footer. A feed card is read
# whole, so it centres. A story is not: the phone's own chrome covers the top,
# the reply control covers the bottom, and the eye lands below the middle —
# so the block is pushed down into the part nobody's thumb is on.
BLOCK_BIAS = {"square": 0.5, "story": 0.62}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Vazirmatn-{weight}.ttf"), size)


def _draw_rtl(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, anchor="ra"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor,
              direction="rtl", language="fa")


def _line_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font, direction="rtl", language="fa")
    return box[2] - box[0]


def _descent(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """How far this line actually reaches below the drawing origin."""
    box = draw.textbbox((0, 0), text, font=font, direction="rtl", language="fa")
    return max(box[3] - font.size, 0)


def _fit(draw, lines: list[str], weight: str, width: int, start: int,
         floor: int = 28) -> ImageFont.FreeTypeFont:
    """Largest size at which every line clears ``width``."""
    size = start
    while size > floor:
        font = _font(weight, size)
        if all(_line_width(draw, line, font) <= width for line in lines):
            return font
        size -= 2
    return _font(weight, floor)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    """Greedy wrap on spaces, honouring the newlines already in the source."""
    out: list[str] = []
    for paragraph in text.split("\n"):
        words, line = paragraph.split(), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if line and _line_width(draw, trial, font) > width:
                out.append(line)
                line = word
            else:
                line = trial
        out.append(line)
    return out


def render(card: dict, language: str, shape: str) -> Image.Image:
    width, height = SIZES[shape]
    accent = ACCENTS[card.get("accent", "brand")]
    copy = card[language]

    image = Image.new("RGB", (width, height), accent.ground)
    draw = ImageDraw.Draw(image)

    margin = 88
    text_width = width - margin * 2
    right = width - margin
    footer_height = 150 if shape == "square" else 300
    draw.rectangle((0, height - footer_height, width, height), fill=accent.footer)

    # Wordmark, top right, with a short accent rule beneath it.
    mark_font = _font("Bold", 52)
    _draw_rtl(draw, (right, margin), WORDMARK[language], mark_font, accent.mark)
    rule_y = margin + 84
    draw.rectangle((right - 96, rule_y, right, rule_y + 6), fill=accent.mark)

    headline_lines = copy["headline"].split("\n")
    headline_font = _fit(draw, headline_lines, "Bold", text_width,
                         start=104 if shape == "square" else 118)
    leading = int(headline_font.size * 1.42)

    support_font = _font("Medium", 40 if shape == "square" else 46)
    support_lines = _wrap(draw, copy["support"], support_font, text_width)
    support_leading = int(support_font.size * 1.5)

    # The gap before the rule is measured, not guessed: Persian descenders
    # (ض, ی, ج) hang well below the baseline, and a fixed gap puts the rule
    # through the last line on exactly the cards with the longest words.
    drop = max(_descent(draw, line, headline_font) for line in headline_lines)
    gap_before_rule = drop + 30

    block = (len(headline_lines) * leading + gap_before_rule + 39
             + len(support_lines) * support_leading)
    top = int((height - footer_height - block) * BLOCK_BIAS[shape])
    top = max(top, rule_y + 110)

    y = top
    for line in headline_lines:
        _draw_rtl(draw, (right, y), line, headline_font, accent.headline)
        y += leading

    y += gap_before_rule - leading + headline_font.size
    draw.rectangle((right - 130, y, right, y + 5), fill=accent.rule)
    y += 34

    for line in support_lines:
        _draw_rtl(draw, (right, y), line, support_font, accent.support)
        y += support_leading

    foot_font = _font("SemiBold", 34 if shape == "square" else 38)
    # On a story the band is deep enough to clear the reply control, so the
    # line sits near its top rather than in the middle of dead space.
    foot_y = (height - footer_height // 2 if shape == "square"
              else height - footer_height + 66)
    _draw_rtl(draw, (right, foot_y), FOOTNOTE[language],
              foot_font, accent.mark, anchor="rm")

    return image


def main() -> int:
    if not features.check("raqm"):
        print("Pillow was built without libraqm: Persian and Pashto would be "
              "rendered unjoined and left-to-right. Install a Pillow with "
              "raqm support and run again.", file=sys.stderr)
        return 1

    cards = tomllib.loads(CARDS.read_text(encoding="utf-8"))["card"]
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for card in cards:
        for language in ("dari", "pashto"):
            for shape in SIZES:
                path = OUT / f"{card['id']}-{language}-{shape}.png"
                save_png(render(card, language, shape), path)
                written += 1
                print(f"  {path.relative_to(ROOT)}")
    print(f"\n{written} cards in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
