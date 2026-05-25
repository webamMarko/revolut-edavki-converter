"""Interactive Brokers Activity Statement CSV adapter."""

from __future__ import annotations

import pandas as pd

from .base import CsvAdapter, ParsedTrade


class IbkrAdapter(CsvAdapter):
    """Parses Interactive Brokers Activity Statement CSV exports.

    IBKR exports a multi-section CSV where each row begins with a section name
    (e.g. 'Trades'). Only 'Order' and 'Trade' DataDiscriminator rows are imported.
    """

    @property
    def broker_name(self) -> str:
        return "ibkr"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        return "Trades" in columns and "DataDiscriminator" in columns

    def parse(self, file_path: str) -> list[ParsedTrade]:
        df = pd.read_csv(file_path)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    def _parse_row(self, row) -> ParsedTrade | None:
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

        if quantity > 0:
            tx_type = "BUY"
        elif quantity < 0:
            tx_type = "SELL"
            quantity = abs(quantity)
        else:
            return None

        price_raw = row.get("T. Price")
        price = float(price_raw) if not pd.isna(price_raw) else None

        proceeds_raw = row.get("Proceeds")
        total_amount = abs(float(proceeds_raw)) if not pd.isna(proceeds_raw) else None

        currency = row.get("Currency", "USD")
        if pd.isna(currency):
            currency = "USD"

        # Commission
        comm_raw = row.get("Comm/Fee")
        commission = abs(float(comm_raw)) if not pd.isna(comm_raw) else None

        return ParsedTrade(
            date=date,
            ticker=ticker,
            type=tx_type,
            quantity=quantity,
            price_per_share=price,
            total_amount=total_amount,
            currency=str(currency),
            fx_rate=1.0,
            asset_class="stock",
            broker_source="ibkr",
            commission=commission,
            raw_row=dict(row),
        )
