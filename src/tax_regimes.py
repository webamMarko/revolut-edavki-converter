"""Tax regime definitions for supported countries.

Each regime defines: capital gains rates, crypto rules, netting rules,
standardized cost allowances, and country-specific exemptions.
"""

from dataclasses import dataclass, field


@dataclass
class TaxBracket:
    min_years: float
    rate: float  # decimal, e.g. 0.25 = 25%


@dataclass
class TaxRegime:
    country_code: str       # ISO 3166-1 alpha-2
    country_name: str
    currency: str           # display currency code
    locale: str             # BCP 47 locale tag for number/date formatting

    # Capital gains brackets (stock / long-term)
    stock_brackets: list[TaxBracket]
    # CFD / derivative brackets (may differ)
    cfd_brackets: list[TaxBracket]
    # Crypto brackets
    crypto_brackets: list[TaxBracket]
    # Savings / money market brackets
    savings_brackets: list[TaxBracket]

    # Standardized cost allowance rates
    std_cost_rate: float = 0.01          # regular instruments
    std_cost_rate_leveraged: float = 0.0025  # leveraged / CFD

    # Crypto exemptions
    crypto_exemption_threshold: float | None = None   # e.g. 5000 EUR for Slovenia
    crypto_exemption_type: str = "none"               # "threshold", "holding", "none"
    crypto_holding_exempt_years: float | None = None   # e.g. 1 year for Germany

    # Loss netting rules
    netting: str = "per_class"  # "per_class", "all_classes", "no_netting"

    # Dividend tax
    dividend_tax_rate: float = 0.0
    dividend_exempt: bool = False

    # Flat tax override (some countries use flat rates regardless of holding)
    flat_rate: float | None = None

    # Display name for the regime
    description: str = ""

    # Legal reference for exemptions/rules
    legal_refs: dict = field(default_factory=dict)


def get_tax_rate(brackets: list[TaxBracket], holding_years: float) -> float:
    """Return tax rate from bracket list for given holding period."""
    # Brackets sorted by min_years descending
    for b in sorted(brackets, key=lambda x: x.min_years, reverse=True):
        if holding_years >= b.min_years:
            return b.rate
    return brackets[0].rate if brackets else 0.0


# ─── Slovenia ───────────────────────────────────────────────────────────

SLOVENIA = TaxRegime(
    country_code="SI",
    country_name="Slovenia",
    currency="EUR",
    locale="sl-SI",
    stock_brackets=[
        TaxBracket(0, 0.25),
        TaxBracket(5, 0.20),
        TaxBracket(10, 0.15),
        TaxBracket(15, 0.10),
        TaxBracket(20, 0.0),
    ],
    cfd_brackets=[
        TaxBracket(0, 0.40),
        TaxBracket(1, 0.275),
        TaxBracket(5, 0.20),
        TaxBracket(10, 0.15),
        TaxBracket(15, 0.10),
        TaxBracket(20, 0.0),
    ],
    crypto_brackets=[
        TaxBracket(0, 0.25),
        TaxBracket(5, 0.20),
        TaxBracket(10, 0.15),
        TaxBracket(15, 0.10),
        TaxBracket(20, 0.0),
    ],
    savings_brackets=[
        TaxBracket(0, 0.25),
        TaxBracket(5, 0.20),
        TaxBracket(10, 0.15),
        TaxBracket(15, 0.10),
        TaxBracket(20, 0.0),
    ],
    std_cost_rate=0.01,
    std_cost_rate_leveraged=0.0025,
    crypto_exemption_threshold=5000.0,
    crypto_exemption_type="threshold",
    netting="per_class",
    dividend_tax_rate=0.25,
    description="Slovenian capital gains tax (Doh-KDVP)",
    legal_refs={
        "crypto_exemption": "ZDoh-2, čl. 97",
        "std_costs": "FURS — normirani stroški",
        "cfd_rates": "FURS — Odsvojil sem izvedene finančne instrumente",
    },
)


# ─── Germany ────────────────────────────────────────────────────────────

