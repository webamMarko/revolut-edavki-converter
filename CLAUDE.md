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

# Run Playwright E2E tests (requires a running server on port 8080)
pip install -r requirements-test.txt
playwright install chromium
python -m pytest tests/e2e/ -v               # all tests (desktop + mobile)
python -m pytest tests/e2e/test_desktop_auth.py -v  # auth flow only
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
- **resend**: Email delivery for invite flows

## Docker Deployment

### Deploy script

```bash
./scripts/deploy.sh           # full deploy (code + databases)
./scripts/deploy.sh --skip-db # code-only update, skip DB copy
```

The script (`scripts/deploy.sh`) does the following:
1. Creates a tarball of the project (excluding `.git`, `data/`, `venv/`, `.env`)
2. Uploads via `scp` to `homeassistant@192.168.4.213`
3. Extracts into `/home/homeassistant/revolut-edavki-converter`
4. Copies `data/marko/portfolio.db`, `data/_demo/portfolio.db`, `data/_system/users.db` (unless `--skip-db`)
5. Creates `.env` from `.env.example` if missing (sets `APP_BASE_URL` to the server IP)
6. Runs `sudo docker build` on the server, then `sudo docker run` (removes old container first)
7. Reports running container status

Requires `sshpass` locally. Uses password auth (`homeassistant@192.168.4.213`).

### Server layout

| Path | Purpose |
|------|---------|
| `/home/homeassistant/revolut-edavki-converter/` | App source + Dockerfile |
| `/home/homeassistant/revolut-edavki-converter/data/` | Volume-mounted data directory |
| `data/_demo/portfolio.db` | Read-only demo DB for unauthenticated visitors |
| `data/_system/users.db` | User registry (roles, password hashes, invite tokens) |
| `data/{username}/portfolio.db` | Per-user isolated portfolio DB |
| `/home/homeassistant/portfolio-sync.log` | Cron sync output log |

### Cron job (on server)

```
15 22 * * 1-5 docker exec portfolio python -m src.cli sync >> /home/homeassistant/portfolio-sync.log 2>&1
```

Runs 15 minutes after NYSE close (22:15 Ljubljana/CEST). Adjust to 21:15 in winter (CET).

### Multi-user auth

- **Session cookies**: `HttpOnly`, `SameSite=Lax`, 7-day TTL, `secrets.token_urlsafe(32)`
- **Passwords**: PBKDF2-HMAC-SHA256, 260k iterations, per-user salt
- **Roles**: `guest` (demo only), `premium` (own DB), `admin` (own DB + user management)
- **Invite flow**: admin creates user → Resend API sends invite email with token → user sets password
- **Data isolation**: `_portfolio_conn(session)` returns demo DB for guests, user DB for premium/admin
- **`src/web.py`**: `_get_session()`, `_create_session()`, `_require_role()`, `_portfolio_conn()`
- **`src/users.py`**: `authenticate()`, `create_user()`, `accept_invite()`, `set_role()`
