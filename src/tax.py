"""Slovenian capital gains tax computation."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


def slovenian_tax_rate(holding_years: float) -> float:
    """Return the Slovenian capital gains tax rate for stocks/crypto/savings.

    - 0–5 years:   25%
    - 5–10 years:  20%
    - 10–15 years: 15%
    - 15–20 years: 10%
    - 20+ years:    0%
    """
    if holding_years >= 20:
        return 0.0
    elif holding_years >= 15:
        return 0.10
    elif holding_years >= 10:
        return 0.15
    elif holding_years >= 5:
        return 0.20
    else:
        return 0.25


def slovenian_cfd_tax_rate(holding_years: float) -> float:
    """Return the Slovenian tax rate for derivative financial instruments (CFDs).

    Source: FURS – Odsvojil sem izvedene finančne instrumente (effective 2020-01-01)
    - < 1 year:    40%
    - 1–5 years:   27.5%
    - 5–10 years:  20%
    - 10–15 years: 15%
    - 15–20 years: 10%
    - 20+ years:    0%
    """
    if holding_years >= 20:
        return 0.0
    elif holding_years >= 15:
        return 0.10
    elif holding_years >= 10:
        return 0.15
    elif holding_years >= 5:
        return 0.20
    elif holding_years >= 1:
        return 0.275
    else:
        return 0.40


def standardized_costs(cost_basis_eur: float, proceeds_eur: float, leveraged: bool) -> float:
    """Return Slovenian standardized cost allowance that reduces the tax base.

    Source: FURS – 0.25% of acquisition + 0.25% of disposal for leveraged instruments;
    1% + 1% for regular instruments. Reduces only a positive gain, cannot exceed it.
    """
    rate = 0.0025 if leveraged else 0.01
    return rate * (cost_basis_eur + proceeds_eur)


@dataclass
class SaleTaxDetail:
    ticker: str
    sell_date: str
    quantity: float
    sell_price_eur: float
    cost_basis_eur: float
    gain_eur: float          # raw gain/loss before standardized costs
    std_costs_eur: float     # standardized cost allowance (reduces positive gains)
    holding_years: float
    tax_rate: float
    tax_eur: float           # per-trade estimate; final tax uses netting (total_realized_tax_eur)


@dataclass
class UnrealizedTaxDetail:
    ticker: str
    quantity: float
    market_value_eur: float
    cost_basis_eur: float
    gain_eur: float
    avg_holding_years: float
    tax_rate: float
    tax_eur: float


@dataclass
class TaxReport:
    year: int
    # Realized
    realized_sales: list[SaleTaxDetail]
    total_realized_gain_eur: float
    total_realized_tax_eur: float
    # Unrealized (optional)
    unrealized_positions: list[UnrealizedTaxDetail]
    total_unrealized_gain_eur: float
    total_unrealized_tax_eur: float
    include_unrealized: bool
    # Dividends
    total_dividends_eur: float
    # Fees (commissions + overnight)
    total_fees_eur: float
    # Summary
    total_tax_eur: float
    # Scope
    scope: str


def compute_tax_report(conn: sqlite3.Connection, year: int,
                       include_unrealized: bool = False,
                       scope: str = "all") -> TaxReport:
    """Compute Slovenian capital gains tax for a fiscal year.

    scope: 'stock', 'cfd', 'crypto', or 'all'
    """
    # Real estate (asset_class='realestate') is taxed under a separate Slovenian form
    # (Doh-Nepremičnine) and must not be included in this Doh-KDVP calculation.
    if scope == "all":
        transactions = conn.execute(
            """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                      currency, fx_rate, asset_class
               FROM transactions WHERE asset_class != 'realestate' ORDER BY date"""
        ).fetchall()
    else:
        transactions = conn.execute(
            """SELECT date, ticker, type, quantity, price_per_share, total_amount,
                      currency, fx_rate, asset_class
               FROM transactions WHERE asset_class = ? ORDER BY date""",
            (scope,)
        ).fetchall()
    transactions = [dict(r) for r in transactions]

    is_cfd_scope = scope == "cfd"

    # Build FIFO lots and process sales
    fifo_lots = defaultdict(list)  # ticker -> [(qty, cost_per_share_eur, buy_date_str)] for longs
    short_lots = defaultdict(list)  # ticker -> [(qty, entry_pps_eur, sell_date_str)] for shorts
    holdings = defaultdict(float)  # signed: positive=long, negative=short
    realized_sales = []
    total_dividends = 0.0
    total_fees = 0.0

    for tx in transactions:
        tx_type = tx["type"]
        ticker = tx["ticker"]
        qty = tx["quantity"] or 0
        amount = tx["total_amount"] or 0
        fx = tx["fx_rate"] or 1.0
        pps = tx["price_per_share"] or 0
        date_str = tx["date"][:10]

        # In 'all' scope, prefix CFD/crypto/savings tickers to avoid mixing with stocks
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
        amount_eur = abs(amount) / fx if fx > 0 else abs(amount)

        if "BUY" in tx_type and ticker and (is_cfd_tx or is_cfd_scope):
            # CFD BUY: can close shorts and/or open longs
            buy_date = datetime.strptime(date_str, "%Y-%m-%d")
            remaining = qty

            # Close short positions first (FIFO)
            if holdings.get(ticker, 0) < 0:
                new_shorts = []
                for s_qty, s_pps, s_date_str in short_lots.get(ticker, []):
                    if remaining <= 0:
                        new_shorts.append((s_qty, s_pps, s_date_str))
                        continue
                    entry_date = datetime.strptime(s_date_str, "%Y-%m-%d")
                    matched = min(s_qty, remaining)
                    # P&L on closing short: (entry_price - exit_price) * qty
                    gain = (s_pps - pps_eur) * matched
                    holding_days = (buy_date - entry_date).days
                    holding_years = holding_days / 365.25

                    if buy_date.year == year:
                        rate = slovenian_cfd_tax_rate(holding_years) if is_cfd_tx else slovenian_tax_rate(holding_years)
                        proceeds = matched * s_pps
                        basis = matched * pps_eur
                        std_c = standardized_costs(basis, proceeds, leveraged=is_cfd_tx)
                        gain_for_tax = max(0, gain - std_c) if gain > 0 else gain
                        tax = max(0, gain_for_tax * rate)
                        realized_sales.append(SaleTaxDetail(
                            ticker=ticker, sell_date=date_str, quantity=matched,
                            sell_price_eur=proceeds, cost_basis_eur=basis,
                            gain_eur=gain, std_costs_eur=std_c if gain > 0 else 0.0,
                            holding_years=holding_years, tax_rate=rate, tax_eur=tax,
                        ))

                    if s_qty <= remaining:
                        remaining -= s_qty
                        holdings[ticker] += s_qty
                    else:
                        new_shorts.append((s_qty - remaining, s_pps, s_date_str))
                        holdings[ticker] += remaining
                        remaining = 0
                short_lots[ticker] = new_shorts

            # Open long with remainder
            if remaining > 0:
                holdings[ticker] += remaining
                fifo_lots[ticker].append((remaining, pps_eur, date_str))

        elif ("BUY" in tx_type or tx_type == "RECEIVE") and ticker and is_crypto_tx:
            # Crypto BUY/RECEIVE: opens a long
            holdings[ticker] += qty
            fifo_lots[ticker].append((qty, pps_eur, date_str))

        elif tx_type == "BUY" and ticker and is_savings_tx:
            # Savings BUY: deposit into money market fund
            holdings[ticker] += qty
            fifo_lots[ticker].append((qty, pps_eur, date_str))

        elif "BUY" in tx_type and ticker:
            # Stock BUY: always opens a long
            holdings[ticker] += qty
            fifo_lots[ticker].append((qty, pps_eur, date_str))

        elif ("SELL" in tx_type or tx_type == "PAYMENT") and ticker and is_crypto_tx:
            # Crypto SELL/PAYMENT: closes a long (FIFO), same as stock
            holdings[ticker] -= qty
            sell_date = datetime.strptime(date_str, "%Y-%m-%d")

            remaining = qty
            total_cost = 0.0
            weighted_buy_date_sum = 0.0

            new_lots = []
            for lot_qty, lot_cost, lot_date_str in fifo_lots.get(ticker, []):
                if remaining <= 0:
                    new_lots.append((lot_qty, lot_cost, lot_date_str))
                    continue
                buy_date = datetime.strptime(lot_date_str, "%Y-%m-%d")
                if lot_qty <= remaining:
                    total_cost += lot_qty * lot_cost
                    weighted_buy_date_sum += lot_qty * (sell_date - buy_date).days
                    remaining -= lot_qty
                else:
                    total_cost += remaining * lot_cost
                    weighted_buy_date_sum += remaining * (sell_date - buy_date).days
                    new_lots.append((lot_qty - remaining, lot_cost, lot_date_str))
                    remaining = 0
            fifo_lots[ticker] = new_lots

            if sell_date.year == year:
                sold_qty = qty - remaining
                if sold_qty > 0:
                    holding_days = weighted_buy_date_sum / sold_qty if sold_qty > 0 else 0
                    holding_years = holding_days / 365.25
                    gain = amount_eur - total_cost
                    rate = slovenian_tax_rate(holding_years)
                    std_c = standardized_costs(total_cost, amount_eur, leveraged=False)
                    gain_for_tax = max(0, gain - std_c) if gain > 0 else gain
                    tax = max(0, gain_for_tax * rate)
                    realized_sales.append(SaleTaxDetail(
                        ticker=ticker, sell_date=date_str, quantity=qty,
                        sell_price_eur=amount_eur, cost_basis_eur=total_cost,
                        gain_eur=gain, std_costs_eur=std_c if gain > 0 else 0.0,
                        holding_years=holding_years, tax_rate=rate, tax_eur=tax,
                    ))

        elif tx_type == "SELL" and ticker and is_savings_tx:
            # Savings SELL: withdrawal from money market fund (FIFO)
            holdings[ticker] -= qty
            sell_date = datetime.strptime(date_str, "%Y-%m-%d")

            remaining = qty
            total_cost = 0.0
            weighted_buy_date_sum = 0.0

            new_lots = []
            for lot_qty, lot_cost, lot_date_str in fifo_lots.get(ticker, []):
                if remaining <= 0:
                    new_lots.append((lot_qty, lot_cost, lot_date_str))
                    continue
                buy_date = datetime.strptime(lot_date_str, "%Y-%m-%d")
                if lot_qty <= remaining:
                    total_cost += lot_qty * lot_cost
                    weighted_buy_date_sum += lot_qty * (sell_date - buy_date).days
                    remaining -= lot_qty
                else:
                    total_cost += remaining * lot_cost
                    weighted_buy_date_sum += remaining * (sell_date - buy_date).days
                    new_lots.append((lot_qty - remaining, lot_cost, lot_date_str))
                    remaining = 0
            fifo_lots[ticker] = new_lots

            if sell_date.year == year:
                sold_qty = qty - remaining
                if sold_qty > 0:
                    holding_days = weighted_buy_date_sum / sold_qty if sold_qty > 0 else 0
                    holding_years = holding_days / 365.25
                    gain = amount_eur - total_cost
                    rate = slovenian_tax_rate(holding_years)
                    std_c = standardized_costs(total_cost, amount_eur, leveraged=False)
                    gain_for_tax = max(0, gain - std_c) if gain > 0 else gain
                    tax = max(0, gain_for_tax * rate)
                    realized_sales.append(SaleTaxDetail(
                        ticker=ticker, sell_date=date_str, quantity=qty,
                        sell_price_eur=amount_eur, cost_basis_eur=total_cost,
                        gain_eur=gain, std_costs_eur=std_c if gain > 0 else 0.0,
                        holding_years=holding_years, tax_rate=rate, tax_eur=tax,
                    ))

        elif "SELL" in tx_type and ticker and (is_cfd_tx or is_cfd_scope):
            # CFD SELL: can close longs and/or open shorts
            sell_date = datetime.strptime(date_str, "%Y-%m-%d")
            remaining = qty

            # Close long positions first (FIFO)
            if holdings.get(ticker, 0) > 0:
                new_lots = []
                for l_qty, l_pps, l_date_str in fifo_lots.get(ticker, []):
                    if remaining <= 0:
                        new_lots.append((l_qty, l_pps, l_date_str))
                        continue
                    buy_date = datetime.strptime(l_date_str, "%Y-%m-%d")
                    matched = min(l_qty, remaining)
                    gain = (pps_eur - l_pps) * matched
                    holding_days = (sell_date - buy_date).days
                    holding_years = holding_days / 365.25

                    if sell_date.year == year:
                        rate = slovenian_cfd_tax_rate(holding_years) if is_cfd_tx else slovenian_tax_rate(holding_years)
                        proceeds = matched * pps_eur
                        basis = matched * l_pps
                        std_c = standardized_costs(basis, proceeds, leveraged=is_cfd_tx)
                        gain_for_tax = max(0, gain - std_c) if gain > 0 else gain
                        tax = max(0, gain_for_tax * rate)
                        realized_sales.append(SaleTaxDetail(
                            ticker=ticker, sell_date=date_str, quantity=matched,
                            sell_price_eur=proceeds, cost_basis_eur=basis,
                            gain_eur=gain, std_costs_eur=std_c if gain > 0 else 0.0,
                            holding_years=holding_years, tax_rate=rate, tax_eur=tax,
                        ))

                    if l_qty <= remaining:
                        remaining -= l_qty
                        holdings[ticker] -= l_qty
                    else:
                        new_lots.append((l_qty - remaining, l_pps, l_date_str))
                        holdings[ticker] -= remaining
                        remaining = 0
                fifo_lots[ticker] = new_lots

            # Open short with remainder
            if remaining > 0:
                holdings[ticker] -= remaining
                short_lots[ticker].append((remaining, pps_eur, date_str))

        elif "SELL" in tx_type and ticker:
            # Stock SELL: always closes a long
            holdings[ticker] -= qty
            sell_date = datetime.strptime(date_str, "%Y-%m-%d")

            remaining = qty
            total_cost = 0.0
            weighted_buy_date_sum = 0.0

            new_lots = []
            for lot_qty, lot_cost, lot_date_str in fifo_lots.get(ticker, []):
                if remaining <= 0:
                    new_lots.append((lot_qty, lot_cost, lot_date_str))
                    continue

                buy_date = datetime.strptime(lot_date_str, "%Y-%m-%d")

                if lot_qty <= remaining:
                    total_cost += lot_qty * lot_cost
                    weighted_buy_date_sum += lot_qty * (sell_date - buy_date).days
                    remaining -= lot_qty
                else:
                    total_cost += remaining * lot_cost
                    weighted_buy_date_sum += remaining * (sell_date - buy_date).days
                    new_lots.append((lot_qty - remaining, lot_cost, lot_date_str))
                    remaining = 0

            fifo_lots[ticker] = new_lots

            if sell_date.year == year:
                sold_qty = qty - remaining
                if sold_qty > 0:
                    holding_days = weighted_buy_date_sum / sold_qty if sold_qty > 0 else 0
                    holding_years = holding_days / 365.25
                    gain = amount_eur - total_cost
                    rate = slovenian_tax_rate(holding_years)
                    std_c = standardized_costs(total_cost, amount_eur, leveraged=False)
                    gain_for_tax = max(0, gain - std_c) if gain > 0 else gain
                    tax = max(0, gain_for_tax * rate)

                    realized_sales.append(SaleTaxDetail(
                        ticker=ticker, sell_date=date_str, quantity=qty,
                        sell_price_eur=amount_eur, cost_basis_eur=total_cost,
                        gain_eur=gain, std_costs_eur=std_c if gain > 0 else 0.0,
                        holding_years=holding_years, tax_rate=rate, tax_eur=tax,
                    ))

        elif "STOCK SPLIT" in tx_type and ticker:
            old_qty = holdings[ticker]
            if old_qty > 0 and qty != 0:
                ratio = (old_qty + qty) / old_qty
                holdings[ticker] = old_qty + qty
                fifo_lots[ticker] = [
                    (lq * ratio, lc / ratio, ld)
                    for lq, lc, ld in fifo_lots[ticker]
                ]

        elif tx_type in ("DIVIDEND", "BOND COUPON") and amount:
            if datetime.strptime(date_str, "%Y-%m-%d").year == year:
                total_dividends += amount_eur

        elif tx_type in ("STAKING REWARD", "LEARN REWARD") and ticker:
            # Crypto rewards: add to holdings at zero cost
            if qty and qty > 0:
                holdings[ticker] += qty
                fifo_lots[ticker].append((qty, 0.0, date_str))
            if amount_eur > 0 and datetime.strptime(date_str, "%Y-%m-%d").year == year:
                total_dividends += amount_eur

        elif tx_type == "INTEREST PAID" and is_savings_tx:
            # Savings interest: taxable as dividend income
            if amount_eur > 0 and datetime.strptime(date_str, "%Y-%m-%d").year == year:
                total_dividends += amount_eur

        elif tx_type == "SERVICE FEE" and is_savings_tx:
            # Savings service fee
            if datetime.strptime(date_str, "%Y-%m-%d").year == year:
                total_fees -= amount_eur

        elif tx_type in ("INTEREST REINVESTED", "INTEREST WITHDRAWN") and is_savings_tx:
            # Skip: reinvested is handled by BUY, withdrawn is already counted in INTEREST PAID
            pass

        elif tx_type in ("COMMISSION CHARGE", "OVERNIGHT FEE"):
            if datetime.strptime(date_str, "%Y-%m-%d").year == year:
                # Use actual signed amount (negative = cost, positive = income)
                fee_eur = amount / fx if fx > 0 else amount
                total_fees += fee_eur

        elif "MERGER" in tx_type and ticker:
            holdings[ticker] = 0
            if "CASH" in tx_type and datetime.strptime(date_str, "%Y-%m-%d").year == year:
                cost = sum(lq * lc for lq, lc, _ in fifo_lots.get(ticker, []))
                gain = amount_eur - cost
                is_cfd_tx = tx.get("asset_class") == "cfd"
                rate = slovenian_cfd_tax_rate(0) if is_cfd_tx else slovenian_tax_rate(0)
                std_c = standardized_costs(cost, amount_eur, leveraged=is_cfd_tx)
                gain_for_tax = max(0, gain - std_c) if gain > 0 else gain
                tax = max(0, gain_for_tax * rate)
                realized_sales.append(SaleTaxDetail(
                    ticker=ticker, sell_date=date_str, quantity=qty,
                    sell_price_eur=amount_eur, cost_basis_eur=cost,
                    gain_eur=gain, std_costs_eur=std_c if gain > 0 else 0.0,
                    holding_years=0, tax_rate=rate, tax_eur=tax,
                ))
            fifo_lots[ticker] = []

        elif tx_type == "POSITION CLOSURE" and ticker:
            holdings[ticker] = 0
            fifo_lots[ticker] = []

        elif tx_type == "RETURN OF CAPITAL" and ticker:
            # Reduce cost basis proportionally across lots
            lots = fifo_lots.get(ticker, [])
            total_lot_value = sum(lq * lc for lq, lc, ld in lots)
            if total_lot_value > 0:
                reduction_ratio = 1 - (amount_eur / total_lot_value)
                fifo_lots[ticker] = [
                    (lq, lc * max(0, reduction_ratio), ld)
                    for lq, lc, ld in lots
                ]

    # Unrealized tax
    unrealized_positions = []
    total_unrealized_gain = 0.0
    total_unrealized_tax = 0.0

    if include_unrealized:
        today = datetime.now()
        for ticker, qty in sorted(holdings.items()):
            if abs(qty) < 1e-10:
                continue

            lots = fifo_lots.get(ticker, [])
            if not lots:
                continue

            # Get current price
            row = conn.execute(
                "SELECT close, currency FROM daily_prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                (ticker,)
            ).fetchone()
            if not row:
                continue

            close, currency = row[0], row[1]

            # Get FX rate
            fx_row = conn.execute(
                "SELECT eur_usd FROM fx_rates ORDER BY date DESC LIMIT 1"
            ).fetchone()
            fx_rate = fx_row[0] if fx_row else 1.10

            price_eur = close / fx_rate if currency != "EUR" else close
            market_value = qty * price_eur

            cost = sum(lq * lc for lq, lc, _ in lots)
            gain = market_value - cost

            # Weighted average holding period
            weighted_days = sum(
                lq * (today - datetime.strptime(ld, "%Y-%m-%d")).days
                for lq, lc, ld in lots
            )
            total_qty = sum(lq for lq, _, _ in lots)
            avg_years = (weighted_days / total_qty / 365.25) if total_qty > 0 else 0

            is_cfd_ticker = is_cfd_scope or ticker.startswith("CFD:")
            rate = slovenian_cfd_tax_rate(avg_years) if is_cfd_ticker else slovenian_tax_rate(avg_years)
            tax = max(0, gain * rate)

            unrealized_positions.append(UnrealizedTaxDetail(
                ticker=ticker, quantity=qty,
                market_value_eur=market_value, cost_basis_eur=cost,
                gain_eur=gain, avg_holding_years=avg_years,
                tax_rate=rate, tax_eur=tax,
            ))
            total_unrealized_gain += gain
            total_unrealized_tax += tax

    total_realized_gain = sum(s.gain_eur for s in realized_sales)

    # Net gains/losses within each tax rate bucket before applying tax.
    # Standardized costs are only deducted from positive individual gains (per trade),
    # then gains and losses net against each other within the same rate bucket.
    rate_buckets = defaultdict(float)
    for s in realized_sales:
        gain_after_costs = s.gain_eur - s.std_costs_eur if s.gain_eur > 0 else s.gain_eur
        rate_buckets[s.tax_rate] += gain_after_costs
    total_realized_tax = sum(max(0, net_gain) * rate for rate, net_gain in rate_buckets.items())

    return TaxReport(
        year=year,
        realized_sales=realized_sales,
        total_realized_gain_eur=total_realized_gain,
        total_realized_tax_eur=total_realized_tax,
        unrealized_positions=unrealized_positions,
        total_unrealized_gain_eur=total_unrealized_gain,
        total_unrealized_tax_eur=total_unrealized_tax,
        include_unrealized=include_unrealized,
        total_dividends_eur=total_dividends,
        total_fees_eur=total_fees,
        total_tax_eur=total_realized_tax + total_unrealized_tax,
        scope=scope,
    )
