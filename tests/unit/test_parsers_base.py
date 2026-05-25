"""TDD Tasks 1-2: ParsedTrade dataclass and CsvAdapter/XmlAdapter ABCs."""

import pytest
from src.parsers.base import ParsedTrade, CsvAdapter, XmlAdapter, UnknownFormatError


# ---------------------------------------------------------------------------
# Task 1: ParsedTrade dataclass
# ---------------------------------------------------------------------------

class TestParsedTrade:
    def test_required_fields_only(self):
        t = ParsedTrade(date="2023-01-10", type="BUY", currency="USD")
        assert t.date == "2023-01-10"
        assert t.type == "BUY"
        assert t.currency == "USD"

    def test_defaults(self):
        t = ParsedTrade(date="2023-01-10", type="BUY", currency="USD")
        assert t.ticker is None
        assert t.quantity is None
        assert t.price_per_share is None
        assert t.total_amount is None
        assert t.fx_rate == 1.0
        assert t.asset_class == "stock"
        assert t.commission is None
        assert t.withholding_tax is None
        assert t.broker_source is None
        assert t.correlation_id is None
        assert t.raw_row == {}

    def test_full_fields(self):
        t = ParsedTrade(
            date="2023-01-10",
            type="BUY",
            currency="USD",
            ticker="AAPL",
            quantity=10.0,
            price_per_share=130.5,
            total_amount=1305.0,
            fx_rate=1.07,
            asset_class="stock",
            commission=1.30,
            withholding_tax=None,
            broker_source="ibkr",
            correlation_id=None,
            raw_row={"Symbol": "AAPL"},
        )
        assert t.ticker == "AAPL"
        assert t.quantity == 10.0
        assert t.price_per_share == 130.5
        assert t.total_amount == 1305.0
        assert t.fx_rate == 1.07
        assert t.commission == 1.30
        assert t.broker_source == "ibkr"

    def test_asset_classes(self):
        for ac in ("stock", "cfd", "crypto", "savings"):
            t = ParsedTrade(date="2023-01-01", type="BUY", currency="EUR", asset_class=ac)
            assert t.asset_class == ac

    def test_raw_row_isolated(self):
        """raw_row defaults to a fresh dict per instance."""
        t1 = ParsedTrade(date="2023-01-01", type="BUY", currency="EUR")
        t2 = ParsedTrade(date="2023-01-02", type="SELL", currency="EUR")
        t1.raw_row["x"] = 1
        assert "x" not in t2.raw_row


# ---------------------------------------------------------------------------
# Task 2: CsvAdapter and XmlAdapter ABCs
# ---------------------------------------------------------------------------

class TestCsvAdapterABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            CsvAdapter()  # type: ignore

    def test_concrete_subclass_must_implement_all_abstract(self):
        class Incomplete(CsvAdapter):
            @property
            def broker_name(self):
                return "incomplete"
            # Missing: detect, parse

        with pytest.raises(TypeError):
            Incomplete()

    def test_minimal_concrete_subclass(self):
        class Minimal(CsvAdapter):
            @property
            def broker_name(self):
                return "minimal"

            def detect(self, df):
                return True

            def parse(self, file_path):
                return []

        adapter = Minimal()
        assert adapter.broker_name == "minimal"
        assert adapter.detect(None) is True
        assert adapter.parse("x.csv") == []


class TestXmlAdapterABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            XmlAdapter()  # type: ignore

    def test_minimal_concrete_subclass(self):
        class MinimalXml(XmlAdapter):
            @property
            def broker_name(self):
                return "minimal_xml"

            def detect(self, root_tag, namespaces):
                return "FlexQueryResponse" in root_tag

            def parse(self, file_path):
                return []

        adapter = MinimalXml()
        assert adapter.broker_name == "minimal_xml"
        assert adapter.detect("FlexQueryResponse", {}) is True
        assert adapter.detect("SomethingElse", {}) is False


class TestUnknownFormatError:
    def test_is_exception(self):
        err = UnknownFormatError("no match")
        assert isinstance(err, Exception)
        assert "no match" in str(err)
