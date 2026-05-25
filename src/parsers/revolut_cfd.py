"""Revolut CFD CSV adapter."""

from __future__ import annotations

import pandas as pd

from .base import CsvAdapter, ParsedTrade
from .utils import _parse_amount


class RevolutCfdAdapter(CsvAdapter):
    """Parses Revolut CFD trading CSV exports."""

    @property
    def broker_name(self) -> str:
        return "revolut_cfd"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        return "Symbol" in columns and "Margin" in columns

    def parse(self, file_path: str) -> list[ParsedTrade]:
        df = pd.read_csv(file_path)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    def _parse_row(self, row) -> ParsedTrade | None:
        date = row.get("Date", "")
        if pd.isna(date) or not date:
            return None

        symbol = row.get("Symbol", None)
        if pd.isna(symbol):
            symbol = None

        # Strip :CFD suffix for storage
        ticker = None
        if symbol:
            ticker = str(symbol).replace(":CFD", "")

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

        return ParsedTrade(
            date=str(date),
            ticker=ticker,
            type=str(tx_type),
            quantity=quantity,
            price_per_share=price_per_share,
            total_amount=total_amount,
            currency=str(currency),
            fx_rate=fx_rate,
            asset_class="cfd",
            broker_source="revolut",
            raw_row=dict(row),
        )
