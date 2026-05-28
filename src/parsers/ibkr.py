"""Interactive Brokers Activity Statement CSV adapter."""

from __future__ import annotations

import csv
import re
import warnings
from collections import defaultdict

import pandas as pd

from .base import CsvAdapter, ParsedTrade

# Corporate action type detection: matched against IBKR Description field
_CA_PATTERNS = [
    (re.compile(r"\bSPINOFF\b", re.IGNORECASE), "SPINOFF"),
    (re.compile(r"\bMERGER\b|\bMERGED\b|\bACQUISITION\b", re.IGNORECASE), "MERGER"),
    (re.compile(r"\bSPLIT\b", re.IGNORECASE), "SPLIT"),
    (re.compile(r"\bRIGHTS\b", re.IGNORECASE), "RIGHTS_ISSUE"),
]

_EQUITY_CATS = {"Stocks", "Equity"}
_UNSUPPORTED_CATS = {"Options", "Futures", "Forex", "Bonds", "Warrants", "Warrant"}


class IbkrAdapter(CsvAdapter):
    """Parses Interactive Brokers Activity Statement CSV exports.

    IBKR exports a multi-section CSV where each row begins with a section name.
    Handles: BUY/SELL trades, dividends (with optional withholding tax), stock
    splits, mergers (MERGER_OUT/MERGER_IN), spinoffs (SPINOFF_OUT/SPINOFF_IN),
    and rights issues. Options, futures, and forex are skipped with a warning.
    """

    @property
    def broker_name(self) -> str:
        return "ibkr"

    def detect(self, df: pd.DataFrame) -> bool:
        # When pandas reads an IBKR CSV, the Trades section header becomes the column
        # names: first column is "Trades", third is "DataDiscriminator".
        columns = set(df.columns)
        return "Trades" in columns and "DataDiscriminator" in columns

    def parse(self, file_path: str) -> list[ParsedTrade]:
        sections = self._read_sections(file_path)
        trades: list[ParsedTrade] = []

        if "Trades" in sections:
            for _, row in sections["Trades"].iterrows():
                parsed = self._parse_trade_row(row)
                if parsed is not None:
                    trades.append(parsed)

        if "Corporate Actions" in sections:
            trades.extend(self._parse_corporate_actions(sections["Corporate Actions"]))

        if "Dividends" in sections:
            dividends = self._collect_dividends(sections["Dividends"])
            withholding: dict[str, float] = {}
            if "Withholding Tax" in sections:
                withholding = self._collect_withholding(sections["Withholding Tax"])
            for key, div in dividends.items():
                if key in withholding:
                    div.withholding_tax = withholding[key]
                trades.append(div)

        return trades

    # ------------------------------------------------------------------
    # Multi-section CSV reader
    # ------------------------------------------------------------------

    def _read_sections(self, file_path: str) -> dict[str, pd.DataFrame]:
        """Parse an IBKR multi-section CSV into per-section DataFrames.

        Each IBKR CSV row starts with the section name (e.g. 'Trades') and a
        marker ('Header' | 'Data' | 'Order' | 'Trade').  This method groups rows
        by section and reconstructs a proper DataFrame per section.
        """
        raw: dict[str, dict] = defaultdict(lambda: {"header": None, "rows": []})

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or not row[0].strip():
                    continue
                section = row[0].strip()
                marker = row[1].strip() if len(row) > 1 else ""
                rest = row[2:]

                if marker == "Header":
                    raw[section]["header"] = rest
                elif marker in ("Data", "Order", "Trade"):
                    raw[section]["rows"].append(rest)

        result: dict[str, pd.DataFrame] = {}
        for section, data in raw.items():
            if data["header"] is not None:
                cols = data["header"]
                rows = data["rows"]
                if rows:
                    padded = [(r + [""] * len(cols))[:len(cols)] for r in rows]
                    result[section] = pd.DataFrame(padded, columns=cols)
                else:
                    result[section] = pd.DataFrame(columns=cols)

        return result

    # ------------------------------------------------------------------
    # Trades section
    # ------------------------------------------------------------------

    def _parse_trade_row(self, row) -> ParsedTrade | None:
        discriminator = row.get("DataDiscriminator", "")
        if pd.isna(discriminator) or str(discriminator) not in ("Order", "Trade"):
            return None

        asset_cat = str(row.get("Asset Category", "")).strip()
        if asset_cat in _UNSUPPORTED_CATS:
            warnings.warn(
                f"IBKR: skipping unsupported asset category '{asset_cat}'",
                UserWarning,
                stacklevel=3,
            )
            return None
        if asset_cat not in _EQUITY_CATS:
            return None

        date_str = row.get("Date/Time", "")
        if pd.isna(date_str) or not str(date_str).strip():
            return None
        date = str(date_str).replace(",", "").strip()

        symbol = row.get("Symbol", "")
        if pd.isna(symbol) or not str(symbol).strip():
            return None
        ticker = str(symbol).strip()

        quantity_raw = row.get("Quantity", "")
        if pd.isna(quantity_raw) or str(quantity_raw).strip() == "":
            return None
        try:
            quantity = float(str(quantity_raw).replace(",", ""))
        except ValueError:
            return None

        if quantity > 0:
            tx_type = "BUY"
        elif quantity < 0:
            tx_type = "SELL"
            quantity = abs(quantity)
        else:
            return None

        price_raw = row.get("T. Price", "")
        price = None
        if not pd.isna(price_raw) and str(price_raw).strip():
            try:
                price = float(str(price_raw).replace(",", ""))
            except ValueError:
                pass

        proceeds_raw = row.get("Proceeds", "")
        total_amount = None
        if not pd.isna(proceeds_raw) and str(proceeds_raw).strip():
            try:
                total_amount = abs(float(str(proceeds_raw).replace(",", "")))
            except ValueError:
                pass

        currency = str(row.get("Currency", "USD") or "USD").strip()
        if pd.isna(row.get("Currency")):
            currency = "USD"

        comm_raw = row.get("Comm/Fee", "")
        commission = None
        if not pd.isna(comm_raw) and str(comm_raw).strip():
            try:
                commission = abs(float(str(comm_raw).replace(",", "")))
            except ValueError:
                pass

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
            broker_source="ibkr",
            commission=commission,
            raw_row=dict(row),
        )

    # ------------------------------------------------------------------
    # Corporate Actions section
    # ------------------------------------------------------------------

    def _parse_corporate_actions(self, df: pd.DataFrame) -> list[ParsedTrade]:
        trades: list[ParsedTrade] = []
        for _, row in df.iterrows():
            result = self._parse_ca_row(row)
            if result is not None:
                trades.append(result)

        # Second pass: link MERGER/SPINOFF pairs by assigning shared correlation_id
        for ca_family, out_type, in_type in (
            ("MERGER", "MERGER_OUT", "MERGER_IN"),
            ("SPINOFF", "SPINOFF_OUT", "SPINOFF_IN"),
        ):
            out_by_date: dict[str, ParsedTrade] = {}
            for t in trades:
                if t.type == out_type:
                    out_by_date[t.date[:10]] = t

            for t in trades:
                if t.type == in_type:
                    date_key = t.date[:10]
                    if date_key in out_by_date:
                        corr = f"ibkr-{ca_family.lower()}-{date_key}"
                        out_by_date[date_key].correlation_id = corr
                        t.correlation_id = corr

        return trades

    def _parse_ca_row(self, row) -> ParsedTrade | None:
        asset_cat = str(row.get("Asset Category", "")).strip()
        if asset_cat in _UNSUPPORTED_CATS:
            warnings.warn(
                f"IBKR: skipping unsupported corporate action for '{asset_cat}'",
                UserWarning,
                stacklevel=4,
            )
            return None
        if asset_cat not in _EQUITY_CATS:
            return None

        description = str(row.get("Description", "")).strip()
        if not description:
            return None

        ticker_match = re.match(r"^([A-Z0-9.]+)(?:\([^)]+\))?", description)
        if not ticker_match:
            return None
        ticker = ticker_match.group(1)

        date_raw = str(row.get("Date/Time", "")).strip().replace(",", "")
        if not date_raw:
            date_raw = str(row.get("Report Date", "")).strip()
        if not date_raw:
            return None

        currency = str(row.get("Currency", "USD") or "USD").strip()

        quantity_raw = row.get("Quantity", "")
        try:
            quantity = float(str(quantity_raw).replace(",", ""))
        except (ValueError, TypeError):
            return None

        ca_type = self._detect_ca_type(description)
        if ca_type is None:
            warnings.warn(
                f"IBKR: unrecognised corporate action '{description[:60]}', skipping",
                UserWarning,
                stacklevel=4,
            )
            return None

        if ca_type == "SPLIT":
            tx_type = "STOCK SPLIT"
        elif ca_type == "MERGER":
            tx_type = "MERGER_OUT" if quantity < 0 else "MERGER_IN"
        elif ca_type == "SPINOFF":
            tx_type = "SPINOFF_OUT" if quantity < 0 else "SPINOFF_IN"
        else:  # RIGHTS_ISSUE
            tx_type = "RIGHTS_ISSUE"

        return ParsedTrade(
            date=date_raw,
            ticker=ticker,
            type=tx_type,
            quantity=abs(quantity),
            price_per_share=None,
            total_amount=None,
            currency=currency,
            fx_rate=1.0,
            asset_class="stock",
            broker_source="ibkr",
            raw_row=dict(row),
        )

    def _detect_ca_type(self, description: str) -> str | None:
        for pattern, ca_type in _CA_PATTERNS:
            if pattern.search(description):
                return ca_type
        return None

    # ------------------------------------------------------------------
    # Dividends section
    # ------------------------------------------------------------------

    def _collect_dividends(self, df: pd.DataFrame) -> dict[str, ParsedTrade]:
        result: dict[str, ParsedTrade] = {}
        for _, row in df.iterrows():
            key, trade = self._parse_dividend_row(row)
            if trade is not None:
                result[key] = trade
        return result

    def _parse_dividend_row(self, row) -> tuple[str, ParsedTrade | None]:
        currency = str(row.get("Currency", "")).strip()
        date_str = str(row.get("Date", "")).strip()
        description = str(row.get("Description", "")).strip()

        if not date_str or not description:
            return ("", None)

        ticker_match = re.match(r"^([A-Z0-9.]+)(?:\([^)]+\))?", description)
        if not ticker_match:
            return ("", None)
        ticker = ticker_match.group(1)

        amount_raw = row.get("Amount", "")
        try:
            amount = float(str(amount_raw).replace(",", ""))
        except (ValueError, TypeError):
            return ("", None)

        key = f"{currency}_{date_str}_{ticker}"
        return (key, ParsedTrade(
            date=date_str,
            ticker=ticker,
            type="DIVIDEND",
            quantity=None,
            price_per_share=None,
            total_amount=abs(amount),
            currency=currency,
            fx_rate=1.0,
            asset_class="stock",
            broker_source="ibkr",
            raw_row=dict(row),
        ))

    # ------------------------------------------------------------------
    # Withholding Tax section
    # ------------------------------------------------------------------

    def _collect_withholding(self, df: pd.DataFrame) -> dict[str, float]:
        result: dict[str, float] = {}
        for _, row in df.iterrows():
            key, tax = self._parse_withholding_row(row)
            if key and tax is not None:
                result[key] = tax
        return result

    def _parse_withholding_row(self, row) -> tuple[str, float | None]:
        currency = str(row.get("Currency", "")).strip()
        date_str = str(row.get("Date", "")).strip()
        description = str(row.get("Description", "")).strip()

        if not date_str or not description:
            return ("", None)

        ticker_match = re.match(r"^([A-Z0-9.]+)(?:\([^)]+\))?", description)
        if not ticker_match:
            return ("", None)
        ticker = ticker_match.group(1)

        amount_raw = row.get("Amount", "")
        try:
            amount = abs(float(str(amount_raw).replace(",", "")))
        except (ValueError, TypeError):
            return ("", None)

        return (f"{currency}_{date_str}_{ticker}", amount)
