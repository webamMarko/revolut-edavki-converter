"""ISO 3166-1 country list with default currencies (ISO 4217)."""

from __future__ import annotations

COUNTRIES: list[dict] = [
    {"code": "SI", "name": "Slovenia", "currency": "EUR"},
    {"code": "AT", "name": "Austria", "currency": "EUR"},
    {"code": "BE", "name": "Belgium", "currency": "EUR"},
    {"code": "HR", "name": "Croatia", "currency": "EUR"},
    {"code": "CY", "name": "Cyprus", "currency": "EUR"},
    {"code": "EE", "name": "Estonia", "currency": "EUR"},
    {"code": "FI", "name": "Finland", "currency": "EUR"},
    {"code": "FR", "name": "France", "currency": "EUR"},
    {"code": "DE", "name": "Germany", "currency": "EUR"},
    {"code": "GR", "name": "Greece", "currency": "EUR"},
    {"code": "IE", "name": "Ireland", "currency": "EUR"},
    {"code": "IT", "name": "Italy", "currency": "EUR"},
    {"code": "LV", "name": "Latvia", "currency": "EUR"},
    {"code": "LT", "name": "Lithuania", "currency": "EUR"},
    {"code": "LU", "name": "Luxembourg", "currency": "EUR"},
    {"code": "MT", "name": "Malta", "currency": "EUR"},
    {"code": "NL", "name": "Netherlands", "currency": "EUR"},
    {"code": "PT", "name": "Portugal", "currency": "EUR"},
    {"code": "SK", "name": "Slovakia", "currency": "EUR"},
    {"code": "ES", "name": "Spain", "currency": "EUR"},
    {"code": "GB", "name": "United Kingdom", "currency": "GBP"},
    {"code": "US", "name": "United States", "currency": "USD"},
    {"code": "CH", "name": "Switzerland", "currency": "CHF"},
    {"code": "NO", "name": "Norway", "currency": "NOK"},
    {"code": "SE", "name": "Sweden", "currency": "SEK"},
    {"code": "DK", "name": "Denmark", "currency": "DKK"},
    {"code": "PL", "name": "Poland", "currency": "PLN"},
    {"code": "CZ", "name": "Czech Republic", "currency": "CZK"},
    {"code": "HU", "name": "Hungary", "currency": "HUF"},
    {"code": "RO", "name": "Romania", "currency": "RON"},
    {"code": "BG", "name": "Bulgaria", "currency": "BGN"},
    {"code": "RS", "name": "Serbia", "currency": "RSD"},
    {"code": "BA", "name": "Bosnia and Herzegovina", "currency": "BAM"},
    {"code": "ME", "name": "Montenegro", "currency": "EUR"},
    {"code": "MK", "name": "North Macedonia", "currency": "MKD"},
    {"code": "AL", "name": "Albania", "currency": "ALL"},
    {"code": "TR", "name": "Turkey", "currency": "TRY"},
    {"code": "UA", "name": "Ukraine", "currency": "UAH"},
    {"code": "CA", "name": "Canada", "currency": "CAD"},
    {"code": "AU", "name": "Australia", "currency": "AUD"},
    {"code": "JP", "name": "Japan", "currency": "JPY"},
    {"code": "CN", "name": "China", "currency": "CNY"},
    {"code": "IN", "name": "India", "currency": "INR"},
    {"code": "BR", "name": "Brazil", "currency": "BRL"},
    {"code": "MX", "name": "Mexico", "currency": "MXN"},
    {"code": "ZA", "name": "South Africa", "currency": "ZAR"},
    {"code": "AE", "name": "United Arab Emirates", "currency": "AED"},
    {"code": "SG", "name": "Singapore", "currency": "SGD"},
    {"code": "NZ", "name": "New Zealand", "currency": "NZD"},
    {"code": "TH", "name": "Thailand", "currency": "THB"},
]

_CODE_MAP: dict[str, dict] = {c["code"]: c for c in COUNTRIES}
_VALID_CODES: frozenset[str] = frozenset(_CODE_MAP)


def get_country(code: str) -> dict | None:
    return _CODE_MAP.get(code.upper())


def default_currency(code: str) -> str:
    country = _CODE_MAP.get(code.upper())
    return country["currency"] if country else "EUR"


def is_valid_code(code: str) -> bool:
    return code.upper() in _VALID_CODES
