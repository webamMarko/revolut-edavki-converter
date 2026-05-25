"""Trading 212 CSV adapter."""

from __future__ import annotations

import pandas as pd

from .base import CsvAdapter, ParsedTrade


class Trading212Adapter(CsvAdapter):
    """Parses Trading 212 CSV exports."""

    @property
    def broker_name(self) -> str:
        return "trading212"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        return (
            "Action" in columns
            and "No. of shares" in columns
            and "Price / share" in columns
        )

    def parse(self, file_path: str) -> list[ParsedTrade]:
        df = pd.read_csv(file_path)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    def _parse_row(self, row) -> ParsedTrade | None:
        action = row.get("Action", "")
        if pd.isna(action) or not action:
            return None

        action_lower = str(action).strip().lower()
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

        fx_rate_raw = row.get("Exchange rate")
        if not pd.isna(fx_rate_raw) and fx_rate_raw != "":
            fx_rate = float(fx_rate_raw)
        else:
            fx_rate = 1.0

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

        return ParsedTrade(
            date=date,
            ticker=ticker,
            type=tx_type,
            quantity=quantity,
            price_per_share=price,
            total_amount=total_amount,
            currency=currency,
            fx_rate=fx_rate,
            asset_class="stock",
            broker_source="trading212",
            raw_row=dict(row),
        )
