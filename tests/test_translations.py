"""The Dari and Pashto catalogues have to keep up with the interface.

This exists because they did not. The dashboard rewrite added fifteen strings —
the whole "needs attention" row, the trend heading, the revenue caption — and
none of them reached a ``.ts`` file, so the flagship screen of a trilingual
product rendered half in English for every Dari and Pashto user. Nothing failed;
the interface just quietly spoke the wrong language.

``pyside6-lupdate`` does not catch that class of regression on its own: the
dashboard holds its captions in class-level tables and calls ``self.tr(caption)``
with a variable, which a literal scan cannot see. So the tables are asserted
directly, alongside the catalogue-wide invariants that do generalise.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TRANSLATIONS = Path(__file__).resolve().parents[1] / "mediflow" / "i18n" / "translations"
LANGUAGES = ("fa_AF", "ps_AF")


def _catalogue(language: str) -> dict[tuple[str, str], str]:
    """``{(context, source): translation}`` for one .ts file.

    Keyed by context, not by source alone. Qt scopes a translation to the class
    that asked for it, and several strings — "Out of stock" among them — appear
    under more than one. A source-only mapping lets the last context in the file
    answer for all of them, which is exactly the kind of silent near-miss these
    tests exist to catch.
    """
    text = (TRANSLATIONS / f"mediflow_{language}.ts").read_text(encoding="utf-8")
    catalogue: dict[tuple[str, str], str] = {}
    for block in re.findall(r"<context>(.*?)</context>", text, re.DOTALL):
        name_match = re.search(r"<name>(.*?)</name>", block, re.DOTALL)
        if not name_match:
            continue
        context = name_match.group(1).strip()
        for source, _attrs, body in re.findall(
            r"<source>(.*?)</source>\s*<translation(.*?)>(.*?)</translation>",
            block, re.DOTALL,
        ):
            catalogue[(context, source)] = body
    return catalogue


def _unfinished(language: str) -> list[str]:
    text = (TRANSLATIONS / f"mediflow_{language}.ts").read_text(encoding="utf-8")
    return re.findall(
        r"<source>(.*?)</source>\s*<translation[^>]*type=\"unfinished\"", text, re.DOTALL
    )


@pytest.fixture(scope="module")
def catalogues() -> dict[str, dict[tuple[str, str], str]]:
    return {language: _catalogue(language) for language in LANGUAGES}


def _dashboard_sources() -> list[str]:
    """The caption strings the dashboard passes to ``tr()`` from its tables."""
    from mediflow.ui.views.dashboard_view import DashboardView

    sources = [caption for _key, caption, _icon in DashboardView._SPECS]
    for _key, _level, title, meta in DashboardView._ALERTS:
        sources += [title, meta]
    return sources


# ── the regression that prompted this file ───────────────────────────────────

@pytest.mark.parametrize("language", LANGUAGES)
def test_every_dashboard_caption_is_translated(language, catalogues):
    catalogue = catalogues[language]
    missing = [s for s in _dashboard_sources()
               if not catalogue.get(("DashboardView", s), "").strip()]
    assert not missing, (
        f"{language} has no translation for {missing}. The dashboard passes these "
        f"to tr() out of DashboardView._SPECS/_ALERTS, so they render in English."
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_dashboard_headings_are_translated(language, catalogues):
    catalogue = catalogues[language]
    headings = [
        "Dashboard", "Today at a glance", "Needs attention",
        "Nothing needs attention.", "Appointments, last 14 days",
        "No appointments in the last 14 days",
    ]
    missing = [s for s in headings
               if not catalogue.get(("DashboardView", s), "").strip()]
    assert not missing, f"{language} is missing {missing}"


# ── catalogue-wide invariants ────────────────────────────────────────────────

def test_dari_and_pashto_cover_the_same_strings(catalogues):
    dari, pashto = set(catalogues["fa_AF"]), set(catalogues["ps_AF"])
    assert not dari - pashto, f"only Dari has: {sorted(dari - pashto)}"
    assert not pashto - dari, f"only Pashto has: {sorted(pashto - dari)}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_translation_is_empty(language, catalogues):
    blank = [key for key, body in catalogues[language].items() if not body.strip()]
    assert not blank, f"{language} has empty translations for {blank}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_nothing_is_left_marked_unfinished(language):
    assert not _unfinished(language)


# ── the compiled catalogue, which is what actually ships ─────────────────────

@pytest.mark.parametrize("language", LANGUAGES)
def test_the_compiled_qm_is_not_stale(language, catalogues):
    """A .ts edit that was never run through lrelease changes nothing at all.

    The application loads the .qm, so an up-to-date .ts with a stale .qm beside
    it is indistinguishable, at runtime, from never having translated the string.
    """
    qtcore = pytest.importorskip("PySide6.QtCore")

    translator = qtcore.QTranslator()
    assert translator.load(f"mediflow_{language}", str(TRANSLATIONS)), (
        f"mediflow_{language}.qm could not be loaded"
    )

    catalogue = catalogues[language]
    stale = [
        source for source in _dashboard_sources()
        if translator.translate("DashboardView", source)
        != catalogue[("DashboardView", source)]
    ]
    assert not stale, (
        f"mediflow_{language}.qm does not carry {stale}. Recompile it:\n"
        f"  pyside6-lrelease mediflow/i18n/translations/mediflow_{language}.ts "
        f"-qm mediflow/i18n/translations/mediflow_{language}.qm"
    )
