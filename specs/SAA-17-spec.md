# Technical Specification: Add Interactive Brokers CSV/Flex Import Support

**Epic:** SAA-17
**Issue:** SAA-17
**PRD:** See issue document: prd
**Created:** 2026-05-24
**Status:** Ready for Review
**Confidence:** 92%

## Overview

This epic adds full Interactive Brokers import support (CSV Activity Statements and Flex Query XML) while refactoring the import layer into a plugin-style broker adapter architecture. The work is phased: (1) plugin refactor with new DB schema, (2) IBKR CSV enhancement with corporate actions/multi-currency/commissions, (3) Flex XML parser.

The existing `importer.py` (1155 lines) contains 8 inline broker parsers. This refactor extracts each into a dedicated module under `src/parsers/` with a common `BrokerAdapter` interface. A new DB schema adds `commission`, `withholding_tax`, and `broker_source` columns. The FX rates table is redesigned for multi-currency support.

## Architecture

### System Context

```
CSV/XML file upload
       |
       v
  Two-stage format detection:
    1. File extension (.xml -> XML adapters, .csv -> CSV adapters)
    2. Content sniffing (CSV headers via DataFrame, XML root element)
       |
       v
  BrokerAdapter.parse(file) -> list[ParsedTrade]
       |
       v
  Importer: validate, deduplicate, insert into DB
       |
       v
  Analytics/Tax pipelines (modified for multi-currency FX at reporting time)
```

### Key Components

#### `src/parsers/base.py` -- Adapter Interface and Data Model

- `ParsedTrade` dataclass with fields: date, ticker, type (BUY/SELL/DIVIDEND/SPLIT/MERGER_OUT/MERGER_IN/SPINOFF/RIGHTS_ISSUE/FEE), quantity, price_per_share, total_amount, currency, fx_rate, asset_class, commission (NEW), withholding_tax (NEW), broker_source (NEW), correlation_id (NEW, for linked rows like mergers), raw_row

- `CsvAdapter` ABC:
  - `detect(df: DataFrame) -> bool` -- abstract
  - `parse(file_path: str) -> list[ParsedTrade]` -- abstract
  - `broker_name` property -- abstract

- `XmlAdapter` ABC:
  - `detect(root_tag: str, namespaces: dict) -> bool` -- abstract
  - `parse(file_path: str) -> list[ParsedTrade]` -- abstract
  - `broker_name` property -- abstract

Two separate base classes. Registry holds both lists and dispatches based on file type.

#### `src/parsers/registry.py` -- Two-Stage Auto-Discovery

- `BrokerRegistry` class with `register()` and `detect_and_parse(file_path)` methods
- Two-stage detection: check file extension first (.xml vs .csv), then content-sniff
- For CSV: read headers into DataFrame, call adapter.detect_csv(df)
- For XML: parse root element, call adapter.detect_xml(root_tag, ns)
- Raises `UnknownFormatError` if no adapter matches

#### Broker Parser Modules

- `src/parsers/revolut_stock.py` -- extracted from `_parse_stock_row`
- `src/parsers/revolut_cfd.py` -- extracted from `_parse_cfd_row`
- `src/parsers/revolut_crypto.py` -- extracted from `_parse_crypto_row`
- `src/parsers/revolut_savings.py` -- extracted from `_parse_savings_row`
- `src/parsers/ilirika.py` -- extracted from `_parse_ilirika_row`
- `src/parsers/ibkr.py` -- enhanced from `_parse_ibkr_row` + corporate actions
- `src/parsers/trading212.py` -- extracted from `_parse_trading212_row`
- `src/parsers/degiro.py` -- extracted from `_parse_degiro_row`
- `src/parsers/ibkr_flex.py` -- NEW: Flex Query XML parser

#### `src/parsers/utils.py` -- Shared Parsing Utilities

Extracted from importer.py: `_parse_amount`, `normalize_date`, `_file_hash`, `_row_hash`, `_parse_eur_amount`. All adapters import from here.

#### `src/importer.py` -- Simplified Orchestrator

Reduced from 1155 lines to ~200 lines. Delegates parsing to registry, handles deduplication and DB insertion.

### Data Model

#### Modified `transactions` table

