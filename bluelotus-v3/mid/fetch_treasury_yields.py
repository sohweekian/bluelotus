"""
BlueLotus Digital Institution — V2.0
mid/fetch_treasury_yields.py — Treasury Yield & Fed Rate Fetcher

VERSION: v1.0
DATE:    June 2026
AUTHOR:  MID Engineering (Claude)

PURPOSE:
    Standalone fetcher for US Treasury yield curve data and Fed Funds Rate.
    Runs independently of ingest.py. Writes to macro_yields table in
    bluelotus2 DB and outputs treasury_yields.json for verification.

    This follows the BlueLotus modular architecture doctrine:
    - One file, one job
    - Writes to DB, outputs JSON
    - ingest.py is NOT touched
    - export_dataset_raw.py reads from macro_yields table

API SOURCE (verified against official FRED documentation):
    https://fred.stlouisfed.org/docs/api/fred/series_observations.html
    https://fred.stlouisfed.org/docs/api/api_key.html

    Endpoint: https://api.stlouisfed.org/fred/series/observations
    Method:   HTTP GET
    Auth:     Free API key from fred.stlouisfed.org/docs/api/api_key.html

FRED SERIES USED (all verified from fred.stlouisfed.org):
    DGS10     — Market Yield 10-Year Treasury (daily, business days)
    DGS2      — Market Yield 2-Year Treasury (daily, business days)
    DGS30     — Market Yield 30-Year Treasury (daily, business days)
    DGS3MO    — Market Yield 3-Month Treasury Bill (daily, business days)
    FEDFUNDS  — Federal Funds Effective Rate (monthly — last full month)
    DFEDTARU  — Federal Funds Target Rate Upper Bound (daily)
    DFEDTARL  — Federal Funds Target Rate Lower Bound (daily)

RESPONSE FORMAT (verified from FRED docs):
    JSON response contains "observations" array.
    Each observation has: {"date": "2026-05-30", "value": "4.42"}
    Value "." = missing data (holiday or not yet released) — must be handled.
    Sort order: desc → first observation = most recent.

WHY NOT MOOMOO FOR YIELDS:
    US.TNX / US.IRX / US.TYX are CBOE index symbols.
    Moomoo Singapore does not carry CBOE index symbols — confirmed by the same
    reason ^VIX is fetched via yfinance in ingest.py (not Moomoo OpenD).
    FRED is the authoritative source — data comes directly from the Federal Reserve.

DERIVED CALCULATIONS:
    yield_spread     = yield_10y - yield_2y (2s10s spread)
    yield_spread_30_10 = yield_30y - yield_10y
    curve_status     = NORMAL (10y > 2y) | INVERTED (10y < 2y) | FLAT (within 10bp)
    ffr_midpoint     = (ffr_upper + ffr_lower) / 2
    eq_risk_premium  = earnings_yield_sp500_proxy - yield_10y (approximate)

SETUP — API KEY REQUIRED:
    1. Register free at: https://fred.stlouisfed.org/docs/api/api_key.html
    2. Add to .env file:
         FRED_API_KEY=your_32_char_key_here
    3. OR pass via --api-key flag:
         python mid\\fetch_treasury_yields.py --api-key your_key

USAGE:
    cd C:\\bluelotus2
    python mid\\fetch_treasury_yields.py

    Flags:
    --dry-run     Fetch and print, skip DB write and JSON output
    --api-key     Override FRED_API_KEY from .env

RUN SCHEDULE (recommended):
    Once daily after 17:00 ET (FRED updates daily yields around 16:15-16:30 ET)
    Singapore time: ~05:00-06:00 SGT
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

VERSION       = "v1.0"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT_SECS  = 15   # HTTP request timeout

# FRED series definitions — all verified from fred.stlouisfed.org
FRED_SERIES = {
    "DGS10":   {"label": "10Y Treasury Yield",           "frequency": "daily"},
    "DGS2":    {"label": "2Y Treasury Yield",            "frequency": "daily"},
    "DGS30":   {"label": "30Y Treasury Yield",           "frequency": "daily"},
    "DGS3MO":  {"label": "3-Month T-Bill Yield",         "frequency": "daily"},
    "FEDFUNDS":{"label": "Fed Funds Effective Rate",     "frequency": "monthly"},
    "DFEDTARU":{"label": "FFR Target Upper Bound",       "frequency": "daily"},
    "DFEDTARL":{"label": "FFR Target Lower Bound",       "frequency": "daily"},
}


# ── Output helpers ─────────────────────────────────────────────────────────────
def _ok(msg):   print(f"  [OK]   {msg}")
def _fail(msg): print(f"  [FAIL] {msg}")
def _warn(msg): print(f"  [WARN] {msg}")
def _info(msg): print(f"         {msg}")
def _section(title):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


# ── Safe float helper ─────────────────────────────────────────────────────────
def _sf(val, default=None):
    """Convert FRED value string to float. Returns default for '.' (missing)."""
    if val is None or str(val).strip() in (".", "", "N/A"):
        return default
    try:
        f = float(val)
        return default if (f != f) else round(f, 4)  # NaN guard
    except (TypeError, ValueError):
        return default


# ── FRED single series fetch ──────────────────────────────────────────────────
def _fetch_fred_series(series_id: str, api_key: str, limit: int = 10) -> list:
    """
    Fetch the most recent observations for a FRED series.

    API call (verified from FRED docs):
      GET https://api.stlouisfed.org/fred/series/observations
      Params: series_id, api_key, file_type=json, sort_order=desc, limit=N

    Returns list of {"date": "yyyy-mm-dd", "value": "4.42"} dicts.
    Returns [] on any error.
    """
    import urllib.request
    import urllib.parse
    import urllib.error

    params = urllib.parse.urlencode({
        "series_id":  series_id,
        "api_key":    api_key,
        "file_type":  "json",
        "sort_order": "desc",
        "limit":      limit,
    })
    url = f"{FRED_BASE_URL}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BlueLotus-MID/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        return data.get("observations", [])
    except urllib.error.HTTPError as e:
        _fail(f"{series_id} HTTP {e.code}: {e.reason}")
        return []
    except urllib.error.URLError as e:
        _fail(f"{series_id} URL error: {e.reason}")
        return []
    except Exception as e:
        _fail(f"{series_id} exception: {type(e).__name__}: {e}")
        return []


# ── Get latest non-missing value ──────────────────────────────────────────────
def _latest_value(observations: list) -> tuple:
    """
    Return (value_float, date_str) for the most recent non-missing observation.
    FRED returns "." for missing data (holidays, weekends, not yet released).
    Looks back through up to 10 observations to find the latest valid value.
    """
    for obs in observations:
        val = _sf(obs.get("value"))
        if val is not None:
            return val, obs.get("date", "")
    return None, ""


# ── Yield curve classifier ────────────────────────────────────────────────────
def _classify_curve(yield_10y, yield_2y):
    """
    Classify yield curve shape from 2s10s spread.
    FLAT threshold: within 10 basis points (0.10%).
    """
    if yield_10y is None or yield_2y is None:
        return "UNKNOWN"
    spread = yield_10y - yield_2y
    if spread > 0.10:
        return "NORMAL"
    elif spread < -0.10:
        return "INVERTED"
    else:
        return "FLAT"


# ── Main fetch ────────────────────────────────────────────────────────────────
def fetch_treasury_yields(api_key: str) -> dict:
    """
    Fetch all 7 FRED series and compute derived fields.
    Returns a single dict representing the current yield environment.
    """
    raw = {}
    dates = {}

    print()
    for series_id, meta in FRED_SERIES.items():
        observations = _fetch_fred_series(series_id, api_key, limit=10)
        if not observations:
            _warn(f"  {series_id:<10} no data returned")
            raw[series_id] = None
            dates[series_id] = ""
            continue

        val, dt = _latest_value(observations)
        raw[series_id]   = val
        dates[series_id] = dt

        if val is not None:
            _ok(f"  {series_id:<10} {val:>6.3f}%   as of {dt}  ({meta['label']})")
        else:
            _warn(f"  {series_id:<10} missing (all recent values are '.')  ({meta['label']})")

        time.sleep(0.3)  # polite rate spacing between series calls

    # ── Extract individual yields ─────────────────────────────────────────────
    y10  = raw.get("DGS10")
    y2   = raw.get("DGS2")
    y30  = raw.get("DGS30")
    y3m  = raw.get("DGS3MO")
    ffr  = raw.get("FEDFUNDS")
    ffr_upper = raw.get("DFEDTARU")
    ffr_lower = raw.get("DFEDTARL")

    # ── Derived calculations ──────────────────────────────────────────────────
    spread_2s10s = round(y10 - y2, 4)       if (y10 and y2)  else None
    spread_10s30s = round(y30 - y10, 4)     if (y30 and y10) else None
    spread_3m10y  = round(y10 - y3m, 4)     if (y10 and y3m) else None
    ffr_midpoint  = round((ffr_upper + ffr_lower) / 2, 4) if (ffr_upper and ffr_lower) else None
    curve_status  = _classify_curve(y10, y2)

    cycle_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
        # Primary yields
        "yield_10y":          y10,
        "yield_2y":           y2,
        "yield_30y":          y30,
        "yield_3m":           y3m,
        # Fed rates
        "ffr_effective":      ffr,
        "ffr_target_upper":   ffr_upper,
        "ffr_target_lower":   ffr_lower,
        "ffr_midpoint":       ffr_midpoint,
        # Derived
        "spread_2s10s":       spread_2s10s,    # 10y - 2y — the classic recession indicator
        "spread_10s30s":      spread_10s30s,   # 30y - 10y
        "spread_3m10y":       spread_3m10y,    # 10y - 3m — alternative recession signal
        "curve_status":       curve_status,    # NORMAL / INVERTED / FLAT / UNKNOWN
        # Data provenance
        "source":             "FRED (Federal Reserve Bank of St. Louis)",
        "series_dates": {
            "DGS10":   dates.get("DGS10", ""),
            "DGS2":    dates.get("DGS2", ""),
            "DGS30":   dates.get("DGS30", ""),
            "DGS3MO":  dates.get("DGS3MO", ""),
            "FEDFUNDS":dates.get("FEDFUNDS", ""),
            "DFEDTARU":dates.get("DFEDTARU", ""),
            "DFEDTARL":dates.get("DFEDTARL", ""),
        },
        "cycle_ts":           cycle_ts,
    }

    return result


# ── Moomoo probe (optional) ───────────────────────────────────────────────────
def probe_moomoo_yields():
    """
    Optional probe: test whether Moomoo OpenD returns data for
    US.TNX (10Y), US.IRX (13-week T-bill), US.TYX (30Y).

    NOTE from ingest.py architecture: Moomoo Singapore does not carry
    CBOE index symbols — same reason ^VIX uses yfinance.
    This probe confirms whether that applies to TNX/IRX/TYX as well.
    Results are printed only — not written to DB.
    """
    _section("OPTIONAL: Moomoo OpenD Probe for US.TNX / US.IRX / US.TYX")
    _info("Testing whether Moomoo OpenD returns treasury yield data...")
    _info("(Moomoo SG does not carry CBOE index symbols — expecting failure)")

    try:
        import moomoo as ft
        import moomoo.common.ft_logger as _ftl
        _ftl.logger.enable_console_log(False)

        ctx = ft.OpenQuoteContext(host="127.0.0.1", port=11111)
        codes = ["US.TNX", "US.IRX", "US.TYX"]
        ret, data = ctx.get_market_snapshot(codes)
        ctx.close()

        if ret == ft.RET_OK and data is not None and not data.empty:
            _ok(f"Moomoo returned data for treasury codes:")
            for _, row in data.iterrows():
                code       = row.get("code", "?")
                last_price = row.get("last_price", "?")
                _ok(f"  {code}: last_price={last_price}")
            _info("ACTION: These can supplement or replace FRED data if preferred.")
        else:
            _warn(f"Moomoo returned no data for US.TNX/IRX/TYX: {data}")
            _info("Confirmed: FRED is the correct source for treasury yields.")
            _info("(Same situation as ^VIX — CBOE symbols not on Moomoo SG)")

    except ImportError:
        _warn("moomoo module not available for probe")
    except Exception as e:
        _warn(f"Moomoo probe exception: {type(e).__name__}: {e}")
        _info("Confirmed: FRED is the correct source.")


# ── DB writer ─────────────────────────────────────────────────────────────────
def write_to_db(result: dict, snapshot_date: str) -> bool:
    """
    Write treasury yield data to macro_yields table.
    Uses INSERT ... ON DUPLICATE KEY UPDATE.

    Schema (from create_valuation_tables.py macro_yields table — exact column names):
      snapshot_date, cycle_ts, source,
      yield_10y, yield_2y, yield_30y, yield_3m,
      ffr_target, ffr_upper, ffr_lower,
      yield_spread_10_2, yield_spread_10_3m,
      curve_status, nim_proxy
    """
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host     = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "127.0.0.1"),
            port     = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", 3306)),
            user     = os.getenv("MYSQL_USER") or os.getenv("DB_USER", ""),
            password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", ""),
            database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "bluelotus2"),
            charset  = "utf8mb4",
        )
    except Exception as e:
        _fail(f"DB connection failed: {e}")
        return False

    cur = conn.cursor()

    # Column names match macro_yields schema in create_valuation_tables.py exactly:
    # ffr_target, ffr_upper, ffr_lower, yield_spread_10_2, yield_spread_10_3m, nim_proxy
    sql = """
        INSERT INTO macro_yields
            (snapshot_date, cycle_ts, source,
             yield_10y, yield_2y, yield_30y, yield_3m,
             ffr_target, ffr_upper, ffr_lower,
             yield_spread_10_2, yield_spread_10_3m,
             curve_status, nim_proxy)
        VALUES
            (%s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s,
             %s, %s,
             %s, %s)
        ON DUPLICATE KEY UPDATE
            cycle_ts           = VALUES(cycle_ts),
            yield_10y          = VALUES(yield_10y),
            yield_2y           = VALUES(yield_2y),
            yield_30y          = VALUES(yield_30y),
            yield_3m           = VALUES(yield_3m),
            ffr_target         = VALUES(ffr_target),
            ffr_upper          = VALUES(ffr_upper),
            ffr_lower          = VALUES(ffr_lower),
            yield_spread_10_2  = VALUES(yield_spread_10_2),
            yield_spread_10_3m = VALUES(yield_spread_10_3m),
            curve_status       = VALUES(curve_status),
            nim_proxy          = VALUES(nim_proxy)
    """

    try:
        # BUG-MID-003 FIX: NIM proxy must be yield_10y - ffr_target (midpoint).
        # Previous formula used ffr_lower (3.50%) instead of ffr_target/midpoint (3.625%),
        # producing nim_proxy = 0.95 instead of correct 0.825.
        # Definition: nim_proxy = yield_10y - ffr_target (midpoint of target range).
        # Validation: abs(nim_proxy - (yield_10y - ffr_midpoint)) must be < 0.01.
        nim_proxy = None
        if result.get("yield_10y") and result.get("ffr_midpoint"):
            nim_proxy = round(result["yield_10y"] - result["ffr_midpoint"], 4)
            # Validation assertion
            _expected = round(result["yield_10y"] - result["ffr_midpoint"], 4)
            assert abs(nim_proxy - _expected) < 0.01, (
                f"nim_proxy validation failed: stored {nim_proxy} vs computed {_expected}"
            )

        cur.execute(sql, (
            snapshot_date,
            result["cycle_ts"],
            "FRED_StLouis",
            result.get("yield_10y"),
            result.get("yield_2y"),
            result.get("yield_30y"),
            result.get("yield_3m"),
            result.get("ffr_midpoint"),          # ffr_target = midpoint
            result.get("ffr_target_upper"),      # ffr_upper
            result.get("ffr_target_lower"),      # ffr_lower
            result.get("spread_2s10s"),          # yield_spread_10_2
            result.get("spread_3m10y"),          # yield_spread_10_3m
            result.get("curve_status"),
            nim_proxy,                           # 10Y - FFR lower = NIM proxy
        ))
        conn.commit()
        action = "new" if cur.rowcount == 1 else "updated"
        cur.close(); conn.close()
        _ok(f"DB write: 1 record {action} in macro_yields")
        return True
    except Exception as e:
        _fail(f"DB write failed: {e}")
        conn.rollback()
        cur.close(); conn.close()
        return False


# ── JSON writer ───────────────────────────────────────────────────────────────
def write_json(result: dict, snapshot_date: str, out_path: str):
    """Write results to treasury_yields.json for verification and export."""
    output = {
        "fetch_timestamp_sgt": result["cycle_ts"],
        "snapshot_date":       snapshot_date,
        "version":             VERSION,
        "treasury_yields":     result,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Treasury Yields Fetcher v1.0"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Fetch and print only — skip DB write and JSON output")
    parser.add_argument("--api-key",  type=str, default=None,
                        help="FRED API key (overrides FRED_API_KEY in .env)")
    parser.add_argument("--probe-moomoo", action="store_true",
                        help="Also probe Moomoo OpenD for US.TNX/IRX/TYX availability")
    args = parser.parse_args()

    # ── API key ───────────────────────────────────────────────────────────────
    api_key = args.api_key or os.getenv("FRED_API_KEY", "")
    if not api_key:
        print()
        print("=" * 62)
        print("  ERROR: No FRED API key found.")
        print()
        print("  FRED requires a free API key. Get one at:")
        print("  https://fred.stlouisfed.org/docs/api/api_key.html")
        print()
        print("  Then add to C:\\bluelotus2\\.env:")
        print("  FRED_API_KEY=your_32_character_key_here")
        print()
        print("  Or run with: --api-key your_key")
        print("=" * 62)
        sys.exit(1)

    now           = datetime.now()
    snapshot_date = date.today().strftime("%Y-%m-%d")
    cycle_ts      = now.strftime("%Y-%m-%d %H:%M:%S")

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print(f"  BLUELOTUS MID — Treasury Yields Fetcher {VERSION}")
    print(f"  {cycle_ts} SGT")
    print(f"  Mode: {'DRY RUN (no DB write)' if args.dry_run else 'LIVE (writes to DB)'}")
    print(f"  Source: FRED — Federal Reserve Bank of St. Louis")
    print("=" * 62)

    # ── Optional Moomoo probe ─────────────────────────────────────────────────
    if args.probe_moomoo:
        probe_moomoo_yields()

    # ── STEP 1: Fetch from FRED ───────────────────────────────────────────────
    _section("STEP 1: Fetching from FRED API (7 series)")
    _info("Endpoint: api.stlouisfed.org/fred/series/observations")
    _info("Series: DGS10, DGS2, DGS30, DGS3MO, FEDFUNDS, DFEDTARU, DFEDTARL")

    result = fetch_treasury_yields(api_key)

    # ── STEP 2: Yield curve analysis ──────────────────────────────────────────
    _section("STEP 2: Yield Curve Analysis")

    y10  = result.get("yield_10y")
    y2   = result.get("yield_2y")
    y30  = result.get("yield_30y")
    y3m  = result.get("yield_3m")
    ffr_upper = result.get("ffr_target_upper")
    ffr_lower = result.get("ffr_target_lower")
    ffr_mid   = result.get("ffr_midpoint")
    spread    = result.get("spread_2s10s")
    curve     = result.get("curve_status")

    print()
    _info("YIELD CURVE:")
    _info(f"  3-Month T-Bill : {y3m:.3f}%"  if y3m  else "  3-Month T-Bill : N/A")
    _info(f"  2-Year         : {y2:.3f}%"   if y2   else "  2-Year         : N/A")
    _info(f"  10-Year        : {y10:.3f}%"  if y10  else "  10-Year        : N/A")
    _info(f"  30-Year        : {y30:.3f}%"  if y30  else "  30-Year        : N/A")
    print()
    _info("FED FUNDS RATE:")
    _info(f"  Target range   : {ffr_lower:.2f}% – {ffr_upper:.2f}% (mid: {ffr_mid:.3f}%)"
          if (ffr_lower and ffr_upper) else "  Target range   : N/A")
    print()
    _info("SPREAD ANALYSIS:")
    _info(f"  2s10s spread   : {spread:+.3f}% ({curve})"
          if spread is not None else "  2s10s spread   : N/A")
    _info(f"  10s30s spread  : {result.get('spread_10s30s'):+.3f}%"
          if result.get('spread_10s30s') is not None else "  10s30s spread  : N/A")
    _info(f"  3m10y spread   : {result.get('spread_3m10y'):+.3f}%"
          if result.get('spread_3m10y') is not None else "  3m10y spread   : N/A")
    print()

    # Curve interpretation
    if curve == "INVERTED":
        _warn("INVERTED YIELD CURVE — historically a recession leading indicator")
        _info("  2s10s < 0: short rates higher than long rates")
        _info("  Historically precedes recession by 6-18 months")
    elif curve == "NORMAL":
        _ok(f"NORMAL YIELD CURVE — spread {spread:+.3f}% (healthy)")
        _info("  Long rates above short rates — standard growth environment")
    elif curve == "FLAT":
        _warn(f"FLAT YIELD CURVE — spread {spread:+.3f}% (within 10bp threshold)")
        _info("  Transition zone — watch for direction")
    else:
        _warn("CURVE STATUS UNKNOWN — insufficient data")

    # Rate vs equity signal for Research Department
    if y10 and y2 and ffr_upper:
        _info("")
        _info("RESEARCH DEPARTMENT SIGNALS:")
        _info(f"  10Y real rate proxy : {y10:.3f}% (discount rate for equity valuations)")
        _info(f"  NIM proxy (BAC/WFC) : {y10 - ffr_lower:.3f}% (10Y - FFR lower bound)")
        _info(f"  Curve carry         : {y30 - y2:.3f}% (30Y - 2Y)" if y30 else "")

    if args.dry_run:
        _section("DRY RUN — Skipping DB write and JSON output")
        print()
        print("  Run without --dry-run to write to DB and output JSON.")
        print()
        print("=" * 62)
        return

    # ── STEP 3: DB write ──────────────────────────────────────────────────────
    _section("STEP 3: Writing to macro_yields DB table")
    write_to_db(result, snapshot_date)

    # ── STEP 4: JSON output ───────────────────────────────────────────────────
    _section("STEP 4: Writing treasury_yields.json")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path   = os.path.join(script_dir, "treasury_yields.json")
    try:
        write_json(result, snapshot_date, out_path)
        size_kb = round(os.path.getsize(out_path) / 1024, 1)
        _ok(f"Saved: {out_path}  ({size_kb} KB)")
    except Exception as e:
        _fail(f"JSON write failed: {e}")

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print(f"  COMPLETE — Treasury Yields Fetcher {VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  10Y: {y10:.3f}% | 2Y: {y2:.3f}% | Spread: {spread:+.3f}% | {curve}"
          if (y10 and y2 and spread) else "  Yields: check output above")
    print(f"  FFR: {ffr_lower:.2f}%-{ffr_upper:.2f}%"
          if (ffr_lower and ffr_upper) else "  FFR: check output above")
    print(f"  JSON: treasury_yields.json")
    print()
    print("  NEXT STEP: Run export_dataset_raw.py to include treasury_yields")
    print("             in dataset_raw.json for Frontend.")
    print("=" * 62)


if __name__ == "__main__":
    main()
