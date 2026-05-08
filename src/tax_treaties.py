"""Double taxation treaty rates for dividend withholding between Slovenia and source countries.

Treaty rates define the maximum withholding tax that the source country can apply.
If actual withholding exceeds the treaty rate, the excess is reclaimable.
Slovenia's domestic dividend tax rate is 25% — any foreign withholding up to the treaty
rate is credited against this obligation.
"""

from dataclasses import dataclass


@dataclass
class TreatyRate:
    source_country: str
    source_country_name: str
    withholding_rate: float  # max treaty withholding (decimal)
    notes: str = ""


# Slovenia's treaties with major dividend-paying countries
# Source: bilateral double taxation agreements (Konvencije o izogibanju dvojnega obdavčevanja)
TREATY_RATES: dict[str, TreatyRate] = {
    "US": TreatyRate("US", "United States", 0.15, "US-SI treaty Art. 10"),
    "GB": TreatyRate("GB", "United Kingdom", 0.15, "UK-SI treaty Art. 10"),
    "DE": TreatyRate("DE", "Germany", 0.15, "DE-SI treaty Art. 10"),
    "FR": TreatyRate("FR", "France", 0.15, "FR-SI treaty Art. 10"),
    "NL": TreatyRate("NL", "Netherlands", 0.15, "NL-SI treaty Art. 10"),
    "IE": TreatyRate("IE", "Ireland", 0.15, "IE-SI treaty Art. 10"),
    "CH": TreatyRate("CH", "Switzerland", 0.15, "CH-SI treaty Art. 10"),
    "AT": TreatyRate("AT", "Austria", 0.15, "AT-SI treaty Art. 10"),
    "IT": TreatyRate("IT", "Italy", 0.15, "IT-SI treaty Art. 10"),
    "ES": TreatyRate("ES", "Spain", 0.15, "ES-SI treaty Art. 10"),
    "SE": TreatyRate("SE", "Sweden", 0.15, "SE-SI treaty Art. 10"),
    "DK": TreatyRate("DK", "Denmark", 0.15, "DK-SI treaty Art. 10"),
    "NO": TreatyRate("NO", "Norway", 0.15, "NO-SI treaty Art. 10"),
    "FI": TreatyRate("FI", "Finland", 0.15, "FI-SI treaty Art. 10"),
    "BE": TreatyRate("BE", "Belgium", 0.15, "BE-SI treaty Art. 10"),
    "LU": TreatyRate("LU", "Luxembourg", 0.15, "LU-SI treaty Art. 10"),
    "CA": TreatyRate("CA", "Canada", 0.15, "CA-SI treaty Art. 10"),
    "JP": TreatyRate("JP", "Japan", 0.05, "JP-SI treaty Art. 10 (5% for 25%+ ownership)"),
    "KR": TreatyRate("KR", "South Korea", 0.15, "KR-SI treaty Art. 10"),
    "CN": TreatyRate("CN", "China", 0.05, "CN-SI treaty Art. 10"),
    "HK": TreatyRate("HK", "Hong Kong", 0.05, "HK-SI treaty Art. 10"),
    "TW": TreatyRate("TW", "Taiwan", 0.10, "TW-SI treaty Art. 10"),
    "IN": TreatyRate("IN", "India", 0.15, "IN-SI treaty Art. 10"),
    "BR": TreatyRate("BR", "Brazil", 0.15, "BR-SI treaty Art. 10"),
    "AU": TreatyRate("AU", "Australia", 0.15, "AU-SI treaty Art. 10"),
    "IL": TreatyRate("IL", "Israel", 0.15, "IL-SI treaty Art. 10"),
}

# Default withholding rate when no treaty exists (FURS guidance)
DEFAULT_WITHHOLDING_RATE = 0.15

# Slovenian domestic dividend tax rate
SI_DIVIDEND_TAX_RATE = 0.25

