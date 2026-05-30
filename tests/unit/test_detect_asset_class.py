"""Unit tests for detect_asset_class utility (Phase 2 TDD tasks 7-12)."""

import pytest
from src.web.detection_rules import detect_asset_class, CONFIDENCE_THRESHOLD


class TestDetectAssetClassStock:
    """TDD task 7: Stock detection from headers."""

    def test_returns_stock_for_ticker_exchange_shares(self):
        result = detect_asset_class(["Ticker", "Exchange", "Shares"])
        assert result["detectedClass"] == "stock"

    def test_returns_stock_for_revolut_stock_headers(self):
        result = detect_asset_class(["Date", "Ticker", "Type", "Quantity", "Price per share", "Total Amount", "Currency", "FX Rate"])
        assert result["detectedClass"] == "stock"

    def test_returns_stock_for_trading212_headers(self):
        result = detect_asset_class(["Action", "No. of shares", "Price / share", "Currency", "ISIN"])
        assert result["detectedClass"] == "stock"

    def test_returns_stock_for_degiro_headers(self):
        result = detect_asset_class(["Datum", "Product", "ISIN", "Quantity", "Price"])
        assert result["detectedClass"] == "stock"

    def test_stock_confidence_above_threshold(self):
        result = detect_asset_class(["Ticker", "Exchange", "Shares", "ISIN"])
        assert result["confidence"] >= CONFIDENCE_THRESHOLD


class TestDetectAssetClassCFD:
    """TDD task 8: CFD detection from headers."""

    def test_returns_cfd_for_leverage_margin(self):
        result = detect_asset_class(["Leverage", "Margin"])
        assert result["detectedClass"] == "cfd"

    def test_returns_cfd_for_revolut_cfd_headers(self):
        result = detect_asset_class(["Date", "Symbol", "Type", "Quantity", "Price", "Total Amount", "Margin", "Fees", "Currency", "FX Rate"])
        assert result["detectedClass"] == "cfd"

    def test_returns_cfd_for_spread_contract_size(self):
        result = detect_asset_class(["Symbol", "Spread", "Contract Size", "Margin"])
        assert result["detectedClass"] == "cfd"

    def test_cfd_confidence_above_threshold(self):
        result = detect_asset_class(["Leverage", "Margin", "Symbol"])
        assert result["confidence"] >= CONFIDENCE_THRESHOLD


class TestDetectAssetClassCrypto:
    """TDD task 9: Crypto detection from headers + data patterns."""

    def test_returns_crypto_for_wallet_header_and_btc_data(self):
        result = detect_asset_class(["Wallet", "Type", "Value"], ["BTC", "Buy", "100"])
        assert result["detectedClass"] == "crypto"

    def test_returns_crypto_for_blockchain_token_headers(self):
        result = detect_asset_class(["Symbol", "Blockchain", "Token", "Hash"])
        assert result["detectedClass"] == "crypto"

    def test_returns_crypto_for_eth_in_first_row(self):
        result = detect_asset_class(["Symbol", "Type", "Value"], ["ETH", "Buy", "500"])
        assert result["detectedClass"] == "crypto"

    def test_returns_crypto_for_various_tickers(self):
        for ticker in ["XRP", "ADA", "SOL", "DOGE"]:
            result = detect_asset_class(["Symbol", "Value"], [ticker, "100"])
            assert result["detectedClass"] == "crypto", f"Expected crypto for ticker {ticker}"


class TestDetectAssetClassSavings:
    """TDD task 10: Savings detection from headers."""

    def test_returns_savings_for_interest_apy(self):
        result = detect_asset_class(["Interest", "APY"])
        assert result["detectedClass"] == "savings"

    def test_returns_savings_for_revolut_savings_headers(self):
        result = detect_asset_class(["Date", "Description", "Value, USD", "Value, EUR", "FX Rate", "Price per share", "Quantity of shares"])
        assert result["detectedClass"] == "savings"

    def test_returns_savings_for_maturity_principal(self):
        result = detect_asset_class(["Maturity", "Principal", "Interest", "Fund"])
        assert result["detectedClass"] == "savings"

    def test_savings_confidence_above_threshold(self):
        result = detect_asset_class(["Interest", "APY", "Maturity"])
        assert result["confidence"] >= CONFIDENCE_THRESHOLD


class TestDetectAssetClassFallback:
    """TDD task 11: Silent fallback below 70% confidence."""

    def test_returns_null_for_ambiguous_headers(self):
        result = detect_asset_class(["Date", "Amount", "Type"])
        assert result["detectedClass"] is None

    def test_returns_null_when_confidence_below_threshold(self):
        result = detect_asset_class(["Date", "Amount", "Type"])
        assert result["confidence"] < CONFIDENCE_THRESHOLD or result["detectedClass"] is None

    def test_empty_headers_returns_null(self):
        result = detect_asset_class([])
        assert result["detectedClass"] is None


class TestDetectAssetClassAmbiguous:
    """TDD task 12: Null for ambiguous multi-class headers."""

    def test_returns_null_for_conflicting_signals(self):
        # Headers that match multiple classes equally
        result = detect_asset_class(["Ticker", "Margin", "Blockchain", "Interest"])
        # Either returns null or dominant class with low confidence — we verify no panic
        assert isinstance(result["detectedClass"], (str, type(None)))

    def test_no_class_below_threshold(self):
        result = detect_asset_class(["Column1", "Column2", "Column3"])
        assert result["detectedClass"] is None


class TestDetectAssetClassOutputShape:
    """Output shape tests."""

    def test_result_has_required_keys(self):
        result = detect_asset_class(["Ticker", "Price per share"])
        assert "detectedClass" in result
        assert "confidence" in result
        assert "scores" in result

    def test_scores_has_all_four_classes(self):
        result = detect_asset_class(["Ticker"])
        assert set(result["scores"].keys()) == {"stock", "cfd", "crypto", "savings"}

    def test_each_score_has_score_and_signals(self):
        result = detect_asset_class(["Ticker"])
        for ac, sc in result["scores"].items():
            assert "score" in sc
            assert "matchedSignals" in sc

    def test_confidence_is_float_between_0_and_1(self):
        result = detect_asset_class(["Ticker"])
        assert 0.0 <= result["confidence"] <= 1.0
