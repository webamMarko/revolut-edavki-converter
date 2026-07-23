"""Ilirika broker CSV adapter."""

from __future__ import annotations

from datetime import datetime as dt

import pandas as pd

from .base import CsvAdapter, ParsedTrade


def _parse_ilirika_date(date_str: str) -> str | None:
    """Parse Ilirika date format 'D. MM. YYYY HH:MM:SS' or 'DD.MM.YYYY' to ISO format."""
    if pd.isna(date_str) or not date_str:
        return None
    s = str(date_str).strip()
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

    'ASTR US' -> ('ASTR', 'USD'), 'SX5EEX GY' -> ('EXW1.DE', 'EUR')
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


def _preprocess_ilirika_splits(df: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Pre-compute net split quantity changes from paired OLD/new Ilirika rows.

    Returns a dict mapping (date, ticker) -> net quantity change for split events.
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

        base_instrument = instrument.replace(" OLD", "").strip()
        ticker, _ = _ilirika_ticker_to_standard(base_instrument)
        key = (date, ticker)
        split_deltas[key] = split_deltas.get(key, 0) + vol

    return split_deltas


class IlirikaAdapter(CsvAdapter):
    """Parses Ilirika broker CSV/Excel exports."""

    @property
    def broker_name(self) -> str:
        return "ilirika"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        return "FinancialInstrument" in columns and "TransactionTypeName" in columns

    def parse(self, file_path: str) -> list[ParsedTrade]:
        path_obj = __import__("pathlib").Path(file_path)
        suffix = path_obj.suffix.lower()

        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
            if len(df.columns) == 1 or (len(df.columns) < 3 and ";" in df.columns[0]):
                df = pd.read_csv(file_path, sep=";")

        split_deltas = _preprocess_ilirika_splits(df)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row, split_deltas)
            if parsed is not None:
                trades.append(parsed)
        return trades

    def _parse_row(self, row, split_deltas: dict | None = None) -> ParsedTrade | None:
        date = _parse_ilirika_date(row.get("DateValue") or row.get("SettlementDate", ""))
        if not date:
            return None

        instrument = row.get("FinancialInstrument", "")
        if pd.isna(instrument) or not instrument:
            return None

        # Skip "OLD" ticker entries (debit side of reverse splits)
        if " OLD" in str(instrument):
            return None

        ticker, currency = _ilirika_ticker_to_standard(str(instrument))

        tx_type_raw = str(row.get("TransactionTypeName", ""))
        tx_type_lower = tx_type_raw.lower()
        type_map = {
            "Nakup": "BUY",
            "Prodaja": "SELL",
        }
        if "Reverse Split" in tx_type_raw:
            tx_type = "STOCK SPLIT"
        elif "Merger" in tx_type_raw and "denar" in tx_type_raw:
            tx_type = "MERGER CASH"
        elif "Merger" in tx_type_raw:
            tx_type = "MERGER"
        elif "Split" in tx_type_raw:
            tx_type = "STOCK SPLIT"
        elif "dividenda" in tx_type_lower or "dividend" in tx_type_lower:
            # "Davek" (tax) rows related to dividends → withholding tax correction
            if "davek" in tx_type_lower:
                tx_type = "DIVIDEND TAX"
            else:
                tx_type = "DIVIDEND"
        else:
            tx_type = type_map.get(tx_type_raw, tx_type_raw.upper())

        quantity = abs(
            _parse_eu_number(row.get("Volume")) or
            _parse_eu_number(row.get("VolumeValue")) or 0
        )
        price = _parse_eu_number(row.get("Price")) or _parse_eu_number(row.get("PriceValue"))

        if tx_type == "MERGER CASH":
            total_amount = price
            price = (price / quantity) if quantity else price
        elif tx_type in ("DIVIDEND", "DIVIDEND TAX"):
            # For dividends: Volume = shares held, Price = per-share dividend rate
            # total = Volume * Price; fallback to Price alone if Volume is 0/missing
            if quantity and price:
                total_amount = abs(quantity * price)
            elif price:
                total_amount = abs(price)
            else:
                total_amount = None
            quantity = quantity or None
        else:
            total_amount = quantity * price if quantity and price else None

        if tx_type == "STOCK SPLIT" and split_deltas:
            date_raw = str(row.get("DateValue") or row.get("SettlementDate", ""))
            key = (date_raw, ticker)
            quantity = split_deltas.get(key, quantity)

        return ParsedTrade(
            date=date,
            ticker=ticker,
            type=tx_type,
            quantity=quantity,
            price_per_share=price,
            total_amount=total_amount,
            currency=currency,
            fx_rate=1.0,
            asset_class="stock",
            broker_source="ilirika",
            raw_row=dict(row),
        )
