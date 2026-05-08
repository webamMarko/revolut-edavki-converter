# Test Coverage Audit & Test Plan

**Date:** 2026-05-08
**Branch:** `ui-overhaul`

---

## Part 1: Current Test Coverage Audit

### Existing Test Suite

The project has **E2E tests only** (Playwright-based), located in `tests/e2e/`. There are **no unit tests** or integration tests for the backend calculation logic.

| File | Tests | Coverage Area |
|------|-------|---------------|
| `test_desktop_auth.py` | 8 | Login, logout, guest access, authenticated access |
| `test_desktop_import.py` | 6 | Upload page, import wizard (3-step flow) |
| `test_desktop_report.py` | 21 | Report navigation, range buttons, theme, asset filter, positions, transactions, tax year selector, gains/heatmap, page persistence |
| `test_desktop_admin.py` | 5 | Admin page load, user table, create user, duplicate user, access control |
| `test_desktop_notes.py` | 7 | Notes CRUD (create, expand, edit, delete), modal open/close, validation |
| `test_mobile_auth.py` | 2 | Mobile login, guest home |
| `test_mobile_import.py` | 2 | Mobile import wizard layout, full flow |
| `test_mobile_report.py` | 14 | Mobile layout, theme, navigation, swipe, filters, responsive elements |
| **Total** | **65 E2E tests** | |

### Infrastructure

- **Framework:** pytest + pytest-playwright
- **Fixtures:** Session-scoped server (real HTTP server in daemon thread), temp data directory, bootstrapped admin/premium users, imported test data from `examples/` CSVs
- **Dependencies:** `requirements-test.txt` — pytest>=7.0, playwright>=1.40, pytest-playwright>=0.4

### What IS Covered

- Web UI rendering and navigation (desktop + mobile)
- Authentication flows (login, logout, guest restrictions)
- Import wizard (file upload, preview, column mapping, full import)
- Report pages (summary, charts, positions, tax, history, notes)
- Theme toggle and persistence
- Asset class filter toggles
- Admin user management
- Notes CRUD

### What is NOT Covered (Gaps)

| Gap | Risk | Priority |
|-----|------|----------|
| **FIFO cost basis calculation** | Incorrect tax liability | Critical |
| **Tax computation logic** (`tax.py`) | Legal/financial errors | Critical |
| **FX rate conversion** | Wrong EUR amounts | Critical |
| **Tax-loss harvesting candidates** (`tax.py:576-638`) | Bad optimizer recommendations | High |
| **Dividend data query** (`html_report.py:160-218`) | Wrong dividend calendar/totals | High |
| **Broker import parsing** — all 5 formats | Silent data corruption | Critical |
| **Date normalization** (`importer.py:97-115`) | Wrong dates, mismatched records | High |
| **Amount parsing** (`_parse_amount`, `_parse_eur_amount`, `_parse_eu_number`) | Wrong financial amounts | High |
| **Savings CSV multi-section parsing** | Broken EUR/GBP section import | High |
| **Stock split handling** | Wrong share counts and cost basis | High |
| **Deduplication** (file hash + row hash) | Duplicate or lost transactions | Medium |
| **Tax regime system** (`tax_regimes.py`) | Wrong rates for non-SI countries | Medium |
| **Standardized costs calculation** | Incorrect tax base reduction | Medium |
| **Analytics engine** (`analytics.py`) | Wrong portfolio metrics | Medium |
| **eDavki XML generation** (`edavki_generator.py`) | Invalid tax filing | Critical |

---

## Part 2: Test Plan

### 2.1 Unit Tests — Tax Optimizer (Tax-Loss Harvesting)

**Module:** `src/tax.py` lines 576-638
**Test file:** `tests/unit/test_tax_optimizer.py`

| # | Test Case | Input | Expected Output |
|---|-----------|-------|-----------------|
| 1 | Identifies position with unrealized loss | Position: cost=1000 EUR, market=800 EUR, rate=25% | Candidate with loss=-200, saving=50 EUR |
| 2 | Excludes positions with gains | Position: cost=500, market=700 | No candidate generated |
| 3 | Excludes trivial losses (<0.01 EUR saving) | Position: cost=100, market=99.99, rate=25% | Filtered out (saving=0.0025 < 0.01) |
| 4 | Sorts by potential saving descending | 3 positions with savings 10, 50, 25 EUR | Order: [50, 25, 10] |
| 5 | Correct tax rate per asset class | stock@2yr=20%, cfd@any=40%, crypto@5yr=15% | Rate matches regime |
| 6 | Holding years calculated correctly | Buy 2024-01-01, eval 2026-01-01 | ~2.0 years |
| 7 | Multiple lots for same ticker | 2 buys at different prices, partial loss | Weighted average cost basis |
| 8 | Zero quantity position excluded | Position with qty=0 | Not included |

