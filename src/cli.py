#!/usr/bin/env python3
"""Command-line interface for Revolut to eDavki converter and portfolio analytics."""

import argparse
import os
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

    if getattr(args, 'all_users', False):
        project_data = Path(__file__).resolve().parent.parent / "data"
        default_dir = str(project_data) if project_data.is_dir() else str(Path.home() / ".revolut-edavki")
        data_dir = Path(os.environ.get("REVOLUT_DATA_DIR", default_dir))
        if not data_dir.is_dir():
            print(f"Data directory not found: {data_dir}")
            return
        synced = 0
        for user_dir in sorted(data_dir.iterdir()):
            if not user_dir.is_dir() or user_dir.name.startswith("_"):
                continue
            db_path = user_dir / "portfolio.db"
            if not db_path.exists():
                continue
            print(f"Syncing {user_dir.name} ...")
            conn = get_connection(db_path=db_path)
            try:
                sync_all(conn, start_date=args.start_date, end_date=args.end_date, verbose=args.verbose)
                synced += 1
            except Exception as e:
                print(f"  Error syncing {user_dir.name}: {e}")
            finally:
                conn.close()
        print(f"Synced {synced} portfolio(s).")
    else:
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
    """Compute capital gains tax for the specified country."""
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
            country=getattr(args, "country", "SI"),
        )
        if getattr(args, "pdf", None):
            from .pdf_report import generate_tax_pdf
            pdf_bytes = generate_tax_pdf(report, country=getattr(args, "country", "SI"))
            with open(args.pdf, "wb") as f:
                f.write(pdf_bytes)
            print(f"Tax PDF written to {args.pdf}")
        else:
            format_tax(report, verbose=args.verbose)
    finally:
        conn.close()


