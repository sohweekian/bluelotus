"""
BlueLotus Digital Institution — V2.0
mid/fetch_fundamentals.py — Fundamental Valuation Fetcher

VERSION: v1.0
DATE:    June 2026
AUTHOR:  MID Engineering (Claude)

PURPOSE:
    Standalone fetcher for fundamental valuation data across all 83 watchlist
    tickers. Runs independently of ingest.py. Writes to ticker_fundamentals
    table in bluelotus2 DB and outputs fundamentals.json for verification.

    This follows the BlueLotus modular architecture doctrine:
    - One file, one job
    - Writes to DB, outputs JSON
    - ingest.py is NOT touched
    - export_dataset_raw.py reads from ticker_fundamentals table

API SOURCE (verified against official docs v10.3):
    https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-market-snapshot.html

    Function:  OpenQuoteContext.get_market_snapshot(code_list)
    Limit:     Up to 400 codes per single call — all 83 tickers in ONE call
    Context:   OpenQuoteContext (NOT OpenSecTradeContext)

VERIFIED DATAFRAME COLUMNS (exact names from official docs):
    equity_valid          bool   — must be True for all fields below to be populated
    pe_ratio              float  — P/E ratio (ratio, not %)
    pe_ttm_ratio          float  — P/E ratio TTM (ratio, not %)
    pb_ratio              float  — P/B ratio (ratio, not %)
    ey_ratio              float  — Earnings yield (ratio, not %)
    earning_per_share     float  — EPS
    net_asset             int    — Total net asset value
    net_profit            int    — Net profit/loss
    net_asset_per_share   float  — Book value per share
    total_market_val      float  — Total market cap (unit: yuan — confirm USD for US)
    issued_shares         int    — Total shares issued
    outstanding_shares    int    — Shares outstanding (float)
    dividend_ttm          float  — Dividend TTM amount
    dividend_ratio_ttm    float  — Dividend yield TTM (% form: 20 = 20%)
    dividend_lfy          float  — Dividend last full year amount
    dividend_lfy_ratio    float  — Dividend yield LFY (% form)
    highest52weeks_price  float  — 52-week high
    lowest52weeks_price   float  — 52-week low
    highest_history_price float  — All-time high
    lowest_history_price  float  — All-time low (note: sometimes returns near-zero)
    volume_ratio          float  — Volume ratio vs average
    turnover_rate         float  — Turnover rate (% form: 20 = 20%)
    amplitude             float  — Daily range amplitude (% form)
    avg_price             float  — Average price (VWAP)
    last_price            float  — Current price (for computed fields)
    circular_market_val   float  — Circulation market cap

COMPUTED FIELDS (derived by this script):
    pct_from_52w_high  — how far below 52-week high (negative = below)
    pct_from_52w_low   — how far above 52-week low (positive = above)
    earnings_yield     — 1/pe_ttm * 100 (%)

NOTES:
    - equity_valid must be True for fundamental fields to be populated
    - TLT (ETF) and other non-equity instruments: equity_valid = False
      For ETFs, the trust_* fields are populated instead. We skip these.
    - total_market_val for US stocks is returned in USD (confirmed via AAPL test)
    - All ratio fields (pe_ratio, pb_ratio, etc.) are plain ratios — NOT percentages
    - dividend_ratio_ttm and turnover_rate ARE in percentage form (20 = 20%)

USAGE:
    cd C:\\bluelotus2
    python mid\\fetch_fundamentals.py

    Flags:
    --dry-run     Fetch and print, skip DB write and JSON output
    --tickers     Comma-separated subset: --tickers BAC,WFC,NVDA

RUN SCHEDULE (recommended):
    Once daily after US market close, or once per week for stable fundamental data.
    Data changes on earnings dates — run after earnings for updated EPS/P/E.
"""

import os
import sys
import json
import argparse
from datetime import datetime, date
from dotenv import load_dotenv
from ticker_universe import ETF_TICKERS, get_universe

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111
VERSION    = "v1.0"

# ── WATCHLIST_83 ──────────────────────────────────────────────────────────────
WATCHLIST_83 = get_universe()

# Tickers known to be non-equity (equity_valid = False)
# Their fundamental fields will be null — we still record them with equity_valid=False
# so the DB has a complete record for all 83 tickers
NON_EQUITY_KNOWN = set(ETF_TICKERS)


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
    """Convert value to float, return default on NaN/None/error."""
    try:
        f = float(val)
        return default if (f != f) else round(f, 6)  # NaN check: NaN != NaN
    except (TypeError, ValueError):
        return default


