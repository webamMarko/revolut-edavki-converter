"""Tax export handlers: eDavki XML, FIFO CSV, tax PDF, Doh-Div."""

import csv as _csv
import io
from urllib.parse import parse_qs, urlparse

from .auth import get_session, get_session_token
from .portfolio import portfolio_conn
from .templates import json_response


def export_year(handler):
    """Parse year from query string and validate session. Returns (session, year) or sends error."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return None, None
    qs = parse_qs(urlparse(handler.path).query)
    try:
        year = int(qs.get("year", [0])[0])
    except (ValueError, IndexError):
        json_response(handler, {"error": "Invalid year."}, status=400)
        return None, None
    if year < 2000 or year > 2100:
        json_response(handler, {"error": "Invalid year."}, status=400)
        return None, None
    return session, year


def handle_export_edavki(handler):
    """GET /export/edavki?year=<year> — export eDavki XML."""
    session, year = export_year(handler)
    if session is None:
        return
    import pandas as pd
    from ..revolut_parser import RevolutTransaction
    from ..edavki_generator import EDavkiGenerator

    conn = portfolio_conn(session, get_session_token(handler))
    try:
        rows = conn.execute(
            "SELECT date, ticker, type, quantity, price_per_share, total_amount, "
            "currency, fx_rate, asset_class FROM transactions "
            "WHERE asset_class = 'stock' ORDER BY date"
        ).fetchall()
        # Convert DB rows to RevolutTransaction objects
        transactions = []
        for r in rows:
            s = pd.Series({
                "Type": r[2], "Ticker": r[1], "Quantity": r[3],
                "Price per share": r[4], "Total Amount": r[5],
                "Currency": r[6], "FX Rate": r[7],
                "Completed Date": r[0], "Date": r[0],
                "State": "COMPLETED",
            })
            transactions.append(RevolutTransaction(s))

        gen = EDavkiGenerator()
        gen.generate_xml(transactions, year)
        xml_bytes = gen.to_string(pretty_print=True).encode("utf-8")

        handler.send_response(200)
        handler.send_header("Content-Type", "application/xml; charset=utf-8")
        handler.send_header("Content-Disposition",
                             f'attachment; filename="Doh_KDVP_{year}.xml"')
        handler.send_header("Content-Length", str(len(xml_bytes)))
        handler.end_headers()
        handler.wfile.write(xml_bytes)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def handle_export_fifo_csv(handler):
    """GET /export/fifo-csv?year=<year> — export FIFO transactions CSV."""
    session, year = export_year(handler)
    if session is None:
        return
    from ..tax import compute_tax_report

    conn = portfolio_conn(session, get_session_token(handler))
    try:
        report = compute_tax_report(conn, year=year, include_unrealized=False, scope="all")
        buf = io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow([
            "Ticker", "Asset Class", "Sell Date", "Quantity",
            "Proceeds EUR", "Cost Basis EUR", "Gain EUR",
            "Std Costs EUR", "Holding Years", "Tax Rate", "Tax EUR",
        ])
        for s in report.realized_sales:
            writer.writerow([
                s.ticker, s.asset_class, s.sell_date,
                f"{s.quantity:.6f}", f"{s.sell_price_eur:.2f}",
                f"{s.cost_basis_eur:.2f}", f"{s.gain_eur:.2f}",
                f"{s.std_costs_eur:.2f}", f"{s.holding_years:.2f}",
                f"{s.tax_rate:.4f}", f"{s.tax_eur:.2f}",
            ])
        csv_bytes = buf.getvalue().encode("utf-8")

        handler.send_response(200)
        handler.send_header("Content-Type", "text/csv; charset=utf-8")
        handler.send_header("Content-Disposition",
                             f'attachment; filename="fifo_transactions_{year}.csv"')
        handler.send_header("Content-Length", str(len(csv_bytes)))
        handler.end_headers()
        handler.wfile.write(csv_bytes)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def handle_export_tax_pdf(handler):
    """GET /export/tax-pdf?year=<year>&country=<country> — export tax summary PDF."""
    session, year = export_year(handler)
    if session is None:
        return
    from ..tax import compute_tax_report
    from ..pdf_report import generate_tax_pdf

    qs = parse_qs(urlparse(handler.path).query)
    country = qs.get("country", ["SI"])[0].upper()

    conn = portfolio_conn(session, get_session_token(handler))
    try:
        report = compute_tax_report(conn, year=year, include_unrealized=False,
                                    scope="all", country=country)
        pdf_bytes = generate_tax_pdf(report, country=country)

        handler.send_response(200)
        handler.send_header("Content-Type", "application/pdf")
        handler.send_header("Content-Disposition",
                             f'attachment; filename="tax_summary_{country}_{year}.pdf"')
        handler.send_header("Content-Length", str(len(pdf_bytes)))
        handler.end_headers()
        handler.wfile.write(pdf_bytes)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def handle_export_doh_div(handler):
    """GET /export/doh-div?year=<year> — export Doh-Div dividend XML."""
    session, year = export_year(handler)
    if session is None:
        return
    from ..doh_div_generator import DohDivGenerator, build_dividend_entries

    conn = portfolio_conn(session, get_session_token(handler))
    try:
        entries = build_dividend_entries(conn, year)
        if not entries:
            json_response(handler, {"error": f"No dividends for {year}"}, status=404)
            return

        gen = DohDivGenerator()
        gen.generate_xml(entries, year)
        xml_bytes = gen.to_string(pretty_print=True).encode("utf-8")

        handler.send_response(200)
        handler.send_header("Content-Type", "application/xml; charset=utf-8")
        handler.send_header("Content-Disposition",
                             f'attachment; filename="Doh_Div_{year}.xml"')
        handler.send_header("Content-Length", str(len(xml_bytes)))
        handler.end_headers()
        handler.wfile.write(xml_bytes)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()
