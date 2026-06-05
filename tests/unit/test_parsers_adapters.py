"""TDD Tasks 4-11: adapter parity tests for all broker parsers."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _trades(adapter_cls, fixture_subdir, filename="trades.csv"):
    from src.parsers.registry import BrokerRegistry
    reg = BrokerRegistry()
    reg.register(adapter_cls())
    path = str(FIXTURES / fixture_subdir / filename)
    return reg.detect_and_parse(path)


# ---------------------------------------------------------------------------
# Task 4: revolut_stock
# ---------------------------------------------------------------------------

class TestRevolutStockAdapter:
    def setup_method(self):
        from src.parsers.revolut_stock import RevolutStockAdapter
        self.adapter = RevolutStockAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "revolut_stock"

    def test_detect_stock_csv(self):
        import pandas as pd
        df = pd.DataFrame({"Ticker": ["AAPL"], "Price per share": [130.5], "Type": ["BUY"]})
        assert self.adapter.detect(df) is True

    def test_detect_rejects_cfd(self):
        import pandas as pd
        df = pd.DataFrame({"Symbol": ["AAPL"], "Margin": [100], "Type": ["BUY"]})
        assert self.adapter.detect(df) is False

    def test_parse_fixture(self):
        trades = _trades(
            __import__("src.parsers.revolut_stock", fromlist=["RevolutStockAdapter"]).RevolutStockAdapter,
            "revolut_stock"
        )
        # 3 parseable rows (stock split row has no type)
        tickers = [t.ticker for t in trades]
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        buy_aapl = next(t for t in trades if t.ticker == "AAPL" and t.type == "BUY")
        assert buy_aapl.quantity == 10.0
        assert buy_aapl.currency == "USD"
        assert buy_aapl.fx_rate == 1.07
        assert buy_aapl.broker_source == "revolut"
        assert buy_aapl.asset_class == "stock"

    def test_parse_skips_empty_rows(self):
        from src.parsers.revolut_stock import RevolutStockAdapter
        import pandas as pd
        adapter = RevolutStockAdapter()
        row = pd.Series({"Date": None, "Ticker": "AAPL", "Type": "BUY",
                          "Quantity": 1, "Price per share": 100, "Total Amount": 100,
                          "Currency": "USD", "FX Rate": 1.0})
        assert adapter._parse_row(row) is None


# ---------------------------------------------------------------------------
# Task 5: revolut_cfd
# ---------------------------------------------------------------------------

class TestRevolutCfdAdapter:
    def setup_method(self):
        from src.parsers.revolut_cfd import RevolutCfdAdapter
        self.adapter = RevolutCfdAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "revolut_cfd"

    def test_detect_cfd(self):
        import pandas as pd
        df = pd.DataFrame({"Symbol": ["X"], "Margin": [100]})
        assert self.adapter.detect(df) is True

    def test_detect_rejects_stock(self):
        import pandas as pd
        df = pd.DataFrame({"Ticker": ["AAPL"], "Price per share": [130]})
        assert self.adapter.detect(df) is False

    def test_parse_fixture(self):
        from src.parsers.revolut_cfd import RevolutCfdAdapter
        trades = _trades(RevolutCfdAdapter, "revolut_cfd")
        assert len(trades) == 2
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.ticker == "AAPL"   # :CFD suffix stripped
        assert buy.asset_class == "cfd"
        assert buy.broker_source == "revolut"

    def test_cfd_suffix_stripped(self):
        import pandas as pd
        from src.parsers.revolut_cfd import RevolutCfdAdapter
        row = pd.Series({"Date": "2023-01-01", "Symbol": "TSLA:CFD", "Type": "BUY",
                          "Quantity": 1, "Price": 100, "Total Amount": 100,
                          "Currency": "USD", "FX Rate": 1.0})
        t = RevolutCfdAdapter()._parse_row(row)
        assert t.ticker == "TSLA"


# ---------------------------------------------------------------------------
# Task 6: revolut_crypto
# ---------------------------------------------------------------------------

class TestRevolutCryptoAdapter:
    def setup_method(self):
        from src.parsers.revolut_crypto import RevolutCryptoAdapter
        self.adapter = RevolutCryptoAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "revolut_crypto"

    def test_detect_crypto(self):
        import pandas as pd
        df = pd.DataFrame({"Symbol": ["BTC"], "Value": [100]})
        assert self.adapter.detect(df) is True

    def test_detect_rejects_cfd(self):
        import pandas as pd
        df = pd.DataFrame({"Symbol": ["X"], "Margin": [10], "Value": [100]})
        assert self.adapter.detect(df) is False

    def test_parse_fixture(self):
        from src.parsers.revolut_crypto import RevolutCryptoAdapter
        trades = _trades(RevolutCryptoAdapter, "revolut_crypto")
        assert len(trades) == 3
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.ticker == "BTC"
        assert buy.asset_class == "crypto"
        assert buy.currency == "EUR"
        reward = next(t for t in trades if "REWARD" in t.type)
        assert reward.type == "STAKING REWARD"


# ---------------------------------------------------------------------------
# Task 7: revolut_savings
# ---------------------------------------------------------------------------

class TestRevolutSavingsAdapter:
    def setup_method(self):
        from src.parsers.revolut_savings import RevolutSavingsAdapter
        self.adapter = RevolutSavingsAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "revolut_savings"

    def test_detect_savings(self):
        import pandas as pd
        df = pd.DataFrame({"Description": ["BUY USD Class R IE000H9J0QX4"]})
        assert self.adapter.detect(df) is True

    def test_detect_rejects_no_class(self):
        import pandas as pd
        df = pd.DataFrame({"Description": ["Some description without class marker"]})
        assert self.adapter.detect(df) is False

    def test_parse_fixture(self):
        from src.parsers.revolut_savings import RevolutSavingsAdapter
        trades = _trades(RevolutSavingsAdapter, "revolut_savings")
        assert len(trades) >= 2
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.asset_class == "savings"
        assert buy.currency == "EUR"
        assert buy.broker_source == "revolut"


# ---------------------------------------------------------------------------
# Task 8: ilirika
# ---------------------------------------------------------------------------

class TestIlirikaAdapter:
    def setup_method(self):
        from src.parsers.ilirika import IlirikaAdapter
        self.adapter = IlirikaAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "ilirika"

    def test_detect_ilirika(self):
        import pandas as pd
        df = pd.DataFrame({"FinancialInstrument": ["AAPL US"],
                           "TransactionTypeName": ["Nakup"]})
        assert self.adapter.detect(df) is True

    def test_parse_fixture(self):
        from src.parsers.ilirika import IlirikaAdapter
        trades = _trades(IlirikaAdapter, "ilirika")
        # OLD row should be skipped; split gives one row
        tickers = [t.ticker for t in trades]
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        buy = next(t for t in trades if t.ticker == "AAPL")
        assert buy.type == "BUY"
        assert buy.quantity == 10.0
        assert buy.currency == "USD"

    def test_split_preprocessing(self):
        """STOCK SPLIT row uses pre-computed net delta (OLD + new combined)."""
        from src.parsers.ilirika import IlirikaAdapter
        trades = _trades(IlirikaAdapter, "ilirika")
        split_rows = [t for t in trades if t.type == "STOCK SPLIT"]
        assert len(split_rows) == 1
        # Net delta: -80 + 5 = -75 (net quantity change is negative for reverse split)
        assert split_rows[0].quantity == pytest.approx(-75.0, abs=0.01)

    def test_old_ticker_skipped(self):
        from src.parsers.ilirika import IlirikaAdapter
        import pandas as pd
        adapter = IlirikaAdapter()
        row = pd.Series({"FinancialInstrument": "ASTR US OLD",
                          "DateValue": "01. 08. 2022 00:00:00",
                          "TransactionTypeName": "Reverse Split",
                          "VolumeValue": -80, "Volume": -80,
                          "PriceValue": None, "Price": None})
        assert adapter._parse_row(row, {}) is None


# ---------------------------------------------------------------------------
# Task 9: ibkr
# ---------------------------------------------------------------------------

class TestIbkrAdapter:
    def setup_method(self):
        from src.parsers.ibkr import IbkrAdapter
        self.adapter = IbkrAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "ibkr"

    def test_detect_ibkr(self):
        import pandas as pd
        df = pd.DataFrame({"Trades": ["Data"], "DataDiscriminator": ["Order"]})
        assert self.adapter.detect(df) is True

    def test_parse_fixture(self):
        from src.parsers.ibkr import IbkrAdapter
        trades = _trades(IbkrAdapter, "ibkr")
        assert len(trades) == 2  # SubTotal row skipped
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.ticker == "AAPL"
        assert buy.commission == pytest.approx(1.30, abs=0.01)
        assert buy.broker_source == "ibkr"
        sell = next(t for t in trades if t.type == "SELL")
        assert sell.ticker == "MSFT"
        assert sell.quantity == 5.0


# ---------------------------------------------------------------------------
# Task 10: trading212
# ---------------------------------------------------------------------------

class TestTrading212Adapter:
    def setup_method(self):
        from src.parsers.trading212 import Trading212Adapter
        self.adapter = Trading212Adapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "trading212"

    def test_detect_trading212(self):
        import pandas as pd
        df = pd.DataFrame({"Action": ["Market buy"],
                           "No. of shares": [10],
                           "Price / share": [130.5]})
        assert self.adapter.detect(df) is True

    def test_parse_fixture(self):
        from src.parsers.trading212 import Trading212Adapter
        trades = _trades(Trading212Adapter, "trading212")
        assert len(trades) == 3
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.ticker == "AAPL"
        assert buy.broker_source == "trading212"
        div = next(t for t in trades if t.type == "DIVIDEND")
        assert div.ticker == "AAPL"


# ---------------------------------------------------------------------------
# Task 11: degiro
# ---------------------------------------------------------------------------

class TestDegiroAdapter:
    def setup_method(self):
        from src.parsers.degiro import DegiroAdapter
        self.adapter = DegiroAdapter()

    def test_broker_name(self):
        assert self.adapter.broker_name == "degiro"

    def test_detect_degiro(self):
        import pandas as pd
        df = pd.DataFrame({"Datum": ["10-01-2023"],
                           "Product": ["Apple Inc"],
                           "ISIN": ["US0378331005"]})
        assert self.adapter.detect(df) is True

    def test_parse_fixture(self):
        from src.parsers.degiro import DegiroAdapter
        trades = _trades(DegiroAdapter, "degiro")
        assert len(trades) == 2
        buy = next(t for t in trades if t.type == "BUY")
        assert buy.ticker == "AAPL"   # ISIN mapped to known ticker
        assert buy.broker_source == "degiro"
        assert buy.quantity == 10.0
        sell = next(t for t in trades if t.type == "SELL")
        assert sell.ticker == "MSFT"
        assert sell.quantity == 5.0

    def test_zero_quantity_skipped(self):
        import pandas as pd
        from src.parsers.degiro import DegiroAdapter
        row = pd.Series({"Datum": "10-01-2023", "Tijd": None,
                          "Product": "Apple", "ISIN": "US0378331005",
                          "Beurs": "NASDAQ", "Aantal": 0,
                          "Koers": 130.5, "Waarde": 0, "Wisselkoers": None})
        assert DegiroAdapter()._parse_row(row) is None
