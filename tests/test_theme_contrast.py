"""WCAG AA contrast pins for the shared MediFlow palette.

Background: an audit of the two stylesheets found eighteen token pairs below
the AA floor — white on the light theme's teal at 3.68:1, the light input
outline at 1.54:1 against the card it sat on, the sidebar's section labels at
3.08:1 over the lower half of the gradient, and, in the dark theme, literal
white on the bright teal fill at 2.16:1. Those were corrected in place. The
point of this file is that they stay corrected: a palette is edited by eye, and
by eye a token that fails by 0.3 looks identical to one that passes.

The tokens are read out of the two stylesheets as text rather than imported, so
the suite keeps running without PySide6 and without a display — the same reason
mediflow.app defers its Qt imports.

Thresholds are WCAG 2.1: 1.4.3 wants 4.5:1 for body text, 1.4.11 wants 3:1 for
the visual boundary that identifies a control. Card borders are deliberately
absent: a card is a decorative container, not a control, and its fill already
separates it from the page.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_THEME_PY = _ROOT / "mediflow" / "ui" / "theme.py"
_APP_CSS = _ROOT / "mediflow" / "web" / "static" / "app.css"

TEXT = 4.5      # WCAG 1.4.3, normal-size text
CONTROL = 3.0   # WCAG 1.4.11, non-text contrast


def _contrast(fg: str, bg: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    def luminance(value: str) -> float:
        value = value.lstrip("#")
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(source: str, pattern: str) -> dict[str, str]:
    """Pull ``name: #hex`` pairs out of one palette block."""
    block = re.search(pattern, source, re.DOTALL)
    assert block, f"palette block not found: {pattern}"
    return {
        name.strip().strip('"').lstrip("-"): value
        for name, value in re.findall(r'([\w"-]+)\s*:\s*"?(#[0-9a-fA-F]{6})"?', block.group(1))
    }


_theme_src = _THEME_PY.read_text(encoding="utf-8")
_css_src = _APP_CSS.read_text(encoding="utf-8")

LIGHT = _tokens(_theme_src, r"Theme\.LIGHT:\s*\{(.*?)\n    \},")
DARK = _tokens(_theme_src, r"Theme\.DARK:\s*\{(.*?)\n    \},")
WEB_LIGHT = _tokens(_css_src, r"\n:root \{(.*?)\n\}")
WEB_DARK = _tokens(_css_src, r"prefers-color-scheme: dark\).*?:root \{(.*?)\n  \}")


def _desktop_pairs(p: dict[str, str], name: str):
    """Every foreground the desktop QSS paints on a background it controls."""
    return [
        (f"{name} body text / window", p["text"], p["bg"], TEXT),
        (f"{name} body text / card", p["text"], p["surface"], TEXT),
        (f"{name} body text / alt fill", p["text"], p["surface_alt"], TEXT),
        (f"{name} muted / card", p["text_muted"], p["surface"], TEXT),
        (f"{name} muted / alt fill", p["text_muted"], p["surface_alt"], TEXT),
        (f"{name} muted / window", p["text_muted"], p["bg"], TEXT),
        (f"{name} primary label", p["on_primary"], p["primary"], TEXT),
        (f"{name} primary label hover", p["on_primary"], p["primary_hover"], TEXT),
        (f"{name} primary label pressed", p["on_primary"], p["primary_press"], TEXT),
        (f"{name} danger label / card", p["danger"], p["surface"], TEXT),
        (f"{name} danger label / soft fill", p["danger"], p["danger_soft"], TEXT),
        (f"{name} success note / card", p["success"], p["surface"], TEXT),
        (f"{name} warn label / card", p["warn"], p["surface"], TEXT),
        (f"{name} warn label / window", p["warn"], p["bg"], TEXT),
        (f"{name} warn pill", p["warn_ink"], p["warn_soft"], TEXT),
        (f"{name} badge", p["badge_text"], p["badge_bg"], TEXT),
        (f"{name} sidebar text / gradient top", p["sidebar_text"], p["sidebar_top"], TEXT),
        (f"{name} sidebar text / gradient bottom", p["sidebar_text"], p["sidebar_bottom"], TEXT),
        (f"{name} sidebar labels / gradient top", p["sidebar_text_dim"], p["sidebar_top"], TEXT),
        (f"{name} sidebar labels / gradient bottom",
         p["sidebar_text_dim"], p["sidebar_bottom"], TEXT),
        (f"{name} brand / gradient top", "#ffffff", p["sidebar_top"], TEXT),
        (f"{name} input outline / input fill", p["border_strong"], p["input_bg"], CONTROL),
        (f"{name} button outline / card", p["border_strong"], p["surface"], CONTROL),
        (f"{name} button outline / own fill", p["border_strong"], p["surface_alt"], CONTROL),
        (f"{name} button outline / window", p["border_strong"], p["bg"], CONTROL),
        (f"{name} focus ring / input fill", p["primary"], p["input_bg"], CONTROL),
        (f"{name} focus ring / card", p["primary"], p["surface"], CONTROL),
        (f"{name} scrollbar handle / window", p["scrollbar"], p["bg"], CONTROL),
    ]


