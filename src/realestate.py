"""Real estate asset management with ETN (Slovenian market registry) valuation.

Properties are stored in real_estate_properties table.
Each property gets a synthetic BUY transaction in the transactions table (asset_class='realestate').
Estimated values are stored in daily_prices (currency='EUR') and forward-filled like stock prices.

ETN data source: JGP service API at ipi.eprostor.gov.si/jgp-service-api
  - Group 131, displayCompositeProductId 323: per-municipality sales by year
  - Group 127, displayCompositeProductId 321: all-Slovenia sales by year (fallback)
"""

import io
import sqlite3
import zipfile
from datetime import datetime

import pandas as pd
import requests

JGP_API = "https://ipi.eprostor.gov.si/jgp-service-api"

# displayCompositeProductId for per-municipality ETN download (group 131)
ETN_MUNI_DCPID = 323
ETN_MUNI_GROUP = 131

# Human-readable property type labels
PROPERTY_TYPE_LABELS = {
    "stanovanje": "Apartment (stanovanje)",
    "hisa":       "House (hiša)",
    "garaza":     "Garage (garaža)",
    "poslovni":   "Commercial space (poslovni prostor)",
    "zemljisce":  "Building land (stavbno zemljišče)",
}

# VRSTA_DELA_STAVBE codes for building-part types
_BUILDING_TYPE_CODES = {
    "stanovanje": [2],           # Stanovanje
    "hisa":       [1],           # Stanovanjska hiša
    "garaza":     [4, 3],        # Garaža, parkirni prostor
    "poslovni":   [5, 6, 7, 8],  # pisarniški, poslovni, zdravstveni, trgovski
}

# VRSTA_ZEMLJISCA codes for land types
_LAND_TYPE_CODES = {
    "zemljisce": [1, 2, 3, 5],  # building plots + appurtenant land
}


# ---------------------------------------------------------------------------
# Municipality lookup
# ---------------------------------------------------------------------------

_muni_cache: dict | None = None


def _get_municipalities() -> list[dict]:
    global _muni_cache
    if _muni_cache is None:
        r = requests.get(JGP_API + "/municipalities", timeout=15,
                         headers={"Accept": "application/json"})
        r.raise_for_status()
        _muni_cache = r.json()
    return _muni_cache


def _resolve_municipality_sifra(name: str) -> str | None:
    """Return the municipality sifra for a given name (case-insensitive partial match)."""
    munis = _get_municipalities()
    name_lower = name.lower()
    # Exact match first
    for m in munis:
        if m["name"].lower() == name_lower:
            return m["sifra"]
    # Partial match
    for m in munis:
        if name_lower in m["name"].lower() or m["name"].lower() in name_lower:
            return m["sifra"]
    return None


# ---------------------------------------------------------------------------
# ETN data downloading via JGP API
# ---------------------------------------------------------------------------