def cmd_dividend(args):
    """Generate Doh-Div XML for dividend income tax declaration."""
    from .db import get_connection
    from .doh_div_generator import (
        DohDivGenerator, build_dividend_entries, compute_dividend_tax_summary
    )

    conn = get_connection()
    try:
        entries = build_dividend_entries(conn, args.year)
        if not entries:
            print(f"No dividend income found for {args.year}.")
            return

        summary = compute_dividend_tax_summary(entries, args.year)

        if args.output:
            generator = DohDivGenerator()
            generator.generate_xml(entries, args.year)
            generator.save_to_file(args.output)
            print(f"Doh-Div XML written to {args.output} ({len(entries)} dividends)")

        # Print summary
        print(f"\n{'='*60}")
        print(f" Dividend Tax Summary — {args.year}")
        print(f"{'='*60}")
        print(f" Total gross dividends:     {summary.total_gross_eur:>10.2f} EUR")
        print(f" Foreign withholding tax:   {summary.total_withholding_eur:>10.2f} EUR")
        print(f" Net received:              {summary.total_net_received_eur:>10.2f} EUR")
        print(f" SI tax liability (25%):    {summary.si_tax_liability:>10.2f} EUR")
        print(f" Treaty credit:            -{summary.total_credit_eur:>10.2f} EUR")
        print(f" Net tax owed to FURS:      {summary.net_tax_owed_si:>10.2f} EUR")
        if summary.total_reclaimable_eur > 0:
            print(f" Reclaimable (excess WHT):  {summary.total_reclaimable_eur:>10.2f} EUR")
        print(f"{'='*60}")

        if args.verbose:
            print(f"\n By Country:")
            print(f" {'Country':<20} {'Gross':>10} {'WHT':>10} {'Credit':>10} {'Reclaim':>10}")
            print(f" {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
            for country, data in sorted(summary.by_country.items()):
                print(f" {data['country_name']:<20} "
                      f"{data['gross_eur']:>10.2f} "
                      f"{data['withholding_eur']:>10.2f} "
                      f"{data['credit_eur']:>10.2f} "
                      f"{data['reclaimable_eur']:>10.2f}")

            print(f"\n Reclaim Guidance:")
            for country, data in sorted(summary.by_country.items()):
                if data["reclaimable_eur"] > 0.01:
                    print(f"  • {data['country_name']}: reclaim {data['reclaimable_eur']:.2f} EUR"
                          f" (withheld above {data['treaty_rate']*100:.0f}% treaty rate)")
            if summary.total_reclaimable_eur < 0.01:
                print("  • No excess withholding to reclaim — all within treaty limits.")
    finally:
        conn.close()


def cmd_harvest(args):
    """Show tax-loss harvesting suggestions."""
    from .db import get_connection
    from .harvest import compute_harvest_suggestions
    from .formatters import format_harvest

    conn = get_connection()
    try:
        report = compute_harvest_suggestions(
            conn,
            year=args.year,
            scope=args.scope,
            country=getattr(args, "country", "SI"),
        )
        format_harvest(report, verbose=args.verbose)
    finally:
        conn.close()


def cmd_report(args):
    """Generate HTML portfolio report."""
    from .db import get_connection
    from .analytics import compute_analytics
    from .tax import compute_tax_report
    from .html_report import generate_html_report, query_transactions, query_real_estate, query_fire_config, query_investment_notes

    conn = get_connection()
    try:
        analytics = compute_analytics(
            conn, year=args.year, start_date=args.start_date,
            end_date=args.end_date, scope="all",
        )

        # Compute tax for every year that has transactions (excluding real estate)
        tax_by_year = {}
        try:
            years_with_tx = [
                int(r[0]) for r in conn.execute(
                    "SELECT DISTINCT strftime('%Y', date) FROM transactions "
                    "WHERE asset_class != 'realestate' ORDER BY 1"
                ).fetchall()
            ]
            country = getattr(args, "country", "SI")
            for yr in years_with_tx:
                try:
                    t = compute_tax_report(conn, year=yr, include_unrealized=False, scope="all",
                                           country=country)
                    tax_by_year[yr] = t
                except Exception:
                    pass
        except Exception:
            pass

        transactions = query_transactions(conn, year=args.year,
                                          start_date=args.start_date, end_date=args.end_date)

        # Per-asset-class analytics for the client-side asset class filter UI
        per_class = {}
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
        fire_cfg = query_fire_config(conn)
        notes = query_investment_notes(conn)
        html = generate_html_report(analytics, tax_by_year, transactions, per_class=per_class,
                                     real_estate=re_data, fire_config=fire_cfg,
                                     investment_notes=notes, conn=conn,
                                     country=getattr(args, "country", "SI"))

        output = args.output or f"portfolio_report_{analytics.start_date}_{analytics.end_date}.html"
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Report written to {output}")
    finally:
        conn.close()


def cmd_fire(args):
    """Manage FIRE (Financial Independence) configuration."""
    from .db import get_connection

    conn = get_connection()
    try:
        subcmd = getattr(args, "subcmd", None)

        if subcmd == "set":
            conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('fire_annual_expenses', ?)",
                         (str(args.annual_expenses),))
            conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('fire_annual_income', ?)",
                         (str(args.annual_income),))
            conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('fire_withdrawal_rate', ?)",
                         (str(args.withdrawal_rate),))
            conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('fire_inflation', ?)",
                         (str(args.inflation),))
            conn.commit()
            net = args.annual_expenses - args.annual_income
            target = net / (args.withdrawal_rate / 100)
            real_return = (1 + args.withdrawal_rate / 100) / (1 + args.inflation / 100) - 1
            print(f"FIRE config saved.")
            print(f"  Annual expenses:  €{args.annual_expenses:,.0f}")
            print(f"  Guaranteed income:€{args.annual_income:,.0f}")
            print(f"  Net annual need:  €{net:,.0f}")
            print(f"  Withdrawal rate:  {args.withdrawal_rate:.2f}%")
            print(f"  Expected inflation:{args.inflation:.1f}%")
            print(f"  FIRE target:      €{target:,.0f}")

        elif subcmd == "show":
            from .html_report import query_fire_config
            cfg = query_fire_config(conn)
            if not cfg:
                print("No FIRE config set. Use: fire set --annual-expenses X --annual-income X")
                return
            net = cfg["annual_expenses"] - cfg["annual_income"]
            print(f"FIRE configuration:")
            print(f"  Annual expenses:  €{cfg['annual_expenses']:,.0f}")
            print(f"  Guaranteed income:€{cfg['annual_income']:,.0f}")
            print(f"  Net annual need:  €{net:,.0f}")
            print(f"  Withdrawal rate:  {cfg['withdrawal_rate']:.2f}%")
            print(f"  Expected inflation:{cfg['inflation_rate']:.1f}%")
            print(f"  FIRE target:      €{cfg['target']:,.0f}")

        elif subcmd == "clear":
            conn.execute("DELETE FROM metadata WHERE key LIKE 'fire_%'")
            conn.commit()
            print("FIRE config cleared.")

        else:
            print("Usage: fire <set|show|clear>")
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


