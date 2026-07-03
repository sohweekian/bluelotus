"""
BlueLotus Digital Institution — V2.0
mid/fetch_ticker_earnings.py

PURPOSE
-------
    Fetches upcoming earnings dates and estimates for all 83 watchlist tickers
    from Finnhub's earnings calendar API and populates the ticker_earnings table.

    This fills the gap identified when ticker_earnings was found empty (0 rows)
    on 2026-06-03 — ingest.py creates the table but does not populate it.

API SOURCE (verified against Finnhub GitHub and production usage)
-----------------------------------------------------------------
    Endpoint : GET https://finnhub.io/api/v1/calendar/earnings
    Params   : from (YYYY-MM-DD), to (YYYY-MM-DD), symbol, token
    Docs     : https://finnhub.io/docs/api/earnings-calendar

    Confirmed response fields (from finnhubio/Finnhub-API GitHub issue #437):
    {
      "earningsCalendar": [
        {
          "date":            "2026-07-28",   -- announcement date
          "symbol":          "AAPL",
          "epsEstimate":      2.11,
          "epsActual":        null,          -- null if not yet reported
          "revenueEstimate":  117900000000,
          "revenueActual":    null,
          "hour":            "amc",          -- amc=after market close
                                             -- bmo=before market open
                                             -- dmh=during market hours
          "quarter":          2,             -- fiscal quarter number
          "year":             2026           -- fiscal year
        }
      ]
    }

STRATEGY
--------
    - One API call per ticker (83 calls total)
    - Forward window: today → today + 180 days (catches next 2 quarters)
    - Rate limit: 60 calls/minute on free tier — we pause 1.1s between calls
      (55 calls/minute, safely under limit)
    - ON DUPLICATE KEY UPDATE — idempotent, safe to re-run daily
    - ETF/commodity tickers skipped (no earnings)

DEPENDENCIES
------------
    pip install requests
    (requests is already installed from fetch_tech_publications.py)

ENVIRONMENT (.env)
------------------
    FINNHUB_API_KEY   (required — get free key at finnhub.io/register)
    MYSQL_HOST / DB_HOST etc. (same as all other fetchers)

USAGE
-----
    cd C:\\bluelotus2
    python mid\\fetch_ticker_earnings.py

    Flags:
    --dry-run     Fetch and print, skip DB write
    --tickers     Comma-separated subset: --tickers NVDA,AAPL,BAC
    --days        Forward window in days (default: 180)
    --verify      After write, print UPCOMING/IMMINENT rows

RUN SCHEDULE
------------
    Every pipeline cycle (hourly via run_v2_pipeline.bat).
    Daily runs ensure Finnhub preliminary-date corrections are picked up
    within hours instead of up to 7 days. ON DUPLICATE KEY UPDATE makes
    this safe — re-runs are idempotent.

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial — Gap 3 remediation, ticker_earnings population
                      Finnhub confirmed trustworthy: founded 2018, NYC,
                      ex-Bloomberg/Google/Tradeweb engineers, used by hedge
                      funds, mutual funds, S&P companies, and IBKR Campus.

AUTHOR
------
    BlueLotus MID Engineering (Claude)
    CIO: Kian Soh
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from ticker_universe import NO_EARNINGS_TICKERS as CENTRAL_NO_EARNINGS_TICKERS, get_universe


# ── Output helpers ─────────────────────────────────────────────────────────────
def _ok(msg):    print(f"  [OK]   {msg}")
def _fail(msg):  print(f"  [FAIL] {msg}")
def _warn(msg):  print(f"  [WARN] {msg}")
def _info(msg):  print(f"         {msg}")
def _section(t):
    print(f"\n{'─'*66}")
    print(f"  {t}")
    print(f"{'─'*66}")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

VERSION        = "v1.0"
FINNHUB_BASE   = "https://finnhub.io/api/v1"
CALL_PAUSE     = 1.1    # seconds between API calls (55/min, safely under 60/min limit)
DEFAULT_DAYS   = 180    # forward window: ~2 quarters

# Tickers with no earnings (ETFs, commodity funds)
# Finnhub returns empty for these — skip to save API calls
NO_EARNINGS_TICKERS = set(CENTRAL_NO_EARNINGS_TICKERS)

WATCHLIST_83 = get_universe()


# ═══════════════════════════════════════════════════════════════════════════════
# DB CONNECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _get_conn():
    import mysql.connector
    return mysql.connector.connect(
        host     = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST",     "127.0.0.1"),
        port     = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", 3306)),
        user     = os.getenv("MYSQL_USER") or os.getenv("DB_USER",     ""),
        password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", ""),
        database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "bluelotus2"),
        charset  = "utf8mb4",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FINNHUB EARNINGS FETCHER
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_earnings_for_ticker(
    ticker: str,
    api_key: str,
    date_from: str,
    date_to: str,
    session,
) -> dict | None:
    """
    Fetch upcoming earnings for a single ticker from Finnhub.
    Returns the most imminent upcoming record, or None if not found.

    Endpoint: GET /calendar/earnings?from=&to=&symbol=&token=
    Response field 'hour': bmo=before market open, amc=after market close,
                           dmh=during market hours
    """
    url = f"{FINNHUB_BASE}/calendar/earnings"
    params = {
        "from":   date_from,
        "to":     date_to,
        "symbol": ticker,
        "token":  api_key,
    }

    try:
        resp = session.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            _warn(f"{ticker}: rate limit hit — pausing 60s")
            time.sleep(60)
            resp = session.get(url, params=params, timeout=10)

        if resp.status_code != 200:
            _warn(f"{ticker}: HTTP {resp.status_code}")
            return None

        data = resp.json()
        calendar = data.get("earningsCalendar") or []

        if not calendar:
            return None

        # Filter to future dates only and sort ascending
        today_str = date_from
        upcoming = [
            r for r in calendar
            if r.get("date", "") >= today_str
        ]
        upcoming.sort(key=lambda r: r.get("date", ""))

        if not upcoming:
            return None

        # Return the next (most imminent) upcoming record
        return upcoming[0]

    except Exception as e:
        _warn(f"{ticker}: fetch error — {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ALERT FLAG
# ═══════════════════════════════════════════════════════════════════════════════

def compute_alert(earn_date: date, today: date) -> tuple[str, int]:
    """Returns (alert_flag, days_until)."""
    if earn_date < today:
        return "PAST", (today - earn_date).days * -1
    if earn_date == today:
        return "ACTIVE", 0
    days = (earn_date - today).days
    if days <= 3:
        return "IMMINENT", days
    if days <= 14:
        return "UPCOMING", days
    return "FUTURE", days


# ═══════════════════════════════════════════════════════════════════════════════
# DB WRITER
# ═══════════════════════════════════════════════════════════════════════════════

def write_to_db(records: list[dict], dry_run: bool = False) -> tuple[int, int, int]:
    """
    Upsert earnings records into ticker_earnings.
    UNIQUE KEY is on (ticker, next_earnings_date) — confirmed from DESCRIBE.
    Returns (inserted, updated, failed).
    """
    if not records:
        return 0, 0, 0

    inserted = updated = failed = 0

    if not dry_run:
        conn = _get_conn()
        cur  = conn.cursor()

    # ticker_earnings columns confirmed from DESCRIBE ticker_earnings (2026-06-03):
    # id, ticker, snapshot_date, cycle_ts, source,
    # next_earnings_date, days_to_earnings, earnings_quarter, earnings_time,
    # eps_estimate, eps_estimate_high, eps_estimate_low,
    # revenue_estimate, eps_actual_last, eps_surprise_pct,
    # revenue_actual_last, earnings_catalyst
    sql = """
        INSERT INTO ticker_earnings (
            ticker, snapshot_date, cycle_ts, source,
            next_earnings_date, days_to_earnings,
            earnings_quarter, earnings_time,
            eps_estimate, eps_estimate_high, eps_estimate_low,
            revenue_estimate,
            earnings_catalyst
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s,
            %s
        )
        ON DUPLICATE KEY UPDATE
            snapshot_date     = VALUES(snapshot_date),
            cycle_ts          = VALUES(cycle_ts),
            source            = VALUES(source),
            days_to_earnings  = VALUES(days_to_earnings),
            earnings_quarter  = VALUES(earnings_quarter),
            earnings_time     = VALUES(earnings_time),
            eps_estimate      = VALUES(eps_estimate),
            eps_estimate_high = VALUES(eps_estimate_high),
            eps_estimate_low  = VALUES(eps_estimate_low),
            revenue_estimate  = VALUES(revenue_estimate),
            earnings_catalyst = VALUES(earnings_catalyst)
    """

    now   = datetime.now()
    today = now.date()

    for r in records:
        earn_date = r["earn_date"]
        alert_flag, days_until = compute_alert(earn_date, today)

        # earnings_quarter: "Q2 2026" format
        quarter_str = f"Q{r['quarter']} {r['year']}" if r.get("quarter") and r.get("year") else None

        # earnings_time: map Finnhub codes to readable labels
        hour_map = {"bmo": "PRE", "amc": "POST", "dmh": "DURING"}
        time_str = hour_map.get(r.get("hour", ""), r.get("hour"))

        # EPS: Finnhub returns one estimate value (not high/low)
        # Store in both high and low for compatibility with ticker_earnings schema
        eps_est = r.get("epsEstimate")
        rev_est = r.get("revenueEstimate")

        if dry_run:
            port_flag = "📁" if r.get("in_portfolio") else "  "
            print(f"  [DRY RUN] {port_flag}{r['ticker']:<6} "
                  f"{earn_date}  [{alert_flag}]  days={days_until}  "
                  f"{quarter_str or '—'}  {time_str or '—'}  "
                  f"EPS={eps_est}  Rev={rev_est}")
            continue

        try:
            cur.execute(sql, (
                r["ticker"],
                today,
                now,
                "Finnhub_EarningsCalendar",
                earn_date,
                days_until,
                quarter_str,
                time_str,
                eps_est,   # eps_estimate (consensus)
                eps_est,   # eps_estimate_high (same — Finnhub gives one consensus value)
                eps_est,   # eps_estimate_low  (same)
                rev_est,   # revenue_estimate
                1,         # earnings_catalyst = TRUE (this IS an earnings event)
            ))
            if cur.rowcount == 1:
                inserted += 1
                label = "Inserted"
            else:
                updated += 1
                label = "Updated "
            _ok(f"{label}: {r['ticker']:<6} {earn_date}  [{alert_flag}]  "
                f"{quarter_str or '—'}  {time_str or '—'}  EPS={eps_est}")
        except Exception as e:
            _fail(f"DB write failed [{r['ticker']}]: {e}")
            failed += 1

    if not dry_run:
        conn.commit()
        cur.close()
        conn.close()

    return inserted, updated, failed


def verify_earnings(cur) -> None:
    """Print IMMINENT and UPCOMING earnings rows."""
    cur.execute("""
        SELECT ticker, next_earnings_date, days_to_earnings,
               earnings_quarter, earnings_time,
               eps_estimate_high, source
        FROM ticker_earnings
        WHERE next_earnings_date >= CURDATE()
        ORDER BY next_earnings_date ASC
        LIMIT 30
    """)
    rows = cur.fetchall()
    if not rows:
        _warn("No upcoming earnings found in ticker_earnings.")
        return
    print(f"\n  {'Ticker':<7} {'Date':<12} {'Days':>4} {'Quarter':<10} "
          f"{'Time':<6} {'EPS Est':>8}")
    print(f"  {'─'*7} {'─'*12} {'─'*4} {'─'*10} {'─'*6} {'─'*8}")
    for r in rows:
        if isinstance(r, dict):
            eps = f"${r['eps_estimate_high']:.2f}" if r.get("eps_estimate_high") else "—"
            print(f"  {r.get('ticker',''):<7} "
                  f"{str(r.get('next_earnings_date','')):<12} "
                  f"{str(r.get('days_to_earnings','')):<4} "
                  f"{r.get('earnings_quarter','') or '—':<10} "
                  f"{r.get('earnings_time','') or '—':<6} "
                  f"{eps:>8}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Ticker Earnings Fetcher v1.0 (Finnhub)"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Fetch and print, skip DB write")
    parser.add_argument("--tickers",  type=str, default=None,
                        help="Comma-separated subset: --tickers NVDA,AAPL,BAC")
    parser.add_argument("--days",     type=int, default=DEFAULT_DAYS,
                        help=f"Forward window in days (default: {DEFAULT_DAYS})")
    parser.add_argument("--verify",   action="store_true",
                        help="After write, print upcoming earnings rows")
    args = parser.parse_args()

    now   = datetime.now()
    today = now.date()

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    # ── API key ───────────────────────────────────────────────────────────────
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        print()
        print("  [FAIL] FINNHUB_API_KEY not set in .env")
        print("         Add this line to C:\\bluelotus2\\.env:")
        print("         FINNHUB_API_KEY=your_key_here")
        print("         Get a free key at: https://finnhub.io/register")
        sys.exit(1)

    # ── Ticker list ───────────────────────────────────────────────────────────
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        tickers = WATCHLIST_83

    # Filter out ETFs
    tickers_to_fetch = [t for t in tickers if t not in NO_EARNINGS_TICKERS]
    skipped          = [t for t in tickers if t in NO_EARNINGS_TICKERS]

    date_from = today.strftime("%Y-%m-%d")
    date_to   = (today + timedelta(days=args.days)).strftime("%Y-%m-%d")

    # Estimate time
    est_minutes = len(tickers_to_fetch) * CALL_PAUSE / 60

    print()
    print("=" * 66)
    print(f"  BLUELOTUS MID — Ticker Earnings Fetcher {VERSION}")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Source     : Finnhub /calendar/earnings")
    print(f"  Tickers    : {len(tickers_to_fetch)} (skipping {len(skipped)} ETFs)")
    print(f"  Window     : {date_from} → {date_to} ({args.days} days)")
    print(f"  Rate limit : {CALL_PAUSE}s pause between calls (~55/min, limit 60/min)")
    print(f"  Est. time  : ~{est_minutes:.1f} minutes")
    print(f"  Mode       : {'DRY RUN' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 66)

    if skipped:
        _info(f"Skipping ETFs: {', '.join(skipped)}")

    # ── Check dependency ──────────────────────────────────────────────────────
    _section("STEP 1: Checking dependencies")
    try:
        import requests
        _ok(f"requests {requests.__version__}")
    except ImportError:
        _fail("requests not installed. Run: pip install requests")
        sys.exit(1)

    # ── Fetch from Finnhub ────────────────────────────────────────────────────
    _section("STEP 2: Fetching earnings from Finnhub")

    import requests as req_lib
    session = req_lib.Session()
    session.headers.update({
        "User-Agent": "BlueLotus-MID/1.0",
        "Accept":     "application/json",
    })

    records    = []
    not_found  = []
    errors     = []
    total      = len(tickers_to_fetch)

    for i, ticker in enumerate(tickers_to_fetch):
        result = fetch_earnings_for_ticker(
            ticker, api_key, date_from, date_to, session
        )

        if result:
            # Parse the date string to a date object
            date_str = result.get("date", "")
            try:
                earn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                _warn(f"  [{i+1:02d}/{total}] {ticker:<6} bad date: {date_str}")
                errors.append(ticker)
                time.sleep(CALL_PAUSE)
                continue

            records.append({
                "ticker":          ticker,
                "earn_date":       earn_date,
                "epsEstimate":     result.get("epsEstimate"),
                "epsActual":       result.get("epsActual"),
                "revenueEstimate": result.get("revenueEstimate"),
                "revenueActual":   result.get("revenueActual"),
                "hour":            result.get("hour"),
                "quarter":         result.get("quarter"),
                "year":            result.get("year"),
            })

            days = (earn_date - today).days
            _ok(f"  [{i+1:02d}/{total}] {ticker:<6} "
                f"{earn_date}  days={days}  "
                f"Q{result.get('quarter','?')} {result.get('year','')}  "
                f"EPS={result.get('epsEstimate')}  "
                f"hour={result.get('hour','?')}")
        else:
            _info(f"  [{i+1:02d}/{total}] {ticker:<6} no upcoming earnings in window")
            not_found.append(ticker)

        time.sleep(CALL_PAUSE)

    session.close()

    # ── Summary of fetch ──────────────────────────────────────────────────────
    _section("STEP 3: Fetch summary")
    _ok(f"Records fetched  : {len(records)}")
    _info(f"Not found        : {len(not_found)} — {', '.join(not_found[:10])}{'...' if len(not_found)>10 else ''}")
    if errors:
        _warn(f"Errors           : {len(errors)} — {', '.join(errors)}")

    # Alert distribution
    imminent = sum(1 for r in records if (r["earn_date"] - today).days <= 3)
    upcoming = sum(1 for r in records if 3 < (r["earn_date"] - today).days <= 14)
    _info(f"IMMINENT (≤3d)   : {imminent}")
    _info(f"UPCOMING (≤14d)  : {upcoming}")

    # ── Write to DB ───────────────────────────────────────────────────────────
    _section("STEP 4: Writing to ticker_earnings")
    inserted, updated, failed = write_to_db(records, dry_run=args.dry_run)

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify and not args.dry_run:
        _section("STEP 5: Verification — upcoming earnings")
        conn = _get_conn()
        cur  = conn.cursor(dictionary=True)
        verify_earnings(cur)
        cur.close()
        conn.close()

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — Ticker Earnings Fetcher {VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Fetched  : {len(records)} tickers with upcoming earnings")
    if not args.dry_run:
        print(f"  Inserted : {inserted}")
        print(f"  Updated  : {updated}")
        print(f"  Failed   : {failed}")
    print()
    print("  NEXT STEPS:")
    print("  1. python mid\\fetch_catalyst_calendar.py --verify")
    print("     → Now reads from ticker_earnings to build catalyst rows")
    print("  2. python mid\\export_dataset_raw.py")
    print("     → Exports v1.8 dataset_raw.json with all gap data")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
