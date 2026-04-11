"""CSV import with deduplication for portfolio analytics."""

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class ImportResult:
    total: int
    new: int
    skipped: int


def _file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_amount(value) -> float | None:
    """Parse an amount string like 'USD 32' or '32' to float."""
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = re.sub(r"^[A-Z]{3}\s+", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _detect_asset_class(df: pd.DataFrame) -> str:
    """Detect whether a file contains stock, CFD, crypto, savings, or Ilirika transactions.

    Ilirika files have 'FinancialInstrument' and 'TransactionTypeName' columns.
    CFD files have 'Symbol' and 'Margin' columns.
    Crypto files have 'Symbol' and 'Value' columns but no 'Margin'.
    Savings files have 'Description' column with fund class info (no 'Symbol'/'Ticker').
    Stock files have a 'Ticker' column and 'Price per share'.
    """
    columns = set(df.columns)
    if "FinancialInstrument" in columns and "TransactionTypeName" in columns:
        return "ilirika"
    if "Symbol" in columns and "Margin" in columns:
        return "cfd"
    if "Symbol" in columns and "Value" in columns and "Ticker" not in columns:
        return "crypto"
    if "Description" in columns and "Symbol" not in columns and "Ticker" not in columns:
        # Savings: Description contains fund class info like "BUY USD Class R IE000H9J0QX4"
        if df["Description"].str.contains("Class", na=False).any():
            return "savings"
    return "stock"


def _parse_eur_amount(value) -> float | None:
    """Parse an EUR amount like '€100.00' or '€8,636.57' or '1.30 PLN' to float."""
    if pd.isna(value) or value == "":
        return None
    s = str(value).strip()
    # Remove € prefix
    s = s.replace("€", "").replace(",", "").strip()
    # Remove currency suffix like ' PLN'
    s = re.sub(r"\s+[A-Z]{2,4}$", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_crypto_date(date_str: str) -> str | None:
    """Parse crypto date format like 'Feb 21, 2020, 9:00:16 AM' to ISO format."""
    from datetime import datetime as dt
    if pd.isna(date_str) or not date_str:
        return None
    s = str(date_str).strip().strip('"')
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S"):
        try:
            return dt.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _parse_savings_row(row) -> dict | None:
    """Parse a row from the savings CSV format into transaction fields.

    The savings CSV has three sections (USD, GBP, EUR) concatenated with re-header
    rows. Column mapping varies by currency class:
    - USD/GBP: Value in 'Value, USD'/'Value, GBP' col, EUR value in 'Value, EUR', FX Rate, PPS, Qty
    - EUR: Value in 'Value, USD' col (positional), PPS in 'Value, EUR' col, Qty in 'FX Rate' col

    Description contains type + currency + fund: "BUY USD Class R IE000H9J0QX4"
    """
    date_str = row.get("Date", "")
    if pd.isna(date_str) or not date_str or date_str == "Date":
        return None  # skip re-header rows

    date = _parse_crypto_date(date_str)  # same date format as crypto
    if not date:
        return None

    desc = str(row.get("Description", ""))
    if not desc:
        return None

    # Extract type and currency from description
    # e.g. "BUY USD Class R IE000H9J0QX4", "Interest PAID EUR Class R IE000AZVL3K0"
    # "Service Fee Charged USD Class IE000H9J0QX4", "Interest Reinvested Class R USD IE000H9J0QX4"
    import re as _re
    # Determine currency class from description
    if " EUR " in desc or desc.endswith(" EUR"):
        currency = "EUR"
    elif " GBP " in desc or desc.endswith(" GBP"):
        currency = "GBP"
    else:
        currency = "USD"

    # Extract type
    type_patterns = [
        ("BUY", "BUY"),
        ("SELL", "SELL"),
        ("Interest Reinvested", "INTEREST REINVESTED"),
        ("Interest WITHDRAWN", "INTEREST WITHDRAWN"),
        ("Interest PAID", "INTEREST PAID"),
        ("Service Fee Charged", "SERVICE FEE"),
    ]
    tx_type = None
    for pattern, mapped in type_patterns:
        if desc.startswith(pattern):
            tx_type = mapped
            break
    if not tx_type:
        return None

    # Extract ISIN from description
    isin_match = _re.search(r'(IE\w+)', desc)
    ticker = isin_match.group(1) if isin_match else currency

    # Parse values based on currency class
    raw_val_usd = row.get("Value, USD")
    raw_val_eur = row.get("Value, EUR")
    raw_fx = row.get("FX Rate")
    raw_pps = row.get("Price per share")
    raw_qty = row.get("Quantity of shares")

    if currency == "EUR":
        # EUR section: positional columns are shifted
        # "Value, USD" col → actual EUR value
        # "Value, EUR" col → price per share
        # "FX Rate" col → quantity of shares
        value_eur = _parse_savings_amount(raw_val_usd)
        pps = _parse_savings_amount(raw_val_eur)
        qty = _parse_savings_amount(raw_fx)
        fx_rate = 1.0
    elif currency == "GBP":
        # GBP section: "Value, USD" col → GBP value, "Value, EUR" → EUR value
        value_eur = _parse_savings_amount(raw_val_eur)
        pps = _parse_savings_amount(raw_pps)
        qty = _parse_savings_amount(raw_qty)
        gbp_val = _parse_savings_amount(raw_val_usd)
        fx_rate = abs(value_eur / gbp_val) if gbp_val and gbp_val != 0 and value_eur else _parse_savings_amount(raw_fx) or 1.0
    else:
        # USD section: standard columns
        value_eur = _parse_savings_amount(raw_val_eur)
        pps = _parse_savings_amount(raw_pps)
        qty = _parse_savings_amount(raw_qty)
        fx_rate = _parse_savings_amount(raw_fx) or 1.0

    # For EUR class, if no value_eur (interest/fees with only one column), use the positional value
    if value_eur is None and currency == "EUR":
        value_eur = _parse_savings_amount(raw_val_usd)
    # For USD, if no value_eur, compute from USD value and fx_rate
    if value_eur is None and currency == "USD":
        usd_val = _parse_savings_amount(raw_val_usd)
        if usd_val is not None and fx_rate:
            value_eur = usd_val * fx_rate

    abs_qty = abs(qty) if qty else None
    abs_value = abs(value_eur) if value_eur else None

    # Price per share in EUR: for non-EUR classes, native PPS is 1.00 but EUR PPS differs
    if abs_qty and abs_value and abs_qty > 0:
        pps_eur = abs_value / abs_qty
    else:
        pps_eur = 1.0

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": abs_qty,
        "price_per_share": pps_eur,
        "total_amount": abs_value,
        "currency": "EUR",
        "fx_rate": 1.0,  # already converted to EUR
    }


def _parse_savings_amount(value) -> float | None:
    """Parse a savings amount that may have commas as thousands separators."""
    if pd.isna(value) or value == "" or value is None:
        return None
    s = str(value).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_crypto_row(row) -> dict | None:
    """Parse a row from the crypto CSV format into transaction fields."""
    date = _parse_crypto_date(row.get("Date", ""))
    if not date:
        return None

    symbol = row.get("Symbol", None)
    if pd.isna(symbol):
        symbol = None
    ticker = str(symbol) if symbol else None

    tx_type = row.get("Type", "")
    if pd.isna(tx_type) or not tx_type:
        return None

    # Map crypto types to standard types
    type_map = {
        "Buy": "BUY",
        "Sell": "SELL",
        "Staking reward": "STAKING REWARD",
        "Learn reward": "LEARN REWARD",
        "Payment": "PAYMENT",
        "Receive": "RECEIVE",
        "Stake": "STAKE",
    }
    mapped_type = type_map.get(str(tx_type), str(tx_type).upper())

    quantity = _parse_amount(row.get("Quantity"))
    price = _parse_eur_amount(row.get("Price"))
    value = _parse_eur_amount(row.get("Value"))
    fees = _parse_eur_amount(row.get("Fees"))

    return {
        "date": date,
        "ticker": ticker,
        "type": mapped_type,
        "quantity": quantity,
        "price_per_share": price,
        "total_amount": value,
        "currency": "EUR",
        "fx_rate": 1.0,
    }


def _parse_cfd_row(row) -> dict | None:
    """Parse a row from the CFD CSV format into transaction fields."""
    date = row.get("Date", "")
    if pd.isna(date) or not date:
        return None

    symbol = row.get("Symbol", None)
    if pd.isna(symbol):
        symbol = None

    # Strip :CFD suffix for storage
    ticker = None
    if symbol:
        ticker = symbol.replace(":CFD", "")

    tx_type = row.get("Type", "")
    if pd.isna(tx_type) or not tx_type:
        return None

    quantity = _parse_amount(row.get("Quantity"))
    price_per_share = _parse_amount(row.get("Price"))
    total_amount = _parse_amount(row.get("Total Amount"))
    currency = row.get("Currency", "USD")
    if pd.isna(currency):
        currency = "USD"

    fx_rate_raw = row.get("FX Rate", 1.0)
    fx_rate = float(fx_rate_raw) if not pd.isna(fx_rate_raw) else 1.0

    return {
        "date": str(date),
        "ticker": ticker,
        "type": str(tx_type),
        "quantity": quantity,
        "price_per_share": price_per_share,
        "total_amount": total_amount,
        "currency": str(currency),
        "fx_rate": fx_rate,
    }


def _parse_ilirika_date(date_str: str) -> str | None:
    """Parse Ilirika date format 'D. MM. YYYY HH:MM:SS' or 'DD.MM.YYYY' to ISO format."""
    from datetime import datetime as dt
    if pd.isna(date_str) or not date_str:
        return None
    s = str(date_str).strip()
    # Try DateValue format: "22. 11. 2021 15:49:00" or "3. 03. 2021 15:30:00"
    for fmt in ("%d. %m. %Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return dt.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _parse_eu_number(value) -> float | None:
    """Parse European number format with comma decimal separator (e.g. '13,04' -> 13.04)."""
    if pd.isna(value) or value == "" or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _ilirika_ticker_to_standard(instrument: str) -> tuple[str, str]:
    """Convert Ilirika Bloomberg-style ticker to standard ticker and infer currency.

    'ASTR US' -> ('ASTR', 'USD'), 'SX5EEX GY' -> ('SXR8.DE', 'EUR')
    """
    parts = instrument.strip().split()
    if len(parts) < 2:
        return instrument, "USD"

    ticker = parts[0]
    exchange = parts[1].upper()

    # Bloomberg ticker -> yfinance ticker overrides (ETFs with non-standard symbols)
    bloomberg_overrides = {
        "SX5EEX": "EXW1",   # iShares Euro STOXX 50 UCITS ETF DE
        "SX8PEX": "EXV3",   # iShares STOXX Europe 600 Technology UCITS ETF DE
    }
    ticker = bloomberg_overrides.get(ticker, ticker)

    # Map exchange suffix to yfinance ticker suffix and currency
    exchange_map = {
        "US": ("", "USD"),
        "GY": (".DE", "EUR"),    # Germany (Xetra)
        "GR": (".DE", "EUR"),    # Germany
        "LN": (".L", "GBP"),     # London
        "FP": (".PA", "EUR"),    # Paris
        "IM": (".MI", "EUR"),    # Milan
        "NA": (".AS", "EUR"),    # Amsterdam
        "SM": (".MC", "EUR"),    # Madrid
        "SW": (".SW", "CHF"),    # Switzerland
        "JP": (".T", "JPY"),     # Tokyo
    }

    suffix, currency = exchange_map.get(exchange, ("", "USD"))
    return ticker + suffix, currency


def _preprocess_ilirika_splits(df: pd.DataFrame) -> dict[str, float]:
    """Pre-compute net split quantity changes from paired OLD/new Ilirika rows.

    Returns a dict mapping (date, ticker) -> net quantity change for split events.
    E.g. ASTR US OLD (-80) + ASTR US (+5) on same date -> net change = -75.
    """
    split_deltas: dict[tuple[str, str], float] = {}
    for _, row in df.iterrows():
        tx_type_raw = str(row.get("TransactionTypeName", ""))
        if "Split" not in tx_type_raw:
            continue
        instrument = str(row.get("FinancialInstrument", ""))
        if not instrument:
            continue
        date = str(row.get("DateValue") or row.get("SettlementDate", ""))
        vol = _parse_eu_number(row.get("VolumeValue")) or _parse_eu_number(row.get("Volume")) or 0

        # Normalize: strip " OLD" suffix to group paired rows
        base_instrument = instrument.replace(" OLD", "").strip()
        ticker, _ = _ilirika_ticker_to_standard(base_instrument)
        key = (date, ticker)
        split_deltas[key] = split_deltas.get(key, 0) + vol

    return split_deltas


def _parse_ilirika_row(row, split_deltas: dict | None = None) -> dict | None:
    """Parse a row from the Ilirika broker CSV format into transaction fields.

    Columns: AccountID, FinancialInstrument, SettlementDate, DateValue,
    TransactionTypeName, VolumeValue, Volume, PriceValue, Price
    """
    date = _parse_ilirika_date(row.get("DateValue") or row.get("SettlementDate", ""))
    if not date:
        return None

    instrument = row.get("FinancialInstrument", "")
    if pd.isna(instrument) or not instrument:
        return None

    # Skip "OLD" ticker entries (they are the debit side of reverse splits)
    if " OLD" in str(instrument):
        return None

    ticker, currency = _ilirika_ticker_to_standard(str(instrument))

    tx_type_raw = str(row.get("TransactionTypeName", ""))
    # Map Slovenian type names to standard types
    type_map = {
        "Nakup": "BUY",
        "Prodaja": "SELL",
    }
    # Handle corporate actions
    if "Reverse Split" in tx_type_raw:
        tx_type = "STOCK SPLIT"
    elif "Merger" in tx_type_raw and "denar" in tx_type_raw:
        tx_type = "MERGER CASH"
    elif "Merger" in tx_type_raw:
        tx_type = "MERGER"
    elif "Split" in tx_type_raw:
        tx_type = "STOCK SPLIT"
    else:
        tx_type = type_map.get(tx_type_raw, tx_type_raw.upper())

    quantity = abs(_parse_eu_number(row.get("Volume")) or _parse_eu_number(row.get("VolumeValue")) or 0)
    price = _parse_eu_number(row.get("Price")) or _parse_eu_number(row.get("PriceValue"))

    total_amount = quantity * price if quantity and price else None

    # For STOCK SPLIT, use the pre-computed net delta (OLD + new combined)
    if tx_type == "STOCK SPLIT" and split_deltas:
        date_raw = str(row.get("DateValue") or row.get("SettlementDate", ""))
        key = (date_raw, ticker)
        quantity = split_deltas.get(key, quantity)

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": quantity,
        "price_per_share": price,
        "total_amount": total_amount,
        "currency": currency,
        "fx_rate": 1.0,  # no FX info in Ilirika CSV; prices in instrument currency
    }


def _parse_stock_row(row) -> dict | None:
    """Parse a row from the stock CSV format into transaction fields."""
    date = row.get("Date") or row.get("Started Date", "")
    if pd.isna(date) or not date:
        return None

    ticker = row.get("Ticker", None)
    if pd.isna(ticker):
        ticker = None

    tx_type = row.get("Type", "")
    if pd.isna(tx_type) or not tx_type:
        return None

    quantity = _parse_amount(row.get("Quantity"))
    price_per_share = _parse_amount(row.get("Price per share"))
    total_amount = _parse_amount(row.get("Total Amount") or row.get("Amount"))
    currency = row.get("Currency", "USD")
    if pd.isna(currency):
        currency = "USD"

    fx_rate_raw = row.get("FX Rate", 1.0)
    fx_rate = float(fx_rate_raw) if not pd.isna(fx_rate_raw) else 1.0

    return {
        "date": str(date),
        "ticker": ticker,
        "type": str(tx_type),
        "quantity": quantity,
        "price_per_share": price_per_share,
        "total_amount": total_amount,
        "currency": str(currency),
        "fx_rate": fx_rate,
    }


def import_csv(conn: sqlite3.Connection, file_path: str, verbose: bool = False) -> ImportResult:
    """Import a Revolut CSV/Excel file into the database with deduplication."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Check file-level dedup
    fhash = _file_hash(file_path)
    existing = conn.execute(
        "SELECT id FROM import_log WHERE file_hash = ?", (fhash,)
    ).fetchone()
    if existing:
        if verbose:
            print(f"File already imported (SHA-256 match): {path.name}")
        return ImportResult(total=0, new=0, skipped=0)

    # Parse file
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
        # If single column or missing expected columns, try semicolon separator (Ilirika format)
        if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
            df = pd.read_csv(path, sep=";")
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    asset_class = _detect_asset_class(df)
    # Ilirika is stored as "stock" asset class
    effective_asset_class = "stock" if asset_class == "ilirika" else asset_class

    if asset_class == "ilirika":
        split_deltas = _preprocess_ilirika_splits(df)
        parse_row = lambda row: _parse_ilirika_row(row, split_deltas)
    else:
        parse_row = {
            "cfd": _parse_cfd_row,
            "crypto": _parse_crypto_row,
            "savings": _parse_savings_row,
        }.get(asset_class, _parse_stock_row)

    if verbose:
        print(f"  Detected format: {asset_class}" + (f" (stored as {effective_asset_class})" if asset_class != effective_asset_class else ""))

    total = len(df)
    new = 0
    skipped = 0

    for _, row in df.iterrows():
        parsed = parse_row(row)
        if parsed is None:
            skipped += 1
            continue

        try:
            conn.execute(
                """INSERT OR IGNORE INTO transactions
                   (date, ticker, type, quantity, price_per_share, total_amount,
                    currency, fx_rate, asset_class, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (parsed["date"], parsed["ticker"], parsed["type"],
                 parsed["quantity"], parsed["price_per_share"],
                 parsed["total_amount"], parsed["currency"],
                 parsed["fx_rate"], effective_asset_class, path.name),
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new += 1
            else:
                skipped += 1
        except sqlite3.Error:
            skipped += 1

    # Log the import
    conn.execute(
        """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped)
           VALUES (?, ?, ?, ?, ?)""",
        (path.name, fhash, total, new, total - new),
    )
    conn.commit()

    return ImportResult(total=total, new=new, skipped=total - new)
