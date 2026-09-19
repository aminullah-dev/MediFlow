"""Render the live application into ``marketing/images/screens/``.

Marketing for clinic software is not believed until the buyer sees the software
in their own language, so these are grabs of the real widgets — same views, same
theme, same translation files the clinic will run — driven by a throwaway
database that ``demo_clinic`` fills with a plausible working day.

Run it from the repository root:

    QT_QPA_PLATFORM=offscreen python marketing/tools/shoot.py

Nothing here is imported by MediFlow; it exists only to produce the images.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# A disposable data folder: the harness must never touch a real installation.
_WORKSPACE = Path(tempfile.mkdtemp(prefix="mediflow-shoot-"))
os.environ["MEDIFLOW_DATA_DIR"] = str(_WORKSPACE)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from marketing.tools import demo_clinic  # noqa: E402
from marketing.tools.imaging import save_png  # noqa: E402
from mediflow.app import build_container  # noqa: E402
from mediflow.core.config import Config  # noqa: E402
from mediflow.core.constants import Language, Theme  # noqa: E402
from mediflow.i18n.translator import TranslationManager  # noqa: E402
from mediflow.ui import theme as theme_tokens  # noqa: E402
from mediflow.ui.main_window import MainWindow  # noqa: E402
from mediflow.ui.theme import ThemeManager, load_fonts  # noqa: E402

OUT = ROOT / "marketing" / "images" / "screens"
WINDOW = (1440, 900)
SCALE = 2  # retina-density grabs; social crops and blog posts both want them

# (nav key, file stem). Keys come from main_window.NAV_ENTRIES.
SHOTS = [
    ("dashboard", "dashboard"),
    ("reception", "reception"),
    ("pharmacy", "pharmacy"),
    ("patients", "patients"),
]
LANGUAGES = {Language.DARI: "dari", Language.PASHTO: "pashto"}
THEMES = {Theme.LIGHT: "light", Theme.DARK: "dark"}


def _first_run_password() -> str:
    text = (_WORKSPACE / "INITIAL_ADMIN_PASSWORD.txt").read_text(encoding="utf-8")
    match = re.search(r"temporary password:\s*(\S+)", text)
    if not match:
        raise SystemExit("could not read the seeded admin password")
    return match.group(1)


def _rename_operator(container) -> None:
    """Put a local name in the header.

    The seeded account is called "System Administrator", and an English name
    sitting above a Dari interface is the first thing a viewer notices — it
    reads as a translated product rather than one built for the clinic.
    """
    from mediflow.data.models.user import User

    with container.database.unit_of_work() as session:
        admin = session.query(User).filter_by(username="admin").one()
        admin.full_name = "داکتر رحیمی"


def _opaque(pixmap, background: str) -> QImage:
    """Flatten a window grab onto the theme background.

    ``QWidget.grab`` returns the widget's own painting, and the stylesheet
    leaves every plain ``QWidget`` transparent — only ``QMainWindow`` carries
    the page colour. Saved straight to PNG the content area therefore comes out
    with an alpha hole, which a viewer sees as a black rectangle. Compositing
    over the live palette's background restores what is actually on screen.
    """
    image = QImage(pixmap.size(), QImage.Format.Format_RGB888)
    image.fill(QColor(background))
    painter = QPainter(image)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return image


def _to_pillow(image: QImage) -> Image.Image:
    """Hand a QImage to Pillow so it can be written with an indexed palette."""
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    buffer = image.constBits().tobytes()
    # Qt pads every row to a 4-byte boundary; Pillow expects none, so the
    # stride has to be given explicitly or the picture shears.
    return Image.frombytes("RGB", (width, height), buffer, "raw", "RGB",
                           image.bytesPerLine())


def main() -> int:
    config = Config.bootstrap()
    container = build_container(config)

    password = _first_run_password()
    user = container.auth.authenticate("admin", password)
    _rename_operator(container)
    # The account is created needing a password change; screenshots must not be
    # of the forced-change dialog, so satisfy the policy before building the UI.
    container.auth.change_password(user.id, password, "Sh0wcase!Demo2026")
    user = container.auth.authenticate("admin", "Sh0wcase!Demo2026")

    demo_clinic.populate(container.database, doctor_id=user.id)

    app = QApplication(sys.argv)
    app.setApplicationName("MediFlow")
    load_fonts()
    translator = TranslationManager(app)
    theme = ThemeManager(app)

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for language, lang_name in LANGUAGES.items():
        translator.install(language)
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        for mode, theme_name in THEMES.items():
            theme.apply(mode)
            window = MainWindow(container, translator, theme)
            window._user = user          # stand in for the login dialog
            window._build_ui()
            window.resize(*WINDOW)
            window.show()
            for key, stem in SHOTS:
                if key not in window._nav_buttons:
                    print(f"  ! no nav entry {key!r}; skipping")
                    continue
                window._navigate(key)
                app.processEvents()
                pixmap = window.grab().scaled(
                    WINDOW[0] * SCALE, WINDOW[1] * SCALE,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image = _opaque(pixmap, theme_tokens.CURRENT["bg"])
                path = OUT / f"{stem}-{lang_name}-{theme_name}.png"
                save_png(_to_pillow(image), path)
                written += 1
                print(f"  {path.relative_to(ROOT)}")
            window.close()
            window.deleteLater()
            app.processEvents()

    container.database.dispose()
    shutil.rmtree(_WORKSPACE, ignore_errors=True)
    print(f"\n{written} screenshots in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