def cmd_notes(args):
    """Manage investment notes."""
    import sys
    from .db import get_connection
    from .notes import add_note, list_notes, get_note, edit_note, delete_note

    conn = get_connection()
    try:
        subcmd = getattr(args, "subcmd", None)

        if subcmd == "add":
            body = ""
            if args.body_file:
                body = open(args.body_file, encoding="utf-8").read()
            elif not sys.stdin.isatty():
                body = sys.stdin.read()
            tickers = ",".join(t.strip().upper() for t in (args.tickers or []))
            note_id = add_note(
                conn,
                title=args.title,
                summary=args.summary,
                body=body,
                tickers=tickers,
                conviction=args.conviction,
                action=args.action,
            )
            print(f"Note #{note_id} added.")

        elif subcmd == "list":
            notes = list_notes(conn)
            if not notes:
                print("No investment notes. Use 'notes add' to create one.")
                return
            print(f"{'ID':>3}  {'Conv':<6}  {'Action':<6}  {'Tickers':<20}  Title")
            print("-" * 70)
            for n in notes:
                tickers_str = (n["tickers"] or "—")[:20]
                print(f"{n['id']:>3}  {n['conviction']:<6}  {n['action']:<6}  {tickers_str:<20}  {n['title']}")
                print(f"     {n['summary'][:65]}")
                print()

        elif subcmd == "show":
            note = get_note(conn, args.id)
            if not note:
                print(f"Note #{args.id} not found.", file=sys.stderr)
                sys.exit(1)
            print(f"#{note['id']}  {note['title']}")
            print(f"Tickers:    {note['tickers'] or '—'}")
            print(f"Conviction: {note['conviction']}   Action: {note['action']}")
            print(f"Created:    {note['created_at']}   Updated: {note['updated_at']}")
            print()
            print(note["summary"])
            if note["body"]:
                print()
                print(note["body"])

        elif subcmd == "edit":
            body = None
            if args.body_file:
                body = open(args.body_file, encoding="utf-8").read()
            elif not sys.stdin.isatty():
                body = sys.stdin.read()
            tickers = ",".join(t.strip().upper() for t in args.tickers) if args.tickers else None
            updated = edit_note(
                conn, args.id,
                title=args.title,
                summary=args.summary,
                body=body,
                tickers=tickers,
                conviction=args.conviction,
                action=args.action,
            )
            if updated:
                print(f"Note #{args.id} updated.")
            else:
                print(f"Note #{args.id} not found or nothing changed.", file=sys.stderr)
                sys.exit(1)

        elif subcmd == "delete":
            deleted = delete_note(conn, args.id)
            if deleted:
                print(f"Note #{args.id} deleted.")
            else:
                print(f"Note #{args.id} not found.", file=sys.stderr)
                sys.exit(1)

        else:
            print("Usage: notes <add|list|show|edit|delete>")
    finally:
        conn.close()


def cmd_delisted(args):
    """Mark/unmark/list tickers as delisted."""
    from .db import get_connection
    from .price_fetcher import mark_delisted, unmark_delisted, get_delisted

    conn = get_connection()
    try:
        subcmd = getattr(args, "subcmd", None)
        if subcmd == "mark":
            for ticker in args.tickers:
                mark_delisted(conn, ticker.upper())
                print(f"Marked {ticker.upper()} as delisted.")
        elif subcmd == "unmark":
            for ticker in args.tickers:
                unmark_delisted(conn, ticker.upper())
                print(f"Unmarked {ticker.upper()} (will sync again).")
        elif subcmd == "list":
            tickers = get_delisted(conn)
            if tickers:
                for t in tickers:
                    print(t)
            else:
                print("No tickers marked as delisted.")
        else:
            print("Usage: delisted <mark|unmark|list>")
    finally:
        conn.close()