GERMANY = TaxRegime(
    country_code="DE",
    country_name="Germany",
    currency="EUR",
    locale="de-DE",
    # Flat 26.375% (25% + 5.5% Solidaritätszuschlag) regardless of holding period
    stock_brackets=[TaxBracket(0, 0.26375)],
    cfd_brackets=[TaxBracket(0, 0.26375)],
    crypto_brackets=[
        TaxBracket(0, 0.0),  # placeholder — crypto uses personal income tax
    ],
    savings_brackets=[TaxBracket(0, 0.26375)],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=600.0,  # Freigrenze: < 600 EUR/year tax-free
    crypto_exemption_type="threshold",
    crypto_holding_exempt_years=1.0,   # held > 1 year = fully exempt
    netting="per_class",  # losses from stocks can only offset stock gains
    dividend_tax_rate=0.26375,
    flat_rate=0.26375,
    description="German Abgeltungsteuer (flat tax on capital gains)",
    legal_refs={
        "flat_tax": "EStG §20, §32d — Abgeltungsteuer 25% + 5.5% Soli",
        "crypto_exemption": "EStG §23 — Freigrenze 600 EUR, 1yr holding exemption",
        "sparerpauschbetrag": "EStG §20(9) — Sparerpauschbetrag 1000 EUR",
    },
)


# ─── Austria ────────────────────────────────────────────────────────────

AUSTRIA = TaxRegime(
    country_code="AT",
    country_name="Austria",
    currency="EUR",
    locale="de-AT",
    # Flat 27.5% KESt
    stock_brackets=[TaxBracket(0, 0.275)],
    cfd_brackets=[TaxBracket(0, 0.275)],
    crypto_brackets=[TaxBracket(0, 0.275)],  # since March 2022
    savings_brackets=[TaxBracket(0, 0.275)],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=None,
    crypto_exemption_type="none",
    netting="all_classes",  # losses from all asset classes can offset each other
    dividend_tax_rate=0.275,
    flat_rate=0.275,
    description="Austrian KESt (Kapitalertragsteuer)",
    legal_refs={
        "kest": "EStG §27a — KESt 27.5%",
        "crypto": "EStG §27b — Kryptowährungen seit 01.03.2022",
    },
)


# ─── United States ──────────────────────────────────────────────────────

US = TaxRegime(
    country_code="US",
    country_name="United States",
    currency="USD",
    locale="en-US",
    # Short-term: taxed as ordinary income (use top bracket ~37% as estimate)
    # Long-term (held > 1 year): 0/15/20% depending on income
    # We use 15% as the default long-term rate (most common bracket)
    stock_brackets=[
        TaxBracket(0, 0.37),    # short-term (ordinary income estimate)
        TaxBracket(1, 0.15),    # long-term
    ],
    cfd_brackets=[
        TaxBracket(0, 0.37),    # 60/40 rule for Section 1256 contracts is complex
        TaxBracket(1, 0.15),
    ],
    crypto_brackets=[
        TaxBracket(0, 0.37),    # short-term
        TaxBracket(1, 0.15),    # long-term
    ],
    savings_brackets=[
        TaxBracket(0, 0.37),
        TaxBracket(1, 0.15),
    ],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=None,
    crypto_exemption_type="none",
    netting="all_classes",  # $3000 annual loss deduction against ordinary income
    dividend_tax_rate=0.15,  # qualified dividends
    description="US federal capital gains tax (estimated rates)",
    legal_refs={
        "short_term": "IRC §1(h) — Short-term gains taxed as ordinary income",
        "long_term": "IRC §1(h) — 0%/15%/20% long-term rates",
        "wash_sale": "IRC §1091 — Wash sale rule (not enforced here)",
        "crypto": "IRS Notice 2014-21 — Crypto treated as property",
    },
)


# ─── Italy ──────────────────────────────────────────────────────────────

