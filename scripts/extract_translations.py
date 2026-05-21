#!/usr/bin/env python3
"""One-shot script to extract TRANSLATIONS and COUNTRY_LOCALE_MAP from src/i18n.py
into flat JSON files under src/locales/.

Usage:
    python scripts/extract_translations.py

Fills missing keys in non-English locales with English fallback values to ensure
key parity across all locale files. Safe to re-run: files are overwritten.
"""

import json
import sys
from pathlib import Path

# Add repo root to path so we can import src.i18n
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.i18n import TRANSLATIONS, COUNTRY_LOCALE_MAP  # noqa: E402

LOCALES_DIR = REPO_ROOT / "src" / "locales"
LOCALES_DIR.mkdir(exist_ok=True)

en = TRANSLATIONS["en"]

# Write each locale JSON file
for lang, translations in TRANSLATIONS.items():
    # Build full dict: start with English (all keys), then override with translated values.
    # This fills any missing keys with English fallback values, ensuring key parity.
    data: dict[str, str] = dict(en)
    data.update(translations)

    out_path = LOCALES_DIR / f"{lang}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    filled = len(en) - len(translations)
    print(f"  wrote {out_path.name}: {len(data)} keys"
          + (f" ({filled} filled from English)" if filled > 0 else ""))

# Write country_map.json
country_map_path = LOCALES_DIR / "country_map.json"
with open(country_map_path, "w", encoding="utf-8") as f:
    json.dump(COUNTRY_LOCALE_MAP, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"  wrote {country_map_path.name}: {len(COUNTRY_LOCALE_MAP)} entries")

print(f"\nDone: {len(TRANSLATIONS)} locale files + 1 country map in {LOCALES_DIR}")
