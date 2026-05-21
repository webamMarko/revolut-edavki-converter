# Technical Specification: Externalize Translations

**Epic:** SAA-19
**PRD:** specs/externalize-translations.md
**Created:** 2026-05-21
**Status:** Ready for Review
**Confidence:** 92%

## Overview

Extract the 7 inline translation dictionaries (~3,000 lines) from `src/i18n.py` into flat JSON files under `src/locales/`, and reduce `i18n.py` to a thin loader that reads those files at import time. The `COUNTRY_LOCALE_MAP` dict moves to `src/locales/country_map.json`. The public API (`get_translations(lang)` and `get_locale_for_country(code)`) is unchanged; consumers (`src/html_report.py`) require zero modifications.

A one-shot extraction script ensures correctness across 7 languages x ~450 keys, eliminating copy-paste risk.

## Architecture

### System Context

```
src/html_report.py
    └── imports get_translations(), get_locale_for_country()
            └── src/i18n.py  (loader, <100 lines)
                    └── reads src/locales/*.json at import time
                            ├── en.json
                            ├── sl.json
                            ├── de.json
                            ├── fr.json
                            ├── it.json
                            ├── es.json
                            ├── nl.json
                            └── country_map.json
```

No other modules import from `i18n.py`. The Dockerfile's existing `COPY src/ src/` includes `src/locales/` automatically.

### Key Components

**`src/i18n.py` (modified)** — Reduced to ~60 lines:
- Module-level `_LOCALES_DIR` resolved via `Path(__file__).parent / "locales"`
- `_load_json(filename)` — reads and parses a single JSON file, returns `dict[str, str]`
- `TRANSLATIONS` — `dict[str, dict[str, str]]` populated at import time by loading all 7 locale files
- `COUNTRY_LOCALE_MAP` — `dict[str, str]` loaded from `country_map.json`
- `get_translations(lang)` — unchanged signature and behavior (merge target over English)
- `get_locale_for_country(code)` — unchanged signature and behavior

**`src/locales/*.json` (new, 7 files)** — Flat key-value JSON:
```json
{
  "nav.overview": "Overview",
  "nav.heatmap": "Heatmap",
  ...
}
```
Keys grouped by prefix (nav.*, summary.*, risk.*, etc.) matching current comment sections in `i18n.py`.

**`src/locales/country_map.json` (new)** — Country code to language mapping:
```json
{
  "SI": "sl",
  "DE": "de",
  "AT": "de",
  "US": "en",
  "IT": "it",
  "ES": "es",
  "FR": "fr",
  "NL": "nl"
}
```

**`scripts/extract_translations.py` (new, one-shot)** — Extraction script:
- Imports current `TRANSLATIONS` and `COUNTRY_LOCALE_MAP` from `src/i18n`
- Writes each language dict to `src/locales/{lang}.json` with `json.dump(..., ensure_ascii=False, indent=2)`
- Writes `COUNTRY_LOCALE_MAP` to `src/locales/country_map.json`
- Prints summary (file count, key count per language)

**`tests/test_i18n_parity.py` (new)** — Pytest key-parity validation:
- Loads all 7 locale JSON files
- Asserts every non-English file has exactly the same keys as `en.json`
- Reports missing and extra keys per language on failure

### Data Model

No database changes. All data is static JSON on the filesystem.

### API Contracts

No API changes. The two public functions retain their exact signatures:

```python
def get_translations(lang: str) -> dict[str, str]: ...
def get_locale_for_country(country_code: str) -> str: ...
```

## Implementation Plan

### Phase 1: Extract (one-shot script)

1. Write `scripts/extract_translations.py`
2. Run it to generate `src/locales/*.json` and `src/locales/country_map.json`
3. Verify output: correct file count, key counts match across languages

### Phase 2: Rewrite loader

1. Write failing tests for the new loader behavior
2. Replace `src/i18n.py` contents with the JSON-based loader
3. Verify tests pass and existing behavior is preserved

### Phase 3: Parity test

1. Write `tests/test_i18n_parity.py` — key-set equality across all locale files
2. Verify it passes on the freshly extracted files

### Phase 4: Cleanup

1. Delete the extraction script (or keep in `scripts/` for future use)
2. Verify `i18n.py` is under 100 lines (`wc -l`)

### TDD Task List

#### Task 1: Extraction script
1. Write `scripts/extract_translations.py` that imports current `TRANSLATIONS` and `COUNTRY_LOCALE_MAP`
2. Run script, verify 7 locale files + 1 country_map file created with correct content
3. Spot-check: `en.json` key count matches `len(TRANSLATIONS["en"])`