### 2.2 Unit Tests — Dividend Calendar

**Module:** `src/html_report.py` lines 160-218
**Test file:** `tests/unit/test_dividend_calendar.py`

| # | Test Case | Input | Expected Output |
|---|-----------|-------|-----------------|
| 1 | Aggregates dividends by ticker | AAPL: 3 payments of 10 EUR | `by_ticker: [{ticker: "AAPL", total_eur: 30, count: 3}]` |
| 2 | Aggregates dividends by month | Jan: 20, Feb: 30 | `by_month: [{month: "2025-01", total_eur: 20}, ...]` |
| 3 | Computes TTM (trailing 12 months) | Payments across 18 months | Only last 365 days included per ticker |
| 4 | FX conversion applied | USD dividend=10, fx_rate=1.1 | total_eur = 10/1.1 = 9.09 |
| 5 | EUR dividends bypass FX | EUR dividend=10, fx_rate=0 | total_eur = 10 (no conversion) |
| 6 | Includes all income types | DIVIDEND + INTEREST PAID + STAKING REWARD | All aggregated together |
| 7 | Empty portfolio returns zeros | No transactions | `{by_ticker: [], by_month: [], total_eur: 0, ttm_by_ticker: {}}` |
| 8 | Grand total matches sum of tickers | Multiple tickers with dividends | total_eur == sum of all by_ticker totals |

### 2.3 Unit Tests — Broker Imports

**Module:** `src/importer.py`
**Test file:** `tests/unit/test_broker_imports.py`

#### 2.3.1 Asset Class Detection (`_detect_asset_class`)

| # | Test Case | Columns Present | Expected |
|---|-----------|-----------------|----------|
| 1 | Detect Revolut stocks | Ticker, Price per share, Type, Date | "stock" |
| 2 | Detect CFDs | Symbol, Margin, Type | "cfd" |
| 3 | Detect crypto | Symbol, Value (no Margin, no Ticker) | "crypto" |
| 4 | Detect savings | Description with "Class" (no Symbol/Ticker) | "savings" |
| 5 | Detect Ilirika | FinancialInstrument, TransactionTypeName | "ilirika" |

#### 2.3.2 Revolut Stock Import

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Standard BUY | `Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate` | Correct row inserted with all fields |
| 2 | SELL transaction | Type=SELL, Quantity=5, Price=100 | Negative total_amount, type=SELL |
| 3 | DIVIDEND transaction | Type=DIVIDEND | type=DIVIDEND, no quantity |
| 4 | STOCK SPLIT | Type=STOCK SPLIT, Quantity=+300 | type=STOCK SPLIT with delta quantity |
| 5 | Old format (Started Date) | `Started Date` instead of `Date` | Parsed correctly |
| 6 | Currency prefix in amounts | "USD 32.50" | Parsed as 32.50 |

#### 2.3.3 IBKR / Trading 212 / DEGIRO Import (via mapped import)

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Mapped import with explicit column mapping | Custom CSV + column_map dict | Correct field mapping |
| 2 | Missing required columns | column_map missing 'date' | ImportError raised |
| 3 | Asset class override | stock CSV imported as "stock" | asset_class field correct |

#### 2.3.4 CFD Import

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Standard CFD trade | Symbol="EUR/USD:CFD", Type=BUY | Ticker="EUR/USD" (stripped), asset_class="cfd" |
| 2 | CFD close (SELL) | Type=SELL | Correct sign on amount |
| 3 | Margin field stored | Margin=100 | margin field populated |

#### 2.3.5 Crypto Import

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Crypto BUY | Symbol=BTC, Type=Buy | type=BUY, asset_class="crypto" |
| 2 | Staking reward | Type="Staking reward" | type=STAKING REWARD, zero cost |
| 3 | Learn reward | Type="Learn reward" | type=LEARN REWARD |
| 4 | Payment (=sell) | Type=Payment | type=PAYMENT |
| 5 | Narrow no-break space in date | "Feb 21, 2020, 9:00:16 AM" | Parsed correctly |

