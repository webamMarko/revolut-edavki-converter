"""Regression test for SAA-756 follow-up: NOVN must resolve to a yfinance ticker.

Bare "NOVN" is delisted on yfinance and the exchange-suffix fallback list
doesn't include ".SW", so without an explicit TICKER_MAP entry the stock
price sync silently fails for Novartis (SIX: NOVN).
"""

from src.price_fetcher import _yf_ticker


def test_novn_maps_to_swiss_exchange_ticker():
    assert _yf_ticker("NOVN") == "NOVN.SW"
