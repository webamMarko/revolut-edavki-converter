"""Key-parity test: every locale JSON file must have exactly the same keys as en.json.

This test catches regressions where a new translation key is added to English but
not propagated to other language files.
"""

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "locales"
LANGUAGES = ["en", "sl", "de", "fr", "it", "es", "nl"]


def _load(lang: str) -> dict[str, str]:
    with open(LOCALES_DIR / f"{lang}.json", encoding="utf-8") as f:
        return json.load(f)


def test_all_locales_have_same_keys():
    """Every non-English locale file has exactly the same key set as en.json."""
    en_keys = set(_load("en").keys())
    errors: list[str] = []

    for lang in LANGUAGES:
        if lang == "en":
            continue
        lang_keys = set(_load(lang).keys())
        missing = en_keys - lang_keys
        extra = lang_keys - en_keys
        if missing:
            preview = sorted(missing)[:5]
            errors.append(
                f"{lang}: missing {len(missing)} key(s) — {preview}"
                + (" ..." if len(missing) > 5 else "")
            )
        if extra:
            preview = sorted(extra)[:5]
            errors.append(
                f"{lang}: {len(extra)} extra key(s) — {preview}"
                + (" ..." if len(extra) > 5 else "")
            )

    assert not errors, "Key parity failures:\n" + "\n".join(errors)


def test_all_locale_files_exist():
    """Every expected locale JSON file is present on disk."""
    for lang in LANGUAGES:
        path = LOCALES_DIR / f"{lang}.json"
        assert path.exists(), f"Missing locale file: {path}"


def test_country_map_exists():
    """country_map.json is present and non-empty."""
    path = LOCALES_DIR / "country_map.json"
    assert path.exists(), f"Missing country map: {path}"
    data = _load("country_map")  # type: ignore[arg-type]
    assert len(data) > 0
