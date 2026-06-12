"""Tests for SAA-691: real estate changes must invalidate the report data hash.

compute_data_hash() drives both the in-memory HTML report cache and the
/report ETag. It previously only looked at non-realestate transactions, so
adding/editing/deleting a real estate property never changed the hash --
the report kept serving a stale cached page (and the browser kept serving a
304 for the matching ETag), making the property appear "missing" on the
dashboard even though it was saved correctly.
"""

import tempfile
from pathlib import Path

import pytest

from src import db
from src.analytics_cache import compute_data_hash
from src.realestate import create_property, soft_delete_property, update_property


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        connection = db.get_connection(Path(tmpdir) / "test.db")
        connection.execute(
            "INSERT INTO transactions (date, ticker, type, quantity, price_per_share, "
            "total_amount, currency, fx_rate, asset_class, source_file, portfolio_id) "
            "VALUES ('2023-01-02', 'AAPL', 'BUY', 1, 100, 100, 'USD', 0.9, 'stock', 'test', 1)"
        )
        connection.commit()
        yield connection
        connection.close()


def _property_data(**overrides):
    data = {
        "property_type": "apartment",
        "address_line_1": "Testna ulica 1",
        "city": "Ljubljana",
        "postal_code": "1000",
        "country": "SI",
        "municipality": "Ljubljana",
        "area_m2": 55,
        "purchase_date": "2020-01-15",
        "acquisition_price": 150000,
    }
    data.update(overrides)
    return data


class TestDataHashRealEstate:
    def test_stable_with_no_changes(self, conn):
        assert compute_data_hash(conn, portfolio_id=1) == compute_data_hash(conn, portfolio_id=1)

    def test_creating_property_changes_hash(self, conn):
        before = compute_data_hash(conn, portfolio_id=1)
        create_property(conn, _property_data(), portfolio_id=1)
        after = compute_data_hash(conn, portfolio_id=1)
        assert before != after

    def test_updating_property_changes_hash(self, conn):
        _, prop = create_property(conn, _property_data(), portfolio_id=1)
        before = compute_data_hash(conn, portfolio_id=1)
        update_property(conn, prop["id"], {"current_market_value": 175000}, portfolio_id=1)
        after = compute_data_hash(conn, portfolio_id=1)
        assert before != after

    def test_deleting_property_changes_hash(self, conn):
        _, prop = create_property(conn, _property_data(), portfolio_id=1)
        before = compute_data_hash(conn, portfolio_id=1)
        soft_delete_property(conn, prop["id"], portfolio_id=1)
        after = compute_data_hash(conn, portfolio_id=1)
        assert before != after

    def test_other_portfolio_unaffected(self, conn):
        """A property added to portfolio 1 must not change portfolio 2's hash."""
        conn.execute(
            "INSERT INTO portfolios (id, name, slug, is_default) VALUES (2, 'Second', 'second', 0)"
        )
        conn.execute(
            "INSERT INTO transactions (date, ticker, type, quantity, price_per_share, "
            "total_amount, currency, fx_rate, asset_class, source_file, portfolio_id) "
            "VALUES ('2023-01-02', 'MSFT', 'BUY', 1, 100, 100, 'USD', 0.9, 'stock', 'test', 2)"
        )
        conn.commit()

        before = compute_data_hash(conn, portfolio_id=2)
        create_property(conn, _property_data(), portfolio_id=1)
        after = compute_data_hash(conn, portfolio_id=2)
        assert before == after
