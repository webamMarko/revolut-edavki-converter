"""CSV import validation with row-level issue detection and correction suggestions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches

import pandas as pd


KNOWN_TICKERS_SAMPLE = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA", "BRK.B",
    "JPM", "JNJ", "V", "PG", "UNH", "HD", "MA", "DIS", "BAC", "XOM", "PFE",
    "KO", "PEP", "CSCO", "ABT", "AVGO", "COST", "TMO", "MRK", "NKE", "ORCL",
    "ACN", "ADBE", "CRM", "NFLX", "AMD", "INTC", "QCOM", "TXN", "HON", "UPS",
    "SHOP", "SQ", "PYPL", "COIN", "PLTR", "SNAP", "UBER", "ABNB", "RBLX",
    "NET", "DDOG", "SNOW", "ZS", "CRWD", "MDB", "RIVN", "LCID", "NIO", "SOFI",
    "VOO", "SPY", "QQQ", "VTI", "IVV", "ARKK", "VXUS", "BND", "VNQ", "SCHD",
]

VALID_STOCK_TYPES = {"BUY", "SELL", "STOCK SPLIT", "DIVIDEND", "CUSTODY FEE"}
VALID_CFD_TYPES = {"BUY", "SELL", "DIVIDEND"}
VALID_CRYPTO_TYPES = {
    "BUY", "SELL", "Payment", "Receive", "Staking reward", "Learn reward",
}
VALID_SAVINGS_TYPES = {
    "BUY", "SELL", "INTEREST PAID", "INTEREST REINVESTED",
    "INTEREST WITHDRAWN", "SERVICE FEE",
}

VALID_TYPES_BY_CLASS = {
    "stock": VALID_STOCK_TYPES,
    "cfd": VALID_CFD_TYPES,
    "crypto": VALID_CRYPTO_TYPES,
    "savings": VALID_SAVINGS_TYPES,
}


@dataclass
class RowIssue:
    row_num: int
    column: str
    severity: str  # "error", "warning", "info"
    message: str
    value: str = ""
    suggestion: str = ""


@dataclass
class ValidationReport:
    total_rows: int = 0
    valid_rows: int = 0
    error_rows: int = 0
    warning_rows: int = 0
    issues: list = field(default_factory=list)
    ticker_suggestions: dict = field(default_factory=dict)
    missing_buys: list = field(default_factory=list)
    date_gaps: list = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "error_rows": self.error_rows,
            "warning_rows": self.warning_rows,
            "issues": [
                {
                    "row": i.row_num,
                    "column": i.column,
                    "severity": i.severity,
                    "message": i.message,
                    "value": i.value,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "ticker_suggestions": self.ticker_suggestions,
            "missing_buys": self.missing_buys,
            "date_gaps": [
                {"ticker": g["ticker"], "from": g["from"], "to": g["to"], "days": g["days"]}
                for g in self.date_gaps
            ],
            "summary": self.summary,
        }


def _parse_amount_safe(value) -> float | None:
    if pd.isna(value) or value == "" or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = re.sub(r"^[A-Z]{3}\s+", "", s)
    s = s.lstrip("€$£¥").strip()
    s = s.replace(",", "")
    s = re.sub(r"\s+[A-Z]{2,4}$", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _is_valid_date(value) -> bool:
    if pd.isna(value) or not value:
        return False
    s = str(value).strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return True
    # Revolut format: "Feb 21, 2020, 9:00:16 AM"
    from datetime import datetime as dt
    s = s.replace(' ', ' ')
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            dt.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def _normalize_date_for_sort(value) -> str | None:
    if pd.isna(value) or not value:
        return None
    s = str(value).strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    from datetime import datetime as dt
    s = s.replace(' ', ' ')
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def validate_csv(
    df: pd.DataFrame,
    column_map: dict,
    asset_class: str,
    existing_tickers: list | None = None,
) -> ValidationReport:
    """Validate a CSV DataFrame against the expected schema for the given asset class.

    column_map: {db_field: csv_header_name} - same format as import wizard
    existing_tickers: list of tickers already in the portfolio (for context checks)
    """
    report = ValidationReport(total_rows=len(df))

    all_known_tickers = set(KNOWN_TICKERS_SAMPLE)
    if existing_tickers:
        all_known_tickers.update(existing_tickers)

    rows_with_errors = set()
    rows_with_warnings = set()

    # Track buys/sells per ticker for missing-buy detection
    ticker_buys = {}
    ticker_sells = {}
    # Track dates per ticker for gap detection
    ticker_dates = {}

    valid_types = VALID_TYPES_BY_CLASS.get(asset_class, VALID_STOCK_TYPES)

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-indexed, +1 for header row

        # --- Date validation ---
        date_header = column_map.get("date")
        if date_header:
            date_val = row.get(date_header)
            if pd.isna(date_val) or not str(date_val).strip():
                report.issues.append(RowIssue(
                    row_num=row_num, column="date", severity="error",
                    message="Missing date value",
                ))
                rows_with_errors.add(row_num)
            elif not _is_valid_date(date_val):
                report.issues.append(RowIssue(
                    row_num=row_num, column="date", severity="error",
                    message="Unrecognized date format",
                    value=str(date_val)[:50],
                ))
                rows_with_errors.add(row_num)
            else:
                norm_date = _normalize_date_for_sort(date_val)
                ticker_header = column_map.get("ticker")
                if ticker_header and norm_date:
                    ticker_val = row.get(ticker_header)
                    if not pd.isna(ticker_val) and str(ticker_val).strip():
                        t = str(ticker_val).strip().upper()
                        ticker_dates.setdefault(t, []).append(norm_date)
        else:
            report.issues.append(RowIssue(
                row_num=row_num, column="date", severity="error",
                message="Date column not mapped",
            ))
            rows_with_errors.add(row_num)
            break  # all rows will have this issue

        # --- Type validation ---
        type_header = column_map.get("type")
        if type_header:
            type_val = row.get(type_header)
            if pd.isna(type_val) or not str(type_val).strip():
                report.issues.append(RowIssue(
                    row_num=row_num, column="type", severity="error",
                    message="Missing transaction type",
                ))
                rows_with_errors.add(row_num)
            else:
                type_str = str(type_val).strip()
                type_upper = type_str.upper()
                if type_upper not in {t.upper() for t in valid_types}:
                    suggestion = ""
                    close = get_close_matches(type_upper, [t.upper() for t in valid_types], n=1, cutoff=0.6)
                    if close:
                        suggestion = f"Did you mean '{close[0]}'?"
                    report.issues.append(RowIssue(
                        row_num=row_num, column="type", severity="warning",
                        message=f"Unknown transaction type for {asset_class}",
                        value=type_str,
                        suggestion=suggestion,
                    ))
                    rows_with_warnings.add(row_num)
                else:
                    # Track buys and sells
                    ticker_header = column_map.get("ticker")
                    if ticker_header:
                        ticker_val = row.get(ticker_header)
                        if not pd.isna(ticker_val) and str(ticker_val).strip():
                            t = str(ticker_val).strip().upper()
                            if type_upper == "BUY":
                                ticker_buys.setdefault(t, []).append(row_num)
                            elif type_upper == "SELL":
                                ticker_sells.setdefault(t, []).append(row_num)

        # --- Ticker validation ---
        ticker_header = column_map.get("ticker")
        if ticker_header:
            ticker_val = row.get(ticker_header)
            if pd.isna(ticker_val) or not str(ticker_val).strip():
                if asset_class in ("cfd", "crypto"):
                    report.issues.append(RowIssue(
                        row_num=row_num, column="ticker", severity="error",
                        message="Missing ticker (required for " + asset_class + ")",
                    ))
                    rows_with_errors.add(row_num)
                elif asset_class == "stock":
                    type_val = row.get(type_header) if type_header else ""
                    type_str = str(type_val).strip().upper() if not pd.isna(type_val) else ""
                    if type_str in ("BUY", "SELL"):
                        report.issues.append(RowIssue(
                            row_num=row_num, column="ticker", severity="warning",
                            message="Missing ticker on BUY/SELL row",
                        ))
                        rows_with_warnings.add(row_num)
            else:
                ticker_str = str(ticker_val).strip()
                if asset_class == "stock" and len(ticker_str) > 0:
                    ticker_upper = ticker_str.upper()
                    if ticker_upper not in all_known_tickers and len(ticker_upper) <= 6:
                        close = get_close_matches(
                            ticker_upper,
                            list(all_known_tickers),
                            n=1, cutoff=0.75,
                        )
                        if close:
                            report.ticker_suggestions[ticker_str] = close[0]
                            report.issues.append(RowIssue(
                                row_num=row_num, column="ticker", severity="info",
                                message=f"Unknown ticker '{ticker_str}'",
                                value=ticker_str,
                                suggestion=f"Did you mean '{close[0]}'?",
                            ))

        # --- Numeric field validation ---
        for num_field in ("quantity", "price_per_share", "total_amount"):
            num_header = column_map.get(num_field)
            if not num_header:
                continue
            num_val = row.get(num_header)
            if pd.isna(num_val) or str(num_val).strip() == "":
                # Missing numeric fields are warnings for BUY/SELL
                type_val = row.get(type_header) if type_header else ""
                type_str = str(type_val).strip().upper() if not pd.isna(type_val) else ""
                if type_str in ("BUY", "SELL") and num_field == "quantity":
                    report.issues.append(RowIssue(
                        row_num=row_num, column=num_field, severity="warning",
                        message=f"Missing {num_field.replace('_', ' ')} on {type_str} row",
                    ))
                    rows_with_warnings.add(row_num)
            else:
                parsed = _parse_amount_safe(num_val)
                if parsed is None:
                    report.issues.append(RowIssue(
                        row_num=row_num, column=num_field, severity="error",
                        message=f"Cannot parse {num_field.replace('_', ' ')} as number",
                        value=str(num_val)[:30],
                    ))
                    rows_with_errors.add(row_num)
                elif parsed < 0 and num_field == "quantity":
                    type_val = row.get(type_header) if type_header else ""
                    type_str = str(type_val).strip().upper() if not pd.isna(type_val) else ""
                    if type_str == "BUY":
                        report.issues.append(RowIssue(
                            row_num=row_num, column=num_field, severity="warning",
                            message="Negative quantity on BUY row",
                            value=str(num_val),
                        ))
                        rows_with_warnings.add(row_num)

        # --- FX rate validation ---
        fx_header = column_map.get("fx_rate")
        if fx_header:
            fx_val = row.get(fx_header)
            if not pd.isna(fx_val) and str(fx_val).strip():
                parsed = _parse_amount_safe(fx_val)
                if parsed is not None and (parsed <= 0 or parsed > 1000):
                    report.issues.append(RowIssue(
                        row_num=row_num, column="fx_rate", severity="warning",
                        message="FX rate looks unusual",
                        value=str(fx_val),
                    ))
                    rows_with_warnings.add(row_num)

    # --- Cross-row checks: sells without buys ---
    for ticker, sell_rows in ticker_sells.items():
        if ticker not in ticker_buys:
            report.missing_buys.append({
                "ticker": ticker,
                "sell_rows": sell_rows[:5],
                "message": f"SELL for '{ticker}' with no matching BUY in this file — possible missing earlier CSV",
            })

    # --- Cross-row checks: date gaps > 365 days per ticker ---
    for ticker, dates in ticker_dates.items():
        sorted_dates = sorted(dates)
        if len(sorted_dates) >= 2:
            from datetime import datetime as dt
            for i in range(1, len(sorted_dates)):
                try:
                    d1 = dt.strptime(sorted_dates[i - 1], "%Y-%m-%d")
                    d2 = dt.strptime(sorted_dates[i], "%Y-%m-%d")
                    gap_days = (d2 - d1).days
                    if gap_days > 365:
                        report.date_gaps.append({
                            "ticker": ticker,
                            "from": sorted_dates[i - 1],
                            "to": sorted_dates[i],
                            "days": gap_days,
                        })
                except ValueError:
                    pass

    # Compute summary
    report.error_rows = len(rows_with_errors)
    report.warning_rows = len(rows_with_warnings - rows_with_errors)
    report.valid_rows = report.total_rows - report.error_rows

    # Build summary text
    parts = []
    if report.error_rows == 0 and report.warning_rows == 0:
        parts.append(f"All {report.total_rows} rows passed validation.")
    else:
        if report.error_rows > 0:
            parts.append(f"{report.error_rows} rows with errors (will be skipped).")
        if report.warning_rows > 0:
            parts.append(f"{report.warning_rows} rows with warnings.")
        parts.append(f"{report.valid_rows} rows will import successfully.")
    if report.missing_buys:
        parts.append(f"{len(report.missing_buys)} ticker(s) have sells without matching buys.")
    if report.date_gaps:
        parts.append(f"{len(report.date_gaps)} date gap(s) > 1 year detected.")
    report.summary = " ".join(parts)

    return report