def _download_etn_zip(muni_sifra: str, year: int) -> bytes | None:
    """Download ETN ZIP for a municipality and year. Returns raw bytes or None."""
    try:
        # Step 1: get signed download URL
        r = requests.get(
            f"{JGP_API}/display-views/groups/{ETN_MUNI_GROUP}/composite-products/{ETN_MUNI_DCPID}/file",
            params={"filterParam": "OBCINE", "filterValue": muni_sifra, "filterYear": str(year)},
            timeout=15, headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return None
        signed_url = r.json().get("url")
        if not signed_url:
            return None

        # Step 2: download the ZIP
        r2 = requests.get(signed_url, timeout=120)
        if r2.status_code != 200:
            return None
        return r2.content
    except Exception:
        return None


def _parse_etn_zip(zip_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse ETN ZIP and return (posli, delistavb, zemljisca) DataFrames."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    posli = pd.DataFrame()
    delistavb = pd.DataFrame()
    zemljisca = pd.DataFrame()

    for fname in z.namelist():
        if "sifranti" in fname.lower() or not fname.endswith(".csv"):
            continue
        with z.open(fname) as f:
            content = f.read().decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(content), sep=",", low_memory=False)
        upper = fname.upper()
        if "POSLI" in upper:
            posli = df
        elif "DELISTAVB" in upper:
            delistavb = df
        elif "ZEMLJISCA" in upper:
            zemljisca = df

    return posli, delistavb, zemljisca


def _extract_price_per_m2(posli: pd.DataFrame, detail_df: pd.DataFrame,
                           is_land: bool, type_codes: list,
                           area_m2: float) -> pd.DataFrame | None:
    """Join posli with building/land detail and return price_per_m2 DataFrame."""
    if posli.empty or detail_df.empty:
        return None

    valid_posla_ids = set(posli["ID_POSLA"])
    df = detail_df[detail_df["ID_POSLA"].isin(valid_posla_ids)].copy()

    if is_land:
        df = df[df["VRSTA_ZEMLJISCA"].isin(type_codes)]
        df = df.rename(columns={"POVRSINA_PARCELE": "_area", "POGODBENA_CENA_PARCELE": "_price"})
    else:
        df = df[df["VRSTA_DELA_STAVBE"].isin(type_codes)]
        df = df.rename(columns={"PRODANA_POVRSINA": "_area", "POGODBENA_CENA_DELA_STAVBE": "_price"})

    if df.empty:
        return None

    # Fall back to POSLI total price for single-unit transactions
    posli_price = posli.set_index("ID_POSLA")["POGODBENA_CENA_ODSKODNINA"]
    tx_counts = df.groupby("ID_POSLA")["ID_POSLA"].transform("count")
    df["_price"] = df.apply(
        lambda row: row["_price"] if pd.notna(row["_price"]) and row["_price"] > 0
        else (posli_price.get(row["ID_POSLA"], float("nan")) if tx_counts[row.name] == 1 else float("nan")),
        axis=1,
    )

    df = df.dropna(subset=["_area", "_price"])
    df = df[(df["_area"] > 0) & (df["_price"] > 1000)]
    df["price_per_m2"] = df["_price"] / df["_area"]

    # Filter comparable size (±40%); relax if too few
    comparable = df[(df["_area"] >= area_m2 * 0.6) & (df["_area"] <= area_m2 * 1.4)]
    if len(comparable) < 3:
        comparable = df

    return comparable if not comparable.empty else None


def fetch_comparable_sales(municipality: str, property_type: str, area_m2: float,
                            months_back: int = 30) -> pd.DataFrame | None:
    """Fetch comparable ETN sales over the last N months. Returns DataFrame with price_per_m2 or None."""
    muni_sifra = _resolve_municipality_sifra(municipality)
    if not muni_sifra:
        return None

    is_land = property_type == "zemljisce"
    type_codes = (_LAND_TYPE_CODES if is_land else _BUILDING_TYPE_CODES).get(property_type, [])
    if not type_codes:
        return None

    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months_back)
    years_needed = sorted({pd.Timestamp.now().year, pd.Timestamp.now().year - 1,
                            pd.Timestamp.now().year - 2}, reverse=True)

    all_frames = []
    for year in years_needed:
        zip_bytes = _download_etn_zip(muni_sifra, year)
        if not zip_bytes:
            continue
        posli, delistavb, zemljisca = _parse_etn_zip(zip_bytes)
        if posli.empty:
            continue
        posli = posli.copy()
        posli["_date"] = pd.to_datetime(posli["DATUM_SKLENITVE_POGODBE"], dayfirst=True, errors="coerce")
        posli = posli.dropna(subset=["_date"])
        posli = posli[posli["_date"] >= cutoff]
        if posli.empty:
            continue
        frame = _extract_price_per_m2(posli, zemljisca if is_land else delistavb,
                                       is_land, type_codes, area_m2)
        if frame is not None:
            all_frames.append(frame)

    if not all_frames:
        return None
    return pd.concat(all_frames, ignore_index=True)


