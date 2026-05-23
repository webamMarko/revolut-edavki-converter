"""CSV import with deduplication for portfolio analytics."""

from __future__ import annotations

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
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


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
    """Detect whether a file contains stock, CFD, crypto, savings, Ilirika, IBKR,
    Trading 212, or Degiro transactions from column headers.

    IBKR Activity Statement: first column is 'Trades' with 'Symbol' and 'DataDiscriminator'.
    Trading 212: has 'Action', 'No. of shares', 'Price / share' columns.
    Degiro: has 'Datum', 'Product', 'ISIN', 'Koers' columns.
    Ilirika: has 'FinancialInstrument' and 'TransactionTypeName' columns.
    CFD: has 'Symbol' and 'Margin' columns.
    Crypto: has 'Symbol' and 'Value' columns but no 'Margin'.
    Savings: has 'Description' column with fund class info (no 'Symbol'/'Ticker').
    Stock: has a 'Ticker' column and 'Price per share'.
    """
    columns = set(df.columns)
    # IBKR Activity Statement CSV has 'Trades' as first col and 'DataDiscriminator'
    if "Trades" in columns and "DataDiscriminator" in columns:
        return "ibkr"
    # Trading 212 has 'Action' and 'No. of shares'
    if "Action" in columns and "No. of shares" in columns and "Price / share" in columns:
        return "trading212"
    # Degiro has 'Datum', 'Product', 'ISIN', 'Koers'
    if "Datum" in columns and "Product" in columns and "ISIN" in columns:
        return "degiro"
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
    """Parse a currency amount like '€100.00', '$5.00', '€8,636.57' or '1.30 PLN' to float."""
    if pd.isna(value) or value == "":
        return None
    s = str(value).strip()
    # Remove currency prefix symbols (€, $, £, etc.)
    s = s.lstrip("€$£¥").strip()
    # Remove thousands separators
    s = s.replace(",", "")
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
    # Replace narrow no-break space (U+202F) used by newer Revolut exports before AM/PM
    s = str(date_str).strip().strip('"').replace('\u202f', ' ')
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S"):
        try:
            return dt.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def normalize_date(date_val) -> str | None:
    """Normalize any date value stored in the DB to YYYY-MM-DD.

    Handles:
    - 'YYYY-MM-DD'                     → returned as-is
    - 'YYYY-MM-DD HH:MM:SS'            → truncated to date part
    - 'YYYY-MM-DDTHH:MM:SS...'         → truncated to date part (ISO 8601)
    - 'Apr 1, 2026, 12:24:31 PM'       → parsed (localized Revolut format)
    - 'Apr 1, 2026, 0:22:14'           → parsed (localized, 24h variant)
    Returns None if the date cannot be parsed.
    """
    if not date_val:
        return None
    s = str(date_val).strip()
    # Fast path: already YYYY-MM-DD or starts with it (ISO timestamp or datetime)
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    # Slow path: localized format (with possible narrow no-break space)
    return _parse_crypto_date(s)[:10] if _parse_crypto_date(s) else None


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
    raw_qty = row.get("Quantity of shares")

    if currency == "EUR":
        # EUR section: positional columns are shifted
        # "Value, USD" col → actual EUR value
        # "Value, EUR" col → price per share
        # "FX Rate" col → quantity of shares
        value_eur = _parse_savings_amount(raw_val_usd)
        qty = _parse_savings_amount(raw_fx)
        fx_rate = 1.0
    elif currency == "GBP":
        # GBP section: "Value, USD" col → GBP value, "Value, EUR" → EUR value
        value_eur = _parse_savings_amount(raw_val_eur)
        qty = _parse_savings_amount(raw_qty)
        gbp_val = _parse_savings_amount(raw_val_usd)
        fx_rate = abs(value_eur / gbp_val) if gbp_val and gbp_val != 0 and value_eur else _parse_savings_amount(raw_fx) or 1.0
    else:
        # USD section: standard columns
        value_eur = _parse_savings_amount(raw_val_eur)
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

    # For MERGER CASH the Price column is the total payout, not per-share
    if tx_type == "MERGER CASH":
        total_amount = price
        price = (price / quantity) if quantity else price
    else:
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


