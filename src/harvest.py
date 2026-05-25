"""Tax-loss harvesting suggestions engine.

Identifies positions with unrealized losses, ranks them by net tax benefit
considering already-realized gains, and flags wash-sale risk (Slovenia: FURS
treats sell-and-rebuy within 30 days as potentially non-deductible).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .importer import normalize_date
from .tax import (
    compute_tax_report,
    _get_rate_for_class,
)
from .tax_regimes import get_regime, DEFAULT_REGIME


WASH_SALE_WINDOW_DAYS = 30


@dataclass
class HarvestLot:
    """A single FIFO lot with its individual loss and tax saving potential."""
    ticker: str
    buy_date: str
    quantity: float
    cost_per_share_eur: float
    current_price_eur: float
    unrealized_loss_eur: float
    holding_years: float
    tax_rate: float
    potential_saving_eur: float


@dataclass
class HarvestSuggestion:
    """Enhanced harvest candidate with lot-level detail and wash-sale warning."""
    ticker: str
    asset_class: str
    total_quantity: float
    cost_basis_eur: float
    market_value_eur: float
    unrealized_loss_eur: float
    avg_holding_years: float
    tax_rate: float
    potential_tax_saving_eur: float
    # How much of the saving directly offsets realized gains this year
    offsetable_gain_eur: float
    net_benefit_eur: float
    # Wash-sale risk: recent buy within 30 days of today
    wash_sale_risk: bool
    wash_sale_note: str
    # The most recent purchase date that triggers wash-sale, and the safe-to-sell date
    wash_sale_trigger_date: str = ""
    wash_sale_clear_date: str = ""
    # Per-lot breakdown
    lots: list[HarvestLot] = field(default_factory=list)


@dataclass
class HarvestReport:
    """Full tax-loss harvesting analysis."""
    year: int
    country: str
    scope: str
    suggestions: list[HarvestSuggestion]
    total_realized_gain_eur: float
    total_realized_tax_eur: float
    total_harvestable_loss_eur: float
    total_potential_saving_eur: float
    total_offsetable_eur: float
    wash_sale_warning_count: int


def compute_harvest_suggestions(
    conn: sqlite3.Connection,
    year: int,
    scope: str = "all",
    country: str = DEFAULT_REGIME,
    prices_conn: sqlite3.Connection | None = None,
    portfolio_id: int | None = None,
) -> HarvestReport:
    """Compute ranked tax-loss harvesting suggestions.

    Builds on the existing tax report (which already computes realized gains/losses
    and basic harvest candidates), then enhances with:
    - Per-lot breakdown showing which lots are most beneficial to sell
    - Net benefit ranking considering how much loss offsets actual realized gains
    - Wash-sale risk detection (30-day buy window)
    """
    # Resolve shared prices DB for price/FX lookups
    _pconn_owned = False
    if prices_conn is None:
        from .prices_db import get_prices_conn_or_none
        prices_conn = get_prices_conn_or_none()
        _pconn_owned = prices_conn is not None
    _pconn = prices_conn if prices_conn is not None else conn

    regime = get_regime(country)

    tax_report = compute_tax_report(
        conn, year=year, include_unrealized=False, scope=scope, country=country,
        prices_conn=prices_conn, portfolio_id=portfolio_id
    )

    total_realized_gain = tax_report.total_realized_gain_eur
    total_realized_tax = tax_report.total_realized_tax_eur

    # Compute per-class realized gains for netting context
    class_gains: dict[str, float] = defaultdict(float)
    for s in tax_report.realized_sales:
        gain_after_costs = s.gain_eur - s.std_costs_eur if s.gain_eur > 0 else s.gain_eur
        class_gains[s.asset_class] += gain_after_costs

    # Rebuild FIFO lots and detect wash-sale risk from recent buys
    if scope == "all":
        if portfolio_id:
            transactions = conn.execute(
                """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                          currency, fx_rate, asset_class
                   FROM transactions WHERE asset_class != 'realestate' AND portfolio_id = ? ORDER BY date""",
                (portfolio_id,)
            ).fetchall()
        else:
            transactions = conn.execute(
                """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                          currency, fx_rate, asset_class
                   FROM transactions WHERE asset_class != 'realestate' ORDER BY date"""
            ).fetchall()
    else:
        if portfolio_id:
            transactions = conn.execute(
                """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                          currency, fx_rate, asset_class
                   FROM transactions WHERE asset_class = ? AND portfolio_id = ? ORDER BY date""",
                (scope, portfolio_id)
            ).fetchall()
        else:
            transactions = conn.execute(
                """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                          currency, fx_rate, asset_class
                   FROM transactions WHERE asset_class = ? ORDER BY date""",
                (scope,)
            ).fetchall()
    transactions = [dict(r) for r in transactions]

    fifo_lots: dict[str, list] = defaultdict(list)
    holdings: dict[str, float] = defaultdict(float)
    recent_buys: dict[str, list[str]] = defaultdict(list)
    today = datetime.now()
    wash_window_start = today - timedelta(days=WASH_SALE_WINDOW_DAYS)

    for tx in transactions:
        tx_type = tx["type"]
        ticker = tx["ticker"]
        qty = tx["quantity"] or 0
        fx = tx["fx_rate"] or 1.0
        pps = tx["price_per_share"] or 0
        date_str = normalize_date(tx["date"]) or ""

        is_cfd_tx = tx.get("asset_class") == "cfd"
        is_crypto_tx = tx.get("asset_class") == "crypto"
        is_savings_tx = tx.get("asset_class") == "savings"
        if scope == "all" and is_cfd_tx and ticker:
            ticker = f"CFD:{ticker}"
        elif scope == "all" and is_crypto_tx and ticker:
            ticker = f"CRYPTO:{ticker}"
        elif scope == "all" and is_savings_tx and ticker:
            ticker = f"SAVINGS:{ticker}"

        pps_eur = pps / fx if fx > 0 else pps

        if "BUY" in tx_type or tx_type == "RECEIVE":
            if ticker and qty > 0:
                holdings[ticker] += qty
                fifo_lots[ticker].append((qty, pps_eur, date_str))
                if date_str:
                    tx_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if tx_date >= wash_window_start:
                        recent_buys[ticker].append(date_str)

        elif "SELL" in tx_type or tx_type == "PAYMENT":
            if ticker and qty > 0:
                holdings[ticker] -= qty
                remaining = qty
                new_lots = []
                for lot_qty, lot_cost, lot_date_str in fifo_lots.get(ticker, []):
                    if remaining <= 0:
                        new_lots.append((lot_qty, lot_cost, lot_date_str))
                        continue
                    if lot_qty <= remaining:
                        remaining -= lot_qty
                    else:
                        new_lots.append((lot_qty - remaining, lot_cost, lot_date_str))
                        remaining = 0
                fifo_lots[ticker] = new_lots

        elif "STOCK SPLIT" in tx_type and ticker:
            old_qty = holdings[ticker]
            if old_qty > 0 and qty != 0:
                ratio = (old_qty + qty) / old_qty
                holdings[ticker] = old_qty + qty
                fifo_lots[ticker] = [
                    (lq * ratio, lc / ratio, ld)
                    for lq, lc, ld in fifo_lots[ticker]
                ]

        elif tx_type == "RETURN OF CAPITAL" and ticker:
            lots = fifo_lots.get(ticker, [])
            amount_eur = abs(tx["total_amount"] or 0) / fx if fx > 0 else abs(tx["total_amount"] or 0)
            total_lot_value = sum(lq * lc for lq, lc, ld in lots)
            if total_lot_value > 0:
                reduction_ratio = 1 - (amount_eur / total_lot_value)
                fifo_lots[ticker] = [
                    (lq, lc * max(0, reduction_ratio), ld)
                    for lq, lc, ld in lots
                ]

    # Get current prices for all held tickers
    fx_row = _pconn.execute(
        "SELECT rate FROM fx_rates WHERE from_currency = 'USD' AND to_currency = 'EUR' ORDER BY date DESC LIMIT 1"
    ).fetchone()
    fx_rate = fx_row[0] if fx_row else 1.10

    suggestions: list[HarvestSuggestion] = []

    for ticker, qty in sorted(holdings.items()):
        if abs(qty) < 1e-10:
            continue
        lots = fifo_lots.get(ticker, [])
        if not lots:
            continue

        row = _pconn.execute(
            "SELECT close, currency FROM daily_prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        if not row:
            # Try last known price from transactions (for crypto/CFD without yfinance)
            last_tx = conn.execute(
                """SELECT price_per_share, fx_rate FROM transactions
                   WHERE ticker = ? AND price_per_share > 0
                   ORDER BY date DESC LIMIT 1""",
                (ticker.replace("CFD:", "").replace("CRYPTO:", "").replace("SAVINGS:", ""),)
            ).fetchone()
            if not last_tx:
                continue
            close = last_tx[0]
            price_eur = close / (last_tx[1] or 1.0)
        else:
            close, currency = row[0], row[1]
            price_eur = close / fx_rate if currency != "EUR" else close

        market_value = qty * price_eur
        cost = sum(lq * lc for lq, lc, _ in lots)
        unrealized = market_value - cost

        if unrealized >= 0:
            continue

        # Determine asset class
        is_cfd_ticker = ticker.startswith("CFD:")
        is_crypto_ticker = ticker.startswith("CRYPTO:")
        is_savings_ticker = ticker.startswith("SAVINGS:")
        ac = "cfd" if is_cfd_ticker else "crypto" if is_crypto_ticker else "savings" if is_savings_ticker else "stock"

        # Per-lot breakdown
        lot_details = []
        for lq, lc, ld in lots:
            lot_value = lq * price_eur
            lot_cost = lq * lc
            lot_loss = lot_value - lot_cost
            if lot_loss >= 0:
                continue
            buy_date = datetime.strptime(ld, "%Y-%m-%d")
            holding_years = (today - buy_date).days / 365.25
            rate = _get_rate_for_class(regime, ac, holding_years)
            saving = abs(lot_loss) * rate

            if saving > 0.01:
                lot_details.append(HarvestLot(
                    ticker=ticker,
                    buy_date=ld,
                    quantity=lq,
                    cost_per_share_eur=round(lc, 4),
                    current_price_eur=round(price_eur, 4),
                    unrealized_loss_eur=round(lot_loss, 2),
                    holding_years=round(holding_years, 2),
                    tax_rate=rate,
                    potential_saving_eur=round(saving, 2),
                ))

        if not lot_details:
            continue

        # Aggregate
        weighted_days = sum(
            lq * (today - datetime.strptime(ld, "%Y-%m-%d")).days
            for lq, lc, ld in lots
        )
        total_qty = sum(lq for lq, _, _ in lots)
        avg_years = (weighted_days / total_qty / 365.25) if total_qty > 0 else 0
        rate = _get_rate_for_class(regime, ac, avg_years)
        potential_saving = abs(unrealized) * rate

        # Net benefit: how much of this loss can offset actual realized gains
        # Under per-class netting, only offsets gains in same class
        if regime.netting == "per_class":
            available_gain = max(0, class_gains.get(ac, 0))
        else:
            available_gain = max(0, total_realized_gain)

        offsetable = min(abs(unrealized), available_gain)
        net_benefit = offsetable * rate

        # Wash-sale risk detection
        wash_risk = bool(recent_buys.get(ticker))
        wash_note = ""
        wash_trigger_date = ""
        wash_clear_date = ""
        if wash_risk:
            dates = recent_buys[ticker]
            # Most recent buy is the triggering date
            trigger_date = max(dates)
            trigger_dt = datetime.strptime(trigger_date, "%Y-%m-%d")
            clear_dt = trigger_dt + timedelta(days=31)
            wash_trigger_date = trigger_date
            wash_clear_date = clear_dt.strftime("%Y-%m-%d")
            wash_note = (
                f"Recent buy(s) within {WASH_SALE_WINDOW_DAYS} days: "
                f"{', '.join(dates[:3])}"
                f"{' ...' if len(dates) > 3 else ''}. "
                f"FURS may disallow loss if repurchased within short window."
            )

        suggestions.append(HarvestSuggestion(
            ticker=ticker,
            asset_class=ac,
            total_quantity=round(qty, 6),
            cost_basis_eur=round(cost, 2),
            market_value_eur=round(market_value, 2),
            unrealized_loss_eur=round(unrealized, 2),
            avg_holding_years=round(avg_years, 1),
            tax_rate=rate,
            potential_tax_saving_eur=round(potential_saving, 2),
            offsetable_gain_eur=round(offsetable, 2),
            net_benefit_eur=round(net_benefit, 2),
            wash_sale_risk=wash_risk,
            wash_sale_note=wash_note,
            wash_sale_trigger_date=wash_trigger_date,
            wash_sale_clear_date=wash_clear_date,
            lots=lot_details,
        ))

    # Rank by net_benefit descending, then by total potential saving
    suggestions.sort(key=lambda s: (s.net_benefit_eur, s.potential_tax_saving_eur), reverse=True)

    total_harvestable = sum(abs(s.unrealized_loss_eur) for s in suggestions)
    total_saving = sum(s.potential_tax_saving_eur for s in suggestions)
    total_offsetable = sum(s.net_benefit_eur for s in suggestions)
    wash_count = sum(1 for s in suggestions if s.wash_sale_risk)

    result = HarvestReport(
        year=year,
        country=country,
        scope=scope,
        suggestions=suggestions,
        total_realized_gain_eur=round(total_realized_gain, 2),
        total_realized_tax_eur=round(total_realized_tax, 2),
        total_harvestable_loss_eur=round(total_harvestable, 2),
        total_potential_saving_eur=round(total_saving, 2),
        total_offsetable_eur=round(total_offsetable, 2),
        wash_sale_warning_count=wash_count,
    )
    if _pconn_owned:
        prices_conn.close()
    return result
