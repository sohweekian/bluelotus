"""
BlueLotus Digital Institution — V2.0
mid/fetch_capital_flow.py — Capital Flow Intelligence Fetcher

VERSION: v1.0
DATE:    June 2026
AUTHOR:  MID Engineering (Claude)

PURPOSE:
    Standalone fetcher for Moomoo capital flow data across all 83 watchlist
    tickers. Runs independently of ingest.py. Writes to ticker_capital_flow
    table in bluelotus2 DB and outputs capital_flow.json for verification.

    This follows the BlueLotus modular architecture doctrine:
    - One file, one job
    - Writes to DB, outputs JSON
    - ingest.py is NOT touched
    - export_dataset_raw.py reads from ticker_capital_flow table

API SOURCE (verified against official docs v10.6):
    https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-capital-flow.html

    Function:  OpenQuoteContext.get_capital_flow(stock_code, period_type, start, end)
    Columns:   in_flow, main_in_flow, super_in_flow, big_in_flow, mid_in_flow,
               sml_in_flow, capital_flow_item_time, last_valid_time
    Limits:    30 requests per 30 seconds — hard limit
    Context:   OpenQuoteContext (NOT OpenSecTradeContext)
    Note:      main_in_flow ONLY available for PeriodType.DAY/WEEK/MONTH
               Stocks, warrants, funds only — NOT indices
               TLT (ETF) IS supported — bond ETF counts as fund

DESIGN:
    - PeriodType.DAY — gets historical daily data, latest trading day = row[-1]
    - Batch size: 25 tickers per batch (leaves buffer under 30/30s limit)
    - Pause: 32 seconds between batches (safely clears the 30-second window)
    - Total time: ~4 batches × (25 × 0.3s + 32s) ≈ 3.5 minutes for 83 tickers
    - DB write: INSERT ... ON DUPLICATE KEY UPDATE (uq_cf_ticker_date)
    - JSON output: capital_flow.json in script directory

INSTITUTIONAL BIAS LOGIC:
    super_in_flow + big_in_flow = institutional / smart money
    sml_in_flow                 = retail
    Combinations → INSTITUTIONAL_ACCUMULATE / INSTITUTIONAL_DISTRIBUTE /
                   INFLOW / OUTFLOW / NEUTRAL

USAGE:
    cd C:\\bluelotus2
    python mid\\fetch_capital_flow.py

    Flags:
    --dry-run     Fetch and print, skip DB write and JSON output
    --tickers     Comma-separated subset: --tickers BAC,WFC,NVDA
    --date        Override date for start/end: --date 2026-05-30

RUN SCHEDULE (recommended):
    Once daily, after US market close (16:30 ET / 04:30 SGT next day)
    Capital flow data for the trading day is finalised after close.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from ticker_universe import get_universe

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
OPEND_HOST   = "127.0.0.1"
OPEND_PORT   = 11111
BATCH_SIZE   = 25    # Tickers per batch — safely under 30/30s limit
BATCH_PAUSE  = 32    # Seconds between batches — clears 30s rate limit window
TICKER_PAUSE = 0.30  # Seconds between individual calls within a batch
LOOKBACK_DAYS = 7    # Days to look back for start date (buffer for weekends/holidays)
VERSION      = "v1.0"

# ── WATCHLIST_83 ──────────────────────────────────────────────────────────────
# Mirrors ingest.py WATCHLIST_83 exactly
# TLT (ETF/fund) IS supported by get_capital_flow — confirmed from API docs
# Indices (^VIX) are NOT supported — excluded here
WATCHLIST_83 = get_universe()

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
    """Convert a value to float, returning default on NaN or error."""
    try:
        f = float(val)
        return default if (f != f) else round(f, 2)  # NaN check: NaN != NaN
    except (TypeError, ValueError):
        return default


# ── Institutional bias classifier ─────────────────────────────────────────────
def _classify_bias(super_in, big_in, sml_in):
    """
    Classify institutional vs retail bias from capital flow components.

    smart_money = super_in_flow + big_in_flow (extra-large + large lots)
    retail      = sml_in_flow (small lots)

    Returns one of:
      INSTITUTIONAL_ACCUMULATE — smart money buying, retail selling
      INSTITUTIONAL_DISTRIBUTE — smart money selling, retail buying
      INFLOW                   — net positive, mixed or same direction
      OUTFLOW                  — net negative, mixed or same direction
      NEUTRAL                  — near zero or both sides balanced
    """
    inst  = (super_in or 0) + (big_in or 0)
    retail = (sml_in or 0)

    if inst > 0 and retail < 0:
        return "ACCUMULATE"   # Smart money in, retail out — strongest signal
    elif inst < 0 and retail > 0:
        return "DISTRIBUTE"   # Smart money out, retail in — distribution
    elif inst > 0:
        return "INFLOW"       # Both buying, or just institutional
    elif inst < 0:
        return "OUTFLOW"      # Both selling, or just institutional
    else:
        return "NEUTRAL"


# ── Single ticker fetch ───────────────────────────────────────────────────────
def _fetch_one(ctx, ticker: str, start_date: str, end_date: str) -> dict:
    """
    Fetch capital flow for one ticker using PeriodType.DAY.
    Returns the most recent trading day's row as a dict.
    Returns {} on any failure — caller logs the error.

    API call: ctx.get_capital_flow(stock_code, period_type, start, end)
    Returns DataFrame with columns:
      in_flow, main_in_flow, super_in_flow, big_in_flow, mid_in_flow,
      sml_in_flow, capital_flow_item_time, last_valid_time
    """
    import moomoo as ft

    code = f"US.{ticker}"
    try:
        ret, data = ctx.get_capital_flow(
            code,
            period_type=ft.PeriodType.DAY,
            start=start_date,
            end=end_date,
        )

        if ret != ft.RET_OK:
            return {"error": str(data)}

        if data is None or data.empty:
            return {"error": "empty dataframe"}

        # Take the most recent row (latest trading day)
        row = data.iloc[-1]

        in_flow    = _sf(row.get("in_flow"))
        main_in    = _sf(row.get("main_in_flow"))    # block orders — DAY only, confirmed
        super_in   = _sf(row.get("super_in_flow"))
        big_in     = _sf(row.get("big_in_flow"))
        mid_in     = _sf(row.get("mid_in_flow"))
        sml_in     = _sf(row.get("sml_in_flow"))
        data_date  = str(row.get("capital_flow_item_time", ""))

        bias = _classify_bias(super_in, big_in, sml_in)

        return {
            "in_flow":            in_flow,
            "main_in_flow":       main_in,
            "super_in_flow":      super_in,
            "big_in_flow":        big_in,
            "mid_in_flow":        mid_in,
            "sml_in_flow":        sml_in,
            "institutional_bias": bias,
            "data_date":          data_date,
            "rows_returned":      len(data),
        }

    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ── Batch fetcher ─────────────────────────────────────────────────────────────
def fetch_all_capital_flow(tickers: list, start_date: str, end_date: str) -> dict:
    """
    Fetch capital flow for all tickers in rate-limited batches.
    Opens one OpenQuoteContext per batch (same pattern as fetch_analyst_targets.py).

    Rate limit: 30 requests per 30 seconds.
    Strategy:   25 tickers per batch + 32s pause = safely compliant.
    """
    import moomoo as ft
    import moomoo.common.ft_logger as _ftl
    _ftl.logger.enable_console_log(False)

    total   = len(tickers)
    batches = [tickers[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    results = {}

    est_secs = len(batches) * (BATCH_SIZE * TICKER_PAUSE + BATCH_PAUSE)
    print(f"\n  Tickers : {total}")
    print(f"  Batches : {len(batches)} × {BATCH_SIZE} tickers")
    print(f"  Pause   : {BATCH_PAUSE}s between batches")
    print(f"  Est.    : ~{int(est_secs // 60)}m {int(est_secs % 60)}s")
    print(f"  Date    : {start_date} → {end_date}")
    print()

    for b_idx, batch in enumerate(batches):
        print(f"  Batch {b_idx+1}/{len(batches)}: {', '.join(batch)}")

        try:
            ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
        except Exception as e:
            _fail(f"Batch {b_idx+1} OpenQuoteContext failed: {e}")
            for ticker in batch:
                results[ticker] = {"error": f"connection failed: {e}"}
            if b_idx < len(batches) - 1:
                time.sleep(BATCH_PAUSE)
            continue

        batch_ok   = 0
        batch_fail = 0

        for i, ticker in enumerate(batch):
            offset = b_idx * BATCH_SIZE + i + 1
            result = _fetch_one(ctx, ticker, start_date, end_date)
            results[ticker] = result

            if "error" in result:
                _fail(f"  [{offset:>3}/{total}] {ticker:<6} {result['error']}")
                batch_fail += 1
            else:
                bias    = result.get("institutional_bias", "?")
                in_flow = result.get("in_flow") or 0
                arrow   = "▲" if in_flow > 0 else "▼"
                _ok(f"  [{offset:>3}/{total}] {ticker:<6} "
                    f"net {arrow}${abs(in_flow)/1e6:>8.2f}M  "
                    f"super ${(result.get('super_in_flow') or 0)/1e6:>8.2f}M  "
                    f"retail ${(result.get('sml_in_flow') or 0)/1e6:>7.2f}M  "
                    f"[{bias}]")
                batch_ok += 1

            time.sleep(TICKER_PAUSE)

        ctx.close()
        print(f"  Batch {b_idx+1} done: {batch_ok} OK / {batch_fail} failed")

        if b_idx < len(batches) - 1:
            print(f"  Pausing {BATCH_PAUSE}s for rate limit...\n")
            time.sleep(BATCH_PAUSE)

    return results


# ── DB writer ─────────────────────────────────────────────────────────────────
def write_to_db(results: dict, snapshot_date: str, cycle_ts: str) -> tuple:
    """
    Write capital flow results to ticker_capital_flow table.
    Uses INSERT ... ON DUPLICATE KEY UPDATE (uq_cf_ticker_date).
    Returns (written, updated, failed) counts.

    Table schema (from create_valuation_tables.py):
      ticker, snapshot_date, cycle_ts, source,
      main_in, main_out, main_net, main_net_ratio,
      super_large_in, super_large_out, super_large_net,
      large_in, large_out, large_net,
      medium_in, medium_out, medium_net,
      small_in, small_out, small_net,
      institutional_bias
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
        INSERT INTO ticker_capital_flow
            (ticker, snapshot_date, cycle_ts, source,
             main_net, super_large_net, large_net, medium_net, small_net,
             super_large_in, super_large_out,
             large_in, large_out,
             medium_in, medium_out,
             small_in, small_out,
             institutional_bias)
        VALUES
            (%s, %s, %s, %s,
             %s, %s, %s, %s, %s,
             %s, %s,
             %s, %s,
             %s, %s,
             %s, %s,
             %s)
        ON DUPLICATE KEY UPDATE
            cycle_ts          = VALUES(cycle_ts),
            main_net          = VALUES(main_net),
            super_large_net   = VALUES(super_large_net),
            large_net         = VALUES(large_net),
            medium_net        = VALUES(medium_net),
            small_net         = VALUES(small_net),
            super_large_in    = VALUES(super_large_in),
            super_large_out   = VALUES(super_large_out),
            large_in          = VALUES(large_in),
            large_out         = VALUES(large_out),
            medium_in         = VALUES(medium_in),
            medium_out        = VALUES(medium_out),
            small_in          = VALUES(small_in),
            small_out         = VALUES(small_out),
            institutional_bias= VALUES(institutional_bias)
    """

    for ticker, data in results.items():
        if "error" in data:
            failed += 1
            continue

        # The API returns net flow per lot size in in_flow family.
        # super_in_flow / big_in_flow / mid_in_flow / sml_in_flow are NET values.
        # The DB schema separates in/out — we store net in the _net column,
        # and derive in/out by sign (positive = inflow, negative = outflow).
        super_net = data.get("super_in_flow") or 0
        big_net   = data.get("big_in_flow")   or 0
        mid_net   = data.get("mid_in_flow")   or 0
        sml_net   = data.get("sml_in_flow")   or 0
        main_net  = data.get("main_in_flow")  or 0

        # Derive in/out from sign of net value
        def _in(v):  return round(v, 2) if v > 0 else 0
        def _out(v): return round(abs(v), 2) if v < 0 else 0

        try:
            cur.execute(sql, (
                ticker, snapshot_date, cycle_ts, "Moomoo_CapitalFlow",
                round(main_net, 2),
                round(super_net, 2),
                round(big_net, 2),
                round(mid_net, 2),
                round(sml_net, 2),
                _in(super_net),  _out(super_net),
                _in(big_net),    _out(big_net),
                _in(mid_net),    _out(mid_net),
                _in(sml_net),    _out(sml_net),
                data.get("institutional_bias", "NEUTRAL"),
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
    """Write results to capital_flow.json for verification and export."""
    output = {
        "fetch_timestamp_sgt": cycle_ts,
        "snapshot_date":       snapshot_date,
        "source":              "Moomoo OpenD get_capital_flow (PeriodType.DAY)",
        "version":             VERSION,
        "ticker_count":        len(results),
        "ok_count":            sum(1 for v in results.values() if "error" not in v),
        "fail_count":          sum(1 for v in results.values() if "error" in v),
        "capital_flow":        results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Capital Flow Fetcher v1.0"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Fetch and print only — skip DB write and JSON output")
    parser.add_argument("--tickers",  type=str, default=None,
                        help="Comma-separated subset: --tickers BAC,WFC,NVDA")
    parser.add_argument("--date",     type=str, default=None,
                        help="Override end date (yyyy-mm-dd): --date 2026-05-30")
    args = parser.parse_args()

    now          = datetime.now()
    end_date     = args.date if args.date else now.strftime("%Y-%m-%d")
    start_date   = (datetime.strptime(end_date, "%Y-%m-%d")
                    - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    snapshot_date = end_date
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
    print(f"  BLUELOTUS MID — Capital Flow Fetcher {VERSION}")
    print(f"  {cycle_ts} SGT")
    print(f"  Mode: {'DRY RUN (no DB write)' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 62)

    # ── STEP 1: Fetch ─────────────────────────────────────────────────────────
    _section("STEP 1: Fetching capital flow from Moomoo OpenD")
    results = fetch_all_capital_flow(tickers, start_date, end_date)

    ok_count   = sum(1 for v in results.values() if "error" not in v)
    fail_count = sum(1 for v in results.values() if "error"     in v)

    print()
    _ok(f"Fetch complete: {ok_count} OK / {fail_count} failed / {len(results)} total")

    # ── STEP 2: Bias summary ──────────────────────────────────────────────────
    _section("STEP 2: Institutional Bias Summary")
    bias_counts = {}
    for ticker, data in results.items():
        if "error" not in data:
            b = data.get("institutional_bias", "NEUTRAL")
            bias_counts[b] = bias_counts.get(b, []) + [ticker]

    for bias, tks in sorted(bias_counts.items()):
        print(f"  {bias:<25} {len(tks):>3} tickers: {', '.join(tks[:8])}"
              + (" ..." if len(tks) > 8 else ""))

    # Top movers by net inflow
    print()
    _info("Top 10 by net in_flow (absolute):")
    movers = [(t, d.get("in_flow") or 0)
              for t, d in results.items() if "error" not in d]
    movers.sort(key=lambda x: abs(x[1]), reverse=True)
    for ticker, flow in movers[:10]:
        arrow = "▲" if flow > 0 else "▼"
        bias  = results[ticker].get("institutional_bias", "?")
        _info(f"  {ticker:<6} {arrow}${abs(flow)/1e6:>8.2f}M  [{bias}]")

    if args.dry_run:
        _section("DRY RUN — Skipping DB write and JSON output")
        print()
        print("  Run without --dry-run to write to DB and output JSON.")
        print()
        print("=" * 62)
        return

    # ── STEP 3: DB write ──────────────────────────────────────────────────────
    _section("STEP 3: Writing to ticker_capital_flow DB table")
    written, updated, db_failed = write_to_db(results, snapshot_date, cycle_ts)
    _ok(f"DB write: {written} new | {updated} updated | {db_failed} failed")

    # ── STEP 4: JSON output ───────────────────────────────────────────────────
    _section("STEP 4: Writing capital_flow.json")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path   = os.path.join(script_dir, "capital_flow.json")
    try:
        write_json(results, snapshot_date, cycle_ts, out_path)
        size_kb = round(os.path.getsize(out_path) / 1024, 1)
        _ok(f"Saved: {out_path}  ({size_kb} KB)")
    except Exception as e:
        _fail(f"JSON write failed: {e}")

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print(f"  COMPLETE — Capital Flow Fetcher {VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Tickers fetched : {len(results)}")
    print(f"  OK              : {ok_count}")
    print(f"  Failed          : {fail_count}")
    print(f"  DB written      : {written} new / {updated} updated")
    print(f"  JSON            : capital_flow.json")
    print()
    print("  NEXT STEP: Run export_dataset_raw.py to include capital_flow")
    print("             in dataset_raw.json for Frontend.")
    print("=" * 62)


if __name__ == "__main__":
    main()
