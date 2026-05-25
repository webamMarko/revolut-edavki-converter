"""Revolut crypto CSV adapter."""

from __future__ import annotations

import pandas as pd

from .base import CsvAdapter, ParsedTrade
from .utils import _parse_amount, _parse_eur_amount, _parse_crypto_date


class RevolutCryptoAdapter(CsvAdapter):
    """Parses Revolut crypto trading CSV exports."""

    @property
    def broker_name(self) -> str:
        return "revolut_crypto"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        return (
            "Symbol" in columns
            and "Value" in columns
            and "Ticker" not in columns
            and "Margin" not in columns
        )

    def parse(self, file_path: str) -> list[ParsedTrade]:
        df = pd.read_csv(file_path)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    _TYPE_MAP = {
        "Buy": "BUY",
        "Sell": "SELL",
        "Staking reward": "STAKING REWARD",
        "Learn reward": "LEARN REWARD",
        "Payment": "PAYMENT",
        "Receive": "RECEIVE",
        "Stake": "STAKE",
    }

    def _parse_row(self, row) -> ParsedTrade | None:
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

        mapped_type = self._TYPE_MAP.get(str(tx_type), str(tx_type).upper())

        quantity = _parse_amount(row.get("Quantity"))
        price = _parse_eur_amount(row.get("Price"))
        value = _parse_eur_amount(row.get("Value"))

        return ParsedTrade(
            date=date,
            ticker=ticker,
            type=mapped_type,
            quantity=quantity,
            price_per_share=price,
            total_amount=value,
            currency="EUR",
            fx_rate=1.0,
            asset_class="crypto",
            broker_source="revolut",
            raw_row=dict(row),
        )
