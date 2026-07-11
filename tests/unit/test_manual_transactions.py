"""Tests for manual transaction validation, CRUD, audit log, and FIFO matching."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.db import get_connection
from src.transactions import (
    ALLOWED_TYPES,
    validate_transaction,
    create_manual_transaction,
    update_manual_transaction,
    delete_manual_transaction,
    get_transaction,
    list_transactions,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    c = get_connection(db_path)
    yield c
    c.close()


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

class TestValidation:
    def test_valid_stock_buy(self):
        data = {
            'date': '2024-01-15',
            'ticker': 'AAPL',
            'type': 'BUY',
            'quantity': 10,
            'price_per_share': 150.0,
            'currency': 'USD',
            'fx_rate': 0.91,
        }
        clean, errors = validate_transaction(data, 'stock')
        assert not errors
        assert clean['ticker'] == 'AAPL'
        assert clean['quantity'] == 10.0
        assert clean['fx_rate'] == 0.91

    def test_future_date_rejected(self):
        data = {
            'date': '2099-01-01',
            'ticker': 'AAPL',
            'type': 'BUY',
            'quantity': 1,
            'price_per_share': 10.0,
            'currency': 'EUR',
        }
        _, errors = validate_transaction(data, 'stock')
        assert 'date' in errors
        assert 'future' in errors['date'].lower()

    def test_invalid_date_format(self):
        data = {'date': '15-01-2024', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'date' in errors

    def test_missing_date(self):
        data = {'ticker': 'X', 'type': 'BUY', 'quantity': 1,
                'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'date' in errors

    def test_ticker_uppercase(self):
        data = {'date': '2024-01-01', 'ticker': 'aapl', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'EUR'}
        clean, errors = validate_transaction(data, 'stock')
        assert not errors
        assert clean['ticker'] == 'AAPL'

    def test_invalid_ticker_chars(self):
        data = {'date': '2024-01-01', 'ticker': 'AAPL!', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'ticker' in errors

    def test_ticker_with_dots_allowed(self):
        data = {'date': '2024-01-01', 'ticker': 'NOVN.SW', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'EUR'}
        clean, errors = validate_transaction(data, 'stock')
        assert not errors
        assert clean['ticker'] == 'NOVN.SW'

    def test_invalid_type_for_asset_class(self):
        data = {'date': '2024-01-01', 'ticker': 'BTC', 'type': 'DIVIDEND',
                'quantity': 1, 'price_per_share': 1, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'crypto')
        assert 'type' in errors

    def test_all_allowed_types_accepted(self):
        for ac, types in ALLOWED_TYPES.items():
            for tx_type in types:
                data = {
                    'date': '2024-01-01',
                    'ticker': 'TEST',
                    'type': tx_type,
                    'quantity': 1 if tx_type in ('BUY', 'SELL') else None,
                    'price_per_share': 10 if tx_type in ('BUY', 'SELL') else None,
                    'currency': 'EUR',
                }
                clean, errors = validate_transaction(data, ac)
                assert 'type' not in errors, f"type={tx_type} ac={ac} errors={errors}"

    def test_negative_quantity_rejected(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': -5, 'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'quantity' in errors

    def test_zero_quantity_rejected(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 0, 'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'quantity' in errors

    def test_negative_price_rejected(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': -1, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'price_per_share' in errors

    def test_zero_price_allowed(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 0, 'currency': 'EUR'}
        clean, errors = validate_transaction(data, 'stock')
        assert 'price_per_share' not in errors
        assert clean['price_per_share'] == 0.0

    def test_fx_rate_required_for_non_eur(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'USD'}
        _, errors = validate_transaction(data, 'stock')
        assert 'fx_rate' in errors

    def test_fx_rate_zero_rejected(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'USD', 'fx_rate': 0}
        _, errors = validate_transaction(data, 'stock')
        assert 'fx_rate' in errors

    def test_eur_currency_defaults_fx_1(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'EUR'}
        clean, errors = validate_transaction(data, 'stock')
        assert not errors
        assert clean['fx_rate'] == 1.0

    def test_invalid_asset_class(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'BUY',
                'quantity': 1, 'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'forex')
        assert 'asset_class' in errors

    def test_missing_quantity_for_sell(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'SELL',
                'price_per_share': 10, 'currency': 'EUR'}
        _, errors = validate_transaction(data, 'stock')
        assert 'quantity' in errors

    def test_quantity_not_required_for_dividend(self):
        data = {'date': '2024-01-01', 'ticker': 'X', 'type': 'DIVIDEND',
                'currency': 'EUR', 'total_amount': 5.0}
        clean, errors = validate_transaction(data, 'stock')
        assert 'quantity' not in errors
        assert 'price_per_share' not in errors


# ------------------------------------------------------------------
# CRUD + Audit
# ------------------------------------------------------------------

class TestCRUD:
    def _make_clean(self):
        return {
            'date': '2023-06-01',
            'ticker': 'AAPL',
            'type': 'BUY',
            'quantity': 10.0,
            'price_per_share': 150.0,
            'currency': 'USD',
            'fx_rate': 0.91,
            'asset_class': 'stock',
        }

    def test_create_sets_broker_source_manual(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean, portfolio_id=1)
        assert row['broker_source'] == 'manual'
        assert row['source_file'] is None

    def test_create_audit_row_written(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        audit = conn.execute(
            "SELECT * FROM transaction_audit WHERE transaction_id = ?", (row['id'],)
        ).fetchall()
        assert len(audit) == 1
        assert audit[0]['action'] == 'create'
        assert audit[0]['new_value'] is not None
        assert audit[0]['old_value'] is None

    def test_create_audit_new_value_is_json(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        audit = conn.execute(
            "SELECT new_value FROM transaction_audit WHERE transaction_id = ?", (row['id'],)
        ).fetchone()
        data = json.loads(audit[0])
        assert data['ticker'] == 'AAPL'

    def test_get_transaction(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        fetched = get_transaction(conn, row['id'])
        assert fetched is not None
        assert fetched['id'] == row['id']

    def test_get_transaction_wrong_portfolio(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean, portfolio_id=1)
        fetched = get_transaction(conn, row['id'], portfolio_id=99)
        assert fetched is None

    def test_update_field_audit(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        updated = update_manual_transaction(conn, row['id'], {'quantity': 20.0})
        assert updated['quantity'] == 20.0
        audits = conn.execute(
            "SELECT * FROM transaction_audit WHERE transaction_id = ? AND action = 'update'",
            (row['id'],)
        ).fetchall()
        assert len(audits) == 1
        assert audits[0]['field_name'] == 'quantity'
        assert audits[0]['old_value'] == '10.0'
        assert audits[0]['new_value'] == '20.0'

    def test_update_no_change_no_audit(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        update_manual_transaction(conn, row['id'], {'quantity': 10.0})
        audits = conn.execute(
            "SELECT * FROM transaction_audit WHERE transaction_id = ? AND action = 'update'",
            (row['id'],)
        ).fetchall()
        assert len(audits) == 0

    def test_update_nonexistent(self, conn):
        result = update_manual_transaction(conn, 9999, {'quantity': 5})
        assert result is None

    def test_delete_removes_row(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        ok = delete_manual_transaction(conn, row['id'])
        assert ok is True
        assert get_transaction(conn, row['id']) is None

    def test_delete_audit_row_has_snapshot(self, conn):
        clean = self._make_clean()
        row = create_manual_transaction(conn, clean)
        tx_id = row['id']
        delete_manual_transaction(conn, tx_id)
        audit = conn.execute(
            "SELECT * FROM transaction_audit WHERE transaction_id = ? AND action = 'delete'",
            (tx_id,)
        ).fetchone()
        assert audit is not None
        snapshot = json.loads(audit['old_value'])
        assert snapshot['ticker'] == 'AAPL'
        assert audit['new_value'] is None

    def test_delete_nonexistent(self, conn):
        ok = delete_manual_transaction(conn, 9999)
        assert ok is False

    def test_list_pagination(self, conn):
        for i in range(5):
            clean = self._make_clean()
            clean['ticker'] = f'T{i:02d}'
            create_manual_transaction(conn, clean)
        result = list_transactions(conn, page=1, per_page=2)
        assert len(result['transactions']) == 2
        assert result['total'] == 5
        assert result['pages'] == 3

    def test_list_filter_ticker(self, conn):
        for ticker in ('AAPL', 'MSFT', 'AAPL'):
            clean = self._make_clean()
            clean['ticker'] = ticker
            create_manual_transaction(conn, clean)
        result = list_transactions(conn, ticker='AAPL')
        assert result['total'] == 2
        assert all(r['ticker'] == 'AAPL' for r in result['transactions'])

    def test_list_filter_date_range(self, conn):
        for date_str in ('2023-01-01', '2023-06-01', '2024-01-01'):
            clean = self._make_clean()
            clean['date'] = date_str
            create_manual_transaction(conn, clean)
        result = list_transactions(conn, date_from='2023-05-01', date_to='2023-12-31')
        assert result['total'] == 1


# ------------------------------------------------------------------
# FIFO matching in analytics pipeline
# ------------------------------------------------------------------

class TestFIFOWithManualTransactions:
    """Verify manual transactions flow through analytics FIFO correctly."""

    def test_manual_buy_sell_produces_realized_gain(self, conn):
        # BUY 10 @ $150, fx=0.91 → pps_eur=164.84, total_amount=1500 USD
        buy = {
            'date': '2022-01-10',
            'ticker': 'AAPL',
            'type': 'BUY',
            'quantity': 10.0,
            'price_per_share': 150.0,
            'total_amount': 1500.0,
            'currency': 'USD',
            'fx_rate': 0.91,
            'asset_class': 'stock',
        }
        create_manual_transaction(conn, buy)

        # SELL 5 @ $200, fx=0.93 → pps_eur=215.05, total_amount=1000 USD
        sell = {
            'date': '2023-06-01',
            'ticker': 'AAPL',
            'type': 'SELL',
            'quantity': 5.0,
            'price_per_share': 200.0,
            'total_amount': 1000.0,
            'currency': 'USD',
            'fx_rate': 0.93,
            'asset_class': 'stock',
        }
        create_manual_transaction(conn, sell)

        from src.analytics import compute_analytics
        result = compute_analytics(conn, scope='stock', prices_conn=None, portfolio_id=1)

        # Should have realized gain (sold 5 shares at profit)
        assert result.total_realized_gain_eur > 0

        # Should still hold 5 shares
        open_pos = [p for p in result.positions if p.ticker == 'AAPL']
        assert len(open_pos) == 1
        assert abs(open_pos[0].quantity - 5.0) < 0.01

    def test_manual_transactions_source_file_null(self, conn):
        clean = {
            'date': '2023-01-01',
            'ticker': 'MSFT',
            'type': 'BUY',
            'quantity': 5.0,
            'price_per_share': 300.0,
            'currency': 'EUR',
            'fx_rate': 1.0,
            'asset_class': 'stock',
        }
        row = create_manual_transaction(conn, clean)
        assert row['broker_source'] == 'manual'
        assert row['source_file'] is None

        # Verify it's in the DB with correct fields
        stored = get_transaction(conn, row['id'])
        assert stored['broker_source'] == 'manual'
        assert stored['source_file'] is None

    def test_mixed_imported_and_manual_fifo(self, conn):
        """Manual BUY + manual SELL should produce correct FIFO lot consumption."""
        # BUY 10 @ €100 (2021), total_amount=1000 EUR
        conn.execute("""
            INSERT INTO transactions
                (date, ticker, type, quantity, price_per_share, total_amount, currency, fx_rate,
                 asset_class, broker_source, source_file, portfolio_id)
            VALUES
                ('2021-03-01','TEST','BUY',10,100.0,1000.0,'EUR',1.0,'stock','revolut',
                 'file.csv', 1)
        """)
        conn.commit()

        # Manual BUY 5 @ €120 (2022), total_amount=600 EUR
        create_manual_transaction(conn, {
            'date': '2022-03-01',
            'ticker': 'TEST',
            'type': 'BUY',
            'quantity': 5.0,
            'price_per_share': 120.0,
            'total_amount': 600.0,
            'currency': 'EUR',
            'fx_rate': 1.0,
            'asset_class': 'stock',
        })

        # Manual SELL 12 @ €150 (2023) — FIFO: 10 from lot1 + 2 from lot2
        # total_amount = 12 * 150 = 1800 EUR
        create_manual_transaction(conn, {
            'date': '2023-01-15',
            'ticker': 'TEST',
            'type': 'SELL',
            'quantity': 12.0,
            'price_per_share': 150.0,
            'total_amount': 1800.0,
            'currency': 'EUR',
            'fx_rate': 1.0,
            'asset_class': 'stock',
        })

        from src.analytics import compute_analytics
        result = compute_analytics(conn, scope='stock', prices_conn=None, portfolio_id=1)

        # sold 12, have 3 left
        open_pos = [p for p in result.positions if p.ticker == 'TEST']
        assert len(open_pos) == 1
        assert abs(open_pos[0].quantity - 3.0) < 0.01

        # realized: 10*(150-100) + 2*(150-120) = 500 + 60 = 560 EUR
        assert abs(result.total_realized_gain_eur - 560.0) < 1.0