def fetch_comparable_sales_for_year(municipality: str, property_type: str, area_m2: float,
                                     year: int) -> pd.DataFrame | None:
    """Fetch comparable ETN sales for a specific calendar year. Returns DataFrame with price_per_m2 or None."""
    muni_sifra = _resolve_municipality_sifra(municipality)
    if not muni_sifra:
        return None

    is_land = property_type == "zemljisce"
    type_codes = (_LAND_TYPE_CODES if is_land else _BUILDING_TYPE_CODES).get(property_type, [])
    if not type_codes:
        return None

    zip_bytes = _download_etn_zip(muni_sifra, year)
    if not zip_bytes:
        return None
    posli, delistavb, zemljisca = _parse_etn_zip(zip_bytes)
    if posli.empty:
        return None

    posli = posli.copy()
    posli["_date"] = pd.to_datetime(posli["DATUM_SKLENITVE_POGODBE"], dayfirst=True, errors="coerce")
    posli = posli.dropna(subset=["_date"])
    # Keep only transactions within the target year
    posli = posli[(posli["_date"].dt.year == year)]
    if posli.empty:
        return None

    return _extract_price_per_m2(posli, zemljisca if is_land else delistavb,
                                  is_land, type_codes, area_m2)


def estimate_property_value(municipality: str, property_type: str, area_m2: float,
                             verbose: bool = False) -> float | None:
    """Estimate current market value via median ETN comparable price per m²."""
    sales = fetch_comparable_sales(municipality, property_type, area_m2)
    if sales is None or sales.empty:
        return None

    median_ppm2 = sales["price_per_m2"].median()
    value = round(median_ppm2 * area_m2, 0)

    if verbose:
        print(f"    {len(sales)} comparables, median {median_ppm2:,.0f} EUR/m² → {value:,.0f} EUR")

    return value


def estimate_property_value_for_year(municipality: str, property_type: str, area_m2: float,
                                      year: int, verbose: bool = False) -> float | None:
    """Estimate property value using ETN sales data from a specific year."""
    sales = fetch_comparable_sales_for_year(municipality, property_type, area_m2, year)
    if sales is None or sales.empty:
        return None

    median_ppm2 = sales["price_per_m2"].median()
    value = round(median_ppm2 * area_m2, 0)

    if verbose:
        print(f"    {year}: {len(sales)} comparables, median {median_ppm2:,.0f} EUR/m² → {value:,.0f} EUR")

    return value


# ---------------------------------------------------------------------------
# Property management
# ---------------------------------------------------------------------------

