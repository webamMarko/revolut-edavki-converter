"""Output formatting for analytics and tax reports."""

import json
import sys
from tabulate import tabulate


def format_analytics(result, fmt: str = "text", output: str | None = None,
                     verbose: bool = False, chart: bool = False):
    """Format and output analytics results."""
    if fmt == "text":
        _print_analytics_text(result, verbose)
    if chart:
        show_chart(result)
    if fmt == "json":
        data = _analytics_to_dict(result)
        text = json.dumps(data, indent=2, default=str)
        if output:
            with open(output, "w") as f:
                f.write(text)
            print(f"Written to {output}")
        else:
            print(text)
    elif fmt == "csv":
        if output:
            result.daily_series.to_csv(output)
            print(f"Daily series written to {output}")
        else:
            print(result.daily_series.to_csv())


def _print_analytics_text(result, verbose: bool = False):
    """Print analytics as formatted terminal tables."""
    scope_label = {"stock": "STOCKS", "cfd": "CFD", "crypto": "CRYPTO", "savings": "SAVINGS", "all": "ALL"}.get(result.scope, "ALL")
    print("=" * 60)
    print(f"PORTFOLIO ANALYTICS — {scope_label}")
    print(f"Period: {result.start_date} to {result.end_date}")
    print("=" * 60)

    # Summary
    print("\n--- Summary ---")
    summary = [
        ["Portfolio Value", f"{result.portfolio_value_eur:,.2f} EUR"],
        ["Total Invested", f"{result.total_invested_eur:,.2f} EUR"],
        ["Absolute Gain", f"{result.absolute_gain_eur:,.2f} EUR"],
        ["Total Return", f"{result.total_return_pct:,.2f}%"],
    ]
    if result.cagr_pct is not None:
        summary.append(["CAGR", f"{result.cagr_pct:,.2f}%"])
    if result.twr_pct is not None:
        summary.append(["Time-Weighted Return", f"{result.twr_pct:,.2f}%"])
    summary.extend([
        ["Max Drawdown", f"{result.max_drawdown_pct:,.2f}%"],
        ["  Peak", result.max_drawdown_peak_date],
        ["  Trough", result.max_drawdown_trough_date],
    ])
    print(tabulate(summary, tablefmt="plain"))

    # Gains breakdown
    print("\n--- Gains Breakdown ---")
    gains = [
        ["Realized Gains", f"{result.total_realized_gain_eur:,.2f} EUR"],
        ["Unrealized Gains", f"{result.total_unrealized_gain_eur:,.2f} EUR"],
        ["Dividends", f"{result.total_dividends_eur:,.2f} EUR"],
    ]
    if result.total_fees_eur != 0:
        gains.append(["Fees (Commissions + Overnight)", f"{result.total_fees_eur:,.2f} EUR"])
    print(tabulate(gains, tablefmt="plain"))

    # Benchmark comparison
    if result.benchmarks:
        print("\n--- Benchmark Comparison ---")
        bench_rows = []
        for b in result.benchmarks:
            bench_rows.append([
                b.name,
                f"{b.return_pct:,.2f}%",
                f"{b.portfolio_return_pct:,.2f}%",
                f"{b.alpha_pct:+,.2f}%",
            ])
        print(tabulate(bench_rows,
                       headers=["Benchmark", "Benchmark Return", "Portfolio Return", "Alpha"],
                       tablefmt="simple"))

    # Positions
    if result.positions:
        print("\n--- Current Positions ---")
        pos_rows = []
        for p in sorted(result.positions, key=lambda x: x.market_value_eur, reverse=True):
            pos_rows.append([
                p.ticker,
                f"{p.quantity:,.4f}",
                f"{p.cost_basis_eur:,.2f}",
                f"{p.market_value_eur:,.2f}",
                f"{p.unrealized_gain_eur:+,.2f}",
                f"{p.unrealized_gain_pct:+,.1f}%",
                f"{p.weight_pct:,.1f}%",
            ])
        print(tabulate(pos_rows,
                       headers=["Ticker", "Qty", "Cost Basis", "Mkt Value",
                                "Unrealized", "Return %", "Weight"],
                       tablefmt="simple"))

    print()


