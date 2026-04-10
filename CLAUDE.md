# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Converts Revolut stock/CFD trading CSV exports into eDavki Doh_KDVP XML format for Slovenian capital gains tax reporting, and provides portfolio analytics with daily granularity.

Four asset classes: **stocks** (holding-period-based tax: 25%→0%), **CFDs** (flat 40% tax), **crypto** (holding-period tax like stocks), and **savings** (money market funds with interest income). The `--scope stock|cfd|crypto|savings|all` flag filters analytics and tax commands by asset class. In "all" mode, tickers are prefixed (`CFD:`, `CRYPTO:`, `SAVINGS:`) to avoid collisions.

## Commands

```bash
# Install dependencies (use venv)
pip install -r requirements.txt

# eDavki XML conversion (original flow)
python -m src.cli convert input.csv output.xml --year 2023

# Portfolio analytics workflow
python -m src.cli import file.csv [file2.csv ...]     # auto-detects stock/CFD/crypto/savings
python -m src.cli sync                                 # fetch yfinance prices + FX rates
python -m src.cli analytics [--scope stock|cfd|crypto|savings|all] [--chart]
python -m src.cli tax --year 2025 [--scope stock|cfd|crypto|savings|all] [--include-unrealized]
python -m src.cli report [--scope stock|cfd|crypto|savings|all] [--output file.html]
python -m src.cli status

# Run tests (not yet implemented)
python -m pytest tests/
```

## Database

SQLite database at `~/.revolut-edavki/portfolio.db`. Imports are deduplicated by file SHA-256 hash and row-level UNIQUE constraint. To reset: `rm ~/.revolut-edavki/portfolio.db` then re-import and sync.

## Architecture

The pipeline is: **CLI (`cli.py`) -> Parser (`revolut_parser.py`) -> Generator (`edavki_generator.py`) -> XML file**

The analytics pipeline is: **CLI -> Importer (`importer.py`) -> DB (`db.py`) -> Price Fetcher (`price_fetcher.py`) -> Analytics/Tax (`analytics.py`/`tax.py`) -> Formatters (`formatters.py`)**

### Key Concepts

- **RevolutTransaction** (`revolut_parser.py`): Data class wrapping a pandas Series row. Handles both old Revolut format (Type/Product/Started Date/State columns) and new format (Ticker/Quantity/Price per share/FX Rate columns). Amounts may have currency prefixes like "USD 32" that get stripped.

- **FIFO matching** (`edavki_generator.py:_filter_by_sales_in_year_with_fifo`): The most complex logic. For a given tax year, it finds securities with sales in that year, then walks the full transaction history to FIFO-match purchases to sales. Only purchases consumed by target-year sales appear in output. Tracks consumption in original (pre-split) terms using `_quantity_output_orig` and `_split_ratio_final` private attributes set directly on transaction objects.

- **Stock splits**: Handled by adjusting the split ratio on existing FIFO lots. The split transaction's `quantity` field is the absolute change in shares (e.g., +300 means you gained 300 additional shares). The ratio is calculated as `(held + change) / held`.

- **XML schema**: Follows `Doh_KDVP_9.xsd` with `EDP-Common-1.xsd` namespaces. Each ticker becomes a `KDVPItem` containing a `Securities` element with `Row` entries. Purchases use `F1`-`F4` fields, sales use `F6`/`F7`/`F9`. `F8` is running balance. All prices are converted from USD to EUR using the transaction's FX rate.

- **Asset class detection** (`importer.py`): Auto-detects format from column headers. CFD CSVs have `Symbol`+`Margin`; crypto has `Symbol`+`Value` (no `Margin`); savings has `Description` with fund class info (no `Symbol`/`Ticker`); stocks have `Ticker`+`Price per share`. CFD tickers have `:CFD` suffix stripped on import.

- **Crypto** (`analytics.py`, `tax.py`): Long-only FIFO. Types: BUY, SELL, Payment (=sell), Receive (=buy), Staking reward, Learn reward. No yfinance prices — uses `last_known_price_eur` from most recent trade. Rewards added at zero cost, recorded as dividends. Net invested = cumulative buys - cumulative sells.

- **Savings** (`importer.py`): Revolut savings CSV has three concatenated sections (USD, GBP, EUR) with shifted column positions for the EUR section. Description contains type + fund ISIN. Types: BUY (deposit), SELL (withdrawal), Interest PAID (daily, → dividends), Service Fee (→ fees), Interest Reinvested (offsets corresponding BUY in invested tracking).

- **CFD valuation** (`analytics.py`): CFDs have no yfinance prices. Open positions use `last_known_price_eur` from the most recent trade. In "all" scope, non-stock tickers are prefixed (`CFD:`, `CRYPTO:`, `SAVINGS:`) to prevent key collisions.

- **Tax rates** (`tax.py`): Stocks/crypto/savings use holding-period-based Slovenian rates (25%/20%/15%/10%/0%). CFDs use a flat 40% rate (`CFD_TAX_RATE`). Tax netting: gains/losses are netted within each rate bucket before applying the rate.

- **HTML reports** (`html_report.py`): Self-contained HTML with Chart.js + zoom plugin. In "all" scope, per-class analytics are computed and embedded so the asset class toggle buttons can recombine daily series client-side without server round-trips.

### Dependencies

- **pandas**: CSV/Excel parsing
- **lxml**: XML generation
- **openpyxl**: Excel file support
- **yfinance**: Historical stock prices and FX rates
- **tabulate**: Terminal table formatting
- **matplotlib**: Portfolio performance charts