#### 2.3.6 Savings Import

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | USD section standard parsing | BUY in USD section | Correct value, quantity, price |
| 2 | EUR section column shift | EUR section row | "Value, USD" col used as EUR value |
| 3 | GBP section parsing | GBP section row | "Value, USD" used as GBP value |
| 4 | Interest PAID → dividend | Type from description | type=INTEREST PAID |
| 5 | ISIN extraction | "BUY USD Class R IE000H9J0QX4" | isin="IE000H9J0QX4" |
| 6 | Interest Reinvested offset | Reinvested row | Does not double-count invested |

#### 2.3.7 Ilirika Import

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Bloomberg ticker conversion | "ASTR US" | ticker="ASTR", currency="USD" |
| 2 | European exchange suffix | "SX5EEX GY" | ticker="EXW1.DE", currency="EUR" |
| 3 | Stock split (OLD + new rows) | "ASTR US OLD" (-80) + "ASTR US" (+5) | Net delta = -75 |
| 4 | MERGER CASH | Price = total payout | Correct total (not per-share) |

#### 2.3.8 Deduplication

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Same file imported twice | Same CSV file | Second import: 0 new rows |
| 2 | Same rows different file | Same data, different filename | Row-level dedup via hash |
| 3 | Different rows same file hash (edge) | Modified content | New rows inserted |

### 2.4 Unit Tests — Financial Calculations

**Module:** `src/tax.py`, `src/analytics.py`, `src/edavki_generator.py`
**Test file:** `tests/unit/test_financial_calculations.py`

#### 2.4.1 FIFO Cost Basis

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Simple FIFO: buy then sell | Buy 10@100, Sell 5 | Cost basis = 5 * 100 = 500 |
| 2 | Multiple lots FIFO | Buy 5@100, Buy 5@120, Sell 7 | Cost = 5*100 + 2*120 = 740 |
| 3 | Full position close | Buy 10@100, Sell 10 | Cost = 1000, position empty |
| 4 | Stock split adjusts lots | Buy 10@100, Split 3:1, Sell 15 | Cost = 5*33.33 = 166.67 (original 5 shares) |
| 5 | Partial sell across years | Buy 2023, Sell partial 2024, Sell rest 2025 | Each year's cost basis correct |
| 6 | Multiple tickers independent | Buy AAPL+MSFT, Sell AAPL | MSFT lots unchanged |

#### 2.4.2 FX Conversion

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | USD to EUR at trade FX rate | Amount=100 USD, FX rate=1.10 | EUR = 100/1.10 = 90.91 |
| 2 | EUR transaction (no conversion) | Amount=100 EUR, currency=EUR | EUR = 100 |
| 3 | Missing FX rate fallback | FX rate=0 or NULL | Uses fallback (1.10 or last known) |
| 4 | GBP conversion | Amount=100 GBP, FX to EUR | Correct cross-rate |

#### 2.4.3 Capital Gains Tax (Slovenian Regime)

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Holding <5 years → 25% | Buy 2024-01, Sell 2024-06, gain=1000 | Tax = 250 EUR |
| 2 | Holding 5-10 years → 20% | Held 6 years, gain=1000 | Tax = 200 EUR |
| 3 | Holding 10-15 years → 15% | Held 12 years, gain=1000 | Tax = 150 EUR |
| 4 | Holding 15-20 years → 10% | Held 16 years, gain=1000 | Tax = 100 EUR |
| 5 | Holding 20+ years → 0% | Held 21 years, gain=1000 | Tax = 0 EUR |
| 6 | CFD flat rate | Any holding period, gain=1000 | Tax = 400 EUR (40%) |
| 7 | Loss netting within class | Gains=500, Losses=-300 | Net=200, tax on 200 only |
| 8 | Standardized costs deduction | Cost=1000, Proceeds=1500, rate=1% | Std cost = 25, taxable gain reduced |
| 9 | Crypto threshold exemption | SI regime, crypto gains < 5000 | Exempt from tax |

#### 2.4.4 Tax Report Integrity

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Total tax = sum of netted buckets | Multiple sales across rate buckets | total_realized_tax_eur matches |
| 2 | Dividends counted separately | Dividend income in year | total_dividends_eur correct |
| 3 | Fees accumulated | Commission fees in transactions | total_fees_eur matches sum |
| 4 | Scope filter works | scope="stock" with mixed data | Only stock transactions in report |
| 5 | Year filter works | Sales in 2024 and 2025, year=2024 | Only 2024 sales included |