```sql
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    ticker          TEXT,
    type            TEXT NOT NULL,  -- BUY, SELL, DIVIDEND, SPLIT, MERGER_OUT, MERGER_IN, SPINOFF, RIGHTS_ISSUE, FEE
    quantity        REAL,
    price_per_share REAL,
    total_amount    REAL,
    currency        TEXT NOT NULL,
    fx_rate         REAL NOT NULL DEFAULT 1.0,
    asset_class     TEXT NOT NULL DEFAULT 'stock',
    commission      REAL,              -- NEW
    withholding_tax REAL,              -- NEW
    broker_source   TEXT,              -- NEW: revolut, ibkr, ilirika, etc.
    correlation_id  TEXT,              -- NEW: links related rows (e.g. MERGER_OUT + MERGER_IN pair)
    source_file     TEXT,
    imported_at     TEXT NOT NULL DEFAULT (datetime('now')),
    row_hash        TEXT UNIQUE
);
```

Schema version bumped to 11. Clean break: users must `rm portfolio.db` and re-import.

#### Redesigned `fx_rates` table

```sql
CREATE TABLE IF NOT EXISTS fx_rates (
    date          TEXT NOT NULL,
    from_currency TEXT NOT NULL,
    to_currency   TEXT NOT NULL,
    rate          REAL NOT NULL,
    PRIMARY KEY (date, from_currency, to_currency)
);
```

Replaces the old `fx_rates (date, eur_usd)` table. The `price_fetcher.py` sync command updated to fetch rates for all currencies found in the transactions table.

### API Contracts

No new API endpoints. Existing upload endpoint in `web.py` calls `import_csv()` which now delegates to `BrokerRegistry.detect_and_parse()`.

Import result enhanced with `skipped_types: list[str]` for unsupported transaction warnings.

## Implementation Plan

### Phase 1: Plugin Architecture Refactor

#### TDD Tasks

1. Test `ParsedTrade` dataclass -- verify all fields, defaults, validation
2. Test `BrokerAdapter` interface -- verify abstract methods enforced, detect_xml default
3. Test `BrokerRegistry` -- register, two-stage detect (CSV + XML), parse delegation, UnknownFormatError
4. Extract `revolut_stock.py` -- test parity with existing `_parse_stock_row`
5. Extract `revolut_cfd.py` -- test parity
6. Extract `revolut_crypto.py` -- test parity
7. Extract `revolut_savings.py` -- test parity
8. Extract `ilirika.py` -- test parity (including `_preprocess_ilirika_splits`preprocessing)
9. Extract `ibkr.py` (current functionality) -- test parity
10. Extract `trading212.py` -- test parity
11. Extract `degiro.py` -- test parity
12. Refactor `importer.py` -- use registry, add new DB columns
13. DB schema migration -- version 11, new columns, redesigned fx_rates
14. Update `price_fetcher.py` -- multi-currency FX rate fetching
15. Integration test -- import existing test CSVs through new pipeline, verify identical results

## Architecture Decision Records

### ADR-1: Two-Stage Format Detection
**Context:** The BrokerAdapter interface needs to handle both CSV and XML files. The existing _detect_asset_class reads a pandas DataFrame, but Flex XML is not a CSV.
**Decision:** Two-stage detection: (1) check file extension (.xml vs .csv), (2) for CSVs read headers into DataFrame and call adapter.detect_csv(df), for XML parse root element and call adapter.detect_xml(root_tag, ns).
**Rationale:** Simple, handles both formats cleanly without forcing XML adapters to implement CSV detection or vice versa.
**Consequences:** BrokerAdapter base class has detect_csv (abstract) and detect_xml (default False). XML-only adapters still need a no-op detect_csv. Consider making both optional with at least one required.

### ADR-2: Generic FX Rates Table
**Context:** The fx_rates table only stores EUR/USD. Multi-currency IB accounts need EUR/GBP, EUR/CHF, etc.
**Decision:** Replace fx_rates (date, eur_usd) with fx_rates (date, from_currency, to_currency, rate) as a generic currency pair table.
**Rationale:** Flexible for any currency pair. No schema changes needed when adding new currencies. price_fetcher.py auto-detects needed pairs from transactions table.
**Consequences:** Existing code querying fx_rates.eur_usd must be updated. All FX lookups become SELECT rate FROM fx_rates WHERE date=? AND from_currency=? AND to_currency=?. Sync command must discover all unique currencies in transactions and fetch rates for each.

