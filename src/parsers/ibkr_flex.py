"""Interactive Brokers Flex Query XML adapter."""

from __future__ import annotations

import re
import warnings

from lxml import etree

from .base import ParsedTrade, XmlAdapter

_CA_PATTERNS = [
    (re.compile(r"\bSPINOFF\b", re.IGNORECASE), "SPINOFF"),
    (re.compile(r"\bMERGER\b|\bMERGED\b|\bACQUISITION\b", re.IGNORECASE), "MERGER"),
    (re.compile(r"\bSPLIT\b", re.IGNORECASE), "SPLIT"),
    (re.compile(r"\bRIGHTS\b", re.IGNORECASE), "RIGHTS_ISSUE"),
]

_EQUITY_CATS = {"STK", "Stocks", "Equity"}
_UNSUPPORTED_CATS = {"OPT", "Options", "FUT", "Futures", "CASH", "Forex", "BOND", "Bonds"}


class IbkrFlexAdapter(XmlAdapter):
    """Parses Interactive Brokers Flex Query XML exports.

    Handles Trade (BUY/SELL), CashTransaction (dividends + withholding tax),
    and CorporateAction (splits, mergers, spinoffs) elements across one or more
    FlexStatement sections.
    """

    @property
    def broker_name(self) -> str:
        return "ibkr_flex"

    def detect(self, root_tag: str, namespaces: dict) -> bool:
        local = root_tag.split("}")[-1] if "}" in root_tag else root_tag
        return local == "FlexQueryResponse"

    def parse(self, file_path: str) -> list[ParsedTrade]:
        tree = etree.parse(file_path)
        root = tree.getroot()

        trades: list[ParsedTrade] = []

        for trade_el in root.iter("Trade"):
            parsed = self._parse_trade(trade_el)
            if parsed is not None:
                trades.append(parsed)

        dividends: dict[str, ParsedTrade] = {}
        withholding: dict[str, float] = {}
        for cash_el in root.iter("CashTransaction"):
            self._process_cash_transaction(cash_el, dividends, withholding)
        for key, div in dividends.items():
            if key in withholding:
                div.withholding_tax = withholding[key]
            trades.append(div)

        ca_trades = self._parse_corporate_actions(root)
        trades.extend(ca_trades)

        return trades

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def _parse_trade(self, el) -> ParsedTrade | None:
        asset_cat = el.get("assetCategory", "").strip()
        if asset_cat in _UNSUPPORTED_CATS:
            warnings.warn(
                f"IBKR Flex: skipping unsupported asset category '{asset_cat}'",
                UserWarning,
                stacklevel=3,
            )
            return None
        if asset_cat not in _EQUITY_CATS:
            return None

        buy_sell = el.get("buySell", "").strip().upper()
        if buy_sell not in ("BUY", "SELL"):
            return None

        symbol = el.get("symbol", "").strip()
        if not symbol:
            return None

        date_raw = el.get("tradeDate", "").strip()
        if not date_raw:
            return None
        date = self._normalise_date(date_raw)

        currency = el.get("currency", "USD").strip() or "USD"

        quantity_raw = el.get("quantity", "").replace(",", "")
        try:
            quantity = abs(float(quantity_raw))
        except (ValueError, TypeError):
            return None

        price_raw = el.get("tradePrice", "").replace(",", "")
        price = None
        try:
            price = float(price_raw)
        except (ValueError, TypeError):
            pass

        proceeds_raw = el.get("proceeds", "").replace(",", "")
        total_amount = None
        try:
            total_amount = abs(float(proceeds_raw))
        except (ValueError, TypeError):
            pass

        comm_raw = el.get("ibCommission", "").replace(",", "")
        commission = None
        try:
            commission = abs(float(comm_raw))
        except (ValueError, TypeError):
            pass

        return ParsedTrade(
            date=date,
            ticker=symbol,
            type=buy_sell,
            quantity=quantity,
            price_per_share=price,
            total_amount=total_amount,
            currency=currency,
            fx_rate=1.0,
            asset_class="stock",
            broker_source="ibkr_flex",
            commission=commission,
            raw_row={k: v for k, v in el.attrib.items()},
        )

    # ------------------------------------------------------------------
    # Cash transactions (dividends + withholding tax)
    # ------------------------------------------------------------------

    def _process_cash_transaction(
        self,
        el,
        dividends: dict[str, ParsedTrade],
        withholding: dict[str, float],
    ) -> None:
        tx_type = el.get("type", "").strip()
        symbol = el.get("symbol", "").strip()
        currency = el.get("currency", "USD").strip() or "USD"
        date_raw = el.get("dateTime", "").strip()
        if not date_raw:
            return
        date = self._normalise_date(date_raw)

        amount_raw = el.get("amount", "").replace(",", "")
        try:
            amount = float(amount_raw)
        except (ValueError, TypeError):
            return

        key = f"{currency}_{date}_{symbol}"

        if tx_type == "Dividends":
            if not symbol:
                return
            dividends[key] = ParsedTrade(
                date=date,
                ticker=symbol,
                type="DIVIDEND",
                quantity=None,
                price_per_share=None,
                total_amount=abs(amount),
                currency=currency,
                fx_rate=1.0,
                asset_class="stock",
                broker_source="ibkr_flex",
                raw_row={k: v for k, v in el.attrib.items()},
            )
        elif tx_type == "Withholding Tax":
            if not symbol:
                return
            withholding[key] = abs(amount)

    # ------------------------------------------------------------------
    # Corporate actions
    # ------------------------------------------------------------------

    def _parse_corporate_actions(self, root) -> list[ParsedTrade]:
        trades: list[ParsedTrade] = []

        for ca_el in root.iter("CorporateAction"):
            result = self._parse_ca(ca_el)
            if result is not None:
                trades.append(result)

        # Link MERGER and SPINOFF pairs with shared correlation_id
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
                        corr = f"ibkr_flex-{ca_family.lower()}-{date_key}"
                        out_by_date[date_key].correlation_id = corr
                        t.correlation_id = corr

        return trades

    def _parse_ca(self, el) -> ParsedTrade | None:
        asset_cat = el.get("assetCategory", "").strip()
        if asset_cat in _UNSUPPORTED_CATS:
            warnings.warn(
                f"IBKR Flex: skipping unsupported corporate action for '{asset_cat}'",
                UserWarning,
                stacklevel=4,
            )
            return None
        if asset_cat not in _EQUITY_CATS:
            return None

        description = el.get("description", "").strip()
        if not description:
            return None

        symbol = el.get("symbol", "").strip()
        if not symbol:
            ticker_match = re.match(r"^([A-Z0-9.]+)(?:\([^)]+\))?", description)
            if not ticker_match:
                return None
            symbol = ticker_match.group(1)

        date_raw = el.get("dateTime", "").strip()
        if not date_raw:
            return None
        date = self._normalise_date(date_raw)

        currency = el.get("currency", "USD").strip() or "USD"

        quantity_raw = el.get("quantity", "").replace(",", "")
        try:
            quantity = float(quantity_raw)
        except (ValueError, TypeError):
            return None

        ca_type = self._detect_ca_type(description)
        if ca_type is None:
            warnings.warn(
                f"IBKR Flex: unrecognised corporate action '{description[:60]}', skipping",
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
        else:
            tx_type = "RIGHTS_ISSUE"

        return ParsedTrade(
            date=date,
            ticker=symbol,
            type=tx_type,
            quantity=abs(quantity),
            price_per_share=None,
            total_amount=None,
            currency=currency,
            fx_rate=1.0,
            asset_class="stock",
            broker_source="ibkr_flex",
            raw_row={k: v for k, v in el.attrib.items()},
        )

    def _detect_ca_type(self, description: str) -> str | None:
        for pattern, ca_type in _CA_PATTERNS:
            if pattern.search(description):
                return ca_type
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_date(raw: str) -> str:
        """Convert YYYYMMDD or YYYY-MM-DD[;HH...] to YYYY-MM-DD."""
        raw = raw.split(";")[0].strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw[:10]
