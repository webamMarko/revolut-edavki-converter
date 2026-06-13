"""Regression test for SAA-764: DCA "Total Invested" must convert non-EUR
amounts to EUR, even when fx_rate=1.0 (the default stored by custom-mapped
CSV imports when no FX-rate column is provided).
"""

import tempfile
from pathlib import Path

import pytest

from src import db
from src.dca_strategy import compute_dca_analysis


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        connection = db.get_connection(Path(tmpdir) / "test_portfolio.db")
        yield connection
        connection.close()


def _insert_chf_buys(conn):
    for i, date in enumerate(["2026-01-01", "2026-02-01", "2026-03-01"]):
        conn.execute(
            """INSERT INTO transactions
               (date, ticker, type, quantity, price_per_share, total_amount,
                currency, fx_rate, asset_class, source_file, row_hash)
               VALUES (?, 'NOVN', 'BUY', 1.831, 109.23, 200.0, 'CHF', 1.0, 'stock', 'Novs.csv', ?)""",
            (date, f"hash{i}"),
        )
    # Historical CHF->EUR rates (CHF is worth more than EUR)
    for date, rate in [("2025-12-31", 1.07499), ("2026-01-30", 1.09308), ("2026-02-27", 1.09560)]:
        conn.execute(
            "INSERT INTO fx_rates (date, from_currency, to_currency, rate) VALUES (?, 'CHF', 'EUR', ?)",
            (date, rate),
        )
    conn.commit()


def test_dca_total_invested_converts_chf_to_eur(conn):
    _insert_chf_buys(conn)

    result = compute_dca_analysis(conn)

    assert result is not None
    novn = next(t for t in result["tickers"] if t["ticker"] == "NOVN")

    # 600 CHF spent, historically worth ~652.73 EUR -- not 600 EUR.
    assert novn["total_invested_eur"] == pytest.approx(652.73, abs=0.01)
    assert novn["avg_cost_eur"] == pytest.approx(652.73 / (1.831 * 3), abs=0.001)