# Ticker → country mapping for common US-listed stocks
# Most stocks on Revolut are US-listed, so US is the default
TICKER_COUNTRY_MAP: dict[str, str] = {
    # European ADRs / cross-listings
    "NVO": "DK",    # Novo Nordisk (Denmark)
    "ASML": "NL",   # ASML (Netherlands)
    "SAP": "DE",    # SAP (Germany)
    "TM": "JP",     # Toyota (Japan)
    "SONY": "JP",   # Sony (Japan)
    "SNE": "JP",    # Sony (old ticker)
    "TSM": "TW",    # TSMC (Taiwan)
    "BABA": "CN",   # Alibaba (China)
    "JD": "CN",     # JD.com (China, Cayman Islands registered but CN-sourced)
    "NIO": "CN",    # NIO (China)
    "SHOP": "CA",   # Shopify (Canada)
    "RY": "CA",     # Royal Bank of Canada
    "BHP": "AU",    # BHP Group (Australia)
    "RIO": "AU",    # Rio Tinto (Australia)
    "UL": "GB",     # Unilever (UK)
    "BP": "GB",     # BP (UK)
    "SHEL": "GB",   # Shell (UK)
    "AZN": "GB",    # AstraZeneca (UK)
    "GSK": "GB",    # GSK (UK)
    "DEO": "GB",    # Diageo (UK)
    "RHM": "DE",    # Rheinmetall (Germany)
    "CSF": "FR",    # Crédit Agricole (France)
}


def get_source_country(ticker: str, currency: str = "USD") -> str:
    """Infer the source country of a dividend from ticker and currency.

    Priority: explicit ticker map → currency-based heuristic → default US.
    """
    if ticker in TICKER_COUNTRY_MAP:
        return TICKER_COUNTRY_MAP[ticker]
    if currency == "EUR":
        return "DE"  # conservative default for EUR-denominated dividends
    if currency == "GBP":
        return "GB"
    return "US"


def get_treaty_rate(source_country: str) -> float:
    """Return the treaty withholding rate for dividends from the source country."""
    treaty = TREATY_RATES.get(source_country)
    if treaty:
        return treaty.withholding_rate
    return DEFAULT_WITHHOLDING_RATE


def compute_dividend_tax(
    net_dividend_eur: float,
    source_country: str,
    actual_withholding_eur: float = 0.0,
) -> dict:
    """Compute Slovenian dividend tax obligation with treaty credit.

    Args:
        net_dividend_eur: Net dividend received (after foreign withholding) in EUR
        source_country: ISO country code of dividend source
        actual_withholding_eur: Actual withholding tax paid (in EUR), 0 if unknown

    Returns:
        Dict with gross, withholding, SI tax, credit, net tax owed, reclaimable
    """
    treaty_rate = get_treaty_rate(source_country)

    if actual_withholding_eur > 0:
        gross_eur = net_dividend_eur + actual_withholding_eur
        withholding_eur = actual_withholding_eur
    else:
        # Estimate: Revolut pays net of treaty-rate withholding for US stocks
        gross_eur = net_dividend_eur / (1 - treaty_rate)
        withholding_eur = gross_eur * treaty_rate

    # Slovenian tax on gross dividend
    si_tax_gross = gross_eur * SI_DIVIDEND_TAX_RATE

    # Credit: min of (actual withholding, treaty-allowed withholding, SI tax)
    max_credit = gross_eur * treaty_rate
    credit = min(withholding_eur, max_credit, si_tax_gross)

    # Net tax owed to Slovenia
    net_tax_si = max(0.0, si_tax_gross - credit)

    # Reclaimable: any withholding above treaty rate
    reclaimable = max(0.0, withholding_eur - max_credit)

    return {
        "gross_eur": gross_eur,
        "withholding_eur": withholding_eur,
        "treaty_rate": treaty_rate,
        "si_tax_gross": si_tax_gross,
        "credit_eur": credit,
        "net_tax_si": net_tax_si,
        "reclaimable_eur": reclaimable,
        "source_country": source_country,
    }
