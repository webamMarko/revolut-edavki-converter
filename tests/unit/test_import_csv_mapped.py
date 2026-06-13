"""Regression test for SAA-756: custom-mapped CSV imports must normalize
transaction `type` to uppercase, otherwise analytics/tax silently drop the
row (they do case-sensitive `"BUY" in tx_type` checks).
"""

import tempfile
from pathlib import Path

import pytest

from src import db
from src.analytics import compute_analytics
from src.importer import import_csv_mapped


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        connection = db.get_connection(Path(tmpdir) / "test_portfolio.db")
        yield connection
        connection.close()


def _write_csv(tmpdir: str) -> str:
    path = Path(tmpdir) / "Novs.csv"
    path.write_text(
        "date;purchase_date;symbol;transaction_type;status;price_per_unit;"
        "currency;amount;available_to_purchase;purchased_shares\n"
        "2026-01-01;2026-04-20;NOVN;buy;Allocated;109.23;CHF;200.00;184.00;1.831\n"
    )
    return str(path)


COLUMN_MAP = {
    "date": "date",
    "type": "transaction_type",
    "ticker": "symbol",
    "quantity": "purchased_shares",
    "price_per_share": "price_per_unit",
    "total_amount": "amount",
    "currency": "currency",
}


def test_lowercase_buy_type_is_normalized_to_uppercase(conn):
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = _write_csv(tmpdir)
        result = import_csv_mapped(conn, csv_path, "stock", COLUMN_MAP, filename_hint="Novs.csv")

    assert result.new == 1

    row = conn.execute("SELECT type FROM transactions WHERE ticker = 'NOVN'").fetchone()
    assert row[0] == "BUY"


def test_lowercase_buy_results_in_visible_position(conn):
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = _write_csv(tmpdir)
        import_csv_mapped(conn, csv_path, "stock", COLUMN_MAP, filename_hint="Novs.csv")

    result = compute_analytics(conn, scope="stock")

    tickers = {p.ticker: p for p in result.positions}
    assert "NOVN" in tickers
    assert tickers["NOVN"].quantity == pytest.approx(1.831)
