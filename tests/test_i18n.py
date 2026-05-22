"""Tests for src/i18n.py loader behavior.

Verifies:
- get_translations("en") returns English dict with known keys
- get_translations("sl") falls back to English for any missing keys
- get_translations("xx") falls back to English for unknown language
- get_locale_for_country("SI") returns "sl"
- get_locale_for_country("ZZ") returns "en" (unknown country)
"""


from src.i18n import get_translations, get_locale_for_country


def test_get_translations_en():
    translations = get_translations("en")
    assert isinstance(translations, dict)
    assert len(translations) > 0
    assert translations["nav.overview"] == "Overview"
    assert translations["nav.positions"] == "Positions"


def test_get_translations_returns_known_language():
    sl = get_translations("sl")
    assert isinstance(sl, dict)
    assert sl["nav.overview"] == "Pregled"


def test_get_translations_fallback():
    """All English keys must be present in every supported language (via fallback)."""
    en = get_translations("en")
    for lang in ["sl", "de", "fr", "it", "es", "nl"]:
        result = get_translations(lang)
        for key in en:
            assert key in result, f"Key '{key}' missing from get_translations('{lang}')"


def test_get_translations_unknown_lang():
    """Unknown language code returns English translations."""
    en = get_translations("en")
    unknown = get_translations("xx")
    assert unknown == en


def test_get_locale_for_country_known():
    assert get_locale_for_country("SI") == "sl"
    assert get_locale_for_country("DE") == "de"
    assert get_locale_for_country("FR") == "fr"
    assert get_locale_for_country("US") == "en"


def test_get_locale_for_country_case_insensitive():
    assert get_locale_for_country("si") == "sl"
    assert get_locale_for_country("de") == "de"


def test_get_locale_for_country_unknown():
    assert get_locale_for_country("ZZ") == "en"
    assert get_locale_for_country("XX") == "en"
