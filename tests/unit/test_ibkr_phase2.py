"""TDD Tasks 16-35: IBKR Phase 2 — corporate actions, dividends, multi-currency."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_full_activity():
    from src.parsers.ibkr import IbkrAdapter
    from src.parsers.registry import BrokerRegistry
    reg = BrokerRegistry()
    reg.register(IbkrAdapter())
    return reg.detect_and_parse(str(FIXTURES / "ibkr" / "full_activity.csv"))


# ---------------------------------------------------------------------------
# Task 16-17: Dividends + withholding tax
# ---------------------------------------------------------------------------

class TestIbkrDividends:
    def test_dividend_parsed(self):
        trades = _load_full_activity()
        divs = [t for t in trades if t.type == "DIVIDEND"]
        assert len(divs) == 1
        assert divs[0].ticker == "AAPL"
        assert divs[0].total_amount == pytest.approx(23.00)
        assert divs[0].currency == "USD"
        assert divs[0].date == "2023-03-01"
        assert divs[0].broker_source == "ibkr"

    def test_withholding_tax_linked_to_dividend(self):
        trades = _load_full_activity()
        div = next(t for t in trades if t.type == "DIVIDEND")
        assert div.withholding_tax == pytest.approx(3.45)


# ---------------------------------------------------------------------------
# Task 18: Stock split
# ---------------------------------------------------------------------------

class TestIbkrStockSplit:
    def test_split_type(self):
        trades = _load_full_activity()
        splits = [t for t in trades if t.type == "STOCK SPLIT"]
        assert len(splits) == 1

    def test_split_ticker_and_quantity(self):
        trades = _load_full_activity()
        split = next(t for t in trades if t.type == "STOCK SPLIT")
        assert split.ticker == "AAPL"
        assert split.quantity == pytest.approx(300.0)
        assert split.broker_source == "ibkr"


# ---------------------------------------------------------------------------
# Tasks 19-21: MERGER_OUT, MERGER_IN, correlation_id
# ---------------------------------------------------------------------------

class TestIbkrMerger:
    def test_merger_out_parsed(self):
        trades = _load_full_activity()
        out = [t for t in trades if t.type == "MERGER_OUT"]
        assert len(out) == 1
        assert out[0].ticker == "AAPL"
        assert out[0].quantity == pytest.approx(50.0)

    def test_merger_in_parsed(self):
        trades = _load_full_activity()
        inc = [t for t in trades if t.type == "MERGER_IN"]
        assert len(inc) == 1
        assert inc[0].ticker == "BETA"
        assert inc[0].quantity == pytest.approx(25.0)

    def test_merger_correlation_id_links_pair(self):
        trades = _load_full_activity()
        out = next(t for t in trades if t.type == "MERGER_OUT")
        inc = next(t for t in trades if t.type == "MERGER_IN")
        assert out.correlation_id is not None
        assert out.correlation_id == inc.correlation_id


# ---------------------------------------------------------------------------
# Tasks 22-24: SPINOFF_OUT, SPINOFF_IN, correlation_id
# ---------------------------------------------------------------------------

class TestIbkrSpinoff:
    def test_spinoff_out_parsed(self):
        trades = _load_full_activity()
        out = [t for t in trades if t.type == "SPINOFF_OUT"]
        assert len(out) == 1
        assert out[0].ticker == "AAPL"
        assert out[0].quantity == pytest.approx(5.0)

    def test_spinoff_in_parsed(self):
        trades = _load_full_activity()
        inc = [t for t in trades if t.type == "SPINOFF_IN"]
        assert len(inc) == 1
        assert inc[0].ticker == "SPINCO"
        assert inc[0].quantity == pytest.approx(5.0)

    def test_spinoff_correlation_id_links_pair(self):
        trades = _load_full_activity()
        out = next(t for t in trades if t.type == "SPINOFF_OUT")
        inc = next(t for t in trades if t.type == "SPINOFF_IN")
        assert out.correlation_id is not None
        assert out.correlation_id == inc.correlation_id


# ---------------------------------------------------------------------------
# Task 25: RIGHTS_ISSUE
# ---------------------------------------------------------------------------

class TestIbkrRightsIssue:
    def test_rights_issue_parsed(self):
        trades = _load_full_activity()
        rights = [t for t in trades if t.type == "RIGHTS_ISSUE"]
        assert len(rights) == 1
        assert rights[0].ticker == "AAPL"
        assert rights[0].quantity == pytest.approx(10.0)
        assert rights[0].broker_source == "ibkr"


# ---------------------------------------------------------------------------
# Tasks 26-27: Skip unsupported asset categories with warnings
# ---------------------------------------------------------------------------

class TestIbkrSkipUnsupported:
    def test_skips_options_with_warning(self):
        import pandas as pd
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        row = pd.Series({
            "DataDiscriminator": "Order",
            "Asset Category": "Options",
            "Currency": "USD",
            "Symbol": "AAPL 20230101C130",
            "Date/Time": "2023-01-01 10:00:00",
            "Quantity": 1,
            "T. Price": 1.50,
            "Proceeds": -150.00,
            "Comm/Fee": -0.65,
        })
        with pytest.warns(UserWarning, match="Options"):
            result = adapter._parse_trade_row(row)
        assert result is None

    def test_skips_futures_with_warning(self):
        import pandas as pd
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        row = pd.Series({
            "DataDiscriminator": "Order",
            "Asset Category": "Futures",
            "Currency": "USD",
            "Symbol": "ESZ3",
            "Date/Time": "2023-01-01 10:00:00",
            "Quantity": 1,
            "T. Price": 4000.0,
            "Proceeds": -200000.00,
            "Comm/Fee": -1.00,
        })
        with pytest.warns(UserWarning, match="Futures"):
            result = adapter._parse_trade_row(row)
        assert result is None


# ---------------------------------------------------------------------------
# Tasks 28-29: Multi-section CSV count and trade integrity
# ---------------------------------------------------------------------------

class TestIbkrMultiSection:
    def test_total_trade_count(self):
        # 2 trades + 1 split + 1 merger_out + 1 merger_in + 1 spinoff_out
        # + 1 spinoff_in + 1 rights_issue + 1 dividend = 9
        trades = _load_full_activity()
        assert len(trades) == 9

    def test_trades_preserved_in_full_activity(self):
        trades = _load_full_activity()
        buy = next(t for t in trades if t.type == "BUY" and t.ticker == "AAPL")
        assert buy.quantity == pytest.approx(10.0)
        assert buy.commission == pytest.approx(1.30)
        assert buy.price_per_share == pytest.approx(130.50)

    def test_sell_preserved_in_full_activity(self):
        trades = _load_full_activity()
        sell = next(t for t in trades if t.type == "SELL" and t.ticker == "MSFT")
        assert sell.quantity == pytest.approx(5.0)
        assert sell.commission == pytest.approx(1.40)


# ---------------------------------------------------------------------------
# Tasks 30-32: _read_sections + backward compat
# ---------------------------------------------------------------------------

class TestIbkrSectionReader:
    def test_read_sections_contains_trades(self):
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        sections = adapter._read_sections(str(FIXTURES / "ibkr" / "full_activity.csv"))
        assert "Trades" in sections
        assert "DataDiscriminator" in sections["Trades"].columns

    def test_read_sections_contains_dividends(self):
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        sections = adapter._read_sections(str(FIXTURES / "ibkr" / "full_activity.csv"))
        assert "Dividends" in sections
        assert "Amount" in sections["Dividends"].columns

    def test_read_sections_contains_corporate_actions(self):
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        sections = adapter._read_sections(str(FIXTURES / "ibkr" / "full_activity.csv"))
        assert "Corporate Actions" in sections
        assert "Description" in sections["Corporate Actions"].columns

    def test_backward_compat_trades_only_fixture(self):
        """Existing trades.csv fixture must still yield exactly 2 trades."""
        from src.parsers.ibkr import IbkrAdapter
        from src.parsers.registry import BrokerRegistry
        reg = BrokerRegistry()
        reg.register(IbkrAdapter())
        trades = reg.detect_and_parse(str(FIXTURES / "ibkr" / "trades.csv"))
        assert len(trades) == 2
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.ticker == "AAPL"
        assert buy.commission == pytest.approx(1.30)


# ---------------------------------------------------------------------------
# Task 33: _parse_trade_row interface
# ---------------------------------------------------------------------------

class TestIbkrTradeRowInterface:
    def test_parse_trade_row_subtotal_skipped(self):
        import pandas as pd
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        row = pd.Series({
            "DataDiscriminator": "SubTotal",
            "Asset Category": "Stocks",
            "Currency": "USD",
            "Symbol": "",
            "Date/Time": "",
            "Quantity": None,
        })
        assert adapter._parse_trade_row(row) is None

    def test_parse_trade_row_zero_quantity_skipped(self):
        import pandas as pd
        from src.parsers.ibkr import IbkrAdapter
        adapter = IbkrAdapter()
        row = pd.Series({
            "DataDiscriminator": "Order",
            "Asset Category": "Stocks",
            "Currency": "USD",
            "Symbol": "AAPL",
            "Date/Time": "2023-01-01 10:00:00",
            "Quantity": 0,
            "T. Price": 130.50,
            "Proceeds": 0,
            "Comm/Fee": 0,
        })
        assert adapter._parse_trade_row(row) is None