def _next_ticker(conn: sqlite3.Connection) -> str:
    """Generate next RE### ticker."""
    row = conn.execute(
        "SELECT ticker FROM real_estate_properties ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        try:
            n = int(row[0].replace("RE", "")) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"RE{n:03d}"


def add_property(conn: sqlite3.Connection, name: str, address: str, municipality: str,
                 cadastral_municipality: str, property_type: str, area_m2: float,
                 purchase_price_eur: float, purchase_date: str, notes: str = "") -> str:
    """Add a property and its synthetic BUY transaction. Returns assigned ticker."""
    ticker = _next_ticker(conn)

    conn.execute("""
        INSERT INTO real_estate_properties
            (ticker, name, address, municipality, cadastral_municipality,
             property_type, area_m2, purchase_price_eur, purchase_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticker, name, address, municipality, cadastral_municipality,
          property_type, area_m2, purchase_price_eur, purchase_date, notes))

    conn.execute("""
        INSERT OR IGNORE INTO transactions
            (date, ticker, type, quantity, price_per_share, total_amount,
             currency, fx_rate, asset_class, source_file)
        VALUES (?, ?, 'BUY', 1.0, ?, ?, 'EUR', 1.0, 'realestate', 'manual-realestate')
    """, (purchase_date + " 00:00:00", ticker, purchase_price_eur, purchase_price_eur))

    conn.commit()
    return ticker


def list_properties(conn: sqlite3.Connection) -> list[dict]:
    """Return all properties with their latest estimated value."""
    rows = conn.execute("""
        SELECT p.*,
               dp.close  AS estimated_value_eur,
               dp.date   AS estimated_date
        FROM real_estate_properties p
        LEFT JOIN (
            SELECT ticker, close, date,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM daily_prices WHERE currency = 'EUR'
        ) dp ON dp.ticker = p.ticker AND dp.rn = 1
        ORDER BY p.purchase_date
    """).fetchall()
    return [dict(r) for r in rows]


def set_manual_valuation(conn: sqlite3.Connection, ticker: str, value_eur: float,
                          date: str | None = None):
    """Manually override a property's estimated value."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT OR REPLACE INTO daily_prices (ticker, date, close, currency) VALUES (?, ?, ?, 'EUR')",
        (ticker, date, value_eur),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# ETN price sync (called from price_fetcher.sync_all)
# ---------------------------------------------------------------------------

def sync_etn_valuations(conn: sqlite3.Connection, verbose: bool = False):
    """Estimate market value for all properties: backfill year-by-year + update today."""
    properties = conn.execute("SELECT * FROM real_estate_properties").fetchall()
    if not properties:
        print("Real estate: no properties in database.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    current_year = datetime.now().year
    updated, failed = 0, []

    for row in properties:
        prop = dict(row)
        ticker, name = prop["ticker"], prop["name"]
        purchase_year = int(prop["purchase_date"][:4])

        # Find which years already have a price stored
        existing_dates = {r[0] for r in conn.execute(
            "SELECT date FROM daily_prices WHERE ticker = ? AND currency = 'EUR'", (ticker,)
        ).fetchall()}
        existing_years = {d[:4] for d in existing_dates}

        if verbose:
            print(f"  {name} ({ticker}): purchase {purchase_year}, existing years: {sorted(existing_years)}")

        prop_updated = False

        # Backfill: one price point per historical year (stored at Dec 31 of that year)
        for year in range(purchase_year, current_year):
            year_str = str(year)
            if year_str in existing_years:
                if verbose:
                    print(f"    {year}: already have price, skipping")
                continue

            if verbose:
                print(f"    {year}: fetching ETN data...")

            value = estimate_property_value_for_year(
                prop["municipality"], prop["property_type"], prop["area_m2"],
                year=year, verbose=verbose,
            )
            if value is not None:
                price_date = f"{year}-12-31"
                conn.execute(
                    "INSERT OR REPLACE INTO daily_prices (ticker, date, close, currency) VALUES (?, ?, ?, 'EUR')",
                    (ticker, price_date, value),
                )
                prop_updated = True
                if not verbose:
                    print(f"  {name} {year}: {value:,.0f} EUR")
            else:
                if verbose:
                    print(f"    {year}: no comparables found")

        # Always update today's estimate (current-year data)
        if verbose:
            print(f"    {current_year} (today): fetching ETN data...")
        value = estimate_property_value(
            prop["municipality"], prop["property_type"], prop["area_m2"], verbose=verbose
        )
        if value is not None:
            conn.execute(
                "INSERT OR REPLACE INTO daily_prices (ticker, date, close, currency) VALUES (?, ?, ?, 'EUR')",
                (ticker, today, value),
            )
            prop_updated = True
            if not verbose:
                print(f"  {name} today: {value:,.0f} EUR")
        else:
            failed.append(name)
            if verbose:
                print(f"    today: no comparables found")
            else:
                print(f"  {name}: no comparables found")

        if prop_updated:
            updated += 1

    conn.commit()
    print(f"Real estate: {updated} properties updated, {len(failed)} failed")
    if failed:
        print(f"  No current data: {', '.join(failed)}")
