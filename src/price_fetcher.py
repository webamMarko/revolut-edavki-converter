"""Fetch historical prices from Yahoo Finance via yfinance."""

import sqlite3
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

# Revolut uses bare tickers; yfinance needs exchange suffixes for EU stocks.
TICKER_MAP = {
    "VOW3": "VOW3.DE",
    "RHM": "RHM.DE",
    "SIE": "SIE.DE",
    "ENR1": "ENR.DE",    # Siemens Energy trades as ENR on Xetra (ENR1 is delisted)
    "HAG": "HAG.DE",
    "E3B": "E3B.DE",
    "SDV1": "SDV1.DE",
    "CSF": "CSF.PA",
    "ABJ": "ABBN.SW",   # ABB Ltd — Amsterdam delisted on yfinance, use Swiss listing
    "FLY": "FLY",
    "VWCE": "VWCE.DE",
}

# Benchmark indexes
BENCHMARKS = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
    "^FTSE": "FTSE 100",
    "VWCE.DE": "VWCE",
    "URTH": "MSCI World",
    "EXSA.DE": "STOXX Europe 600",
}

FX_TICKER = "EURUSD=X"
FX_EURCHF = "EURCHF=X"

# Suffixes to try when a bare ticker fails on yfinance
_EXCHANGE_SUFFIXES = [".DE", ".F", ".AS", ".L", ".PA"]


def _yf_ticker(revolut_ticker: str) -> str:
    """Map a Revolut ticker to a yfinance-compatible ticker."""
    return TICKER_MAP.get(revolut_ticker, revolut_ticker)


def _fetch_history(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    """Fetch daily close prices for a single ticker. Returns DataFrame or None on failure."""
    try:
        data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if data is None or data.empty:
            return None
        # yf.download returns MultiIndex columns when single ticker; flatten
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data[["Close"]].rename(columns={"Close": "close"})
    except Exception:
        return None


def _fetch_with_fallback(revolut_ticker: str, start: str, end: str) -> tuple[str, pd.DataFrame | None]:
    """Try the mapped ticker, then fallback suffixes."""
    yf_ticker = _yf_ticker(revolut_ticker)
    df = _fetch_history(yf_ticker, start, end)
    if df is not None and not df.empty:
        return yf_ticker, df

    # If mapped ticker failed and it's the same as the bare ticker, try suffixes
    if yf_ticker == revolut_ticker:
        for suffix in _EXCHANGE_SUFFIXES:
            candidate = revolut_ticker + suffix
            df = _fetch_history(candidate, start, end)
            if df is not None and not df.empty:
                return candidate, df

    return yf_ticker, None


def mark_delisted(conn: sqlite3.Connection, ticker: str) -> None:
    """Flag a ticker as delisted so sync will skip it.

    Checks both the user DB (legacy) and prices DB.
    """
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, 'true')",
        (f"delisted:{ticker}",),
    )
    conn.commit()


def unmark_delisted(conn: sqlite3.Connection, ticker: str) -> None:
    """Remove the delisted flag from a ticker."""
    conn.execute("DELETE FROM metadata WHERE key = ?", (f"delisted:{ticker}",))
    conn.commit()


def get_delisted(conn: sqlite3.Connection, prices_conn: sqlite3.Connection | None = None) -> list[str]:
    """Return list of all tickers marked as delisted (from user DB and shared prices DB)."""
    rows = conn.execute(
        "SELECT key FROM metadata WHERE key LIKE 'delisted:%'"
    ).fetchall()
    result = set(row[0][len("delisted:"):] for row in rows)
    if prices_conn is not None:
        try:
            rows2 = prices_conn.execute(
                "SELECT key FROM metadata WHERE key LIKE 'delisted:%'"
            ).fetchall()
            result.update(row[0][len("delisted:"):] for row in rows2)
        except Exception:
            pass
    return sorted(result)