#### Task 2: Loader — test for `get_translations`
1. **Write failing test**: `tests/test_i18n.py::test_get_translations_en` — call `get_translations("en")`, assert returns dict with known key `"nav.overview"` = `"Overview"`
2. **Write failing test**: `tests/test_i18n.py::test_get_translations_fallback` — call `get_translations("sl")`, assert keys missing in Slovenian fall back to English values
3. **Write failing test**: `tests/test_i18n.py::test_get_translations_unknown_lang` — call `get_translations("xx")`, assert returns English translations
4. **Implement**: Rewrite `src/i18n.py` as JSON loader
5. **Verify**: All three tests pass

#### Task 3: Loader — test for `get_locale_for_country`
1. **Write failing test**: `tests/test_i18n.py::test_get_locale_for_country_known` — assert `get_locale_for_country("SI")` == `"sl"`
2. **Write failing test**: `tests/test_i18n.py::test_get_locale_for_country_unknown` — assert `get_locale_for_country("ZZ")` == `"en"`
3. **Verify**: Tests pass with the rewritten loader

#### Task 4: Key parity test
1. **Write test**: `tests/test_i18n_parity.py::test_all_locales_have_same_keys` — load all JSON files, assert key sets identical to `en.json`
2. **Verify**: Test passes

#### Task 5: Line count and cleanup
1. Assert `src/i18n.py` is under 100 lines
2. Verify `src/html_report.py` works without changes (import still resolves, translations render)

## Requirement Coverage Matrix

| PRD Requirement | Spec Section | Test Coverage |
|---|---|---|
| R1: Flat JSON files with dot-notation keys | Key Components — locale files | Task 4: parity test validates structure |
| R2: One JSON file per language | Phase 1 extraction | Task 1: verify 7 files created |
| R3: i18n.py < 100 lines | Phase 4 cleanup | Task 5: line count check |
| R4: Existing API preserved | API Contracts | Tasks 2-3: get_translations + get_locale_for_country tests |
| R5: Missing-key fallback to English | Key Components — get_translations | Task 2: test_get_translations_fallback |
| R6: Key parity via pytest | Phase 3 | Task 4: test_all_locales_have_same_keys |
| R7: Locale files at src/locales/ | System Context | Task 1: extraction writes to src/locales/ |
| R8: Keys grouped by prefix | Key Components — locale files | Task 1: extraction preserves insertion order from source |
| R9: COUNTRY_LOCALE_MAP externalized | Key Components — country_map.json | Task 3: get_locale_for_country tests |
| R10: Automated extraction script | Phase 1 | Task 1 |
| R11: No Dockerfile changes | System Context | Manual: verify no Dockerfile edits needed |

## Acceptance Criteria Verification

| Criterion | Verification |
|---|---|
| AC1: src/i18n.py under 100 lines | Automated: `wc -l src/i18n.py` in Task 5 |
| AC2: All 7 locale files exist with identical key sets | Automated: `test_all_locales_have_same_keys` (Task 4) |
| AC3: All pages render correctly in all languages | Manual: run app, switch languages, verify no broken strings |
| AC4: Pytest validates key parity | Automated: Task 4 test |
| AC5: No new dependencies | Manual: verify no additions to requirements.txt; only stdlib `json` and `pathlib` used |

## Dependencies

- None. Uses only Python stdlib (`json`, `pathlib`).

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Extraction script misses keys or mangles Unicode | High | Low | Script reads directly from Python dict (no regex parsing); `ensure_ascii=False` preserves Unicode; parity test catches missing keys |
| JSON key ordering differs from source grouping | Low | Medium | Use Python 3.7+ dict ordering guarantee; extraction script iterates in insertion order |
| Import-time file read fails in Docker | High | Very Low | `src/locales/` is inside `src/` which is already `COPY`-ed; add a smoke test that imports `i18n` |

## Architecture Decision Records

All technical decisions were made during PRD brainstorming and are recorded in the PRD's Decisions Log. No additional architecture decisions are needed — the scope is narrow (file format, directory layout, loading strategy, key validation timing all pre-decided).

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
| File format | Flat JSON | No extra dependency, stdlib support, translation-tool compatible | 2026-05-21 |
| Directory layout | `src/locales/{lang}.json` | Simple, standard i18n convention | 2026-05-21 |
| Key validation | Test-time only (pytest) | No runtime overhead; missing keys fall back to English | 2026-05-21 |
| Loading strategy | Module import time | Deterministic, matches current behavior | 2026-05-21 |
| COUNTRY_LOCALE_MAP | `src/locales/country_map.json` | Full externalization for consistency | 2026-05-21 |
| Migration approach | Automated extraction script | Eliminates copy-paste errors across 7 langs x ~450 keys | 2026-05-21 |
