"""Goal-based investing tracker with Monte Carlo projections."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np


@dataclass
class GoalProjection:
    goal_id: int
    current_value_eur: float
    target_amount_eur: float
    progress_pct: float
    months_remaining: int
    required_monthly_eur: float
    probability_of_success: float
    percentile_10: float
    percentile_50: float
    percentile_90: float


def list_goals(conn: sqlite3.Connection, portfolio_id: int | None = None) -> list[dict]:
    if portfolio_id:
        rows = conn.execute(
            "SELECT id, name, target_amount_eur, target_date, monthly_contribution, "
            "scope, tickers, created_at, updated_at FROM goals WHERE portfolio_id = ? ORDER BY target_date",
            (portfolio_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, target_amount_eur, target_date, monthly_contribution, "
            "scope, tickers, created_at, updated_at FROM goals ORDER BY target_date"
        ).fetchall()
    return [dict(r) for r in rows]


def get_goal(conn: sqlite3.Connection, goal_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, target_amount_eur, target_date, monthly_contribution, "
        "scope, tickers, created_at, updated_at FROM goals WHERE id = ?",
        (goal_id,)
    ).fetchone()
    return dict(row) if row else None


def create_goal(conn: sqlite3.Connection, name: str, target_amount_eur: float,
                target_date: str, monthly_contribution: float = 0,
                scope: str = "all", tickers: str = "",
                portfolio_id: int | None = None) -> int:
    if portfolio_id:
        cur = conn.execute(
            "INSERT INTO goals (name, target_amount_eur, target_date, monthly_contribution, scope, tickers, portfolio_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, target_amount_eur, target_date, monthly_contribution, scope, tickers, portfolio_id)
        )
    else:
        cur = conn.execute(
            "INSERT INTO goals (name, target_amount_eur, target_date, monthly_contribution, scope, tickers) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, target_amount_eur, target_date, monthly_contribution, scope, tickers)
        )
    conn.commit()
    return cur.lastrowid


def update_goal(conn: sqlite3.Connection, goal_id: int, **fields) -> bool:
    allowed = {"name", "target_amount_eur", "target_date", "monthly_contribution", "scope", "tickers"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [goal_id]
    conn.execute(f"UPDATE goals SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return conn.total_changes > 0


def delete_goal(conn: sqlite3.Connection, goal_id: int) -> bool:
    conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    return conn.total_changes > 0


def compute_goal_projection(
    conn: sqlite3.Connection,
    goal_id: int,
    prices_conn: sqlite3.Connection | None = None,
    n_simulations: int = 1000,
) -> GoalProjection | None:
    """Run Monte Carlo simulation for a goal and return projection."""
    goal = get_goal(conn, goal_id)
    if not goal:
        return None

    target_date = datetime.strptime(goal["target_date"], "%Y-%m-%d").date()
    today = date.today()
    if target_date <= today:
        months_remaining = 0
    else:
        months_remaining = (target_date.year - today.year) * 12 + (target_date.month - today.month)

    current_value = _get_current_value(conn, goal, prices_conn)
    target = goal["target_amount_eur"]
    monthly_contrib = goal["monthly_contribution"]

    progress_pct = (current_value / target * 100) if target > 0 else 0

    if months_remaining <= 0:
        return GoalProjection(
            goal_id=goal_id,
            current_value_eur=current_value,
            target_amount_eur=target,
            progress_pct=min(progress_pct, 100),
            months_remaining=0,
            required_monthly_eur=0,
            probability_of_success=100.0 if current_value >= target else 0.0,
            percentile_10=current_value,
            percentile_50=current_value,
            percentile_90=current_value,
        )

    mu, sigma = _estimate_return_params(conn, goal, prices_conn)

    terminal_values = _run_monte_carlo(
        current_value, monthly_contrib, mu, sigma, months_remaining, n_simulations
    )

    probability = float(np.sum(terminal_values >= target) / n_simulations * 100)
    p10 = float(np.percentile(terminal_values, 10))
    p50 = float(np.percentile(terminal_values, 50))
    p90 = float(np.percentile(terminal_values, 90))

    shortfall = target - current_value
    if shortfall <= 0:
        required_monthly = 0.0
    else:
        required_monthly = _required_monthly_contribution(
            current_value, target, mu, months_remaining
        )

    return GoalProjection(
        goal_id=goal_id,
        current_value_eur=round(current_value, 2),
        target_amount_eur=target,
        progress_pct=round(min(progress_pct, 100), 1),
        months_remaining=months_remaining,
        required_monthly_eur=round(max(required_monthly, 0), 2),
        probability_of_success=round(probability, 1),
        percentile_10=round(p10, 2),
        percentile_50=round(p50, 2),
        percentile_90=round(p90, 2),
    )


def _get_current_value(conn: sqlite3.Connection, goal: dict,
                       prices_conn: sqlite3.Connection | None) -> float:
    """Get current portfolio value relevant to the goal's scope/tickers."""
    from .analytics import compute_analytics

    scope = goal["scope"]
    tickers_str = goal["tickers"].strip()

    if scope == "all" and not tickers_str:
        result = compute_analytics(conn, scope="stock", prices_conn=prices_conn)
        return result.portfolio_value_eur

    if tickers_str:
        ticker_list = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
        result = compute_analytics(conn, scope=scope if scope != "all" else "stock", prices_conn=prices_conn)
        total = 0.0
        for p in result.positions:
            if p.ticker in ticker_list:
                total += p.market_value_eur
        return total

    result = compute_analytics(conn, scope=scope, prices_conn=prices_conn)
    return result.portfolio_value_eur


