"""Revolut stock CSV adapter."""

from __future__ import annotations

import pandas as pd

from .base import CsvAdapter, ParsedTrade
from .utils import _parse_amount


class RevolutStockAdapter(CsvAdapter):
    """Parses Revolut stock trading CSV exports."""

    @property
    def broker_name(self) -> str:
        return "revolut_stock"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        # Stock CSVs have a Ticker column and Price per share
        if "Ticker" in columns and "Price per share" in columns:
            return True
        # Older Revolut format: Started Date + Type + Product
        if "Started Date" in columns and "Type" in columns and "Product" in columns:
            return True
        return False

    def parse(self, file_path: str) -> list[ParsedTrade]:
        path_obj = __import__("pathlib").Path(file_path)
        suffix = path_obj.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)

        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    def _parse_row(self, row) -> ParsedTrade | None:
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

        return ParsedTrade(
            date=str(date),
            ticker=str(ticker) if ticker else None,
            type=str(tx_type),
            quantity=quantity,
            price_per_share=price_per_share,
            total_amount=total_amount,
            currency=str(currency),
            fx_rate=fx_rate,
            asset_class="stock",
            broker_source="revolut",
            raw_row=dict(row),
        )
