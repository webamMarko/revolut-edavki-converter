"""TDD Task 3: BrokerRegistry — register, two-stage detect, parse delegation, UnknownFormatError."""

import os
import tempfile

import pytest

from src.parsers.base import CsvAdapter, XmlAdapter, ParsedTrade, UnknownFormatError
from src.parsers.registry import BrokerRegistry


# ---------------------------------------------------------------------------
# Helpers / stub adapters
# ---------------------------------------------------------------------------

class _StockCsvAdapter(CsvAdapter):
    @property
    def broker_name(self):
        return "stub_stock"

    def detect(self, df):
        return "Ticker" in df.columns and "Price per share" in df.columns

    def parse(self, file_path):
        return [ParsedTrade(date="2023-01-01", type="BUY", currency="USD", ticker="AAPL")]


class _CfdCsvAdapter(CsvAdapter):
    @property
    def broker_name(self):
        return "stub_cfd"

    def detect(self, df):
        return "Symbol" in df.columns and "Margin" in df.columns

    def parse(self, file_path):
        return [ParsedTrade(date="2023-01-01", type="BUY", currency="USD", ticker="TSLA")]


class _XmlAdapter(XmlAdapter):
    @property
    def broker_name(self):
        return "stub_xml"

    def detect(self, root_tag, namespaces):
        return "FlexQueryResponse" in root_tag

    def parse(self, file_path):
        return [ParsedTrade(date="2023-01-01", type="BUY", currency="USD", ticker="IBM")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STOCK_CSV_CONTENT = "Ticker,Price per share,Type\nAAPL,130.5,BUY\n"
CFD_CSV_CONTENT = "Symbol,Margin,Type\nTSLA:CFD,100,BUY\n"
XML_CONTENT = b"""<?xml version="1.0"?>
<FlexQueryResponse><Trades><Trade symbol="IBM"/></Trades></FlexQueryResponse>"""


@pytest.fixture
def registry():
    reg = BrokerRegistry()
    reg.register(_StockCsvAdapter())
    reg.register(_CfdCsvAdapter())
    reg.register(_XmlAdapter())
    return reg


def _write_tmp(content, suffix):
    f = tempfile.NamedTemporaryFile(mode="w" if isinstance(content, str) else "wb",
                                    suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBrokerRegistryRegister:
    def test_register_csv_adapter(self):
        reg = BrokerRegistry()
        reg.register(_StockCsvAdapter())
        assert len(reg.csv_adapters) == 1
        assert len(reg.xml_adapters) == 0

    def test_register_xml_adapter(self):
        reg = BrokerRegistry()
        reg.register(_XmlAdapter())
        assert len(reg.xml_adapters) == 1

    def test_register_invalid_type_raises(self):
        reg = BrokerRegistry()
        with pytest.raises(TypeError):
            reg.register("not_an_adapter")  # type: ignore

    def test_register_multiple(self):
        reg = BrokerRegistry()
        reg.register(_StockCsvAdapter())
        reg.register(_CfdCsvAdapter())
        assert len(reg.csv_adapters) == 2


class TestBrokerRegistryDetectAndParse:
    def test_csv_stock_detected(self, registry):
        path = _write_tmp(STOCK_CSV_CONTENT, ".csv")
        try:
            trades = registry.detect_and_parse(path)
            assert len(trades) == 1
            assert trades[0].ticker == "AAPL"
        finally:
            os.unlink(path)

    def test_csv_cfd_detected(self, registry):
        path = _write_tmp(CFD_CSV_CONTENT, ".csv")
        try:
            trades = registry.detect_and_parse(path)
            assert len(trades) == 1
            assert trades[0].ticker == "TSLA"
        finally:
            os.unlink(path)

    def test_xml_detected(self, registry):
        path = _write_tmp(XML_CONTENT, ".xml")
        try:
            trades = registry.detect_and_parse(path)
            assert len(trades) == 1
            assert trades[0].ticker == "IBM"
        finally:
            os.unlink(path)

    def test_unknown_extension_raises(self, registry):
        path = _write_tmp("data", ".tsv")
        try:
            with pytest.raises(UnknownFormatError):
                registry.detect_and_parse(path)
        finally:
            os.unlink(path)

    def test_no_matching_adapter_raises(self):
        """Registry with no adapters raises UnknownFormatError for any CSV."""
        reg = BrokerRegistry()
        path = _write_tmp(STOCK_CSV_CONTENT, ".csv")
        try:
            with pytest.raises(UnknownFormatError):
                reg.detect_and_parse(path)
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self, registry):
        with pytest.raises(FileNotFoundError):
            registry.detect_and_parse("/tmp/nonexistent_file_xyz.csv")

    def test_first_matching_adapter_wins(self):
        """When two adapters both claim a file, the first-registered wins."""
        class AlwaysTrue(CsvAdapter):
            def __init__(self, result_ticker):
                self._ticker = result_ticker
            @property
            def broker_name(self):
                return f"always_{self._ticker}"
            def detect(self, df):
                return True
            def parse(self, file_path):
                return [ParsedTrade(date="2023-01-01", type="BUY", currency="USD",
                                    ticker=self._ticker)]

        reg = BrokerRegistry()
        reg.register(AlwaysTrue("FIRST"))
        reg.register(AlwaysTrue("SECOND"))

        path = _write_tmp(STOCK_CSV_CONTENT, ".csv")
        try:
            trades = reg.detect_and_parse(path)
            assert trades[0].ticker == "FIRST"
        finally:
            os.unlink(path)
