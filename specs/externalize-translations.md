# PRD: Externalize Translations

**Epic:** SAA-19
**Status:** Draft
**Confidence:** 85%
**Last updated:** 2026-05-21

## Summary

Move the 3,032-line `src/i18n.py` module's 7 language dictionaries (en, sl, de, fr, it, es, nl) into external flat JSON files under a `locales/` directory, reducing `i18n.py` to a thin loader while preserving the existing `get_translations(lang)` and `get_locale_for_country(code)` API. Key parity across languages is enforced via pytest, not at startup.

## Requirements

1. Translation strings stored as flat JSON files (`locales/{lang}.json`) with dot-notation keys (e.g. `"nav.overview": "Overview"`)
2. One JSON file per language: `en.json`, `sl.json`, `de.json`, `fr.json`, `it.json`, `es.json`, `nl.json`
3. `i18n.py` reduced to a loader module (<100 lines) that reads JSON files from `src/locales/` at module import time
4. Existing API preserved: `get_translations(lang)` and `get_locale_for_country(code)` unchanged
5. Missing-key fallback: return English string for any key missing in a target language
6. Key parity validated by a pytest test, not at runtime startup
7. Locale files live at `src/locales/` (inside the package, resolved via `__file__`-relative path)
8. Keys grouped by prefix within each JSON file (nav.*, summary.*, etc.) matching current i18n.py section structure
9. `COUNTRY_LOCALE_MAP` externalized to `src/locales/country_map.json`
10. Extraction performed via a one-shot Python script to avoid copy-paste errors across 7 languages x ~450 keys
11. No Dockerfile changes needed — `src/locales/` ships inside `src/` automatically

## Acceptance Criteria

1. `src/i18n.py` is under 100 lines
2. All 7 locale files exist in `locales/` and contain identical key sets
3. All existing pages render correctly in all languages (no broken translations)
4. A pytest test validates that every locale file has the same keys as `en.json`
5. No new dependencies added (uses stdlib `json` module)

## Open Questions

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| File format | Flat JSON | No extra dependency, stdlib support, widely supported by translation tools (Crowdin, Lokalise) | 2026-05-21 |
| Directory layout | One file per language (`locales/{lang}.json`) | Simple, matches current structure, easy to diff/review, standard i18n convention | 2026-05-21 |
| Key validation timing | Test-time only (pytest) | Fast startup, no runtime overhead; missing keys still fall back to English at runtime | 2026-05-21 |
| Loading strategy | Module import time | Simple, deterministic, matches current behavior; ~7 small JSON files loaded once | 2026-05-21 |
| Locales directory | `src/locales/` | Inside the package, easy `__file__`-relative resolution, ships naturally with the package | 2026-05-21 |
| Key organization | Grouped by prefix | Matches existing comment-section structure in i18n.py, easier for translators to find related strings | 2026-05-21 |
| COUNTRY_LOCALE_MAP | Externalize to `country_map.json` | Full externalization for consistency; allows adding country mappings without code changes | 2026-05-21 |
| Docker/deployment | No changes needed | `src/locales/` auto-included via existing `COPY src/` in Dockerfile | 2026-05-21 |
| Migration approach | Automated script | Guarantees no copy-paste errors across 7 languages x ~450 keys | 2026-05-21 |