def _parse_ibkr_row(row) -> dict | None:
    """Parse a row from Interactive Brokers Activity Statement CSV (Trades section).

    IBKR exports a multi-section CSV where each row starts with a section name.
    The Trades section has: Trades,Header/Data,DataDiscriminator,Asset Category,
    Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,...
    """
    # Only parse data rows (skip headers and totals)
    discriminator = row.get("DataDiscriminator", "")
    if pd.isna(discriminator) or str(discriminator) not in ("Order", "Trade"):
        return None

    # Only handle stocks/equity for now
    asset_cat = row.get("Asset Category", "")
    if pd.isna(asset_cat) or str(asset_cat) not in ("Stocks", "Equity"):
        return None

    date_str = row.get("Date/Time", "")
    if pd.isna(date_str) or not date_str:
        return None
    # IBKR date format: "2023-01-15 10:30:00" or "2023-01-15, 10:30:00"
    date = str(date_str).replace(",", "").strip()

    symbol = row.get("Symbol", "")
    if pd.isna(symbol) or not symbol:
        return None
    ticker = str(symbol).strip()

    quantity_raw = row.get("Quantity")
    if pd.isna(quantity_raw):
        return None
    quantity = float(quantity_raw)

    # Positive quantity = buy, negative = sell
    if quantity > 0:
        tx_type = "BUY"
    elif quantity < 0:
        tx_type = "SELL"
        quantity = abs(quantity)
    else:
        return None

    price_raw = row.get("T. Price")
    price = float(price_raw) if not pd.isna(price_raw) else None

    total_amount = abs(float(row.get("Proceeds", 0))) if not pd.isna(row.get("Proceeds")) else None

    currency = row.get("Currency", "USD")
    if pd.isna(currency):
        currency = "USD"

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": quantity,
        "price_per_share": price,
        "total_amount": total_amount,
        "currency": str(currency),
        "fx_rate": 1.0,
    }


def _parse_trading212_row(row) -> dict | None:
    """Parse a row from Trading 212 CSV export.

    Columns: Action, Time, ISIN, Ticker, Name, No. of shares, Price / share,
    Currency (Price / share), Exchange rate, Result (EUR), Total (EUR), ...
    """
    action = row.get("Action", "")
    if pd.isna(action) or not action:
        return None

    action_str = str(action).strip()

    # Map Trading 212 actions to standard types
    action_lower = action_str.lower()
    if "buy" in action_lower:
        tx_type = "BUY"
    elif "sell" in action_lower:
        tx_type = "SELL"
    elif "dividend" in action_lower:
        tx_type = "DIVIDEND"
    else:
        return None

    date_str = row.get("Time", "")
    if pd.isna(date_str) or not date_str:
        return None
    date = str(date_str).strip()

    ticker = row.get("Ticker", "")
    if pd.isna(ticker) or not ticker:
        return None
    ticker = str(ticker).strip()

    quantity = None
    qty_raw = row.get("No. of shares")
    if not pd.isna(qty_raw) and qty_raw != "":
        quantity = float(qty_raw)

    price = None
    price_raw = row.get("Price / share")
    if not pd.isna(price_raw) and price_raw != "":
        price = float(price_raw)

    currency = row.get("Currency (Price / share)", "USD")
    if pd.isna(currency) or not currency:
        currency = "USD"
    currency = str(currency).strip()

    # Trading 212 provides exchange rate (foreign to EUR)
    fx_rate_raw = row.get("Exchange rate")
    if not pd.isna(fx_rate_raw) and fx_rate_raw != "":
        fx_rate = float(fx_rate_raw)
    else:
        fx_rate = 1.0

    # Total in EUR is provided directly; for dividends use Charge amount
    total_eur_raw = row.get("Total (EUR)")
    charge_raw = row.get("Charge amount (EUR)")
    if not pd.isna(total_eur_raw) and total_eur_raw != "":
        total_amount = abs(float(total_eur_raw))
    elif not pd.isna(charge_raw) and charge_raw != "":
        total_amount = abs(float(charge_raw))
    elif quantity and price:
        total_amount = quantity * price
    else:
        total_amount = None

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": quantity,
        "price_per_share": price,
        "total_amount": total_amount,
        "currency": currency,
        "fx_rate": fx_rate,
    }


_DEGIRO_EXCHANGE_SUFFIXES = {
    "NASDAQ": "",
    "NSY": "",
    "NYSE": "",
    "XNAS": "",
    "XNYS": "",
    "AEX": ".AS",
    "XAMS": ".AS",
    "XET": ".DE",
    "XETR": ".DE",
    "FRA": ".F",
    "XFRA": ".F",
    "MIL": ".MI",
    "XMIL": ".MI",
    "EPA": ".PA",
    "XPAR": ".PA",
    "LSE": ".L",
    "XLSE": ".L",
    "BME": ".MC",
    "XMCE": ".MC",
    "SWX": ".SW",
    "XSWX": ".SW",
}


