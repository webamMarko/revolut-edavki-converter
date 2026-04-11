#!/usr/bin/env python3
"""Command-line interface for Revolut to eDavki converter and portfolio analytics."""

import argparse
import sys
from datetime import datetime
from pathlib import Path


def parse_date(date_string: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_convert(args):
    """Convert Revolut CSV to eDavki XML (original flow, unchanged)."""
    from .revolut_parser import RevolutParser
    from .edavki_generator import EDavkiGenerator

    try:
        if args.verbose:
            print(f"Parsing Revolut file: {args.input_file}")

        revolut_parser = RevolutParser(args.input_file)
        transactions = revolut_parser.parse()

        if args.verbose:
            print(f"Parsed {len(transactions)} transactions")

        if args.completed_only:
            transactions = revolut_parser.filter_completed()
            if args.verbose:
                print(f"Filtered to {len(transactions)} completed transactions")

        if args.start_date and args.end_date:
            transactions = revolut_parser.filter_by_date_range(args.start_date, args.end_date)
            if args.verbose:
                print(f"Filtered to {len(transactions)} transactions in date range")

        if args.currency:
            transactions = revolut_parser.filter_by_currency(args.currency)
            if args.verbose:
                print(f"Filtered to {len(transactions)} transactions in {args.currency}")

        if not transactions:
            print("Warning: No transactions to export after filtering", file=sys.stderr)
            sys.exit(1)

        if args.verbose:
            print("Generating eDavki XML...")

        generator = EDavkiGenerator()
        generator.generate_xml(transactions, args.year)
        generator.save_to_file(args.output_file)

        print(f"Successfully generated {args.output_file} with {len(transactions)} transactions")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def cmd_import(args):
    """Import Revolut CSV/Excel files into the portfolio database."""
    from .db import get_connection
    from .importer import import_csv

    conn = get_connection()
    try:
        for file_path in args.files:
            if args.verbose:
                print(f"Importing {file_path}...")
            result = import_csv(conn, file_path, verbose=args.verbose)
            print(f"{file_path}: {result.new} new, {result.skipped} skipped (of {result.total} rows)")
    finally:
        conn.close()


def cmd_sync(args):
    """Fetch historical prices from Yahoo Finance."""
    from .db import get_connection
    from .price_fetcher import sync_all

    conn = get_connection()
    try:
        sync_all(conn, start_date=args.start_date, end_date=args.end_date, verbose=args.verbose)
    finally:
        conn.close()


def cmd_analytics(args):
    """Display portfolio analytics."""
    from .db import get_connection
    from .analytics import compute_analytics
    from .formatters import format_analytics

    conn = get_connection()
    try:
        results = compute_analytics(
            conn,
            year=args.year,
            start_date=args.start_date,
            end_date=args.end_date,
            scope=args.scope,
        )
        format_analytics(results, fmt=args.format, output=args.output,
                        verbose=args.verbose, chart=args.chart)
    finally:
        conn.close()


def cmd_tax(args):
    """Compute Slovenian capital gains tax."""
    from .db import get_connection
    from .tax import compute_tax_report
    from .formatters import format_tax

    conn = get_connection()
    try:
        report = compute_tax_report(
            conn,
            year=args.year,
            include_unrealized=args.include_unrealized,
            scope=args.scope,
        )
        format_tax(report, verbose=args.verbose)
    finally:
        conn.close()


def cmd_report(args):
    """Generate HTML portfolio report."""
    from .db import get_connection
    from .analytics import compute_analytics
    from .tax import compute_tax_report
    from .html_report import generate_html_report, query_transactions, query_real_estate

    conn = get_connection()
    try:
        analytics = compute_analytics(
            conn, year=args.year, start_date=args.start_date,
            end_date=args.end_date, scope=args.scope,
        )

        tax = None
        tax_year = args.year or (args.end_date.year if args.end_date else datetime.now().year)
        try:
            tax = compute_tax_report(conn, year=tax_year, include_unrealized=True, scope=args.scope)
        except Exception:
            pass

        transactions = query_transactions(conn, scope=args.scope, year=args.year,
                                          start_date=args.start_date, end_date=args.end_date)

        # Per-asset-class analytics for the "all" scope filter UI
        per_class = {}
        if args.scope == "all":
            asset_classes = [r[0] for r in conn.execute(
                "SELECT DISTINCT asset_class FROM transactions"
            ).fetchall()]
            for ac in asset_classes:
                try:
                    per_class[ac] = compute_analytics(
                        conn, year=args.year, start_date=args.start_date,
                        end_date=args.end_date, scope=ac,
                    )
                except Exception:
                    pass

        re_data = query_real_estate(conn)
        html = generate_html_report(analytics, tax, transactions, per_class=per_class, real_estate=re_data)

        output = args.output or f"portfolio_report_{analytics.start_date}_{analytics.end_date}.html"
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Report written to {output}")
    finally:
        conn.close()


def cmd_realestate(args):
    """Manage real estate properties."""
    from .db import get_connection
    from .realestate import (
        add_property, list_properties, set_manual_valuation,
        sync_etn_valuations, PROPERTY_TYPE_LABELS,
    )

    conn = get_connection()
    try:
        subcmd = args.subcmd

        if subcmd == "list":
            props = list_properties(conn)
            if not props:
                print("No properties in database. Use 'realestate add' to add one.")
                return
            print(f"{'Ticker':<8} {'Name':<30} {'Type':<20} {'Area m²':>8} {'Purchase EUR':>13} {'Est. EUR':>10} {'Est. date':<12}")
            print("-" * 110)
            for p in props:
                est = f"{p['estimated_value_eur']:>10,.0f}" if p['estimated_value_eur'] else "        n/a"
                edate = p['estimated_date'] or ""
                print(f"{p['ticker']:<8} {p['name']:<30} {PROPERTY_TYPE_LABELS.get(p['property_type'], p['property_type']):<20} "
                      f"{p['area_m2']:>8.1f} {p['purchase_price_eur']:>13,.0f} {est} {edate:<12}")

        elif subcmd == "add":
            ticker = add_property(
                conn,
                name=args.name,
                address=args.address or "",
                municipality=args.municipality,
                cadastral_municipality=args.cadastral_municipality or "",
                property_type=args.property_type,
                area_m2=args.area_m2,
                purchase_price_eur=args.purchase_price,
                purchase_date=args.purchase_date,
                notes=args.notes or "",
            )
            print(f"Property added with ticker {ticker}")

        elif subcmd == "value":
            set_manual_valuation(conn, args.ticker, args.value_eur, args.date)
            print(f"{args.ticker}: manual valuation set to {args.value_eur:,.0f} EUR")

        elif subcmd == "sync":
            sync_etn_valuations(conn, verbose=args.verbose)

    finally:
        conn.close()


def cmd_web(args):
    """Start web UI for CSV upload and import."""
    from .web import start_server
    start_server(host=args.host, port=args.port, verbose=args.verbose)


def cmd_status(args):
    """Show database status summary."""
    from .db import get_connection, DB_PATH

    if not DB_PATH.exists():
        print("No database found. Run 'import' first.")
        return

    conn = get_connection()
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        ticker_count = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM transactions WHERE ticker IS NOT NULL"
        ).fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(date), MAX(date) FROM transactions"
        ).fetchone()
        import_count = conn.execute("SELECT COUNT(*) FROM import_log").fetchone()[0]
        last_import = conn.execute(
            "SELECT imported_at FROM import_log ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        price_count = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        last_sync = conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_price_sync'"
        ).fetchone()

        print(f"Database:       {DB_PATH}")
        print(f"Transactions:   {row_count}")
        print(f"Tickers:        {ticker_count}")
        if date_range and date_range[0]:
            print(f"Date range:     {date_range[0][:10]} to {date_range[1][:10]}")
        print(f"Imports:        {import_count}")
        if last_import:
            print(f"Last import:    {last_import[0]}")
        print(f"Price records:  {price_count}")
        if last_sync:
            print(f"Last sync:      {last_sync[0]}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Argument parser setup
# ---------------------------------------------------------------------------

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Revolut to eDavki converter & portfolio analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- convert ---
    p_convert = subparsers.add_parser(
        "convert",
        help="Convert Revolut export to eDavki XML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s transactions.csv output.xml --year 2023
  %(prog)s transactions.xlsx output.xml --year 2023 --currency EUR
        """,
    )
    p_convert.add_argument("input_file", help="Path to Revolut export file (CSV or Excel)")
    p_convert.add_argument("output_file", help="Path to output eDavki XML file")
    p_convert.add_argument("--year", type=int, required=True, help="Tax year for the report")
    p_convert.add_argument("--start-date", type=parse_date, help="Filter from date (YYYY-MM-DD)")
    p_convert.add_argument("--end-date", type=parse_date, help="Filter until date (YYYY-MM-DD)")
    p_convert.add_argument("--currency", help="Filter by currency (e.g., EUR, USD)")
    p_convert.add_argument("--completed-only", action="store_true", help="Only completed transactions")
    p_convert.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_convert.set_defaults(func=cmd_convert)

    # --- import ---
    p_import = subparsers.add_parser("import", help="Import Revolut CSV/Excel into portfolio database")
    p_import.add_argument("files", nargs="+", help="CSV or Excel file(s) to import")
    p_import.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_import.set_defaults(func=cmd_import)

    # --- sync ---
    p_sync = subparsers.add_parser("sync", help="Fetch historical prices from Yahoo Finance")
    p_sync.add_argument("--from", dest="start_date", type=parse_date, help="Start date (YYYY-MM-DD)")
    p_sync.add_argument("--to", dest="end_date", type=parse_date, help="End date (YYYY-MM-DD)")
    p_sync.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_sync.set_defaults(func=cmd_sync)

    # --- analytics ---
    p_analytics = subparsers.add_parser("analytics", help="Display portfolio analytics")
    p_analytics.add_argument("--year", type=int, help="Limit to a specific year")
    p_analytics.add_argument("--from", dest="start_date", type=parse_date, help="Start date")
    p_analytics.add_argument("--to", dest="end_date", type=parse_date, help="End date")
    p_analytics.add_argument("--format", choices=["text", "json", "csv"], default="text")
    p_analytics.add_argument("--output", help="Output file (default: stdout)")
    p_analytics.add_argument("--chart", action="store_true", help="Show performance chart")
    p_analytics.add_argument("--scope", choices=["stock", "cfd", "crypto", "savings", "realestate", "all"], default="all",
                             help="Asset class scope (default: all)")
    p_analytics.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_analytics.set_defaults(func=cmd_analytics)

    # --- tax ---
    p_tax = subparsers.add_parser("tax", help="Compute Slovenian capital gains tax")
    p_tax.add_argument("--year", type=int, required=True, help="Fiscal year")
    p_tax.add_argument("--include-unrealized", action="store_true",
                       help="Include unrealized tax liability")
    p_tax.add_argument("--scope", choices=["stock", "cfd", "crypto", "savings", "realestate", "all"], default="all",
                       help="Asset class scope (default: all)")
    p_tax.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_tax.set_defaults(func=cmd_tax)

    # --- report ---
    p_report = subparsers.add_parser("report", help="Generate HTML portfolio report")
    p_report.add_argument("--year", type=int, help="Limit to a specific year")
    p_report.add_argument("--from", dest="start_date", type=parse_date, help="Start date")
    p_report.add_argument("--to", dest="end_date", type=parse_date, help="End date")
    p_report.add_argument("--scope", choices=["stock", "cfd", "crypto", "savings", "realestate", "all"], default="all",
                          help="Asset class scope (default: all)")
    p_report.add_argument("--output", "-o", help="Output HTML file path")
    p_report.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_report.set_defaults(func=cmd_report)

    # --- realestate ---
    p_re = subparsers.add_parser("realestate", help="Manage real estate properties")
    re_sub = p_re.add_subparsers(dest="subcmd", help="Real estate sub-commands")
    p_re.set_defaults(func=cmd_realestate)

    # realestate list
    re_sub.add_parser("list", help="List all properties with latest valuations")

    # realestate add
    p_re_add = re_sub.add_parser("add", help="Add a new property")
    p_re_add.add_argument("--name", required=True, help="Property name / label")
    p_re_add.add_argument("--address", help="Full address")
    p_re_add.add_argument("--municipality", required=True, help="Municipality (občina) for ETN search")
    p_re_add.add_argument("--cadastral-municipality", help="Cadastral municipality (katastrska občina)")
    p_re_add.add_argument("--type", dest="property_type", required=True,
                          choices=["stanovanje", "hisa", "garaza", "poslovni", "zemljisce"],
                          help="Property type")
    p_re_add.add_argument("--area", dest="area_m2", type=float, required=True, help="Area in m²")
    p_re_add.add_argument("--price", dest="purchase_price", type=float, required=True,
                          help="Purchase price in EUR")
    p_re_add.add_argument("--date", dest="purchase_date", required=True, help="Purchase date (YYYY-MM-DD)")
    p_re_add.add_argument("--notes", help="Optional notes")

    # realestate value
    p_re_val = re_sub.add_parser("value", help="Set manual valuation for a property")
    p_re_val.add_argument("ticker", help="Property ticker (e.g. RE001)")
    p_re_val.add_argument("value_eur", type=float, help="Estimated market value in EUR")
    p_re_val.add_argument("--date", help="Valuation date (default: today, YYYY-MM-DD)")

    # realestate sync
    p_re_sync = re_sub.add_parser("sync", help="Sync valuations from ETN database")
    p_re_sync.add_argument("--verbose", "-v", action="store_true")

    # --- web ---
    p_web = subparsers.add_parser("web", help="Start web UI for CSV upload and import")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    p_web.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_web.set_defaults(func=cmd_web)

    # --- status ---
    p_status = subparsers.add_parser("status", help="Show database status")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
