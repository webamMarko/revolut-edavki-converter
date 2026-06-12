"""Asset class detection rules: weighted header keywords and data patterns."""
import re
from typing import Optional

# Each rule: list of (pattern, weight) tuples.
# Header patterns are matched case-insensitively against stripped column names.
# Data patterns are matched against values in the first data row.
DETECTION_RULES = {
    "stock": {
        "header_keywords": [
            (re.compile(r"\bticker\b", re.I), 3.5),
            # "Price per share" only strong signal when no savings-specific context
            (re.compile(r"\bprice\s*per\s*share\b", re.I), 1.5),
            (re.compile(r"\bisin\b", re.I), 2.5),
            (re.compile(r"\bexchange\b", re.I), 1.5),
            (re.compile(r"\bno\.\s*of\s*shares\b", re.I), 2.5),
            (re.compile(r"\baction\b", re.I), 0.8),
            (re.compile(r"\bdatum\b", re.I), 0.5),
            (re.compile(r"\bproduct\b", re.I), 0.5),
            (re.compile(r"\bdata\s*discriminator\b", re.I), 2.5),
            (re.compile(r"\btrades\b", re.I), 1.5),
            (re.compile(r"\bfinancial\s*instrument\b", re.I), 2.0),
            (re.compile(r"^quantity$", re.I), 1.5),
        ],
        "data_patterns": [],
    },
    "cfd": {
        "header_keywords": [
            (re.compile(r"\bmargin\b", re.I), 4.0),
            (re.compile(r"\bleverage\b", re.I), 4.0),
            (re.compile(r"\bspread\b", re.I), 2.0),
            (re.compile(r"\bcontract\s*size\b", re.I), 3.0),
            (re.compile(r"\bsymbol\b", re.I), 0.8),
            (re.compile(r"\bswap\b", re.I), 1.5),
            (re.compile(r"\bcfd\b", re.I), 5.0),
        ],
        "data_patterns": [
            (re.compile(r":CFD$", re.I), 4.0),
        ],
    },
    "crypto": {
        "header_keywords": [
            (re.compile(r"\bwallet\b", re.I), 4.0),
            (re.compile(r"\bblockchain\b", re.I), 4.0),
            (re.compile(r"\btoken\b", re.I), 3.0),
            (re.compile(r"\bhash\b", re.I), 3.0),
            # "Symbol" is too generic — crypto detected primarily via data patterns
            (re.compile(r"\bnetwork\b", re.I), 1.5),
            (re.compile(r"\baddress\b", re.I), 2.0),
        ],
        "data_patterns": [
            # Common crypto tickers
            (re.compile(r"^(BTC|ETH|XRP|ADA|SOL|DOT|MATIC|LTC|LINK|UNI|DOGE|SHIB|AVAX|BNB|XLM)$", re.I), 5.0),
        ],
    },
    "savings": {
        "header_keywords": [
            (re.compile(r"\binterest\b", re.I), 4.0),
            (re.compile(r"\bapy\b", re.I), 5.0),
            (re.compile(r"\bmaturity\b", re.I), 4.0),
            (re.compile(r"\bprincipal\b", re.I), 4.0),
            # Low weight: "Description" alone is too generic — old-format Revolut
            # stock CSVs also have a Description column (transaction description).
            (re.compile(r"\bdescription\b", re.I), 0.5),
            (re.compile(r"\byield\b", re.I), 2.0),
            (re.compile(r"\bfund\b", re.I), 1.5),
            (re.compile(r"\bdeposit\b", re.I), 1.5),
            # Revolut savings CSVs have currency-valued columns like "Value, USD"
            (re.compile(r"\bvalue,?\s*(usd|eur|gbp|chf)\b", re.I), 3.0),
            # Revolut savings uses "Quantity of shares" (not plain "Quantity")
            (re.compile(r"\bquantity\s+of\s+shares\b", re.I), 2.5),
        ],
        "data_patterns": [
            # Description values typical for savings (fund names / interest labels)
            (re.compile(r"interest\s*(paid|reinvested)|service\s*fee|money\s*market", re.I), 4.0),
        ],
    },
}

CONFIDENCE_THRESHOLD = 0.70


def detect_asset_class(
    headers: list[str],
    first_row: Optional[list[str]] = None,
) -> dict:
    """Score each asset class against headers and first-row data.

    Returns:
        {
            "detectedClass": str | None,  # None when top score < threshold
            "confidence": float,          # 0.0–1.0
            "scores": {class: {"score": float, "matchedSignals": [str]}}
        }
    """
    stripped_headers = [h.strip() for h in headers]
    first_row_vals = [str(v).strip() for v in (first_row or [])]

    raw_scores: dict[str, float] = {}
    matched_signals: dict[str, list[str]] = {}

    for ac, rules in DETECTION_RULES.items():
        score = 0.0
        signals: list[str] = []

        for pattern, weight in rules["header_keywords"]:
            for h in stripped_headers:
                if pattern.search(h):
                    score += weight
                    signals.append(f"header:{h}")
                    break  # count each pattern once

        if first_row_vals:
            for pattern, weight in rules["data_patterns"]:
                for val in first_row_vals:
                    if val and pattern.search(val):
                        score += weight
                        signals.append(f"data:{val}")
                        break  # count each pattern once

        raw_scores[ac] = score
        matched_signals[ac] = signals

    total = sum(raw_scores.values()) or 1.0
    norm_scores = {ac: s / total for ac, s in raw_scores.items()}

    best_class = max(norm_scores, key=lambda k: norm_scores[k])
    best_conf = norm_scores[best_class]

    return {
        "detectedClass": best_class if best_conf >= CONFIDENCE_THRESHOLD else None,
        "confidence": round(best_conf, 4),
        "scores": {
            ac: {"score": round(norm_scores[ac], 4), "matchedSignals": matched_signals[ac]}
            for ac in DETECTION_RULES
        },
    }
