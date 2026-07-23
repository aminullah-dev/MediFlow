"""Light/Dark theming via Qt Style Sheets.

A single palette dictionary per theme drives one QSS template, so both themes
stay visually consistent and new design tokens are added in exactly one place.
The manager applies the stylesheet application-wide and switches at runtime.

The design language: a fixed deep-navy brand sidebar (identity is constant
across themes), a calm clinical teal as the primary accent, generous radii and
spacing, and a clear typographic hierarchy.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from mediflow.core.constants import Theme

# Palette derived from the ui-ux-pro-max "healthcare/clinic" design system:
# medical teal primary (#0891B2), health-green success (#16A34A), WCAG-checked.
_PALETTES: dict[Theme, dict[str, str]] = {
    Theme.LIGHT: {
        "bg": "#eaf0f1",
        "surface": "#ffffff",
        "surface_alt": "#f1f6f7",
        "surface_hover": "#e9f1f2",
        "text": "#12252b",
        "text_muted": "#5a6b72",
        "text_faint": "#93a6ac",
        "primary": "#0891b2",
        "primary_hover": "#0e7490",
        "primary_press": "#155e75",
        "on_primary": "#ffffff",
        "danger": "#dc2626",
        "danger_hover": "#b91c1c",
        "danger_soft": "#fdecec",
        "success": "#16a34a",
        "border": "#dde7e9",
        "border_strong": "#c4d3d6",
        "sidebar_top": "#0a3a44",
        "sidebar_bottom": "#0d5563",
        "sidebar_text": "#bcd4d8",
        "sidebar_text_dim": "#7ea3a8",
        "input_bg": "#ffffff",
        "scrollbar": "#c8d6d9",
        "badge_bg": "#e0f5f4",
        "badge_text": "#0e7490",
    },
    Theme.DARK: {
        "bg": "#0b1418",
        "surface": "#121e23",
        "surface_alt": "#18272d",
        "surface_hover": "#1d2f36",
        "text": "#e6f0f2",
        "text_muted": "#8ba0a6",
        "text_faint": "#60767c",
        "primary": "#22c3c9",
        "primary_hover": "#3dd6db",
        "primary_press": "#12a3a9",
        "on_primary": "#04231f",
        "danger": "#f26d6d",
        "danger_hover": "#f58787",
        "danger_soft": "#3a1f1f",
        "success": "#37c26a",
        "border": "#243a41",
        "border_strong": "#33505a",
        "sidebar_top": "#072830",
        "sidebar_bottom": "#0a4451",
        "sidebar_text": "#aac6cc",
        "sidebar_text_dim": "#6c9199",
        "input_bg": "#0e1a1f",
        "scrollbar": "#2a4149",
        "badge_bg": "#0e3a3d",
        "badge_text": "#3dd6db",
    },
}

# Live copy of the active palette, so views can pick theme-aware icon colours
# without threading the ThemeManager through every widget.
CURRENT: dict[str, str] = dict(_PALETTES[Theme.LIGHT])

_QSS_TEMPLATE = """
* {{
    font-family: "Segoe UI", "Vazirmatn", "Iranian Sans", "Tahoma", sans-serif;
    font-size: 14px;
    outline: 0;
}}
QMainWindow, QDialog {{ background-color: {bg}; }}
QWidget {{ background-color: transparent; color: {text}; }}

/* ---- Sidebar --------------------------------------------------------- */
QFrame#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {sidebar_top}, stop:1 {sidebar_bottom});
    border: none;
}}
QLabel#Brand {{
    color: #ffffff;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#BrandTag {{
    color: {sidebar_text_dim};
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QFrame#SidebarRule {{ background-color: rgba(255,255,255,0.08); max-height: 1px; }}
QLabel#NavSection {{
    color: {sidebar_text_dim};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
}}
QPushButton#NavButton {{
    background: transparent;
    color: {sidebar_text};
    border: none;
    border-radius: 9px;
    padding: 10px 14px;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton#NavButton:hover {{ background-color: rgba(255,255,255,0.08); color: #ffffff; }}
QPushButton#NavButton:checked {{
    background-color: {primary};
    color: #ffffff;
    font-weight: 600;
}}

/* ---- Header ---------------------------------------------------------- */
QFrame#Header {{
    background-color: {surface};
    border: none;
    border-bottom: 1px solid {border};
}}
QLabel#HeaderTitle {{ font-size: 18px; font-weight: 700; color: {text}; }}
QLabel#HeaderUser {{ color: {text_muted}; font-size: 13px; }}
QFrame#Avatar {{
    background-color: {primary};
    border-radius: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
}}
QLabel#AvatarText {{ color: #ffffff; font-weight: 700; font-size: 14px; background: transparent; }}

/* ---- Cards ----------------------------------------------------------- */
QFrame#Card, QGroupBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 16px;
}}
QFrame#StatCard {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 16px;
}}
QLabel#StatIcon {{
    background-color: {primary};
    border-radius: 12px;
    min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px;
}}
QLabel#StatValue {{ font-size: 30px; font-weight: 700; color: {text}; }}
QLabel#StatCaption {{ color: {text_muted}; font-size: 13px; font-weight: 500; }}