def _web_pairs(p: dict[str, str], name: str):
    return [
        (f"{name} body text / page", p["text"], p["bg"], TEXT),
        (f"{name} body text / card", p["text"], p["surface"], TEXT),
        (f"{name} muted / page", p["muted"], p["bg"], TEXT),
        (f"{name} muted / card", p["muted"], p["surface"], TEXT),
        (f"{name} muted / alt fill", p["muted"], p["surface-alt"], TEXT),
        (f"{name} link / card", p["primary"], p["surface"], TEXT),
        (f"{name} link / row hover", p["primary"], p["surface-alt"], TEXT),
        (f"{name} button label", p["on-primary"], p["primary"], TEXT),
        (f"{name} button label hover", p["on-primary"], p["primary-hover"], TEXT),
        (f"{name} danger / card", p["danger"], p["surface"], TEXT),
        (f"{name} danger / banner fill", p["danger"], p["danger-soft"], TEXT),
        (f"{name} warn / card", p["warn"], p["surface"], TEXT),
        (f"{name} warn / page", p["warn"], p["bg"], TEXT),
        (f"{name} pill teal", p["primary"], p["accent-soft"], TEXT),
        (f"{name} pill amber", p["warn-ink"], p["warn-soft"], TEXT),
        (f"{name} pill blue", p["info"], p["info-soft"], TEXT),
        (f"{name} pill green", p["success"], p["success-soft"], TEXT),
        (f"{name} queue token, serving", p["info"], p["surface-alt"], TEXT),
        (f"{name} queue token, done", p["success"], p["surface-alt"], TEXT),
        (f"{name} field outline / field fill", p["border-strong"], p["input-bg"], CONTROL),
        (f"{name} field outline / card", p["border-strong"], p["surface"], CONTROL),
        (f"{name} field outline / page", p["border-strong"], p["bg"], CONTROL),
        (f"{name} field outline / alt fill", p["border-strong"], p["surface-alt"], CONTROL),
        (f"{name} focus ring / field fill", p["primary"], p["input-bg"], CONTROL),
    ]


PAIRS = (
    _desktop_pairs(LIGHT, "desktop light")
    + _desktop_pairs(DARK, "desktop dark")
    + _web_pairs(WEB_LIGHT, "web light")
    + _web_pairs(WEB_DARK, "web dark")
)


@pytest.mark.parametrize("label,fg,bg,required", PAIRS, ids=[p[0] for p in PAIRS])
def test_pair_meets_wcag_aa(label, fg, bg, required):
    measured = _contrast(fg, bg)
    assert measured >= required, (
        f"{label}: {fg} on {bg} is {measured:.2f}:1, below the {required}:1 floor"
    )


def test_web_palettes_define_the_same_tokens():
    """A token defined only in the dark block would leave a hole in light mode."""
    assert set(WEB_LIGHT) - {"radius"} == set(WEB_DARK)


def test_no_colour_literals_outside_the_palette_blocks():
    """Colours belong to a theme.

    The sheet used to hardcode the status-pill tints (``background: #10331c``)
    in the rules themselves, which is precisely why it could only ever be dark:
    a literal cannot follow a media query. The print block is the exception —
    it is paper, not a theme.
    """
    body = re.sub(r"/\*.*?\*/", "", _css_src, flags=re.DOTALL)  # prose may cite a hex
    for pattern in (r"\n:root \{.*?\n\}",
                    r"@media \(prefers-color-scheme: dark\) \{.*?\n  \}\n\}",
                    r"@media print \{.*?\n\}"):
        body, count = re.subn(pattern, "", body, flags=re.DOTALL)
        assert count == 1, f"palette block not matched: {pattern}"
    assert not re.findall(r"#[0-9a-fA-F]{3,6}\b", body)