def _degiro_ticker(product: str, isin: str, exchange: str) -> str:
    """Derive a yfinance-compatible ticker from Degiro product/ISIN/exchange.

    Degiro CSVs have full product names but not ticker symbols. We use a
    well-known ISIN->ticker map for common stocks, otherwise fall back to ISIN.
    """
    # Well-known ISIN -> ticker mappings (covers most popular retail holdings)
    isin_map = {
        "US0378331005": "AAPL",
        "US5949181045": "MSFT",
        "US0231351067": "AMZN",
        "US02079K3059": "GOOGL",
        "US30303M1027": "META",
        "US67066G1040": "NVDA",
        "US88160R1014": "TSLA",
        "US4781601046": "JNJ",
        "US92826C8394": "V",
        "US7427181091": "PG",
        "US46625H1005": "JPM",
        "US0846707026": "BRK-B",
        "US58933Y1055": "MRK",
        "US00507V1098": "ABNB",
        "US6541061031": "NKE",
        "US2546871060": "DIS",
        "US79466L3024": "CRM",
        "US7170811035": "PFE",
        "US4592001014": "IBM",
        "US0970231058": "BA",
        "US6516391066": "NFLX",
        "US00724F1012": "ADBE",
        "US7960508882": "SAP",
        "NL0010273215": "ASML",
        "IE00B4L5Y983": "IWDA.AS",
        "IE00B3RBWM25": "VWRL.AS",
        "IE00BK5BQT80": "VWCE.DE",
        "DE0005933931": "EXW1.DE",
    }

    ticker = isin_map.get(isin)
    if ticker:
        return ticker

    # For unknown ISINs, use ISIN as fallback (user can map manually via sync)
    suffix = _DEGIRO_EXCHANGE_SUFFIXES.get(exchange, "")
    return isin + suffix