# ── Safe int helper ───────────────────────────────────────────────────────────
def _si(val, default=None):
    """Convert value to int, return default on error."""
    try:
        f = float(val)
        if f != f:  # NaN
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


# ── Main fetch ────────────────────────────────────────────────────────────────
def fetch_fundamentals(tickers: list) -> dict:
    """
    Fetch fundamental data for all tickers in a single get_market_snapshot() call.
    Returns dict keyed by ticker.

    API: OpenQuoteContext.get_market_snapshot(code_list)
    All 83 tickers in ONE call (limit is 400 per call — well within limit).
    No rate limiting needed.
    """
    import moomoo as ft
    import moomoo.common.ft_logger as _ftl
    _ftl.logger.enable_console_log(False)

    codes = [f"US.{t}" for t in tickers]
    results = {}

    print(f"\n  Tickers : {len(tickers)}")
    print(f"  API call: 1 × get_market_snapshot({len(codes)} codes)")
    print(f"  Rate limit: 400 max per call — well within limit")
    print()

    try:
        ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
    except Exception as e:
        _fail(f"OpenQuoteContext connection failed: {e}")
        return {}

    try:
        ret, data = ctx.get_market_snapshot(codes)
    except Exception as e:
        _fail(f"get_market_snapshot() exception: {e}")
        ctx.close()
        return {}

    ctx.close()

    if ret != ft.RET_OK:
        _fail(f"get_market_snapshot() error: {data}")
        return {}

    if data is None or data.empty:
        _fail("get_market_snapshot() returned empty DataFrame")
        return {}

    _ok(f"get_market_snapshot() returned {len(data)} rows")
    print()

    cycle_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in data.iterrows():
        code   = str(row.get("code", "")).replace("US.", "")
        equity = bool(row.get("equity_valid", False))

        # Base entry — always recorded even for non-equity
        rec = {
            "equity_valid": equity,
            "cycle_ts":     cycle_ts,
        }

        if equity:
            # ── Valuation ratios ──────────────────────────────────────────
            pe       = _sf(row.get("pe_ratio"))
            pe_ttm   = _sf(row.get("pe_ttm_ratio"))
            pb       = _sf(row.get("pb_ratio"))
            ey       = _sf(row.get("ey_ratio"))

            # ── Per-share data ────────────────────────────────────────────
            eps      = _sf(row.get("earning_per_share"))
            bvps     = _sf(row.get("net_asset_per_share"))

            # ── Scale data ────────────────────────────────────────────────
            mkt_cap  = _sf(row.get("total_market_val"))
            net_ast  = _sf(row.get("net_asset"))
            net_pft  = _sf(row.get("net_profit"))
            issued   = _si(row.get("issued_shares"))
            outstand = _si(row.get("outstanding_shares"))
            circ_mkt = _sf(row.get("circular_market_val"))

            # ── Dividends ─────────────────────────────────────────────────
            div_ttm       = _sf(row.get("dividend_ttm"))
            div_yield_ttm = _sf(row.get("dividend_ratio_ttm"))  # % form: 20 = 20%
            div_lfy       = _sf(row.get("dividend_lfy"))
            div_yield_lfy = _sf(row.get("dividend_lfy_ratio"))  # % form

            # ── 52-week and historical price range ────────────────────────
            high_52w = _sf(row.get("highest52weeks_price"))
            low_52w  = _sf(row.get("lowest52weeks_price"))
            ath      = _sf(row.get("highest_history_price"))
            atl      = _sf(row.get("lowest_history_price"))

            # ── Market microstructure ─────────────────────────────────────
            vol_ratio   = _sf(row.get("volume_ratio"))
            volume      = _sf(row.get("volume"))
            avg_volume_30d = (
                round(volume / vol_ratio, 2)
                if volume and vol_ratio and vol_ratio > 0
                else None
            )
            turn_rate   = _sf(row.get("turnover_rate"))   # % form
            amplitude   = _sf(row.get("amplitude"))       # % form
            avg_price   = _sf(row.get("avg_price"))
            last_price  = _sf(row.get("last_price"))

            # ── Computed fields ───────────────────────────────────────────
            pct_from_52w_high = None
            pct_from_52w_low  = None
            earnings_yield    = None

            if last_price and high_52w and high_52w > 0:
                pct_from_52w_high = round((last_price - high_52w) / high_52w * 100, 4)

            if last_price and low_52w and low_52w > 0:
                pct_from_52w_low = round((last_price - low_52w) / low_52w * 100, 4)

            if pe_ttm and pe_ttm > 0:
                earnings_yield = round(1 / pe_ttm * 100, 4)

            rec.update({
                # Valuation
                "pe_ratio":           pe,
                "pe_ttm_ratio":       pe_ttm,
                "pb_ratio":           pb,
                "ey_ratio":           ey,
                # Per-share
                "earning_per_share":  eps,
                "net_asset_per_share": bvps,
                # Scale
                "total_market_val":   mkt_cap,
                "net_asset":          net_ast,
                "net_profit":         net_pft,
                "issued_shares":      issued,
                "outstanding_shares": outstand,
                "circular_market_val": circ_mkt,
                # Dividends
                "dividend_ttm":       div_ttm,
                "dividend_ratio_ttm": div_yield_ttm,
                "dividend_lfy":       div_lfy,
                "dividend_lfy_ratio": div_yield_lfy,
                # Price range
                "high_52w":           high_52w,
                "low_52w":            low_52w,
                "all_time_high":      ath,
                "all_time_low":       atl,
                # Microstructure
                "volume_ratio":       vol_ratio,
                "snapshot_volume":    volume,
                "avg_volume_30d":     avg_volume_30d,
                "turnover_rate":      turn_rate,
                "amplitude":          amplitude,
                "avg_price":          avg_price,
                "last_price":         last_price,
                # Computed
                "pct_from_52w_high":  pct_from_52w_high,
                "pct_from_52w_low":   pct_from_52w_low,
                "earnings_yield":     earnings_yield,
            })

            arrow = "+" if (last_price or 0) > 0 else ""
            _ok(f"  {code:<6} PE={pe_ttm or 'N/A':>7}  PB={pb or 'N/A':>6}  "
                f"EPS={eps or 'N/A':>7}  "
                f"52w: {pct_from_52w_high or 0:>+.1f}%  "
                f"MktCap=${mkt_cap/1e9:.1f}B" if mkt_cap else
                f"  {code:<6} equity_valid=True but mkt_cap=None")
        else:
            # Non-equity (ETF, fund, index) — record with null fundamentals
            _warn(f"  {code:<6} equity_valid=False "
                  f"{'(ETF/fund — expected)' if code in NON_EQUITY_KNOWN else '(unexpected)'}")
            rec.update({
                "pe_ratio": None, "pe_ttm_ratio": None, "pb_ratio": None,
                "ey_ratio": None, "earning_per_share": None,
                "net_asset_per_share": None, "total_market_val": None,
                "net_asset": None, "net_profit": None,
                "issued_shares": None, "outstanding_shares": None,
                "circular_market_val": None,
                "dividend_ttm": None, "dividend_ratio_ttm": None,
                "dividend_lfy": None, "dividend_lfy_ratio": None,
                "high_52w": None, "low_52w": None,
                "all_time_high": None, "all_time_low": None,
                "volume_ratio": None, "snapshot_volume": None, "avg_volume_30d": None,
                "turnover_rate": None,
                "amplitude": None, "avg_price": None, "last_price": None,
                "pct_from_52w_high": None, "pct_from_52w_low": None,
                "earnings_yield": None,
            })

        results[code] = rec

    return results