def _analytics_to_dict(result) -> dict:
    """Convert analytics result to a JSON-serializable dict."""
    return {
        "period": {"start": result.start_date, "end": result.end_date},
        "summary": {
            "portfolio_value_eur": round(result.portfolio_value_eur, 2),
            "total_invested_eur": round(result.total_invested_eur, 2),
            "absolute_gain_eur": round(result.absolute_gain_eur, 2),
            "total_return_pct": round(result.total_return_pct, 2),
            "cagr_pct": round(result.cagr_pct, 2) if result.cagr_pct else None,
            "twr_pct": round(result.twr_pct, 2) if result.twr_pct else None,
            "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        },
        "gains": {
            "realized_eur": round(result.total_realized_gain_eur, 2),
            "unrealized_eur": round(result.total_unrealized_gain_eur, 2),
            "dividends_eur": round(result.total_dividends_eur, 2),
            "fees_eur": round(result.total_fees_eur, 2),
        },
        "benchmarks": [
            {
                "name": b.name,
                "return_pct": round(b.return_pct, 2),
                "portfolio_return_pct": round(b.portfolio_return_pct, 2),
                "alpha_pct": round(b.alpha_pct, 2),
            }
            for b in result.benchmarks
        ],
        "positions": [
            {
                "ticker": p.ticker,
                "quantity": round(p.quantity, 4),
                "cost_basis_eur": round(p.cost_basis_eur, 2),
                "market_value_eur": round(p.market_value_eur, 2),
                "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                "weight_pct": round(p.weight_pct, 2),
            }
            for p in result.positions
        ],
    }


def format_tax(report, verbose: bool = False):
    """Print tax report as formatted terminal output."""
    scope_label = {"stock": "STOCKS", "cfd": "CFD", "crypto": "CRYPTO", "savings": "SAVINGS", "all": "ALL"}.get(report.scope, "ALL")
    country = getattr(report, "country", "SI")
    from .tax_regimes import get_regime
    regime = get_regime(country)
    print("=" * 60)
    print(f"{regime.country_name.upper()} CAPITAL GAINS TAX — {report.year} — {scope_label}")
    print("=" * 60)

    # Realized sales
    if report.realized_sales:
        print("\n--- Realized Sales ---")
        rows = []
        for s in report.realized_sales:
            rows.append([
                s.ticker,
                s.sell_date,
                f"{s.quantity:,.4f}",
                f"{s.sell_price_eur:,.2f}",
                f"{s.cost_basis_eur:,.2f}",
                f"{s.gain_eur:+,.2f}",
                f"{s.holding_years:,.1f}y",
                f"{s.tax_rate:.0%}",
                f"{s.tax_eur:,.2f}",
            ])
        print(tabulate(rows,
                       headers=["Ticker", "Date", "Qty", "Proceeds", "Cost Basis",
                                "Gain", "Held", "Rate", "Tax"],
                       tablefmt="simple"))
    else:
        print("\nNo realized sales in this year.")

    # Summary
    print("\n--- Realized Summary ---")
    summary = [
        ["Total Realized Gain", f"{report.total_realized_gain_eur:+,.2f} EUR"],
        ["Total Tax on Realized", f"{report.total_realized_tax_eur:,.2f} EUR"],
        ["Dividend Income", f"{report.total_dividends_eur:,.2f} EUR"],
    ]
    if report.total_fees_eur != 0:
        summary.append(["Fees (Commissions + Overnight)", f"{report.total_fees_eur:,.2f} EUR"])
    print(tabulate(summary, tablefmt="plain"))

    # Unrealized
    if report.include_unrealized and report.unrealized_positions:
        print("\n--- Unrealized Positions (hypothetical tax if sold today) ---")
        rows = []
        for u in report.unrealized_positions:
            rows.append([
                u.ticker,
                f"{u.quantity:,.4f}",
                f"{u.market_value_eur:,.2f}",
                f"{u.cost_basis_eur:,.2f}",
                f"{u.gain_eur:+,.2f}",
                f"{u.avg_holding_years:,.1f}y",
                f"{u.tax_rate:.0%}",
                f"{u.tax_eur:,.2f}",
            ])
        print(tabulate(rows,
                       headers=["Ticker", "Qty", "Mkt Value", "Cost Basis",
                                "Gain", "Avg Held", "Rate", "Tax"],
                       tablefmt="simple"))

        print(f"\nTotal Unrealized Tax:  {report.total_unrealized_tax_eur:,.2f} EUR")

    print(f"\n{'=' * 60}")
    print(f"TOTAL TAX LIABILITY:  {report.total_tax_eur:,.2f} EUR")
    print(f"{'=' * 60}")
    print()


def show_chart(result):
    """Display portfolio performance chart with benchmarks."""
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import pandas as pd
    from .price_fetcher import BENCHMARKS

    daily = result.daily_series
    dates = pd.to_datetime(daily.index)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[2, 1],
                                    sharex=True)
    fig.suptitle(f"Portfolio Analytics  |  {result.start_date} to {result.end_date}",
                 fontsize=13, fontweight="bold")

    # --- Top chart: portfolio value + invested ---
    ax1.fill_between(dates, daily["value_eur"], alpha=0.15, color="C0")
    ax1.plot(dates, daily["value_eur"], linewidth=1.5, color="C0", label="Portfolio Value")
    ax1.plot(dates, daily["invested_eur"], linewidth=1, color="gray",
             linestyle="--", label="Cash Invested")
    ax1.set_ylabel("EUR")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_title("Portfolio Value vs Cash Invested", fontsize=10)

    # --- Bottom chart: rebased performance vs benchmarks ---
    # Rebase portfolio to 100 using invested capital as the base, so the
    # scale is comparable to benchmark index growth (100 → ~200).
    # portfolio_rebased = (value / invested) * 100
    portfolio_values = daily["value_eur"]
    invested_values = daily["invested_eur"]

    # Use value/invested ratio, rebased to 100
    mask = invested_values > 0
    rebased_portfolio = pd.Series(index=daily.index, dtype=float)
    rebased_portfolio[mask] = (portfolio_values[mask] / invested_values[mask]) * 100
    rebased_portfolio = rebased_portfolio.ffill().fillna(100)
    ax2.plot(dates, rebased_portfolio, linewidth=1.8, color="C0", label="Portfolio")

    # Plot benchmarks
    colors = {"^GSPC": "C1", "^IXIC": "C2", "^DJI": "C3", "^FTSE": "C4"}
    for ticker, series in result.benchmark_series.items():
        name = BENCHMARKS.get(ticker, ticker)
        bench_dates = pd.to_datetime(series.index)
        ax2.plot(bench_dates, series.values, linewidth=1, alpha=0.8,
                 color=colors.get(ticker, "C5"), label=name)

    ax2.axhline(y=100, color="gray", linewidth=0.5, linestyle=":")
    ax2.set_ylabel("Value per 100 EUR invested")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize=8, ncol=3)
    ax2.grid(True, alpha=0.3)
    ax2.set_title("Portfolio vs Benchmarks (100 = breakeven)", fontsize=10)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()
    plt.show()
