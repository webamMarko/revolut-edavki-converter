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
    p_analytics.add_argument("--scope", choices=["stock", "cfd", "all"], default="all",
                             help="Asset class scope (default: all)")
    p_analytics.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_analytics.set_defaults(func=cmd_analytics)

    # --- tax ---
    p_tax = subparsers.add_parser("tax", help="Compute Slovenian capital gains tax")
    p_tax.add_argument("--year", type=int, required=True, help="Fiscal year")
    p_tax.add_argument("--include-unrealized", action="store_true",
                       help="Include unrealized tax liability")
    p_tax.add_argument("--scope", choices=["stock", "cfd", "all"], default="all",
                       help="Asset class scope (default: all)")
    p_tax.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_tax.set_defaults(func=cmd_tax)

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
