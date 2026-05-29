"""TDD Tasks 36-43: IBKR Phase 3 — Flex Query XML Parser."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"
FLEX_XML = FIXTURES / "ibkr_flex" / "flex_query.xml"


def _load_flex():
    from src.parsers.ibkr_flex import IbkrFlexAdapter
    from src.parsers.registry import BrokerRegistry
    reg = BrokerRegistry()
    reg.register(IbkrFlexAdapter())
    return reg.detect_and_parse(str(FLEX_XML))


# ---------------------------------------------------------------------------
# Task 36: Flex XML detection
# ---------------------------------------------------------------------------

class TestFlexXmlDetection:
    def test_detect_by_root_tag(self):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        adapter = IbkrFlexAdapter()
        assert adapter.detect("FlexQueryResponse", {}) is True

    def test_detect_rejects_other_root(self):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        adapter = IbkrFlexAdapter()
        assert adapter.detect("FlexStatements", {}) is False
        assert adapter.detect("Activities", {}) is False

    def test_detect_via_registry_xml_routing(self, tmp_path):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        from src.parsers.registry import BrokerRegistry
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(
            '<?xml version="1.0"?><FlexQueryResponse type="AF">'
            '<FlexStatements count="0"/></FlexQueryResponse>'
        )
        reg = BrokerRegistry()
        reg.register(IbkrFlexAdapter())
        trades = reg.detect_and_parse(str(xml_file))
        assert trades == []

    def test_broker_name(self):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        assert IbkrFlexAdapter().broker_name == "ibkr_flex"


# ---------------------------------------------------------------------------
# Task 37: Trade parsing — BUY / SELL
# ---------------------------------------------------------------------------

class TestFlexXmlTrades:
    def test_buy_parsed(self):
        trades = _load_flex()
        buys = [t for t in trades if t.type == "BUY"]
        assert len(buys) == 1
        assert buys[0].ticker == "AAPL"
        assert buys[0].quantity == pytest.approx(10.0)
        assert buys[0].price_per_share == pytest.approx(130.50)
        assert buys[0].total_amount == pytest.approx(1305.00)
        assert buys[0].commission == pytest.approx(1.30)
        assert buys[0].currency == "USD"
        assert buys[0].date == "2023-01-05"
        assert buys[0].broker_source == "ibkr_flex"
        assert buys[0].asset_class == "stock"

    def test_sell_parsed(self):
        trades = _load_flex()
        sells = [t for t in trades if t.type == "SELL"]
        assert len(sells) == 1
        assert sells[0].ticker == "MSFT"
        assert sells[0].quantity == pytest.approx(5.0)
        assert sells[0].commission == pytest.approx(1.40)
        assert sells[0].date == "2023-02-10"

    def test_options_skipped_with_warning(self):
        trades = _load_flex()
        tickers = [t.ticker for t in trades]
        assert "AAPL 20230101C130" not in tickers

    def test_options_emit_warning(self):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        from lxml import etree
        adapter = IbkrFlexAdapter()
        el = etree.fromstring(
            '<Trade assetCategory="OPT" symbol="AAPL 20230101C130" currency="USD"'
            ' tradeDate="20230106" quantity="1" tradePrice="1.50"'
            ' proceeds="-150.00" ibCommission="-0.65" buySell="BUY"/>'
        )
        with pytest.warns(UserWarning, match="OPT"):
            result = adapter._parse_trade(el)
        assert result is None


# ---------------------------------------------------------------------------
# Task 39: Dividends and withholding tax
# ---------------------------------------------------------------------------

class TestFlexXmlDividends:
    def test_dividend_parsed(self):
        trades = _load_flex()
        divs = [t for t in trades if t.type == "DIVIDEND"]
        assert len(divs) == 1
        assert divs[0].ticker == "AAPL"
        assert divs[0].total_amount == pytest.approx(23.00)
        assert divs[0].currency == "USD"
        assert divs[0].date == "2023-03-01"
        assert divs[0].broker_source == "ibkr_flex"

    def test_withholding_tax_linked_to_dividend(self):
        trades = _load_flex()
        div = next(t for t in trades if t.type == "DIVIDEND")
        assert div.withholding_tax == pytest.approx(3.45)


# ---------------------------------------------------------------------------
# Task 41: Corporate actions — split, merger, spinoff
# ---------------------------------------------------------------------------

class TestFlexXmlSplit:
    def test_split_parsed(self):
        trades = _load_flex()
        splits = [t for t in trades if t.type == "STOCK SPLIT"]
        assert len(splits) == 1
        assert splits[0].ticker == "AAPL"
        assert splits[0].quantity == pytest.approx(300.0)
        assert splits[0].date == "2023-06-01"
        assert splits[0].broker_source == "ibkr_flex"


class TestFlexXmlMerger:
    def test_merger_out_parsed(self):
        trades = _load_flex()
        out = [t for t in trades if t.type == "MERGER_OUT"]
        assert len(out) == 1
        assert out[0].ticker == "AAPL"
        assert out[0].quantity == pytest.approx(50.0)
        assert out[0].date == "2023-07-15"

    def test_merger_in_parsed(self):
        trades = _load_flex()
        inc = [t for t in trades if t.type == "MERGER_IN"]
        assert len(inc) == 1
        assert inc[0].ticker == "BETA"
        assert inc[0].quantity == pytest.approx(25.0)

    def test_merger_correlation_id_links_pair(self):
        trades = _load_flex()
        out = next(t for t in trades if t.type == "MERGER_OUT")
        inc = next(t for t in trades if t.type == "MERGER_IN")
        assert out.correlation_id is not None
        assert out.correlation_id == inc.correlation_id


class TestFlexXmlSpinoff:
    def test_spinoff_out_parsed(self):
        trades = _load_flex()
        out = [t for t in trades if t.type == "SPINOFF_OUT"]
        assert len(out) == 1
        assert out[0].ticker == "AAPL"
        assert out[0].quantity == pytest.approx(5.0)

    def test_spinoff_in_parsed(self):
        trades = _load_flex()
        inc = [t for t in trades if t.type == "SPINOFF_IN"]
        assert len(inc) == 1
        assert inc[0].ticker == "SPINCO"
        assert inc[0].quantity == pytest.approx(5.0)

    def test_spinoff_correlation_id_links_pair(self):
        trades = _load_flex()
        out = next(t for t in trades if t.type == "SPINOFF_OUT")
        inc = next(t for t in trades if t.type == "SPINOFF_IN")
        assert out.correlation_id is not None
        assert out.correlation_id == inc.correlation_id


# ---------------------------------------------------------------------------
# Task 43: Integration — total count and default registry
# ---------------------------------------------------------------------------

class TestFlexXmlIntegration:
    def test_total_trade_count(self):
        # 1 BUY + 1 SELL + 1 DIVIDEND + 1 STOCK SPLIT
        # + 1 MERGER_OUT + 1 MERGER_IN + 1 SPINOFF_OUT + 1 SPINOFF_IN = 8
        trades = _load_flex()
        assert len(trades) == 8

    def test_registered_in_default_registry(self):
        from src.parsers.default_registry import build_default_registry
        reg = build_default_registry()
        assert any(a.broker_name == "ibkr_flex" for a in reg.xml_adapters)

    def test_default_registry_parses_flex_xml(self):
        from src.parsers.default_registry import build_default_registry
        reg = build_default_registry()
        trades = reg.detect_and_parse(str(FLEX_XML))
        assert len(trades) == 8

    def test_all_trades_have_broker_source(self):
        trades = _load_flex()
        for t in trades:
            assert t.broker_source == "ibkr_flex"

    def test_all_trades_have_dates(self):
        trades = _load_flex()
        for t in trades:
            assert t.date and len(t.date) >= 10

    def test_date_normalisation_yyyymmdd(self):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        assert IbkrFlexAdapter._normalise_date("20230105") == "2023-01-05"

    def test_date_normalisation_with_time(self):
        from src.parsers.ibkr_flex import IbkrFlexAdapter
        assert IbkrFlexAdapter._normalise_date("2023-03-01;120000") == "2023-03-01"