def _parse_degiro_row(row) -> dict | None:
    """Parse a row from Degiro Account Statement CSV.

    Columns: Datum, Tijd, Product, ISIN, Beurs, Uitvoeringsplaats, Aantal,
    Koers, [currency], Lokale waarde, [currency], Waarde, [currency],
    Wisselkoers, Transactiekosten en/of, [currency], Totaal, [currency], Order ID
    """
    date_str = row.get("Datum", "")
    if pd.isna(date_str) or not date_str:
        return None

    # Degiro date format: DD-MM-YYYY
    from datetime import datetime as dt
    try:
        date = dt.strptime(str(date_str).strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None

    time_str = row.get("Tijd", "")
    if not pd.isna(time_str) and time_str:
        date = f"{date} {str(time_str).strip()}:00"

    product = row.get("Product", "")
    if pd.isna(product) or not product:
        return None

    isin = row.get("ISIN", "")
    if pd.isna(isin) or not isin:
        return None

    exchange = row.get("Beurs", "")
    if pd.isna(exchange):
        exchange = ""
    exchange = str(exchange).strip()

    ticker = _degiro_ticker(str(product), str(isin).strip(), exchange)

    quantity_raw = row.get("Aantal")
    if pd.isna(quantity_raw):
        return None
    quantity = float(quantity_raw)

    # Positive quantity = buy, negative = sell
    if quantity > 0:
        tx_type = "BUY"
    elif quantity < 0:
        tx_type = "SELL"
        quantity = abs(quantity)
    else:
        return None

    price_raw = row.get("Koers")
    price = float(price_raw) if not pd.isna(price_raw) else None

    # Use 'Waarde' (EUR value) as total amount
    waarde_raw = row.get("Waarde")
    if not pd.isna(waarde_raw) and waarde_raw != "":
        total_amount = abs(float(waarde_raw))
    elif quantity and price:
        total_amount = quantity * price
    else:
        total_amount = None

    # Currency from exchange
    eur_exchanges = {"AEX", "XET", "FRA", "MIL", "EPA", "BME", "XAMS", "XETR", "XFRA", "XMIL", "XPAR", "XMCE"}
    if exchange in eur_exchanges:
        currency = "EUR"
    else:
        currency = "USD"

    # Wisselkoers is the FX rate applied
    fx_raw = row.get("Wisselkoers")
    if not pd.isna(fx_raw) and fx_raw != "" and fx_raw is not None:
        try:
            fx_rate = float(str(fx_raw).replace(",", "."))
        except (ValueError, TypeError):
            fx_rate = 1.0
    else:
        fx_rate = 1.0

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": quantity,
        "price_per_share": price,
        "total_amount": total_amount,
        "currency": currency,
        "fx_rate": fx_rate,
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


def _row_hash(parsed: dict, asset_class: str) -> str:
    """Compute deterministic dedup hash for a parsed transaction row."""
    from .db import transaction_row_hash
    return transaction_row_hash(
        parsed["date"], parsed["ticker"], parsed["type"],
        parsed["quantity"], parsed["total_amount"], parsed["currency"],
    )


def _apply_map(row, column_map: dict, asset_class: str) -> dict | None:
    """Map a raw CSV row to a transaction dict using the user-supplied column mapping.

    column_map: {db_field: csv_header_name}
    Returns None if required fields (date, type) are missing.
    """
    def get(field):
        header = column_map.get(field)
        if not header:
            return None
        val = row.get(header)
        if pd.isna(val) if not isinstance(val, str) else (not val):
            return None
        return val

    # Date
    raw_date = get("date")
    if not raw_date:
        return None
    if asset_class == "crypto":
        date = _parse_crypto_date(str(raw_date))
    else:
        date = str(raw_date)
    if not date:
        return None

    # Type
    raw_type = get("type")
    if not raw_type:
        return None
    tx_type = str(raw_type)

    # Ticker
    raw_ticker = get("ticker")
    ticker = str(raw_ticker) if raw_ticker is not None else None

    # Quantity
    raw_qty = get("quantity")
    quantity = _parse_amount(raw_qty) if raw_qty is not None else None

    # Price per share
    raw_pps = get("price_per_share")
    if raw_pps is not None:
        if asset_class in ("crypto", "savings"):
            price_per_share = _parse_eur_amount(raw_pps)
        else:
            price_per_share = _parse_amount(raw_pps)
    else:
        price_per_share = None

    # Total amount
    raw_total = get("total_amount")
    if raw_total is not None:
        if asset_class in ("crypto", "savings"):
            total_amount = _parse_eur_amount(raw_total)
        else:
            total_amount = _parse_amount(raw_total)
    else:
        total_amount = None

    # Currency
    raw_currency = get("currency")
    if raw_currency is not None:
        currency = str(raw_currency)
    else:
        currency = "EUR" if asset_class in ("crypto", "savings") else "USD"

    # FX Rate
    raw_fx = get("fx_rate")
    if raw_fx is not None:
        try:
            fx_rate = float(raw_fx)
        except (ValueError, TypeError):
            fx_rate = 1.0
    else:
        fx_rate = 1.0

    return {
        "date": date,
        "ticker": ticker,
        "type": tx_type,
        "quantity": quantity,
        "price_per_share": price_per_share,
        "total_amount": total_amount,
        "currency": currency,
        "fx_rate": fx_rate,
    }


def import_csv_mapped(
    conn: sqlite3.Connection,
    file_path: str,
    asset_class: str,
    column_map: dict,
    filename_hint: str = "",
    verbose: bool = False,
    portfolio_id: int | None = None,
) -> ImportResult:
    """Import a CSV using an explicit user-supplied column mapping.

    asset_class: "stock" | "cfd" | "crypto" | "savings"
    column_map: {db_field: csv_header_name}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # File-level dedup check (after reading so we know total rows)
    fhash = _file_hash(file_path)

    # Read CSV — comma first, retry with semicolon if single column
    df = pd.read_csv(path)
    if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
        df = pd.read_csv(path, sep=";")

    total = len(df)

    existing = conn.execute(
        "SELECT id FROM import_log WHERE file_hash = ?", (fhash,)
    ).fetchone()
    if existing:
        if verbose:
            print(f"File already imported (SHA-256 match): {filename_hint or path.name}")
        return ImportResult(total=total, new=0, skipped=total)

    new = 0
    skipped = 0

    for _, row in df.iterrows():
        parsed = _apply_map(row, column_map, asset_class)
        if parsed is None:
            skipped += 1
            continue

        try:
            rh = _row_hash(parsed, asset_class)
            if portfolio_id:
                conn.execute(
                    """INSERT OR IGNORE INTO transactions
                       (date, ticker, type, quantity, price_per_share, total_amount,
                        currency, fx_rate, asset_class, source_file, row_hash, portfolio_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (parsed["date"], parsed["ticker"], parsed["type"],
                     parsed["quantity"], parsed["price_per_share"],
                     parsed["total_amount"], parsed["currency"],
                     parsed["fx_rate"], asset_class, filename_hint or path.name, rh, portfolio_id),
                )
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO transactions
                       (date, ticker, type, quantity, price_per_share, total_amount,
                        currency, fx_rate, asset_class, source_file, row_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (parsed["date"], parsed["ticker"], parsed["type"],
                     parsed["quantity"], parsed["price_per_share"],
                     parsed["total_amount"], parsed["currency"],
                     parsed["fx_rate"], asset_class, filename_hint or path.name, rh),
                )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new += 1
            else:
                skipped += 1
        except sqlite3.Error:
            skipped += 1

    display_name = filename_hint or path.name
    if portfolio_id:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped, portfolio_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (display_name, fhash, total, new, total - new, portfolio_id),
        )
    else:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped)
               VALUES (?, ?, ?, ?, ?)""",
            (display_name, fhash, total, new, total - new),
        )
    conn.commit()

    return ImportResult(total=total, new=new, skipped=total - new)


def import_csv(conn: sqlite3.Connection, file_path: str, verbose: bool = False,
               portfolio_id: int | None = None) -> ImportResult:
    """Import a Revolut CSV/Excel file into the database with deduplication."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    fhash = _file_hash(file_path)

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
    # External brokers and Ilirika are stored as "stock" asset class
    effective_asset_class = "stock" if asset_class in ("ilirika", "ibkr", "trading212", "degiro") else asset_class

    if asset_class == "ilirika":
        split_deltas = _preprocess_ilirika_splits(df)
        def parse_row(row):
            return _parse_ilirika_row(row, split_deltas)
    else:
        parse_row = {
            "cfd": _parse_cfd_row,
            "crypto": _parse_crypto_row,
            "savings": _parse_savings_row,
            "ibkr": _parse_ibkr_row,
            "trading212": _parse_trading212_row,
            "degiro": _parse_degiro_row,
        }.get(asset_class, _parse_stock_row)

    if verbose:
        print(f"  Detected format: {asset_class}" + (f" (stored as {effective_asset_class})" if asset_class != effective_asset_class else ""))

    total = len(df)

    # Check file-level dedup (after parsing so we know row count)
    existing = conn.execute(
        "SELECT id FROM import_log WHERE file_hash = ?", (fhash,)
    ).fetchone()
    if existing:
        if verbose:
            print(f"File already imported (SHA-256 match): {path.name}")
        return ImportResult(total=total, new=0, skipped=total)

    new = 0
    skipped = 0
    warnings = []
    parse_failed_count = 0
    dup_count = 0

    for idx, row in df.iterrows():
        parsed = parse_row(row)
        if parsed is None:
            skipped += 1
            parse_failed_count += 1
            if parse_failed_count <= 5:
                warnings.append(f"Row {idx + 2}: could not parse (missing required fields)")
            continue

        try:
            rh = _row_hash(parsed, effective_asset_class)
            if portfolio_id:
                conn.execute(
                    """INSERT OR IGNORE INTO transactions
                       (date, ticker, type, quantity, price_per_share, total_amount,
                        currency, fx_rate, asset_class, source_file, row_hash, portfolio_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (parsed["date"], parsed["ticker"], parsed["type"],
                     parsed["quantity"], parsed["price_per_share"],
                     parsed["total_amount"], parsed["currency"],
                     parsed["fx_rate"], effective_asset_class, path.name, rh, portfolio_id),
                )
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO transactions
                       (date, ticker, type, quantity, price_per_share, total_amount,
                        currency, fx_rate, asset_class, source_file, row_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (parsed["date"], parsed["ticker"], parsed["type"],
                     parsed["quantity"], parsed["price_per_share"],
                     parsed["total_amount"], parsed["currency"],
                     parsed["fx_rate"], effective_asset_class, path.name, rh),
                )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new += 1
            else:
                skipped += 1
                dup_count += 1
        except sqlite3.Error:
            skipped += 1

    if parse_failed_count > 5:
        warnings.append(f"...and {parse_failed_count - 5} more rows could not be parsed")
    if dup_count > 0:
        warnings.append(f"{dup_count} duplicate rows skipped")

    # Log the import
    if portfolio_id:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped, portfolio_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (path.name, fhash, total, new, total - new, portfolio_id),
        )
    else:
        conn.execute(
            """INSERT INTO import_log (filename, file_hash, rows_total, rows_new, rows_skipped)
               VALUES (?, ?, ?, ?, ?)""",
            (path.name, fhash, total, new, total - new),
        )
    conn.commit()

    return ImportResult(total=total, new=new, skipped=total - new, warnings=warnings)
