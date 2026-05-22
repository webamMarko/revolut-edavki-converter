"""Generator for eDavki Doh-Div XML (dividend income tax declaration).

Generates the Doh_Div XML file for Slovenian tax authority (FURS) reporting of
dividend income received from foreign sources. Each dividend payment becomes a
separate Dividend element within the declaration.

XML Schema: http://edavki.durs.si/Documents/Schemas/Doh_Div_3.xsd
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .tax_treaties import (
    SI_DIVIDEND_TAX_RATE,
    compute_dividend_tax,
    get_source_country,
    get_treaty_rate,
    TREATY_RATES,
)


@dataclass
class DividendEntry:
    """A single dividend payment for Doh-Div reporting."""
    date: str              # payment date (YYYY-MM-DD)
    ticker: str            # security ticker
    source_country: str    # ISO country code of payer
    gross_eur: float       # gross dividend in EUR
    withholding_eur: float # foreign tax withheld in EUR
    net_eur: float         # net received in EUR
    currency: str          # original currency
    fx_rate: float         # EUR/foreign rate at payment


@dataclass
class DividendTaxSummary:
    """Aggregated dividend tax results for a tax year."""
    year: int
    total_gross_eur: float
    total_withholding_eur: float
    total_net_received_eur: float
    si_tax_liability: float       # 25% on gross
    total_credit_eur: float       # credited foreign tax (up to treaty limit)
    net_tax_owed_si: float        # SI liability minus credits
    total_reclaimable_eur: float  # excess withholding above treaty rates
    entries: list[DividendEntry]
    by_country: dict[str, dict]   # country → aggregated breakdown


class DohDivGenerator:
    """Generator for eDavki Doh-Div (dividend income) XML files."""

    NSMAP = {
        None: "http://edavki.durs.si/Documents/Schemas/Doh_Div_3.xsd",
        'edp': "http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd",
    }

    def __init__(self):
        self.root = None
        self.entries: list[DividendEntry] = []

    def generate_xml(self, entries: list[DividendEntry], tax_year: int,
                     taxpayer_info: dict | None = None) -> etree.Element:
        """Generate Doh-Div XML from dividend entries.

        Args:
            entries: List of DividendEntry for the tax year
            tax_year: Tax year being declared
            taxpayer_info: Optional dict with taxpayer details (taxNumber, name, etc.)
        """
        self.entries = entries

        self.root = etree.Element("Envelope", nsmap=self.NSMAP)

        self._add_header(taxpayer_info)
        self._add_signatures()

        body = etree.SubElement(self.root, "body")
        self._add_body_content(body)

        doh_div = etree.SubElement(body, "Doh_Div")
        self._add_div_metadata(doh_div, tax_year)
        self._add_dividend_items(doh_div)

        return self.root

    def _add_header(self, taxpayer_info: dict | None = None):
        """Add EDP Header element."""
        edp_ns = self.NSMAP['edp']
        header = etree.SubElement(self.root, f"{{{edp_ns}}}Header")
        taxpayer = etree.SubElement(header, f"{{{edp_ns}}}taxpayer")

        if taxpayer_info:
            if taxpayer_info.get("taxNumber"):
                etree.SubElement(taxpayer, f"{{{edp_ns}}}taxNumber").text = taxpayer_info["taxNumber"]
            if taxpayer_info.get("taxpayerType"):
                etree.SubElement(taxpayer, f"{{{edp_ns}}}taxpayerType").text = taxpayer_info["taxpayerType"]
            if taxpayer_info.get("name"):
                etree.SubElement(taxpayer, f"{{{edp_ns}}}name").text = taxpayer_info["name"]
            if taxpayer_info.get("address1"):
                etree.SubElement(taxpayer, f"{{{edp_ns}}}address1").text = taxpayer_info["address1"]
            if taxpayer_info.get("city"):
                etree.SubElement(taxpayer, f"{{{edp_ns}}}city").text = taxpayer_info["city"]
            if taxpayer_info.get("postNumber"):
                etree.SubElement(taxpayer, f"{{{edp_ns}}}postNumber").text = taxpayer_info["postNumber"]

    def _add_signatures(self):
        """Add EDP Signatures element."""
        etree.SubElement(self.root, f"{{{self.NSMAP['edp']}}}Signatures")

    def _add_body_content(self, body: etree.Element):
        """Add EDP bodyContent element."""
        etree.SubElement(body, f"{{{self.NSMAP['edp']}}}bodyContent")

    def _add_div_metadata(self, doh_div: etree.Element, tax_year: int):
        """Add Doh_Div metadata section."""
        etree.SubElement(doh_div, "DocumentWorkflowID").text = "O"
        etree.SubElement(doh_div, "Year").text = str(tax_year)
        etree.SubElement(doh_div, "PeriodStart").text = f"{tax_year}-01-01"
        etree.SubElement(doh_div, "PeriodEnd").text = f"{tax_year}-12-31"

    def _add_dividend_items(self, doh_div: etree.Element):
        """Add individual Dividend elements for each payment."""
        for i, entry in enumerate(self.entries, 1):
            div_el = etree.SubElement(doh_div, "Dividend")

            etree.SubElement(div_el, "Date").text = entry.date
            etree.SubElement(div_el, "PayerName").text = entry.ticker
            etree.SubElement(div_el, "PayerAddress").text = ""
            etree.SubElement(div_el, "PayerCountry").text = entry.source_country
            etree.SubElement(div_el, "Type").text = "1"  # 1 = ordinary dividend

            etree.SubElement(div_el, "Value").text = f"{entry.gross_eur:.2f}"
            etree.SubElement(div_el, "ForeignTax").text = f"{entry.withholding_eur:.2f}"
            etree.SubElement(div_el, "SourceCountry").text = entry.source_country

            # Treaty relief: indicate that treaty was applied
            if entry.source_country in TREATY_RATES:
                etree.SubElement(div_el, "ReliefStatement").text = (
                    f"Konvencija med RS in {TREATY_RATES[entry.source_country].source_country_name}"
                )

    def save_to_file(self, file_path: str, pretty_print: bool = True):
        """Save the generated XML to a file."""
        if self.root is None:
            raise ValueError("No XML generated yet. Call generate_xml() first.")
        tree = etree.ElementTree(self.root)
        tree.write(file_path, pretty_print=pretty_print, xml_declaration=True, encoding='UTF-8')

    def to_string(self, pretty_print: bool = True) -> str:
        """Convert the XML to a string."""
        if self.root is None:
            raise ValueError("No XML generated yet. Call generate_xml() first.")
        return etree.tostring(
            self.root, pretty_print=pretty_print, xml_declaration=True, encoding='UTF-8'
        ).decode('utf-8')


def build_dividend_entries(conn, year: int) -> list[DividendEntry]:
    """Query dividend transactions from DB and build DividendEntry list for a tax year.

    Handles:
    - DIVIDEND type transactions (net amount received)
    - DIVIDEND TAX (CORRECTION) entries (withholding adjustments)
    - Currency conversion via fx_rate
    """
    rows = conn.execute("""
        SELECT date, ticker, type, total_amount, currency, fx_rate
        FROM transactions
        WHERE asset_class = 'stock'
          AND type LIKE 'DIVIDEND%'
          AND date >= ? AND date < ?
        ORDER BY date, ticker
    """, (f"{year}-01-01", f"{year + 1}-01-01")).fetchall()

    # Group by ticker+date to pair dividends with their tax corrections
    from collections import defaultdict
    grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "net_amount": 0.0, "tax_corrections": 0.0,
        "currency": "USD", "fx_rate": 1.0, "date": ""
    })

    for row in rows:
        from .importer import normalize_date
        date_str = normalize_date(row["date"]) or row["date"][:10]
        ticker = row["ticker"] or ""
        tx_type = row["type"]
        amount = row["total_amount"] or 0.0
        currency = row["currency"]
        fx_rate = row["fx_rate"] or 1.0

        key = (ticker, date_str)

        if "TAX" in tx_type or "CORRECTION" in tx_type:
            # Tax correction: negative = withholding taken, positive = refund
            grouped[key]["tax_corrections"] += amount
        else:
            grouped[key]["net_amount"] += amount
            grouped[key]["currency"] = currency
            grouped[key]["fx_rate"] = fx_rate
            grouped[key]["date"] = date_str

    entries = []
    for (ticker, date_str), data in sorted(grouped.items(), key=lambda x: x[0][1]):
        if not data["date"] or data["net_amount"] <= 0:
            continue

        net_amount = data["net_amount"]
        fx_rate = data["fx_rate"]
        currency = data["currency"]

        # Convert to EUR
        if currency == "EUR":
            net_eur = net_amount
        else:
            net_eur = net_amount / fx_rate if fx_rate > 0 else net_amount

        source_country = get_source_country(ticker, currency)
        treaty_rate = get_treaty_rate(source_country)

        # Tax corrections are usually negative (tax taken from account)
        actual_withholding = abs(data["tax_corrections"]) / fx_rate if data["tax_corrections"] < 0 else 0.0

        if actual_withholding > 0:
            gross_eur = net_eur + actual_withholding
            withholding_eur = actual_withholding
        else:
            # Estimate: Revolut withholds at treaty rate for US stocks
            gross_eur = net_eur / (1 - treaty_rate)
            withholding_eur = gross_eur * treaty_rate

        entries.append(DividendEntry(
            date=date_str,
            ticker=ticker,
            source_country=source_country,
            gross_eur=round(gross_eur, 2),
            withholding_eur=round(withholding_eur, 2),
            net_eur=round(net_eur, 2),
            currency=currency,
            fx_rate=fx_rate,
        ))

    return entries


def compute_dividend_tax_summary(entries: list[DividendEntry], year: int) -> DividendTaxSummary:
    """Compute full dividend tax summary with per-country breakdown."""
    from collections import defaultdict

    total_gross = 0.0
    total_withholding = 0.0
    total_net = 0.0
    total_credit = 0.0
    total_reclaimable = 0.0
    by_country: dict[str, dict] = defaultdict(lambda: {
        "gross_eur": 0.0, "withholding_eur": 0.0, "net_eur": 0.0,
        "credit_eur": 0.0, "reclaimable_eur": 0.0, "count": 0,
        "treaty_rate": 0.0, "country_name": "",
    })

    for entry in entries:
        result = compute_dividend_tax(
            net_dividend_eur=entry.net_eur,
            source_country=entry.source_country,
            actual_withholding_eur=entry.withholding_eur,
        )

        total_gross += result["gross_eur"]
        total_withholding += result["withholding_eur"]
        total_net += entry.net_eur
        total_credit += result["credit_eur"]
        total_reclaimable += result["reclaimable_eur"]

        country = entry.source_country
        by_country[country]["gross_eur"] += result["gross_eur"]
        by_country[country]["withholding_eur"] += result["withholding_eur"]
        by_country[country]["net_eur"] += entry.net_eur
        by_country[country]["credit_eur"] += result["credit_eur"]
        by_country[country]["reclaimable_eur"] += result["reclaimable_eur"]
        by_country[country]["count"] += 1
        by_country[country]["treaty_rate"] = get_treaty_rate(country)
        treaty = TREATY_RATES.get(country)
        by_country[country]["country_name"] = treaty.source_country_name if treaty else country

    si_tax_liability = total_gross * SI_DIVIDEND_TAX_RATE

    return DividendTaxSummary(
        year=year,
        total_gross_eur=round(total_gross, 2),
        total_withholding_eur=round(total_withholding, 2),
        total_net_received_eur=round(total_net, 2),
        si_tax_liability=round(si_tax_liability, 2),
        total_credit_eur=round(total_credit, 2),
        net_tax_owed_si=round(max(0, si_tax_liability - total_credit), 2),
        total_reclaimable_eur=round(total_reclaimable, 2),
        entries=entries,
        by_country=dict(by_country),
    )