### 2.5 Unit Tests — Date and Amount Parsing

**Test file:** `tests/unit/test_parsing.py`

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | ISO date | "2024-03-15" | "2024-03-15" |
| 2 | Revolut format | "Apr 1, 2026, 12:24:31 PM" | "2026-04-01" |
| 3 | Narrow no-break space | "Feb 21, 2020, 9:00:16 AM" | "2020-02-21" |
| 4 | European number (comma decimal) | "13,04" | 13.04 |
| 5 | Currency prefix | "USD 32.50" | 32.50 |
| 6 | Euro symbol | "€8,636.57" | 8636.57 |
| 7 | PLN suffix | "1.30 PLN" | 1.30 |
| 8 | Negative amount | "-USD 50" | -50.0 |

### 2.6 Integration Tests — End-to-End Pipeline

**Test file:** `tests/integration/test_pipeline.py`

| # | Test Case | Description | Verification |
|---|-----------|-------------|--------------|
| 1 | Stock CSV → import → tax report | Import `sample_transactions.csv`, compute tax | Tax amounts match expected values |
| 2 | Crypto CSV → import → tax report | Import `crypto.csv`, compute tax | Staking rewards counted, FIFO correct |
| 3 | CFD CSV → import → tax report | Import `cfds.csv`, compute tax | 40% rate applied, margin handled |
| 4 | Savings CSV → import → dividends | Import `savings.csv`, query dividends | Interest income aggregated correctly |
| 5 | Multi-broker combined | Import all 4 CSVs, scope=all | Prefixed tickers, no collisions |
| 6 | Report generation with all data | Import all → generate HTML report | No template errors, all sections render |
| 7 | eDavki XML generation | Import stocks → convert to XML | Valid against XSD schema, correct structure |

### 2.7 Regression Tests — Known-Good Outputs

**Test file:** `tests/regression/test_known_outputs.py`

| # | Test Case | Fixture | Assertion |
|---|-----------|---------|-----------|
| 1 | Stock tax for 2024 | `sample_transactions.csv` | total_realized_gain_eur == X.XX (pin after first run) |
| 2 | Dividend total | `sample_transactions.csv` | total_dividends_eur == X.XX |
| 3 | CFD tax (40% flat) | `cfds.csv` | total_tax matches expected |
| 4 | Portfolio value | All CSVs imported + synced | portfolio_value_eur within tolerance |

---

## Part 3: Implementation Priority

### Phase 1 (Critical — immediate)
1. `tests/unit/test_financial_calculations.py` — FIFO, FX, tax rates
2. `tests/unit/test_broker_imports.py` — all 5 broker parsers
3. `tests/unit/test_parsing.py` — date/amount normalization

### Phase 2 (High — next sprint)
4. `tests/unit/test_tax_optimizer.py` — tax-loss harvesting logic
5. `tests/unit/test_dividend_calendar.py` — dividend data query
6. `tests/integration/test_pipeline.py` — end-to-end flows

### Phase 3 (Medium — hardening)
7. `tests/regression/test_known_outputs.py` — pin known-good values
8. Extend E2E tests for tax optimizer UI and dividend calendar UI sections

---

## Part 4: Test Infrastructure Needs

- **pytest fixtures:** In-memory SQLite DB pre-loaded with synthetic transactions
- **Synthetic test data:** Small, predictable datasets with known outcomes (avoid real user data)
- **Marker tags:** `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`
- **CI integration:** `python -m pytest tests/unit tests/integration` (fast), E2E separate

---

## Appendix: Test File Structure

```
tests/
  conftest.py              # shared fixtures (DB setup, synthetic data)
  unit/
    __init__.py
    test_parsing.py
    test_broker_imports.py
    test_financial_calculations.py
    test_tax_optimizer.py
    test_dividend_calendar.py
  integration/
    __init__.py
    test_pipeline.py
  regression/
    __init__.py
    test_known_outputs.py
  e2e/                     # existing Playwright tests
    conftest.py
    test_desktop_auth.py
    test_desktop_import.py
    test_desktop_report.py
    test_desktop_admin.py
    test_desktop_notes.py
    test_mobile_auth.py
    test_mobile_import.py
    test_mobile_report.py
```
