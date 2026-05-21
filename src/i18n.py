"""Internationalization (i18n) for portfolio report UI strings.

Translations are stored as flat JSON files in src/locales/{lang}.json.
Keys are dot-notation strings (e.g. "nav.overview") used by the frontend
t() function to look up translations.

Public API:
    get_translations(lang)          -> dict[str, str]
    get_locale_for_country(code)    -> str
"""

from __future__ import annotations

import json
from pathlib import Path

_LOCALES_DIR: Path = Path(__file__).parent / "locales"

_LANGS = ("en", "sl", "de", "fr", "it", "es", "nl")


def _load_json(filename: str) -> dict[str, str]:
    """Read and parse a single JSON file from the locales directory."""
    path = _LOCALES_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# All translations loaded once at import time.
TRANSLATIONS: dict[str, dict[str, str]] = {
    lang: _load_json(f"{lang}.json") for lang in _LANGS
}

# Country code → default UI language, loaded from country_map.json.
COUNTRY_LOCALE_MAP: dict[str, str] = _load_json("country_map.json")  # type: ignore[assignment]


def get_translations(lang: str) -> dict[str, str]:
    """Return translation dict for a language, falling back to English for missing keys."""
    en = TRANSLATIONS["en"]
    if lang == "en":
        return en
    target = TRANSLATIONS.get(lang, {})
    merged = dict(en)
    merged.update(target)
    return merged


def get_locale_for_country(country_code: str) -> str:
    """Return the default UI language for a given ISO 3166-1 alpha-2 country code."""
    return COUNTRY_LOCALE_MAP.get(country_code.upper(), "en")
