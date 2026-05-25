"""Revolut savings CSV adapter."""

from __future__ import annotations

import re

import pandas as pd

from .base import CsvAdapter, ParsedTrade
from .utils import _parse_crypto_date


def _parse_savings_amount(value) -> float | None:
    """Parse a savings amount that may have commas as thousands separators."""
    if pd.isna(value) or value == "" or value is None:
        return None
    s = str(value).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


class RevolutSavingsAdapter(CsvAdapter):
    """Parses Revolut savings (money market fund) CSV exports."""

    @property
    def broker_name(self) -> str:
        return "revolut_savings"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        if "Description" not in columns or "Symbol" in columns or "Ticker" in columns:
            return False
        # Savings: Description contains fund class info like "BUY USD Class R IE000H9J0QX4"
        return bool(df["Description"].str.contains("Class", na=False).any())

    def parse(self, file_path: str) -> list[ParsedTrade]:
        df = pd.read_csv(file_path)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    _TYPE_PATTERNS = [
        ("BUY", "BUY"),
        ("SELL", "SELL"),
        ("Interest Reinvested", "INTEREST REINVESTED"),
        ("Interest WITHDRAWN", "INTEREST WITHDRAWN"),
        ("Interest PAID", "INTEREST PAID"),
        ("Service Fee Charged", "SERVICE FEE"),
    ]

    def _parse_row(self, row) -> ParsedTrade | None:
        date_str = row.get("Date", "")
        if pd.isna(date_str) or not date_str or date_str == "Date":
            return None  # skip re-header rows

        date = _parse_crypto_date(date_str)  # same date format as crypto
        if not date:
            return None

        desc = str(row.get("Description", ""))
        if not desc:
            return None

        # Determine currency class from description
        if " EUR " in desc or desc.endswith(" EUR"):
            currency = "EUR"
        elif " GBP " in desc or desc.endswith(" GBP"):
            currency = "GBP"
        else:
            currency = "USD"

        # Extract type
        tx_type = None
        for pattern, mapped in self._TYPE_PATTERNS:
            if desc.startswith(pattern):
                tx_type = mapped
                break
        if not tx_type:
            return None

        # Extract ISIN from description
        isin_match = re.search(r'(IE\w+)', desc)
        ticker = isin_match.group(1) if isin_match else currency

        # Parse values based on currency class
        raw_val_usd = row.get("Value, USD")
        raw_val_eur = row.get("Value, EUR")
        raw_fx = row.get("FX Rate")
        raw_qty = row.get("Quantity of shares")

        if currency == "EUR":
            # EUR section: positional columns are shifted
            value_eur = _parse_savings_amount(raw_val_usd)
            qty = _parse_savings_amount(raw_fx)
            fx_rate = 1.0
        elif currency == "GBP":
            value_eur = _parse_savings_amount(raw_val_eur)
            qty = _parse_savings_amount(raw_qty)
            gbp_val = _parse_savings_amount(raw_val_usd)
            fx_rate = (
                abs(value_eur / gbp_val)
                if gbp_val and gbp_val != 0 and value_eur
                else _parse_savings_amount(raw_fx) or 1.0
            )
        else:
            # USD section: standard columns
            value_eur = _parse_savings_amount(raw_val_eur)
            qty = _parse_savings_amount(raw_qty)
            fx_rate = _parse_savings_amount(raw_fx) or 1.0

        # Fallbacks
        if value_eur is None and currency == "EUR":
            value_eur = _parse_savings_amount(raw_val_usd)
        if value_eur is None and currency == "USD":
            usd_val = _parse_savings_amount(raw_val_usd)
            if usd_val is not None and fx_rate:
                value_eur = usd_val * fx_rate

        abs_qty = abs(qty) if qty else None
        abs_value = abs(value_eur) if value_eur else None

        # Price per share in EUR
        if abs_qty and abs_value and abs_qty > 0:
            pps_eur = abs_value / abs_qty
        else:
            pps_eur = 1.0

        return ParsedTrade(
            date=date,
            ticker=ticker,
            type=tx_type,
            quantity=abs_qty,
            price_per_share=pps_eur,
            total_amount=abs_value,
            currency="EUR",
            fx_rate=1.0,
            asset_class="savings",
            broker_source="revolut",
            raw_row=dict(row),
        )