# ── DB writer ─────────────────────────────────────────────────────────────────
def write_to_db(results: dict, snapshot_date: str) -> tuple:
    """
    Write fundamentals to ticker_fundamentals table.
    Uses INSERT ... ON DUPLICATE KEY UPDATE (uq_ticker_date).
    Returns (written, updated, failed) counts.

    Schema maps (our field → DB column):
      pe_ttm_ratio   → pe_ttm
      pb_ratio       → pb_ratio
      total_market_val → market_cap
      outstanding_shares → shares_outstanding
      dividend_ratio_ttm → dividend_yield
      earning_per_share → eps_ttm
      ey_ratio → earnings_yield (raw ratio — we also compute 1/pe*100)
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
        return 0, 0, len(results)

    cur = conn.cursor()
    written = updated = failed = 0

    sql = """
        INSERT INTO ticker_fundamentals
            (ticker, snapshot_date, cycle_ts, source,
             pe_ttm, pe_forward, pb_ratio, eps_ttm, eps_forward, dividend_yield,
             market_cap, shares_outstanding,
             avg_volume_30d,
             high_52w, low_52w,
             pct_from_52w_high, pct_from_52w_low,
             earnings_yield,
             net_income_ttm, revenue_ttm)
        VALUES
            (%s, %s, %s, %s,
             %s, %s, %s, %s, %s, %s,
             %s, %s,
             %s,
             %s, %s,
             %s, %s,
             %s,
             %s, %s)
        ON DUPLICATE KEY UPDATE
            cycle_ts          = VALUES(cycle_ts),
            pe_ttm            = VALUES(pe_ttm),
            pb_ratio          = VALUES(pb_ratio),
            eps_ttm           = VALUES(eps_ttm),
            dividend_yield    = VALUES(dividend_yield),
            market_cap        = VALUES(market_cap),
            shares_outstanding= VALUES(shares_outstanding),
            avg_volume_30d    = VALUES(avg_volume_30d),
            high_52w          = VALUES(high_52w),
            low_52w           = VALUES(low_52w),
            pct_from_52w_high = VALUES(pct_from_52w_high),
            pct_from_52w_low  = VALUES(pct_from_52w_low),
            pe_forward        = VALUES(pe_forward),
            eps_forward       = VALUES(eps_forward),
            earnings_yield    = VALUES(earnings_yield),
            net_income_ttm    = VALUES(net_income_ttm),
            revenue_ttm       = VALUES(revenue_ttm)
    """

    for ticker, data in results.items():
        try:
            cur.execute(sql, (
                ticker,
                snapshot_date,
                data.get("cycle_ts"),
                "Moomoo_Fundamentals",
                data.get("pe_ttm_ratio"),
                data.get("pe_ratio"),            # pe_forward column = static PE
                data.get("pb_ratio"),
                data.get("earning_per_share"),
                data.get("net_asset_per_share"),  # stored in eps_forward column
                data.get("dividend_ratio_ttm"),
                data.get("total_market_val"),
                data.get("outstanding_shares"),
                data.get("avg_volume_30d"),
                data.get("high_52w"),
                data.get("low_52w"),
                data.get("pct_from_52w_high"),
                data.get("pct_from_52w_low"),
                data.get("earnings_yield"),
                data.get("net_profit"),      # net_profit = net income TTM in Moomoo
                None,                         # revenue_ttm — not available in snapshot
            ))
            if cur.rowcount == 1:
                written += 1
            else:
                updated += 1
        except Exception as e:
            _fail(f"DB write failed for {ticker}: {e}")
            failed += 1

    conn.commit()
    cur.close()
    conn.close()
    return written, updated, failed


# ── JSON writer ───────────────────────────────────────────────────────────────
def write_json(results: dict, snapshot_date: str, cycle_ts: str, out_path: str):
    """Write results to fundamentals.json for verification and export."""
    equity_count = sum(1 for v in results.values() if v.get("equity_valid"))
    output = {
        "fetch_timestamp_sgt": cycle_ts,
        "snapshot_date":       snapshot_date,
        "source":              "Moomoo OpenD get_market_snapshot() equityExData",
        "version":             VERSION,
        "ticker_count":        len(results),
        "equity_count":        equity_count,
        "non_equity_count":    len(results) - equity_count,
        "fundamentals":        results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Fundamentals Fetcher v1.0"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Fetch and print only — skip DB write and JSON output")
    parser.add_argument("--tickers",  type=str, default=None,
                        help="Comma-separated subset: --tickers BAC,WFC,NVDA")
    args = parser.parse_args()

    now           = datetime.now()
    snapshot_date = date.today().strftime("%Y-%m-%d")
    cycle_ts      = now.strftime("%Y-%m-%d %H:%M:%S")

    # Ticker list
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        _warn(f"Custom ticker list: {tickers}")
    else:
        tickers = WATCHLIST_83

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print(f"  BLUELOTUS MID — Fundamentals Fetcher {VERSION}")
    print(f"  {cycle_ts} SGT")
    print(f"  Mode: {'DRY RUN (no DB write)' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 62)

    # ── STEP 1: Fetch ─────────────────────────────────────────────────────────
    _section("STEP 1: Fetching fundamentals from Moomoo OpenD")
    _info("Single get_market_snapshot() call — all 83 tickers at once")
    _info("No batching or rate limiting needed (limit: 400 codes per call)")

    results = fetch_fundamentals(tickers)

    if not results:
        _fail("No results returned — check Moomoo OpenD connection")
        sys.exit(1)

    equity_tickers  = [t for t,v in results.items() if v.get("equity_valid")]
    non_equity      = [t for t,v in results.items() if not v.get("equity_valid")]

    print()
    _ok(f"Fetched: {len(results)} tickers | {len(equity_tickers)} equity | {len(non_equity)} non-equity")
    if non_equity:
        _info(f"Non-equity (null fundamentals): {non_equity}")

    # ── STEP 2: Valuation summary ─────────────────────────────────────────────
    _section("STEP 2: Valuation Summary")

    # Cheapest by P/E TTM
    by_pe = [(t, v.get("pe_ttm_ratio")) for t,v in results.items()
             if v.get("pe_ttm_ratio") and v["pe_ttm_ratio"] > 0]
    by_pe.sort(key=lambda x: x[1])

    _info("Cheapest by P/E TTM (top 10):")
    for t, pe in by_pe[:10]:
        pb = results[t].get("pb_ratio") or 0
        ey = results[t].get("earnings_yield") or 0
        _info(f"  {t:<6} PE={pe:>7.2f}  PB={pb:>6.2f}  EY={ey:>5.2f}%")

    # Most expensive
    _info("")
    _info("Most expensive by P/E TTM (top 5):")
    for t, pe in by_pe[-5:][::-1]:
        _info(f"  {t:<6} PE={pe:>7.2f}")

    # Highest dividend yield
    by_div = [(t, v.get("dividend_ratio_ttm") or 0) for t,v in results.items()
              if v.get("equity_valid") and v.get("dividend_ratio_ttm")]
    by_div.sort(key=lambda x: x[1], reverse=True)
    _info("")
    _info("Highest dividend yield TTM (top 5):")
    for t, dy in by_div[:5]:
        _info(f"  {t:<6} yield={dy:.2f}%")

    # Most below 52w high (buying opportunity indicator)
    below_52w = [(t, v.get("pct_from_52w_high") or 0)
                 for t,v in results.items()
                 if v.get("equity_valid") and v.get("pct_from_52w_high") is not None]
    below_52w.sort(key=lambda x: x[1])
    _info("")
    _info("Most below 52-week high (top 5):")
    for t, pct in below_52w[:5]:
        low_52 = results[t].get("low_52w") or 0
        pct_above_low = results[t].get("pct_from_52w_low") or 0
        _info(f"  {t:<6} {pct:>+.1f}% from 52w high | {pct_above_low:>+.1f}% from 52w low")

    # Portfolio positions
    _info("")
    _info("Your portfolio positions:")
    for t in ["BAC", "WFC"]:
        v = results.get(t, {})
        _info(f"  {t}: PE={v.get('pe_ttm_ratio') or 'N/A'}  "
              f"PB={v.get('pb_ratio') or 'N/A'}  "
              f"EPS={v.get('earning_per_share') or 'N/A'}  "
              f"Div%={v.get('dividend_ratio_ttm') or 'N/A'}  "
              f"52w: {v.get('pct_from_52w_high') or 0:+.1f}%")

    if args.dry_run:
        _section("DRY RUN — Skipping DB write and JSON output")
        print()
        print("  Run without --dry-run to write to DB and output JSON.")
        print()
        print("=" * 62)
        return

    # ── STEP 3: DB write ──────────────────────────────────────────────────────
    _section("STEP 3: Writing to ticker_fundamentals DB table")
    written, updated, db_failed = write_to_db(results, snapshot_date)
    _ok(f"DB write: {written} new | {updated} updated | {db_failed} failed")

    # ── STEP 4: JSON output ───────────────────────────────────────────────────
    _section("STEP 4: Writing fundamentals.json")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path   = os.path.join(script_dir, "fundamentals.json")
    try:
        write_json(results, snapshot_date, cycle_ts, out_path)
        size_kb = round(os.path.getsize(out_path) / 1024, 1)
        _ok(f"Saved: {out_path}  ({size_kb} KB)")
    except Exception as e:
        _fail(f"JSON write failed: {e}")

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print(f"  COMPLETE — Fundamentals Fetcher {VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Tickers fetched : {len(results)}")
    print(f"  Equity          : {len(equity_tickers)}")
    print(f"  Non-equity      : {len(non_equity)}")
    print(f"  DB written      : {written} new / {updated} updated")
    print(f"  JSON            : fundamentals.json")
    print()
    print("  NEXT STEP: Run export_dataset_raw.py to include fundamentals")
    print("             in dataset_raw.json for Frontend.")
    print("=" * 62)


if __name__ == "__main__":
    main()
