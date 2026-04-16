# Revolut to eDavki Converter & Portfolio Analytics

A Python tool that converts Revolut transaction exports into eDavki-compliant XML for Slovenian tax reporting, and provides portfolio analytics with interactive HTML reports.

## Features

- **eDavki XML generation** from Revolut CSV/Excel exports (Doh_KDVP format)
- **Portfolio analytics** with daily granularity — value tracking, CAGR, TWR, max drawdown, benchmark comparison
- **Slovenian capital gains tax** computation with holding-period-based rates and FIFO matching
- **Interactive HTML reports** with Chart.js charts, drag-to-zoom, and asset class filtering
- **Four asset classes**: stocks, CFDs, crypto, and savings accounts — auto-detected on import
- Filter by date range, currency, asset class scope

## Installation

```bash
git clone <repo-url>
cd revolut-edavki-converter
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### eDavki XML Conversion

Convert a Revolut stock trading export to eDavki XML:

```bash
python -m src.cli convert transactions.csv output.xml --year 2025
python -m src.cli convert transactions.csv output.xml --year 2025 --start-date 2025-01-01 --end-date 2025-12-31
python -m src.cli convert transactions.csv output.xml --year 2025 --currency EUR --completed-only
```

### Portfolio Analytics Workflow

```bash
# 1. Import Revolut exports (auto-detects stock, CFD, crypto, or savings format)
python -m src.cli import stocks.csv cfd.csv crypto.csv savings.csv

# 2. Fetch historical prices and FX rates from Yahoo Finance
python -m src.cli sync

# 3. View analytics in the terminal
python -m src.cli analytics
python -m src.cli analytics --scope stock --chart
python -m src.cli analytics --scope crypto --format json --output analytics.json

# 4. Compute tax liability
python -m src.cli tax --year 2025
python -m src.cli tax --year 2025 --scope cfd --include-unrealized

# 5. Generate interactive HTML report
python -m src.cli report --output report.html
python -m src.cli report --scope savings --output savings.html
python -m src.cli report --year 2025 --output 2025.html

# Check database status
python -m src.cli status
```

### Database

Portfolio data is stored in `~/.revolut-edavki/portfolio.db` (SQLite). Imports are deduplicated by file hash and row uniqueness, so re-running `import` on the same file is safe.

To clear all data and start fresh:

```bash
rm ~/.revolut-edavki/portfolio.db
python -m src.cli import stocks.csv cfd.csv crypto.csv savings.csv
python -m src.cli sync
```

### Asset Class Scopes

Use `--scope` to filter by asset class:

| Scope | Description |
|-------|-------------|
| `stock` | Revolut stock trading (holding-period tax: 25% down to 0%) |
| `cfd` | CFD trading (flat 40% tax rate) |
| `crypto` | Cryptocurrency (holding-period tax, same rates as stocks) |
| `savings` | Savings accounts / money market funds (interest as income) |
| `all` | All asset classes combined (default) |

### HTML Report

The `report` command generates a self-contained HTML file with:

- Summary metrics cards (portfolio value, invested, gains, CAGR, drawdown)
- Interactive portfolio value chart with drag-to-zoom period selection
- Benchmark comparison chart (S&P 500, NASDAQ, Dow Jones, FTSE 100)
- Gains breakdown, positions table, tax summary, transaction history
- **Asset class toggles** (in "all" scope) — click to show/hide asset classes, charts and metrics update live

## Revolut Export Formats

The importer auto-detects the format based on column headers:

| Format | Key Columns | How to Export |
|--------|-------------|---------------|
| **Stocks** | `Ticker`, `Price per share`, `FX Rate` | Revolut app > Stocks > Statements |
| **CFD** | `Symbol`, `Margin` | Revolut app > CFD > Statements |
| **Crypto** | `Symbol`, `Value`, `Type` (Buy/Sell/Staking reward...) | Revolut app > Crypto > Statements |
| **Savings** | `Description` with fund class info (e.g. "BUY USD Class R IE000H9J0QX4") | Revolut app > Savings > Statements |

## Docker Deployment

The app can be deployed as a multi-user web service via Docker.

### First-time deploy

Requirements: `sshpass` installed locally (`brew install sshpass`).

```bash
./scripts/deploy.sh
```

This will:
1. Package the source code and upload it to the server
2. Copy all databases (`data/marko/`, `data/_demo/`, `data/_system/`)
3. Create `.env` from `.env.example` if it doesn't exist
4. Build the Docker image on the server
5. Start (or restart) the `portfolio` container on port **8081**

### Code-only update (skip DB copy)

```bash
./scripts/deploy.sh --skip-db
```

Use this for deploying code changes when databases don't need to be synced.

### Server details

| Setting | Value |
|---------|-------|
| Host | `192.168.4.213` |
| Port | `8081` |
| Container name | `portfolio` |
| Remote path | `/home/homeassistant/revolut-edavki-converter` |
| Data volume | `./data:/data` |

### Automatic price sync

A cron job runs on the server every weekday at **22:15 Ljubljana time** (15 min after NYSE close):

```
15 22 * * 1-5 docker exec portfolio python -m src.cli sync >> /home/homeassistant/portfolio-sync.log 2>&1
```

### Multi-user architecture

- Unauthenticated visitors see a read-only demo portfolio (`data/_demo/portfolio.db`)
- Each registered user has an isolated database at `data/{username}/portfolio.db`
- User registry is stored in `data/_system/users.db`
- Roles: `guest` (demo only), `premium` (own DB), `admin` (own DB + user management)

### Admin tasks

```bash
# Bootstrap first admin user (run locally, then deploy DB)
python scripts/hash_password.py bootstrap admin@example.com mypassword

# Or on the server:
docker exec portfolio python scripts/hash_password.py bootstrap admin@example.com mypassword
```

## Project Structure

```
revolut-edavki-converter/
├── src/
│   ├── cli.py              # Command-line interface (subcommands)
│   ├── revolut_parser.py   # Revolut CSV/Excel parser (eDavki flow)
│   ├── edavki_generator.py # eDavki XML generator with FIFO matching
│   ├── importer.py         # CSV import with auto-detection & deduplication
│   ├── db.py               # SQLite database schema and connection
│   ├── price_fetcher.py    # Yahoo Finance price & FX rate sync
│   ├── analytics.py        # Portfolio analytics engine (daily reconstruction)
│   ├── tax.py              # Slovenian capital gains tax computation
│   ├── formatters.py       # Terminal output formatting
│   ├── html_report.py      # Interactive HTML report generator
│   ├── web.py              # Multi-user HTTP server with auth
│   ├── users.py            # User registry and authentication
│   └── email_service.py    # Resend API email wrapper
├── scripts/
│   ├── deploy.sh           # Remote deployment script
│   └── hash_password.py    # CLI helper for password hashing and user bootstrap
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── examples/               # Sample CSV files
├── requirements.txt
└── README.md
```

## Tax Computation Details

- **Stocks & Crypto**: Slovenian holding-period rates — 25% (0-5y), 20% (5-10y), 15% (10-15y), 10% (15-20y), 0% (20y+)
- **CFDs**: Flat 40% tax rate
- **Savings**: Interest reported as income; capital gains from fund share sales use holding-period rates
- **FIFO matching**: Purchases matched to sales in first-in-first-out order
- **Tax netting**: Gains and losses are netted within each tax rate bucket before applying the rate

## Disclaimer

This tool is provided for convenience and may require adjustments for your specific situation. Always verify generated XML against eDavki requirements before submission. Consult a tax professional if needed.