/* ---- Typography ------------------------------------------------------ */
QLabel#PageTitle {{ font-size: 22px; font-weight: 700; color: {text}; letter-spacing: -0.2px; }}
QLabel#Subtitle {{ color: {text_muted}; font-size: 14px; }}
QLabel#SectionTitle {{ font-size: 15px; font-weight: 700; color: {text}; }}
QLabel#SectionHint {{ color: {text_muted}; font-size: 12px; }}
QFrame#SectionIcon {{
    background-color: {primary}; border-radius: 10px;
    min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px;
}}
QLabel#SectionEmoji {{ font-size: 18px; background: transparent; }}
QFrame#Divider {{ background-color: {border}; max-height: 1px; min-height: 1px; }}
QFrame#FormFooter {{
    background-color: {surface}; border: 1px solid {border}; border-radius: 12px;
}}
QLabel#SavedNote {{ color: {success}; font-weight: 600; }}
QLabel#Muted {{ color: {text_muted}; }}
QLabel#Badge {{
    background-color: {badge_bg};
    color: {badge_text};
    border-radius: 11px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#EmptyGlyph {{ font-size: 46px; }}

/* ---- Inputs ---------------------------------------------------------- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {input_bg};
    border: 1px solid {border_strong};
    border-radius: 9px;
    padding: 9px 12px;
    color: {text};
    selection-background-color: {primary};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {primary}; padding: 8px 11px; }}
QLineEdit:hover, QComboBox:hover {{ border: 1px solid {primary}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background-color: {surface};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {primary};
    selection-color: #ffffff;
    outline: 0;
}}

/* ---- Buttons --------------------------------------------------------- */
QPushButton {{
    background-color: {surface_alt};
    color: {text};
    border: 1px solid {border_strong};
    border-radius: 9px;
    padding: 9px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {surface_hover}; border: 1px solid {primary}; }}
QPushButton:pressed {{ background-color: {border}; }}
QPushButton:disabled {{ color: {text_faint}; border: 1px solid {border}; }}

QPushButton#Primary {{
    background-color: {primary}; color: {on_primary}; border: none; padding: 11px 18px;
}}
QPushButton#Primary:hover {{ background-color: {primary_hover}; }}
QPushButton#Primary:pressed {{ background-color: {primary_press}; }}
QPushButton#Primary:disabled {{ background-color: {surface_alt}; color: {text_faint}; }}

QPushButton#Ghost {{
    background-color: transparent; border: 1px solid {border_strong};
    padding: 8px 14px; color: {text_muted};
}}
QPushButton#Ghost:hover {{ border: 1px solid {primary}; color: {text}; }}

QPushButton#Danger {{ background-color: transparent; color: {danger}; border: 1px solid {border_strong}; }}
QPushButton#Danger:hover {{ background-color: {danger_soft}; color: {danger}; border: 1px solid {danger}; }}
QPushButton#Danger:disabled {{ color: {text_faint}; border: 1px solid {border}; background-color: transparent; }}

QPushButton#Segment {{
    background-color: {surface_alt}; color: {text_muted};
    border: 1px solid {border_strong}; padding: 8px 18px;
}}
QPushButton#Segment:checked {{ background-color: {primary}; color: {on_primary}; border: none; }}

/* ---- Tables ---------------------------------------------------------- */
QTableView {{
    background-color: {surface};
    alternate-background-color: {surface_alt};
    gridline-color: {border};
    border: 1px solid {border};
    border-radius: 14px;
    selection-background-color: {primary};
    selection-color: #ffffff;
}}
QTableView::item {{ padding: 8px 10px; }}
QHeaderView::section {{
    background-color: {surface_alt};
    color: {text_muted};
    padding: 12px 10px;
    border: none;
    border-bottom: 1px solid {border};
    font-weight: 700;
    letter-spacing: 0.3px;
}}

/* ---- Scrollbars ------------------------------------------------------ */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scrollbar}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {text_faint}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {scrollbar}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Dialogs / messages --------------------------------------------- */
QMessageBox {{ background-color: {surface}; }}
QToolTip {{
    background-color: {surface}; color: {text};
    border: 1px solid {border_strong}; border-radius: 6px; padding: 6px 8px;
}}
"""


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._current = Theme.LIGHT

    @property
    def current(self) -> Theme:
        return self._current

    def apply(self, theme: Theme) -> None:
        palette = _PALETTES[theme]
        CURRENT.clear()
        CURRENT.update(palette)
        self._app.setStyleSheet(_QSS_TEMPLATE.format(**palette))
        self._current = theme
        self.theme_changed.emit(theme.value)

    def toggle(self) -> None:
        self.apply(Theme.DARK if self._current is Theme.LIGHT else Theme.LIGHT)