### ADR-3: Explicit Corporate Action Types
**Context:** IB exports include mergers, spinoffs, and rights issues. The current type system has BUY, SELL, DIVIDEND, SPLIT.
**Decision:** Add new transaction types: MERGER, SPINOFF, RIGHTS_ISSUE as first-class types.
**Rationale:** Each corporate action has distinct tax treatment in Slovenian tax law. Explicit types make analytics.py and tax.py handling clear and auditable.
**Consequences:** analytics.py and tax.py need new branches for each type. The type column values expand. UI may need to display these action types in transaction lists.

### ADR-4: Shared Utilities in src/parsers/utils.py
**Context:** After extracting broker parsers to separate modules, shared helpers (_parse_amount, normalize_date, etc.) need a home.
**Decision:** Create `src/parsers/utils.py` as a dedicated utilities module.
**Rationale:** Clean separation, no circular dependency risk (adapters import utils, importer imports registry). All adapters have a single import path for shared functionality.
**Consequences:** Minor refactor to move ~5 utility functions. Import paths change but functionality is identical.

### ADR-5: Merger as Two Linked Rows (MERGER_OUT + MERGER_IN)
**Context:** A merger converts shares of company A into shares of company B at a ratio. Need to model this in the single-ticker-per-row transactions table.
**Decision:** Two rows linked by a `correlation_id` field: MERGER_OUT (removes old ticker) and MERGER_IN (adds new ticker).
**Rationale:** Clear audit trail. Each row has exactly one ticker. Tax calculation can trace the cost basis from old to new shares via correlation_id. Same pattern can be reused for spinoffs.
**Consequences:** New `correlation_id` TEXT column in transactions table. Analytics/tax code must follow correlation_id links when computing cost basis for merger targets. SPINOFF can use the same pattern (SPINOFF_OUT + SPINOFF_IN).

### ADR-6: Separate CsvAdapter and XmlAdapter Base Classes
**Context:** ADR-1 noted XML-only adapters awkwardly need a no-op detect_csv. Need cleaner separation.
**Decision:** Two separate abstract base classes: `CsvAdapter` (with detect(df) + parse) and `XmlAdapter` (with detect(root_tag, ns) + parse). Registry holds both lists.
**Rationale:** Most explicit type separation. Each adapter class only implements what it needs. No awkward no-ops. Registry dispatches by file type: .csv -> try CsvAdapters, .xml -> try XmlAdapters.
**Consequences:** Slightly more classes but cleaner contract. `ibkr_flex.py` extends XmlAdapter, all others extend CsvAdapter. If a future broker has both CSV and XML, it would be two separate adapter classes (acceptable).

### ADR-7: yfinance for Multi-Currency FX Rates
**Context:** Multi-currency support needs FX rates beyond EUR/USD (e.g. EUR/GBP, EUR/CHF).
**Decision:** Use yfinance currency pair tickers (e.g. GBPEUR=X) via the existing sync mechanism.
**Rationale:** Already a dependency, same code path as stock price fetching. No new dependency or API integration needed. Supports all major currency pairs.
**Consequences:** price_fetcher.py discovers unique currencies in transactions, fetches the corresponding yfinance pair. If yfinance is unavailable for a pair, warn and skip.

### ADR-8: Spinoff as Two Linked Rows (SPINOFF_OUT + SPINOFF_IN)
**Context:** Spinoffs create new company shares from an existing holding. Need to model cost basis allocation.
**Decision:** Use the same two-linked-rows pattern as mergers: SPINOFF_OUT (reduces parent quantity/cost basis) + SPINOFF_IN (adds new ticker) linked by correlation_id.
**Rationale:** Consistent with merger pattern. Tax code can use the same correlation_id logic to trace cost basis. Slovenian tax law requires cost basis to be split proportionally.
**Consequences:** Tax calculation must implement proportional cost basis splitting for SPINOFF pairs. Type values: SPINOFF_OUT, SPINOFF_IN added to the type enum.

### ADR-9: Synthetic Test Fixtures
**Context:** TDD tasks need sample IB CSV and Flex XML data for testing.
**Decision:** Hand-craft minimal synthetic test fixtures committed to the tests/ directory.
**Rationale:** No PII concerns, predictable and reproducible results, minimal file size, each fixture exercises a specific transaction type. Easy to maintain and extend.
**Consequences:** Test fixtures live in tests/fixtures/ibkr/ (CSV) and tests/fixtures/ibkr_flex/ (XML). Each file targets a specific scenario (trades, dividends, mergers, etc.).