def _last_price_date(conn: sqlite3.Connection, ticker: str, prices_conn: sqlite3.Connection | None = None) -> str | None:
    """Get the last date we have a price for this ticker (prefers shared prices DB)."""
    target = prices_conn if prices_conn is not None else conn
    row = target.execute(
        "SELECT MAX(date) FROM daily_prices WHERE ticker = ?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _store_prices(conn: sqlite3.Connection, revolut_ticker: str, df: pd.DataFrame, currency: str = "USD"):
    """Insert price rows into daily_prices."""
    rows = [
        (revolut_ticker, idx.strftime("%Y-%m-%d"), float(row["close"]), currency)
        for idx, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO daily_prices (ticker, date, close, currency) VALUES (?, ?, ?, ?)",
        rows,
    )


def _store_fx_rates(conn: sqlite3.Connection, df: pd.DataFrame):
    """Insert EUR/USD rates into fx_rates."""
    rows = [
        (idx.strftime("%Y-%m-%d"), float(row["close"]))
        for idx, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO fx_rates (date, eur_usd) VALUES (?, ?)",
        rows,
    )


def sync_stock_prices(conn: sqlite3.Connection, start_date: datetime | None = None,
                      end_date: datetime | None = None, verbose: bool = False,
                      prices_conn: sqlite3.Connection | None = None):
    """Fetch prices for all tickers that appear in the transactions table.

    prices_conn: shared prices DB to write into (falls back to conn if None).
    """
    tickers = [
        row[0] for row in
        conn.execute(
            "SELECT DISTINCT ticker FROM transactions WHERE ticker IS NOT NULL AND asset_class = 'stock'"
        ).fetchall()
    ]

    if not tickers:
        print("No tickers found in database. Import transactions first.")
        return

    target = prices_conn if prices_conn is not None else conn

    if end_date is None:
        end_date = datetime.now()
    end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    if start_date is None:
        row = conn.execute("SELECT MIN(date) FROM transactions").fetchone()
        start_date = datetime.fromisoformat(row[0][:10]) if row and row[0] else datetime(2019, 1, 1)

    fetched = 0
    failed = []

    delisted = set(get_delisted(conn, prices_conn))

    for ticker in sorted(tickers):
        # Skip bond CUSIPs — yfinance can't look these up
        if ticker.startswith("US") and len(ticker) > 8 and not ticker.isalpha():
            if verbose:
                print(f"  Skipping bond: {ticker}")
            continue

        # Skip tickers explicitly marked as delisted
        if ticker in delisted:
            if verbose:
                print(f"  Skipping delisted: {ticker}")
            continue

        last = _last_price_date(conn, ticker, prices_conn)
        fetch_start = last if last else start_date.strftime("%Y-%m-%d")

        if verbose:
            print(f"  {ticker}: fetching from {fetch_start}...")

        yf_ticker, df = _fetch_with_fallback(ticker, fetch_start, end_str)

        if df is not None and not df.empty:
            # Determine currency by exchange suffix
            if yf_ticker.endswith((".DE", ".F", ".AS", ".PA", ".L")):
                currency = "EUR"
            elif yf_ticker.endswith(".SW"):
                # Swiss franc — convert to EUR at storage time using EURCHF rate
                chf_df = _fetch_history(FX_EURCHF, fetch_start, end_str)
                if chf_df is not None and not chf_df.empty:
                    # EURCHF rate: 1 EUR = X CHF, so CHF price / rate = EUR price
                    df = df.join(chf_df.rename(columns={"close": "eurchf"}), how="left")
                    df["eurchf"] = df["eurchf"].ffill().bfill()
                    df["close"] = df["close"] / df["eurchf"]
                currency = "EUR"
            else:
                currency = "USD"
            _store_prices(target, ticker, df, currency)
            fetched += 1
            if verbose:
                print(f"    -> {len(df)} price records ({yf_ticker})")
        else:
            failed.append(ticker)
            if verbose:
                print(f"    -> FAILED (tried {yf_ticker})")

    target.commit()
    print(f"Stock prices: {fetched} tickers updated, {len(failed)} failed")
    if failed:
        print(f"  Failed tickers: {', '.join(failed)}")


def sync_benchmarks(conn: sqlite3.Connection, start_date: datetime | None = None,
                    end_date: datetime | None = None, verbose: bool = False,
                    prices_conn: sqlite3.Connection | None = None):
    """Fetch benchmark index prices."""
    target = prices_conn if prices_conn is not None else conn

    if end_date is None:
        end_date = datetime.now()
    end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    if start_date is None:
        row = conn.execute("SELECT MIN(date) FROM transactions").fetchone()
        start_date = datetime.fromisoformat(row[0][:10]) if row and row[0] else datetime(2019, 1, 1)

    start_str = start_date.strftime("%Y-%m-%d")

    for ticker, name in BENCHMARKS.items():
        last = _last_price_date(conn, ticker, prices_conn)
        fetch_start = last if last else start_str

        if verbose:
            print(f"  {name} ({ticker}): fetching from {fetch_start}...")

        df = _fetch_history(ticker, fetch_start, end_str)
        if df is not None and not df.empty:
            currency = "GBP" if ticker == "^FTSE" else "EUR" if ticker == "VWCE.DE" else "USD"
            _store_prices(target, ticker, df, currency)
            if verbose:
                print(f"    -> {len(df)} records")
        else:
            if verbose:
                print(f"    -> FAILED")

    target.commit()
    print("Benchmark indexes updated")


def sync_fx_rates(conn: sqlite3.Connection, start_date: datetime | None = None,
                  end_date: datetime | None = None, verbose: bool = False,
                  prices_conn: sqlite3.Connection | None = None):
    """Fetch EUR/USD exchange rates."""
    target = prices_conn if prices_conn is not None else conn

    if end_date is None:
        end_date = datetime.now()
    end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    if start_date is None:
        row = conn.execute("SELECT MIN(date) FROM transactions").fetchone()
        start_date = datetime.fromisoformat(row[0][:10]) if row and row[0] else datetime(2019, 1, 1)

    last = target.execute("SELECT MAX(date) FROM fx_rates").fetchone()
    fetch_start = last[0] if last and last[0] else start_date.strftime("%Y-%m-%d")

    if verbose:
        print(f"  EUR/USD: fetching from {fetch_start}...")

    df = _fetch_history(FX_TICKER, fetch_start, end_str)
    if df is not None and not df.empty:
        _store_fx_rates(target, df)
        if verbose:
            print(f"    -> {len(df)} records")
        print("FX rates updated")
    else:
        print("FX rates: no data fetched")

    target.commit()


def sync_ticker_metadata(conn: sqlite3.Connection, verbose: bool = False):
    """Fetch sector, industry, and company name for stock tickers via yfinance .info."""
    tickers = [
        row[0] for row in
        conn.execute(
            "SELECT DISTINCT ticker FROM transactions WHERE ticker IS NOT NULL AND asset_class = 'stock'"
        ).fetchall()
    ]
    if not tickers:
        return

    # Only fetch for tickers that don't already have sector metadata
    existing = {
        row[0][len("sector:"):] for row in
        conn.execute("SELECT key FROM metadata WHERE key LIKE 'sector:%'").fetchall()
    }

    delisted = set(get_delisted(conn))
    to_fetch = [t for t in tickers if t not in existing and t not in delisted
                and not (t.startswith("US") and len(t) > 8 and not t.isalpha())]

    if not to_fetch:
        if verbose:
            print("  All tickers already have sector metadata")
        return

    fetched = 0
    for ticker in sorted(to_fetch):
        yf_ticker = _yf_ticker(ticker)
        try:
            info = yf.Ticker(yf_ticker).info or {}
        except Exception:
            if verbose:
                print(f"  {ticker}: failed to fetch info")
            continue

        sector = info.get("sector", "")
        industry = info.get("industry", "")
        country = info.get("country", "")
        name = info.get("longName") or info.get("shortName") or ""

        if sector:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (f"sector:{ticker}", sector),
            )
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (f"industry:{ticker}", industry),
            )
            fetched += 1
        if country:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (f"country:{ticker}", country),
            )
        if name:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (f"company_name:{ticker}", name),
            )
        if verbose:
            print(f"  {ticker}: {sector or '—'} / {industry or '—'} / {country or '—'}")

    conn.commit()
    print(f"Ticker metadata: {fetched}/{len(to_fetch)} tickers updated")