ITALY = TaxRegime(
    country_code="IT",
    country_name="Italy",
    currency="EUR",
    locale="it-IT",
    stock_brackets=[TaxBracket(0, 0.26)],
    cfd_brackets=[TaxBracket(0, 0.26)],
    crypto_brackets=[TaxBracket(0, 0.26)],
    savings_brackets=[TaxBracket(0, 0.26)],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=2000.0,  # below 2000 EUR gains per year
    crypto_exemption_type="threshold",
    netting="per_class",
    dividend_tax_rate=0.26,
    flat_rate=0.26,
    description="Italian imposta sostitutiva (26%)",
    legal_refs={
        "rate": "TUIR art. 67 — 26% imposta sostitutiva",
        "crypto": "L. 197/2022 art. 1, c. 126 — crypto 26%, soglia 2000 EUR",
    },
)


# ─── Spain ──────────────────────────────────────────────────────────────

SPAIN = TaxRegime(
    country_code="ES",
    country_name="Spain",
    currency="EUR",
    locale="es-ES",
    # Progressive savings base rates (2024)
    stock_brackets=[
        TaxBracket(0, 0.19),    # first 6000 EUR
    ],
    cfd_brackets=[TaxBracket(0, 0.19)],
    crypto_brackets=[TaxBracket(0, 0.19)],
    savings_brackets=[TaxBracket(0, 0.19)],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=None,
    crypto_exemption_type="none",
    netting="all_classes",
    dividend_tax_rate=0.19,
    flat_rate=0.19,
    description="Spanish savings base tax (base del ahorro)",
    legal_refs={
        "rates": "IRPF art. 66 — 19%/21%/23%/27%/28% progressive",
    },
)


# ─── France ─────────────────────────────────────────────────────────────

FRANCE = TaxRegime(
    country_code="FR",
    country_name="France",
    currency="EUR",
    locale="fr-FR",
    # Flat 30% PFU (Prélèvement Forfaitaire Unique)
    stock_brackets=[TaxBracket(0, 0.30)],
    cfd_brackets=[TaxBracket(0, 0.30)],
    crypto_brackets=[TaxBracket(0, 0.30)],
    savings_brackets=[TaxBracket(0, 0.30)],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=305.0,  # < 305 EUR annual proceeds exempt
    crypto_exemption_type="threshold",
    netting="all_classes",
    dividend_tax_rate=0.30,
    flat_rate=0.30,
    description="French PFU / Flat Tax (30%)",
    legal_refs={
        "pfu": "CGI art. 200A — Prélèvement Forfaitaire Unique 30%",
        "crypto": "CGI art. 150VH bis — seuil 305 EUR",
    },
)


# ─── Netherlands ────────────────────────────────────────────────────────

NETHERLANDS = TaxRegime(
    country_code="NL",
    country_name="Netherlands",
    currency="EUR",
    locale="nl-NL",
    # Box 3: wealth tax on assumed yield, not actual gains
    # 36% on fictional yield (~6.17% in 2024)
    stock_brackets=[TaxBracket(0, 0.36)],  # effective ~2.2% of portfolio value
    cfd_brackets=[TaxBracket(0, 0.36)],
    crypto_brackets=[TaxBracket(0, 0.36)],
    savings_brackets=[TaxBracket(0, 0.36)],
    std_cost_rate=0.0,
    std_cost_rate_leveraged=0.0,
    crypto_exemption_threshold=None,
    crypto_exemption_type="none",
    netting="all_classes",
    dividend_tax_rate=0.15,  # withholding
    flat_rate=0.36,
    description="Dutch Box 3 wealth tax (vermogensrendementsheffing)",
    legal_refs={
        "box3": "IB art. 5.2 — forfaitair rendement",
    },
)


# ─── Registry ───────────────────────────────────────────────────────────

REGIMES: dict[str, TaxRegime] = {
    "SI": SLOVENIA,
    "DE": GERMANY,
    "AT": AUSTRIA,
    "US": US,
    "IT": ITALY,
    "ES": SPAIN,
    "FR": FRANCE,
    "NL": NETHERLANDS,
}

DEFAULT_REGIME = "SI"


def get_regime(code: str) -> TaxRegime:
    """Return a tax regime by country code (case-insensitive)."""
    return REGIMES[code.upper()]


def list_regimes() -> list[dict]:
    """Return summary of all available regimes."""
    return [
        {"code": r.country_code, "name": r.country_name, "description": r.description}
        for r in REGIMES.values()
    ]
