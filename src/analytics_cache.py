"""Persistent caching layer for compute_analytics() results."""

import hashlib
import io
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime

import pandas as pd

from .analytics import (
    AnalyticsResult,
    BenchmarkComparison,
    ClosedPositionDetail,
    PositionDetail,
)


def compute_data_hash(conn: sqlite3.Connection,
                      prices_conn: sqlite3.Connection | None = None) -> str:
    """SHA-256 of transaction count + last transaction date + last sync date."""
    row = conn.execute(
        "SELECT COUNT(*), MAX(date) FROM transactions WHERE asset_class != 'realestate'"
    ).fetchone()
    tx_count = row[0] or 0
    last_tx_date = row[1] or ""

    source = prices_conn if prices_conn is not None else conn
    sync_row = source.execute(
        "SELECT MAX(date) FROM daily_prices"
    ).fetchone()
    last_sync_date = sync_row[0] if sync_row else ""

    fx_row = source.execute(
        "SELECT MAX(date) FROM fx_rates"
    ).fetchone()
    last_fx_date = fx_row[0] if fx_row else ""

    payload = f"{tx_count}|{last_tx_date}|{last_sync_date}|{last_fx_date}"
    return hashlib.sha256(payload.encode()).hexdigest()


def get_cached(conn: sqlite3.Connection, scope: str, data_hash: str) -> AnalyticsResult | None:
    """Return cached AnalyticsResult if hash matches, else None."""
    row = conn.execute(
        "SELECT result_json FROM cached_analytics WHERE scope = ? AND data_hash = ?",
        (scope, data_hash)
    ).fetchone()
    if not row:
        return None
    return _deserialize(row[0])


def put_cache(conn: sqlite3.Connection, scope: str, data_hash: str, result: AnalyticsResult):
    """Upsert analytics result into cache."""
    result_json = _serialize(result)
    conn.execute(
        "INSERT OR REPLACE INTO cached_analytics (scope, data_hash, result_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (scope, data_hash, result_json, datetime.now().isoformat())
    )
    conn.commit()


def invalidate_cache(conn: sqlite3.Connection):
    """Delete all cached analytics entries."""
    conn.execute("DELETE FROM cached_analytics")
    conn.commit()


def _serialize(result: AnalyticsResult) -> str:
    """Serialize AnalyticsResult to JSON string."""
    d = {}
    d["portfolio_value_eur"] = result.portfolio_value_eur
    d["total_invested_eur"] = result.total_invested_eur
    d["absolute_gain_eur"] = result.absolute_gain_eur
    d["total_return_pct"] = result.total_return_pct
    d["cagr_pct"] = result.cagr_pct
    d["twr_pct"] = result.twr_pct
    d["max_drawdown_pct"] = result.max_drawdown_pct
    d["max_drawdown_peak_date"] = result.max_drawdown_peak_date
    d["max_drawdown_trough_date"] = result.max_drawdown_trough_date
    d["total_dividends_eur"] = result.total_dividends_eur
    d["total_realized_gain_eur"] = result.total_realized_gain_eur
    d["total_unrealized_gain_eur"] = result.total_unrealized_gain_eur
    d["total_fees_eur"] = result.total_fees_eur
    d["positions"] = [asdict(p) for p in result.positions]
    d["closed_positions"] = [asdict(p) for p in result.closed_positions]
    d["position_lots"] = result.position_lots
    d["benchmarks"] = [asdict(b) for b in result.benchmarks]
    d["daily_series"] = result.daily_series.to_json(orient="split", date_format="iso")
    d["benchmark_series"] = {
        k: v.to_json(orient="split", date_format="iso")
        for k, v in result.benchmark_series.items()
    }
    d["risk_metrics"] = result.risk_metrics
    d["start_date"] = result.start_date
    d["end_date"] = result.end_date
    d["scope"] = result.scope
    return json.dumps(d)


def _deserialize(json_str: str) -> AnalyticsResult:
    """Deserialize JSON string back to AnalyticsResult."""
    d = json.loads(json_str)

    positions = [PositionDetail(**p) for p in d["positions"]]
    closed_positions = [ClosedPositionDetail(**p) for p in d["closed_positions"]]
    benchmarks = [BenchmarkComparison(**b) for b in d["benchmarks"]]

    daily_series = pd.read_json(io.StringIO(d["daily_series"]), orient="split")
    benchmark_series = {
        k: pd.read_json(io.StringIO(v), orient="split", typ="series")
        for k, v in d["benchmark_series"].items()
    }

    return AnalyticsResult(
        portfolio_value_eur=d["portfolio_value_eur"],
        total_invested_eur=d["total_invested_eur"],
        absolute_gain_eur=d["absolute_gain_eur"],
        total_return_pct=d["total_return_pct"],
        cagr_pct=d["cagr_pct"],
        twr_pct=d["twr_pct"],
        max_drawdown_pct=d["max_drawdown_pct"],
        max_drawdown_peak_date=d["max_drawdown_peak_date"],
        max_drawdown_trough_date=d["max_drawdown_trough_date"],
        total_dividends_eur=d["total_dividends_eur"],
        total_realized_gain_eur=d["total_realized_gain_eur"],
        total_unrealized_gain_eur=d["total_unrealized_gain_eur"],
        total_fees_eur=d["total_fees_eur"],
        positions=positions,
        closed_positions=closed_positions,
        position_lots=d["position_lots"],
        benchmarks=benchmarks,
        daily_series=daily_series,
        benchmark_series=benchmark_series,
        risk_metrics=d["risk_metrics"],
        start_date=d["start_date"],
        end_date=d["end_date"],
        scope=d["scope"],
    )