def sync_all(conn: sqlite3.Connection, start_date: datetime | None = None,
             end_date: datetime | None = None, verbose: bool = False,
             prices_conn: sqlite3.Connection | None = None):
    """Run all syncs: stock prices, benchmarks, FX rates, real estate ETN valuations.

    conn: user portfolio DB (reads tickers from transactions).
    prices_conn: shared system prices DB (writes prices/FX). Falls back to conn if None.
    """
    print("Syncing stock prices...")
    sync_stock_prices(conn, start_date, end_date, verbose, prices_conn=prices_conn)

    print("\nSyncing benchmark indexes...")
    sync_benchmarks(conn, start_date, end_date, verbose, prices_conn=prices_conn)

    print("\nSyncing FX rates...")
    sync_fx_rates(conn, start_date, end_date, verbose, prices_conn=prices_conn)

    # Sync real estate valuations from ETN if any properties exist
    has_props = conn.execute(
        "SELECT COUNT(*) FROM real_estate_properties"
    ).fetchone()[0]
    if has_props:
        from .realestate import sync_etn_valuations
        print("\nSyncing real estate ETN valuations...")
        sync_etn_valuations(conn, verbose=verbose, prices_conn=prices_conn)

    # Fetch sector/industry metadata for stock tickers
    print("\nSyncing ticker metadata (sector/industry)...")
    sync_ticker_metadata(conn, verbose)

    # Record sync time in both user DB and shared prices DB
    target = prices_conn if prices_conn is not None else conn
    target.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_price_sync', datetime('now'))"
    )
    target.commit()
    if prices_conn is not None:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_price_sync', datetime('now'))"
        )
        conn.commit()