def cmd_send_reports(args):
    """Send scheduled email reports to subscribed users."""
    from .email_reports import send_reports

    if args.verbose:
        print(f"Running {args.type} report delivery...")
    sent, failed = send_reports(report_type=args.type, verbose=args.verbose)
    print(f"Done: {sent} sent, {failed} failed")


def cmd_web(args):
    """Start web UI for CSV upload and import."""
    import os
    from .web import start_server
    # When spawned by the reloader, always run as plain server (no re-reload)
    reload = args.reload and not os.environ.get("_RELOADER_CHILD")
    start_server(host=args.host, port=args.port, verbose=args.verbose, reload=reload)


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
    p_sync.add_argument("--all-users", action="store_true", help="Sync all user portfolios in REVOLUT_DATA_DIR")
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
    p_tax = subparsers.add_parser("tax", help="Compute capital gains tax")
    p_tax.add_argument("--year", type=int, required=True, help="Fiscal year")
    p_tax.add_argument("--include-unrealized", action="store_true",
                       help="Include unrealized tax liability")
    p_tax.add_argument("--scope", choices=["stock", "cfd", "crypto", "savings", "realestate", "all"], default="all",
                       help="Asset class scope (default: all)")
    p_tax.add_argument("--country", default="SI",
                       help="Country tax regime: SI, DE, AT, US, IT, ES, FR, NL (default: SI)")
    p_tax.add_argument("--pdf", type=str, metavar="FILE",
                       help="Export tax summary as PDF to the specified file")
    p_tax.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_tax.set_defaults(func=cmd_tax)

    # --- dividend ---
    p_div = subparsers.add_parser("dividend", help="Dividend income tax (Doh-Div) declaration")
    p_div.add_argument("--year", type=int, required=True, help="Fiscal year")
    p_div.add_argument("--output", "-o", type=str, metavar="FILE",
                       help="Output Doh-Div XML file path")
    p_div.add_argument("--verbose", "-v", action="store_true",
                       help="Show per-country breakdown and reclaim guidance")
    p_div.set_defaults(func=cmd_dividend)

    # --- harvest ---
    p_harvest = subparsers.add_parser("harvest", help="Tax-loss harvesting suggestions")
    p_harvest.add_argument("--year", type=int, default=datetime.now().year,
                           help="Fiscal year for realized gain context (default: current year)")
    p_harvest.add_argument("--scope", choices=["stock", "cfd", "crypto", "savings", "all"], default="all",
                           help="Asset class scope (default: all)")
    p_harvest.add_argument("--country", default="SI",
                           help="Country tax regime: SI, DE, AT, US, IT, ES, FR, NL (default: SI)")
    p_harvest.add_argument("--verbose", "-v", action="store_true",
                           help="Show per-lot breakdown and wash-sale details")
    p_harvest.set_defaults(func=cmd_harvest)

    # --- report ---
    p_report = subparsers.add_parser("report", help="Generate HTML portfolio report")
    p_report.add_argument("--year", type=int, help="Limit to a specific year")
    p_report.add_argument("--from", dest="start_date", type=parse_date, help="Start date")
    p_report.add_argument("--to", dest="end_date", type=parse_date, help="End date")
    p_report.add_argument("--country", default="SI",
                          help="Country tax regime: SI, DE, AT, US, IT, ES, FR, NL (default: SI)")
    p_report.add_argument("--output", "-o", help="Output HTML file path")
    p_report.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_report.set_defaults(func=cmd_report)

    # --- fire ---
    p_fire = subparsers.add_parser("fire", help="Manage FIRE target configuration")
    fire_sub = p_fire.add_subparsers(dest="subcmd", help="FIRE sub-commands")
    p_fire.set_defaults(func=cmd_fire)

    # fire set
    p_fire_set = fire_sub.add_parser("set", help="Set FIRE parameters")
    p_fire_set.add_argument("--annual-expenses", type=float, required=True,
                             help="Total annual expenses in EUR")
    p_fire_set.add_argument("--annual-income", type=float, default=0.0,
                             help="Guaranteed income offsetting expenses (pension etc.) in EUR (default: 0)")
    p_fire_set.add_argument("--withdrawal-rate", type=float, default=4.0,
                             help="Safe withdrawal rate in %% (default: 4.0)")
    p_fire_set.add_argument("--inflation", type=float, default=2.5,
                             help="Expected annual inflation in %% (default: 2.5)")

    # fire show
    fire_sub.add_parser("show", help="Show current FIRE config and computed target")

    # fire clear
    fire_sub.add_parser("clear", help="Remove FIRE configuration")

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

    # --- notes ---
    p_notes = subparsers.add_parser("notes", help="Manage investment notes")
    notes_sub = p_notes.add_subparsers(dest="subcmd", help="Notes sub-commands")
    p_notes.set_defaults(func=cmd_notes)

    # notes add
    p_notes_add = notes_sub.add_parser("add", help="Add a new investment note")
    p_notes_add.add_argument("--title", required=True, help="Note title")
    p_notes_add.add_argument("--summary", required=True, help="One-to-two sentence summary")
    p_notes_add.add_argument("--tickers", nargs="+", metavar="TICKER", help="Related tickers (space-separated)")
    p_notes_add.add_argument("--conviction", choices=["high", "medium", "low"], default="medium")
    p_notes_add.add_argument("--action", choices=["buy", "watch", "avoid", "sell"], default="watch")
    p_notes_add.add_argument("--body-file", metavar="FILE", help="Markdown body file (or pipe via stdin)")

    # notes list
    notes_sub.add_parser("list", help="List all investment notes")

    # notes show
    p_notes_show = notes_sub.add_parser("show", help="Show a note in full")
    p_notes_show.add_argument("id", type=int, help="Note ID")

    # notes edit
    p_notes_edit = notes_sub.add_parser("edit", help="Edit fields of an existing note")
    p_notes_edit.add_argument("id", type=int, help="Note ID")
    p_notes_edit.add_argument("--title", help="New title")
    p_notes_edit.add_argument("--summary", help="New summary")
    p_notes_edit.add_argument("--tickers", nargs="+", metavar="TICKER")
    p_notes_edit.add_argument("--conviction", choices=["high", "medium", "low"])
    p_notes_edit.add_argument("--action", choices=["buy", "watch", "avoid", "sell"])
    p_notes_edit.add_argument("--body-file", metavar="FILE", help="Replace body from file (or pipe via stdin)")

    # notes delete
    p_notes_del = notes_sub.add_parser("delete", help="Delete a note")
    p_notes_del.add_argument("id", type=int, help="Note ID")

    # --- delisted ---
    p_delisted = subparsers.add_parser("delisted", help="Manage delisted ticker flags")
    delisted_sub = p_delisted.add_subparsers(dest="subcmd", help="Sub-commands")
    p_delisted.set_defaults(func=cmd_delisted)

    p_del_mark = delisted_sub.add_parser("mark", help="Mark ticker(s) as delisted (skip during sync)")
    p_del_mark.add_argument("tickers", nargs="+", metavar="TICKER")

    p_del_unmark = delisted_sub.add_parser("unmark", help="Unmark ticker(s) as delisted")
    p_del_unmark.add_argument("tickers", nargs="+", metavar="TICKER")

    delisted_sub.add_parser("list", help="List all tickers marked as delisted")

    # --- send-reports ---
    p_send = subparsers.add_parser("send-reports", help="Send scheduled email reports to subscribed users")
    p_send.add_argument("--type", choices=["weekly", "monthly"], required=True,
                        help="Report type to send")
    p_send.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_send.set_defaults(func=cmd_send_reports)

    # --- web ---
    p_web = subparsers.add_parser("web", help="Start web UI for CSV upload and import")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    p_web.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_web.add_argument("--reload", "-r", action="store_true",
                       help="Auto-reload on file changes (development mode)")
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
