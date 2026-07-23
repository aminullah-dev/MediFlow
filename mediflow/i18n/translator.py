"""Runtime translation management for Dari, Pashto (and future English).

Design
------
* Translations are compiled Qt ``.qm`` files under ``i18n/translations``.
* Switching language installs the matching :class:`QTranslator` and flips the
  application layout direction (RTL for Dari/Pashto) **without restarting**.
* Widgets never hardcode strings: they call ``self.tr("...")`` and implement a
  ``retranslate_ui`` method. On language change the manager emits
  :attr:`language_changed`; the main window walks the widget tree and calls
  every ``retranslate_ui`` so all visible text updates live.

If a ``.qm`` file is missing (e.g. during early development) the source strings
are shown, so the app remains fully usable while translations are authored.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTranslator, Signal

from mediflow.core.constants import Language
from mediflow.core.logging_config import get_logger

log = get_logger("i18n")

_TRANSLATIONS_DIR = Path(__file__).parent / "translations"


class TranslationManager(QObject):
    language_changed = Signal(str)  # emits the new Language value

    def __init__(self, app: QCoreApplication):
        super().__init__()
        self._app = app
        self._translator = QTranslator()
        self._current = Language.DARI

    @property
    def current(self) -> Language:
        return self._current

    def install(self, language: Language) -> None:
        """Load and apply ``language``; safe to call repeatedly."""
        self._app.removeTranslator(self._translator)
        self._translator = QTranslator()

        qm_path = _TRANSLATIONS_DIR / f"mediflow_{language.value}.qm"
        if qm_path.exists():
            if self._translator.load(str(qm_path)):
                self._app.installTranslator(self._translator)
            else:
                log.warning("Failed to load translation file %s", qm_path)
        else:
            log.info("Translation file %s not found; using source strings.", qm_path.name)

        direction = Qt.LayoutDirection.RightToLeft if language.is_rtl else Qt.LayoutDirection.LeftToRight
        self._app.setLayoutDirection(direction)

        self._current = language
        self.language_changed.emit(language.value)
        log.info("Language switched to %s (%s).", language.name,
                 "RTL" if language.is_rtl else "LTR")


def retranslate_tree(root: QObject) -> None:
    """Depth-first call ``retranslate_ui`` on every widget that defines it."""
    stack: list[QObject] = [root]
    while stack:
        node = stack.pop()
        hook = getattr(node, "retranslate_ui", None)
        if callable(hook):
            hook()
        stack.extend(node.children())