def _estimate_return_params(conn: sqlite3.Connection, goal: dict,
                            prices_conn: sqlite3.Connection | None) -> tuple[float, float]:
    """Estimate monthly return (mu) and volatility (sigma) from historical data."""
    from .analytics import compute_analytics

    scope = goal["scope"] if goal["scope"] != "all" else "stock"

    try:
        result = compute_analytics(conn, scope=scope, prices_conn=prices_conn)
    except (ValueError, Exception):
        return 0.005, 0.04

    daily_series = result.daily_series
    if daily_series is None or len(daily_series) < 60:
        return 0.005, 0.04

    pi = daily_series["perf_index"] if "perf_index" in daily_series.columns else None
    if pi is None:
        return 0.005, 0.04

    pi = pi[pi > 0]
    if len(pi) < 60:
        return 0.005, 0.04

    values = pi.values
    daily_returns = np.diff(values) / values[:-1]
    daily_returns = daily_returns[np.isfinite(daily_returns)]

    if len(daily_returns) < 30:
        return 0.005, 0.04

    mu_daily = float(np.mean(daily_returns))
    sigma_daily = float(np.std(daily_returns, ddof=1))

    mu_monthly = mu_daily * 21
    sigma_monthly = sigma_daily * np.sqrt(21)

    return mu_monthly, sigma_monthly


def _run_monte_carlo(
    current_value: float,
    monthly_contribution: float,
    mu: float,
    sigma: float,
    months: int,
    n_simulations: int,
) -> np.ndarray:
    """Run Monte Carlo simulation returning terminal portfolio values."""
    rng = np.random.default_rng()

    monthly_returns = rng.normal(mu, sigma, size=(n_simulations, months))

    portfolio = np.full(n_simulations, current_value)
    for m in range(months):
        portfolio = portfolio * (1 + monthly_returns[:, m]) + monthly_contribution

    portfolio = np.maximum(portfolio, 0)
    return portfolio


def _required_monthly_contribution(
    current_value: float, target: float, mu_monthly: float, months: int
) -> float:
    """Calculate required monthly contribution assuming expected return."""
    if months <= 0:
        return max(target - current_value, 0)

    future_value_of_current = current_value * (1 + mu_monthly) ** months

    shortfall = target - future_value_of_current
    if shortfall <= 0:
        return 0.0

    if abs(mu_monthly) < 1e-10:
        return shortfall / months

    fv_annuity_factor = ((1 + mu_monthly) ** months - 1) / mu_monthly
    return shortfall / fv_annuity_factor
