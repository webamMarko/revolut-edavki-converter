"""Persistent caching layer for compute_tax_report() results."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime

from .tax import TaxReport, SaleTaxDetail, UnrealizedTaxDetail, TaxLossHarvestCandidate


def get_cached_tax(conn: sqlite3.Connection, year: int, scope: str,
                   country: str, data_hash: str,
                   portfolio_id: int | None = None) -> TaxReport | None:
    """Return cached TaxReport if valid, else None.

    Immutable entries (past years) skip hash check entirely.
    Current-year entries require matching data_hash.
    """
    if portfolio_id:
        row = conn.execute(
            "SELECT result_json, is_immutable, data_hash FROM cached_tax_reports "
            "WHERE year = ? AND scope = ? AND country = ? AND portfolio_id = ?",
            (year, scope, country, portfolio_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT result_json, is_immutable, data_hash FROM cached_tax_reports "
            "WHERE year = ? AND scope = ? AND country = ?",
            (year, scope, country)
        ).fetchone()
    if not row:
        return None
    if row["is_immutable"]:
        return _deserialize(row["result_json"])
    if row["data_hash"] == data_hash:
        return _deserialize(row["result_json"])
    return None


def put_tax_cache(conn: sqlite3.Connection, year: int, scope: str,
                  country: str, data_hash: str, report: TaxReport,
                  current_year: int, portfolio_id: int | None = None):
    """Upsert tax report into cache. Mark immutable if year < current_year."""
    result_json = _serialize(report)
    is_immutable = 1 if year < current_year else 0
    if portfolio_id:
        conn.execute(
            "INSERT OR REPLACE INTO cached_tax_reports "
            "(year, scope, country, data_hash, result_json, is_immutable, created_at, portfolio_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (year, scope, country, data_hash, result_json, is_immutable,
             datetime.now().isoformat(), portfolio_id)
        )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO cached_tax_reports "
            "(year, scope, country, data_hash, result_json, is_immutable, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (year, scope, country, data_hash, result_json, is_immutable,
             datetime.now().isoformat())
        )
    conn.commit()


def invalidate_current_year_tax(conn: sqlite3.Connection):
    """Delete mutable (current-year) tax cache entries."""
    conn.execute("DELETE FROM cached_tax_reports WHERE is_immutable = 0")
    conn.commit()


def _serialize(report: TaxReport) -> str:
    d = asdict(report)
    return json.dumps(d)


def _deserialize(json_str: str) -> TaxReport:
    d = json.loads(json_str)
    d["realized_sales"] = [SaleTaxDetail(**s) for s in d["realized_sales"]]
    d["unrealized_positions"] = [UnrealizedTaxDetail(**u) for u in d["unrealized_positions"]]
    if d.get("harvest_candidates") is not None:
        d["harvest_candidates"] = [TaxLossHarvestCandidate(**h) for h in d["harvest_candidates"]]
    return TaxReport(**d)
