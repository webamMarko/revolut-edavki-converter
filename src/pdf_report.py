"""Generate PDF tax summary report for accountant handoff.

Produces a formatted PDF with: per-ticker gain/loss summary, holding period
breakdown, total tax liability by bracket, and reconciliation details.
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable,
)

from .tax import TaxReport
from .tax_regimes import get_regime


def _fmt_eur(val: float) -> str:
    sign = "-" if val < 0 else ""
    return f"{sign}€{abs(val):,.2f}"


def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def _fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return d or ""


def _header_footer(canvas, doc, year: int, country: str):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm,
                      f"Tax Summary Report — {country} — Year {year}")
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.2 * cm,
                           f"Generated: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    canvas.drawString(2 * cm, 1 * cm, "WealthEagle — Portfolio Tax Report")
    canvas.drawRightString(A4[0] - 2 * cm, 1 * cm, f"Page {doc.page}")
    canvas.restoreState()


def generate_tax_pdf(report: TaxReport, country: str = "SI") -> bytes:
    """Generate PDF bytes from a TaxReport.

    Returns the PDF content as bytes suitable for writing to file or HTTP response.
    """
    regime = get_regime(country)
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "SectionTitle", parent=styles["Heading2"],
        spaceAfter=6, spaceBefore=12,
        textColor=colors.HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        "SubSection", parent=styles["Heading3"],
        spaceAfter=4, spaceBefore=8,
    ))
    styles.add(ParagraphStyle(
        "SmallNote", parent=styles["Normal"],
        fontSize=7, textColor=colors.grey,
    ))

    elements = []

    # --- Title ---
    elements.append(Paragraph(
        f"Capital Gains Tax Summary — {regime.country_name} ({regime.country_code})",
        styles["Title"],
    ))
    elements.append(Paragraph(f"Tax Year: {report.year}", styles["Heading2"]))
    elements.append(Spacer(1, 4 * mm))

    # --- Summary Box ---
    elements.append(Paragraph("Summary", styles["SectionTitle"]))
    summary_data = [
        ["Total Realized Gain/Loss", _fmt_eur(report.total_realized_gain_eur)],
        ["Total Tax Liability (realized)", _fmt_eur(report.total_realized_tax_eur)],
        ["Total Dividends", _fmt_eur(report.total_dividends_eur)],
        ["Total Fees", _fmt_eur(report.total_fees_eur)],
    ]
    if report.include_unrealized:
        summary_data.append(["Total Unrealized Gain/Loss", _fmt_eur(report.total_unrealized_gain_eur)])
        summary_data.append(["Unrealized Tax Estimate", _fmt_eur(report.total_unrealized_tax_eur)])

    summary_table = Table(summary_data, colWidths=[8 * cm, 5 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 6 * mm))

    # --- Tax Regime Info ---
    elements.append(Paragraph("Tax Regime", styles["SectionTitle"]))
    regime_info = [
        f"Country: {regime.country_name} ({regime.country_code})",
        f"Netting: {regime.netting.replace('_', ' ').title()}",
        f"Standardized cost rate: {regime.std_cost_rate * 100:.1f}%",
    ]
    if regime.crypto_exemption_type != "none":
        if regime.crypto_exemption_type == "threshold":
            regime_info.append(f"Crypto exemption: gains under €{regime.crypto_exemption_threshold:,.0f}")
        elif regime.crypto_exemption_type == "holding":
            regime_info.append(f"Crypto exemption: held >{regime.crypto_holding_exempt_years:.0f} year(s)")
    for line in regime_info:
        elements.append(Paragraph(line, styles["Normal"]))

    # Brackets table
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph("Holding Period Tax Rates (Stocks)", styles["SubSection"]))
    bracket_data = [["Min. Holding (years)", "Tax Rate"]]
    for b in regime.stock_brackets:
        bracket_data.append([f"{b.min_years:.0f}+", _fmt_pct(b.rate)])
    bt = Table(bracket_data, colWidths=[5 * cm, 3 * cm])
    bt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(bt)
    elements.append(Spacer(1, 6 * mm))

    # --- Per-Ticker Summary ---
    elements.append(Paragraph("Per-Ticker Gain/Loss Summary", styles["SectionTitle"]))

    if report.realized_sales:
        ticker_summary = defaultdict(lambda: {
            "proceeds": 0.0, "cost": 0.0, "gain": 0.0,
            "std_costs": 0.0, "tax": 0.0, "count": 0,
        })
        for s in report.realized_sales:
            t = ticker_summary[s.ticker]
            t["proceeds"] += s.sell_price_eur
            t["cost"] += s.cost_basis_eur
            t["gain"] += s.gain_eur
            t["std_costs"] += s.std_costs_eur
            t["tax"] += s.tax_eur
            t["count"] += 1

        ticker_data = [["Ticker", "# Sales", "Proceeds", "Cost Basis", "Gain/Loss", "Std Costs", "Tax"]]
        for ticker in sorted(ticker_summary.keys()):
            t = ticker_summary[ticker]
            ticker_data.append([
                ticker,
                str(t["count"]),
                _fmt_eur(t["proceeds"]),
                _fmt_eur(t["cost"]),
                _fmt_eur(t["gain"]),
                _fmt_eur(t["std_costs"]),
                _fmt_eur(t["tax"]),
            ])
        # Totals row
        ticker_data.append([
            "TOTAL",
            str(len(report.realized_sales)),
            _fmt_eur(sum(t["proceeds"] for t in ticker_summary.values())),
            _fmt_eur(sum(t["cost"] for t in ticker_summary.values())),
            _fmt_eur(report.total_realized_gain_eur),
            _fmt_eur(sum(t["std_costs"] for t in ticker_summary.values())),
            _fmt_eur(report.total_realized_tax_eur),
        ])

        col_widths = [2.5 * cm, 1.5 * cm, 2.8 * cm, 2.8 * cm, 2.5 * cm, 2 * cm, 2.5 * cm]
        tt = Table(ticker_data, colWidths=col_widths)
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            # Totals row
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        elements.append(tt)
    else:
        elements.append(Paragraph("No realized sales in this tax year.", styles["Normal"]))

    elements.append(Spacer(1, 6 * mm))

    # --- Holding Period Breakdown ---
    elements.append(Paragraph("Holding Period Breakdown", styles["SectionTitle"]))
    if report.realized_sales:
        bracket_gains = defaultdict(lambda: {"gain": 0.0, "tax": 0.0, "count": 0})
        for s in report.realized_sales:
            key = _fmt_pct(s.tax_rate)
            bracket_gains[key]["gain"] += s.gain_eur
            bracket_gains[key]["tax"] += s.tax_eur
            bracket_gains[key]["count"] += 1

        hp_data = [["Tax Rate", "# Sales", "Total Gain/Loss", "Tax"]]
        for rate_str in sorted(bracket_gains.keys()):
            b = bracket_gains[rate_str]
            hp_data.append([rate_str, str(b["count"]), _fmt_eur(b["gain"]), _fmt_eur(b["tax"])])

        hp_table = Table(hp_data, colWidths=[3 * cm, 2 * cm, 4 * cm, 3.5 * cm])
        hp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(hp_table)
    elements.append(Spacer(1, 6 * mm))

    # --- Detailed Sales (reconciliation) ---
    elements.append(Paragraph("Detailed Realized Sales", styles["SectionTitle"]))
    elements.append(Paragraph(
        "Line-by-line reconciliation of all capital dispositions.",
        styles["SmallNote"],
    ))
    elements.append(Spacer(1, 2 * mm))

    if report.realized_sales:
        detail_data = [["#", "Ticker", "Class", "Date", "Qty", "Proceeds", "Cost", "Gain", "Holding", "Rate", "Tax"]]
        for i, s in enumerate(report.realized_sales, 1):
            detail_data.append([
                str(i),
                s.ticker,
                s.asset_class[:5],
                _fmt_date(s.sell_date),
                f"{s.quantity:.4g}",
                _fmt_eur(s.sell_price_eur),
                _fmt_eur(s.cost_basis_eur),
                _fmt_eur(s.gain_eur),
                f"{s.holding_years:.1f}y",
                _fmt_pct(s.tax_rate),
                _fmt_eur(s.tax_eur),
            ])

        col_w = [0.8 * cm, 2 * cm, 1.2 * cm, 2 * cm, 1.5 * cm, 2.2 * cm, 2.2 * cm, 2 * cm, 1.3 * cm, 1.2 * cm, 2 * cm]
        dt = Table(detail_data, colWidths=col_w, repeatRows=1)
        dt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ]))
        elements.append(dt)

    elements.append(Spacer(1, 8 * mm))

    # --- Footer disclaimer ---
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "This report is generated for informational purposes. Verify all figures with your "
        "tax advisor before filing. Tax calculations are based on FIFO matching and the "
        f"{regime.country_name} tax regime rates as configured.",
        styles["SmallNote"],
    ))

    def on_page(canvas, doc):
        _header_footer(canvas, doc, report.year, regime.country_code)

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
