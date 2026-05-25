"""Degiro CSV adapter."""

from __future__ import annotations

from datetime import datetime as dt

import pandas as pd

from .base import CsvAdapter, ParsedTrade


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

_EUR_EXCHANGES = {
    "AEX", "XET", "FRA", "MIL", "EPA", "BME",
    "XAMS", "XETR", "XFRA", "XMIL", "XPAR", "XMCE",
}

# Well-known ISIN -> ticker mappings (covers most popular retail holdings)
_ISIN_MAP = {
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


def _degiro_ticker(product: str, isin: str, exchange: str) -> str:
    """Derive a yfinance-compatible ticker from Degiro product/ISIN/exchange."""
    ticker = _ISIN_MAP.get(isin)
    if ticker:
        return ticker
    suffix = _DEGIRO_EXCHANGE_SUFFIXES.get(exchange, "")
    return isin + suffix


class DegiroAdapter(CsvAdapter):
    """Parses Degiro Account Statement CSV exports."""

    @property
    def broker_name(self) -> str:
        return "degiro"

    def detect(self, df: pd.DataFrame) -> bool:
        columns = set(df.columns)
        return "Datum" in columns and "Product" in columns and "ISIN" in columns

    def parse(self, file_path: str) -> list[ParsedTrade]:
        df = pd.read_csv(file_path)
        trades = []
        for _, row in df.iterrows():
            parsed = self._parse_row(row)
            if parsed is not None:
                trades.append(parsed)
        return trades

    def _parse_row(self, row) -> ParsedTrade | None:
        date_str = row.get("Datum", "")
        if pd.isna(date_str) or not date_str:
            return None

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

        if quantity > 0:
            tx_type = "BUY"
        elif quantity < 0:
            tx_type = "SELL"
            quantity = abs(quantity)
        else:
            return None

        price_raw = row.get("Koers")
        price = float(price_raw) if not pd.isna(price_raw) else None

        waarde_raw = row.get("Waarde")
        if not pd.isna(waarde_raw) and waarde_raw != "":
            total_amount = abs(float(waarde_raw))
        elif quantity and price:
            total_amount = quantity * price
        else:
            total_amount = None

        currency = "EUR" if exchange in _EUR_EXCHANGES else "USD"

        fx_raw = row.get("Wisselkoers")
        if not pd.isna(fx_raw) and fx_raw != "" and fx_raw is not None:
            try:
                fx_rate = float(str(fx_raw).replace(",", "."))
            except (ValueError, TypeError):
                fx_rate = 1.0
        else:
            fx_rate = 1.0

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
            broker_source="degiro",
            raw_row=dict(row),
        )
