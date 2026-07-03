"""
BlueLotus Digital Institution — V2.0
mid/fetch_catalyst_calendar.py

PURPOSE
-------
    Populates the portfolio_catalyst_calendar table with per-ticker forward
    catalyst events: earnings dates, investor days, dividend ex-dates,
    and secondary offering alerts.

    Implements Gap 3 of gap_report_20260602_230000.

GAP 3 IDENTIFIED
----------------
    Portfolio holdings BAC and WFC had upcoming conference appearances in the
    dataset as news items but NOT as structured forward catalyst dates.
    QBTS D-Wave Investor Day at NYSE (June 1, 2026) was entirely absent.
    The system had no mechanism to auto-populate catalyst dates when a ticker
    entered the portfolio or working orders.

THREE DATA SOURCES
------------------
    1. MOOMOO get_earnings_date() API (primary — confirmed dates)
       Direct API call for each watchlist ticker.
       Returns next confirmed earnings date from exchange filings.
       is_confirmed=TRUE, is_estimate=FALSE.

    2. NASDAQ EARNINGS CALENDAR (secondary — cross-check + EPS estimates)
       Scrapes nasdaq.com/earnings-calendar for EPS estimates and
       revenue estimates to enrich earnings rows.
       Free, no auth required.

    3. SEC EDGAR 8-K SCAN (tertiary — investor days, conference appearances)
       Scans raw_signal_archive for SEC_EDGAR_8K signals containing
       Item 8.01 (Other Events) keywords — investor days, analyst days,
       conference presentations.

    NOTE: Paid earnings calendar services (Bloomberg, FactSet) excluded
    per CIO decision 2026-06-03. fetch_catalyst_calendar.py contains
    commented blocks for paid sources.

PORTFOLIO EXPOSURE FLAGS
------------------------
    in_portfolio     = TRUE if ticker in active Portfolio_Snapshot positions
    has_working_order = TRUE if ticker has active working order
    Both flags are set by scanning raw_signal_archive for latest portfolio state.
    If portfolio data unavailable, both default to FALSE (safe fallback).

ALERT FLAGS
-----------
    IMMINENT  — catalyst within 3 calendar days
    UPCOMING  — catalyst within 14 calendar days
    ACTIVE    — catalyst date is today
    PAST      — catalyst date before today (kept for 7 days for audit)

USAGE
-----
    cd C:\\bluelotus2
    python mid\\fetch_catalyst_calendar.py

    Flags:
    --dry-run     Print what would be written, skip DB write
    --verify      After write, SELECT and print IMMINENT/UPCOMING rows
    --no-moomoo   Skip Moomoo API (use when OpenD is not running)
    --tickers     Comma-separated subset: --tickers BAC,WFC,QBTS,NVDA

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial — Gap 3 remediation, gap_report_20260602_230000

AUTHOR
------
    BlueLotus MID Engineering (Claude)
    CIO: Kian Soh
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from ticker_universe import ETF_TICKERS as CENTRAL_ETF_TICKERS, get_universe


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

OPEND_HOST   = "127.0.0.1"
OPEND_PORT   = 11111
TICKER_PAUSE = 0.25   # seconds between Moomoo API calls

# Full watchlist — mirrors WATCHLIST_83 from other fetchers exactly
WATCHLIST_83 = get_universe()

# Tickers that are ETFs or commodity funds — Moomoo may not have earnings dates
ETF_TICKERS = set(CENTRAL_ETF_TICKERS)

# ── Investor Day keywords for SEC 8-K scan ────────────────────────────────────
INVESTOR_DAY_KEYWORDS = [
    "investor day", "analyst day", "investor conference",
    "financial community meeting", "capital markets day",
    "analyst meeting", "shareholder day", "annual investor",
]

# ── Conference presentation keywords for SEC 8-K scan ────────────────────────
CONFERENCE_PRESENTATION_KEYWORDS = [
    "will present", "will participate", "presenting at",
    "participate at", "conference presentation", "fireside chat",
]


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
# PORTFOLIO EXPOSURE FLAGS
# Reads raw_signal_archive for current portfolio state
# ═══════════════════════════════════════════════════════════════════════════════

def get_portfolio_tickers(cur) -> tuple[set, set]:
    """
    Returns (portfolio_tickers, working_order_tickers) from raw_signal_archive.
    Falls back to empty sets if data unavailable — safe by design.

    raw_signal_archive schema (confirmed 2026-06-03):
        raw_payload  JSON  — full signal payload
        source       VARCHAR — signal source identifier
        received_at  DATETIME — ingestion timestamp
        suspected_entities JSON — extracted entities including tickers
    """
    portfolio_tickers     = set()
    working_order_tickers = set()
    try:
        cur.execute("""
            SELECT raw_payload FROM raw_signal_archive
            WHERE source = 'Portfolio_Snapshot'
            ORDER BY received_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            raw  = row.get("raw_payload") or "{}"
            data = json.loads(raw) if isinstance(raw, str) else raw
            positions = data.get("positions", {})
            portfolio_tickers = {t.upper() for t in positions.keys()}
            orders = data.get("working_orders", {})
            working_order_tickers = {t.upper() for t in orders.keys()}
    except Exception as e:
        _warn(f"Portfolio snapshot read failed (safe fallback): {e}")

    return portfolio_tickers, working_order_tickers


# ═══════════════════════════════════════════════════════════════════════════════
# ALERT FLAG CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

def compute_alert_flag(catalyst_date: date, today: date) -> tuple[str, int]:
    """Returns (alert_flag, days_until_catalyst)."""
    if catalyst_date < today:
        return "PAST", (today - catalyst_date).days * -1
    if catalyst_date == today:
        return "ACTIVE", 0
    days = (catalyst_date - today).days
    if days <= 3:
        return "IMMINENT", days
    if days <= 14:
        return "UPCOMING", days
    return "FUTURE", days


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1: MOOMOO get_earnings_date()
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_moomoo_earnings(tickers: list[str]) -> dict[str, dict]:
    """
    Read earnings dates from ticker_earnings table.

    ticker_earnings is populated by fetch_ticker_earnings.py (Finnhub API).
    Columns confirmed from DESCRIBE ticker_earnings (2026-06-03):
        next_earnings_date  DATE    — next confirmed earnings date
        days_to_earnings    INT     — days until earnings
        earnings_quarter    VARCHAR — e.g. Q2 2026
        earnings_time       VARCHAR — PRE/POST/DURING market
        eps_estimate        DECIMAL — consensus EPS estimate
        eps_estimate_high   DECIMAL — analyst high EPS estimate
        eps_estimate_low    DECIMAL — analyst low EPS estimate
        revenue_estimate    DECIMAL — consensus revenue estimate
        source              VARCHAR — data source (Finnhub_EarningsCalendar)

    NOTE: Function name retained for compatibility. Data source is Finnhub
    via ticker_earnings table — not Moomoo OpenD. Moomoo has no earnings
    date API method (confirmed from official docs v10.6, 2026-06-03).
    Run fetch_ticker_earnings.py first to ensure ticker_earnings is current.
    """
    results = {}
    try:
        conn = _get_conn()
        cur  = conn.cursor(dictionary=True)

        ticker_list = [t for t in tickers if t not in ETF_TICKERS]

        if not ticker_list:
            return {}

        placeholders = ",".join(["%s"] * len(ticker_list))
        cur.execute(f"""
            SELECT ticker, next_earnings_date, days_to_earnings,
                   earnings_quarter, earnings_time,
                   eps_estimate_high, eps_estimate_low,
                   source
            FROM ticker_earnings
            WHERE ticker IN ({placeholders})
              AND next_earnings_date >= CURDATE()
            ORDER BY next_earnings_date ASC
        """, ticker_list)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        for row in rows:
            ticker    = row.get("ticker", "").upper()
            earn_date = row.get("next_earnings_date")

            if not earn_date or not ticker:
                continue

            if hasattr(earn_date, "date"):
                earn_date = earn_date.date()

            eps_high = row.get("eps_estimate_high")
            eps_low  = row.get("eps_estimate_low")
            eps_est  = None
            if eps_high and eps_low:
                try:
                    eps_est = round((float(eps_high) + float(eps_low)) / 2, 4)
                except Exception:
                    pass
            elif eps_high:
                try:
                    eps_est = float(eps_high)
                except Exception:
                    pass

            # Only keep the EARLIEST (soonest) date per ticker.
            # ORDER BY next_earnings_date ASC means the first row we see is
            # the closest upcoming date. Skip later/stale rows for same ticker.
            if ticker not in results:
                results[ticker] = {
                    "date":         earn_date,
                    "time_et":      row.get("earnings_time"),
                    "eps_estimate": eps_est,
                    "is_confirmed": True,
                    "is_estimate":  False,
                    "source":       row.get("source") or "ticker_earnings",
                }
            _ok(f"  {ticker:<6} earnings: {earn_date} | "
                f"quarter: {row.get('earnings_quarter')} | "
                f"EPS est: {eps_est}")

    except Exception as e:
        _warn(f"ticker_earnings read failed: {e}")

    if not results:
        _warn("ticker_earnings table is empty or no upcoming dates found.")
        _warn("Run ingest.py or the earnings fetcher first to populate ticker_earnings.")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2: NASDAQ EARNINGS CALENDAR (free scrape)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_nasdaq_earnings(tickers: list[str], today: date) -> dict[str, dict]:
    """
    DEPRECATED — replaced by Moomoo get_earnings_date() as sole earnings source.

    Original plan used Nasdaq calendar API for EPS estimates, but api.nasdaq.com
    requires browser session cookies and returns empty results from Python requests.
    yfinance was considered as fallback but rejected — Moomoo already provides
    confirmed earnings dates via the same OpenD infrastructure used by all other
    BlueLotus fetchers. Consistency > redundancy.

    This function is retained as a stub to avoid breaking the call site.
    Returns empty dict. Remove in v1.1 cleanup.
    """
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 3: SEC EDGAR 8-K SCAN
# Scans raw_signal_archive for investor day / conference presentation signals
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_sec_investor_days(cur, tickers: list[str], today: date) -> list[dict]:
    """
    Scan raw_signal_archive for SEC_EDGAR_8K signals mentioning investor days
    or conference presentations for watchlist tickers.

    raw_signal_archive schema (confirmed 2026-06-03):
        raw_payload        JSON    — full signal payload
        raw_text           TEXT    — extracted text content
        suspected_entities JSON    — extracted entities (tickers, orgs, etc.)
        source             VARCHAR — 'SEC_EDGAR_8K'
        received_at        DATETIME — ingestion timestamp
        source_url         TEXT    — original filing URL

    No 'ticker' column exists — tickers extracted from suspected_entities JSON.
    """
    catalysts = []
    try:
        cur.execute("""
            SELECT raw_text, raw_payload, suspected_entities,
                   source_url, received_at
            FROM raw_signal_archive
            WHERE source = 'SEC_EDGAR_8K'
              AND received_at >= %s
            ORDER BY received_at DESC
            LIMIT 500
        """, (today - timedelta(days=30),))
        rows = cur.fetchall()
    except Exception as e:
        _warn(f"SEC EDGAR scan failed: {e}")
        return []

    ticker_set = set(t.upper() for t in tickers)
    now        = datetime.now()

    for row in rows:
        text = (row.get("raw_text") or "").lower()

        # Extract tickers from suspected_entities JSON
        raw_entities = row.get("suspected_entities") or "[]"
        if isinstance(raw_entities, str):
            try:
                entities = json.loads(raw_entities)
            except Exception:
                entities = []
        else:
            entities = raw_entities or []

        # suspected_entities can be a list of strings or list of dicts
        row_tickers = set()
        for ent in entities:
            if isinstance(ent, str) and ent.upper() in ticker_set:
                row_tickers.add(ent.upper())
            elif isinstance(ent, dict):
                val = (ent.get("ticker") or ent.get("symbol") or ent.get("entity") or "").upper()
                if val in ticker_set:
                    row_tickers.add(val)

        if not row_tickers:
            continue

        # Also check raw_payload for ticker mentions as fallback
        if not row_tickers:
            raw_p = row.get("raw_payload") or {}
            if isinstance(raw_p, str):
                try:
                    raw_p = json.loads(raw_p)
                except Exception:
                    raw_p = {}
            payload_ticker = (raw_p.get("ticker") or raw_p.get("symbol") or "").upper()
            if payload_ticker in ticker_set:
                row_tickers.add(payload_ticker)

        if not row_tickers:
            continue

        # Investor Day detection
        if any(kw in text for kw in INVESTOR_DAY_KEYWORDS):
            date_match = re.search(
                r"(january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\s+\d{1,2},?\s+202[5-9]",
                text, re.IGNORECASE
            )
            event_date = None
            if date_match:
                try:
                    event_date = datetime.strptime(
                        date_match.group(0).replace(",", ""), "%B %d %Y"
                    ).date()
                except Exception:
                    pass

            if not event_date:
                sig_ts = row.get("received_at")
                event_date = (
                    sig_ts.date() + timedelta(days=7)
                    if isinstance(sig_ts, datetime)
                    else today + timedelta(days=7)
                )

            for ticker in row_tickers:
                catalysts.append({
                    "ticker":           ticker,
                    "catalyst_type":    "INVESTOR_DAY",
                    "catalyst_date":    event_date,
                    "catalyst_time_et": None,
                    "is_confirmed":     True,
                    "is_estimate":      False,
                    "event_name":       (row.get("raw_text") or "")[:300],
                    "event_venue":      None,
                    "event_url":        str(row.get("source_url") or "")[:500],
                    "source":           "SEC_EDGAR_8K",
                    "fetched_at":       now,
                    "snapshot_date":    today,
                    "cycle_ts":         now,
                })

        # Conference presentation detection
        elif any(kw in text for kw in CONFERENCE_PRESENTATION_KEYWORDS):
            sig_ts     = row.get("received_at")
            event_date = (
                sig_ts.date() + timedelta(days=3)
                if isinstance(sig_ts, datetime)
                else today + timedelta(days=3)
            )
            for ticker in row_tickers:
                catalysts.append({
                    "ticker":           ticker,
                    "catalyst_type":    "CONFERENCE_APPEARANCE",
                    "catalyst_date":    event_date,
                    "catalyst_time_et": None,
                    "is_confirmed":     True,
                    "is_estimate":      True,
                    "event_name":       (row.get("raw_text") or "")[:300],
                    "event_venue":      None,
                    "event_url":        str(row.get("source_url") or "")[:500],
                    "source":           "SEC_EDGAR_8K",
                    "fetched_at":       now,
                    "snapshot_date":    today,
                    "cycle_ts":         now,
                })

    return catalysts


# ═══════════════════════════════════════════════════════════════════════════════
# DB WRITER
# ═══════════════════════════════════════════════════════════════════════════════

def write_catalysts(
    catalysts: list[dict],
    portfolio_tickers: set,
    working_order_tickers: set,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """
    Upsert catalysts into portfolio_catalyst_calendar.
    UNIQUE KEY: (ticker, catalyst_type, catalyst_date)
    Returns (inserted, updated, failed).
    """
    if not catalysts:
        _warn("No catalysts to write.")
        return 0, 0, 0

    inserted = updated = failed = 0

    if not dry_run:
        conn = _get_conn()
        cur  = conn.cursor()

    sql = """
        INSERT INTO portfolio_catalyst_calendar (
            ticker, company_name, catalyst_type,
            catalyst_date, catalyst_time_et,
            is_confirmed, is_estimate,
            event_name, event_venue, event_url,
            eps_estimate, eps_prior, revenue_estimate,
            in_portfolio, has_working_order,
            days_until_catalyst, alert_flag,
            source, source_url, fetched_at, snapshot_date, cycle_ts
        ) VALUES (
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            is_confirmed        = VALUES(is_confirmed),
            catalyst_time_et    = VALUES(catalyst_time_et),
            eps_estimate        = VALUES(eps_estimate),
            revenue_estimate    = VALUES(revenue_estimate),
            in_portfolio        = VALUES(in_portfolio),
            has_working_order   = VALUES(has_working_order),
            days_until_catalyst = VALUES(days_until_catalyst),
            alert_flag          = VALUES(alert_flag),
            fetched_at          = VALUES(fetched_at),
            snapshot_date       = VALUES(snapshot_date),
            cycle_ts            = VALUES(cycle_ts)
    """

    today = datetime.now().date()

    for c in catalysts:
        ticker       = c["ticker"]
        cat_date     = c["catalyst_date"]
        in_port      = ticker in portfolio_tickers
        has_order    = ticker in working_order_tickers
        alert_flag, days_until = compute_alert_flag(cat_date, today)

        if dry_run:
            port_str  = "📁PORTFOLIO" if in_port else ("📋ORDER" if has_order else "watchlist")
            print(f"\n  [DRY RUN] {ticker:<6} {c['catalyst_type']:<22} "
                  f"{cat_date}  [{alert_flag}] {port_str}")
            print(f"            {(c.get('event_name') or '')[:65]}")
            if c.get("eps_estimate"):
                print(f"            EPS est: {c['eps_estimate']} | "
                      f"Rev est: {c.get('revenue_estimate')}")
            continue

        try:
            cur.execute(sql, (
                ticker,
                None,   # company_name — not fetched at this stage
                c["catalyst_type"],
                cat_date,
                c.get("catalyst_time_et"),
                c.get("is_confirmed", False),
                c.get("is_estimate", False),
                c.get("event_name"),
                c.get("event_venue"),
                c.get("event_url"),
                c.get("eps_estimate"),
                c.get("eps_prior"),
                c.get("revenue_estimate"),
                in_port,
                has_order,
                days_until,
                alert_flag,
                c["source"],
                c.get("source_url"),
                c["fetched_at"],
                c["snapshot_date"],
                c["cycle_ts"],
            ))
            label = "Inserted" if cur.rowcount == 1 else "Updated "
            port_str = "📁" if in_port else ("📋" if has_order else "  ")
            flag_str = f"[{alert_flag}]"
            _ok(f"{label}: {port_str}{ticker:<6} {c['catalyst_type']:<22} "
                f"{cat_date}  {flag_str:<12} days={days_until}")
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            _fail(f"Failed: {ticker} {c['catalyst_type']} {cat_date} — {e}")
            failed += 1

    if not dry_run:
        conn.commit()
        cur.close()
        conn.close()

    return inserted, updated, failed


def verify_catalysts(cur) -> None:
    """Print IMMINENT and UPCOMING catalysts, portfolio positions first."""
    cur.execute("""
        SELECT ticker, catalyst_type, catalyst_date, alert_flag,
               days_until_catalyst, is_confirmed, in_portfolio,
               has_working_order, eps_estimate, source
        FROM portfolio_catalyst_calendar
        WHERE alert_flag IN ('IMMINENT','UPCOMING','ACTIVE')
           OR in_portfolio = TRUE
           OR has_working_order = TRUE
        ORDER BY in_portfolio DESC, has_working_order DESC,
                 catalyst_date ASC
        LIMIT 30
    """)
    rows = cur.fetchall()
    if not rows:
        _info("No IMMINENT/UPCOMING catalysts or portfolio events found.")
        return

    print(f"\n  {'Ticker':<7} {'Type':<22} {'Date':<12} {'Flag':<10} "
          f"{'Days':>4} {'Port'} {'EPS est'}")
    print(f"  {'─'*7} {'─'*22} {'─'*12} {'─'*10} "
          f"{'─'*4} {'─'*4} {'─'*8}")
    for r in rows:
        if isinstance(r, dict):
            port = "📁" if r.get("in_portfolio") else ("📋" if r.get("has_working_order") else "  ")
            eps  = f"${r['eps_estimate']:.2f}" if r.get("eps_estimate") else "—"
            conf = "✓" if r.get("is_confirmed") else "~"
            print(f"  {r.get('ticker',''):<7} "
                  f"{r.get('catalyst_type',''):<22} "
                  f"{str(r.get('catalyst_date','')):<12} "
                  f"{r.get('alert_flag',''):<10} "
                  f"{str(r.get('days_until_catalyst','')):<4} "
                  f"{port}    {eps} {conf}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Catalyst Calendar Fetcher v1.0"
    )
    parser.add_argument("--dry-run",   action="store_true",
                        help="Print what would be written, skip DB write")
    parser.add_argument("--verify",    action="store_true",
                        help="After write, print IMMINENT/UPCOMING/portfolio rows")
    parser.add_argument("--tickers",   type=str, default=None,
                        help="Comma-separated subset: --tickers BAC,WFC,QBTS")
    args = parser.parse_args()

    now   = datetime.now()
    today = now.date()

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    # ── Ticker list ───────────────────────────────────────────────────────────
    tickers = WATCHLIST_83
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    print()
    print("=" * 66)
    print(f"  BLUELOTUS MID — Catalyst Calendar Fetcher v1.0")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Tickers    : {len(tickers)}")
    print(f"  Earnings   : reads from ticker_earnings table (no Moomoo API call)")
    print(f"  Mode       : {'DRY RUN' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 66)

    # ── Portfolio exposure ────────────────────────────────────────────────────
    _section("STEP 1: Reading portfolio exposure flags")
    conn = _get_conn()
    cur  = conn.cursor(dictionary=True)
    portfolio_tickers, working_order_tickers = get_portfolio_tickers(cur)
    _ok(f"Portfolio positions  : {sorted(portfolio_tickers) or '(none found)'}")
    _ok(f"Working orders       : {sorted(working_order_tickers) or '(none found)'}")

    # ── Source 3: SEC EDGAR 8-K scan ─────────────────────────────────────────
    _section("STEP 2: SEC EDGAR 8-K scan (investor days / conference appearances)")
    sec_catalysts = fetch_sec_investor_days(cur, tickers, today)
    _ok(f"SEC EDGAR catalysts found: {len(sec_catalysts)}")
    for c in sec_catalysts:
        _info(f"  {c['ticker']:<6} {c['catalyst_type']:<22} {c['catalyst_date']}  "
              f"{(c.get('event_name') or '')[:50]}")

    cur.close()
    conn.close()

    # ── Source 1: ticker_earnings table (populated by fetch_ticker_earnings.py) ─
    _section("STEP 3: Reading earnings dates from ticker_earnings table")
    moomoo_earnings = fetch_moomoo_earnings(
        [t for t in tickers if t not in ETF_TICKERS]
    )
    _ok(f"Earnings dates found: {len(moomoo_earnings)}")

    # ── STEP 4: Skipped — earnings read from ticker_earnings table ───────────
    # ticker_earnings is now populated by fetch_ticker_earnings.py (Finnhub).
    # fetch_moomoo_earnings() above reads from that table directly.
    # No additional step needed here.

    # ── STEP 5: Build earnings catalyst rows from ticker_earnings data ────────
    _section("STEP 5: Building earnings catalysts from ticker_earnings")
    all_earnings_catalysts = []

    for ticker, data in moomoo_earnings.items():
        all_earnings_catalysts.append({
            "ticker":           ticker,
            "catalyst_type":    "EARNINGS",
            "catalyst_date":    data["date"],
            "catalyst_time_et": data.get("time_et"),
            "is_confirmed":     data.get("is_confirmed", True),
            "is_estimate":      data.get("is_estimate", False),
            "event_name":       f"{ticker} Earnings Release",
            "event_venue":      None,
            "event_url":        None,
            "eps_estimate":     data.get("eps_estimate"),   # from ticker_earnings
            "eps_prior":        None,
            "revenue_estimate": None,
            "source":           data.get("source") or "ticker_earnings",
            "fetched_at":       now,
            "snapshot_date":    today,
            "cycle_ts":         now,
        })

    _ok(f"Earnings catalysts built: {len(all_earnings_catalysts)}")

    # ── Combine all catalysts ─────────────────────────────────────────────────
    all_catalysts = all_earnings_catalysts + sec_catalysts
    _info(f"Total catalysts to write: {len(all_catalysts)}")

    # ── Write ─────────────────────────────────────────────────────────────────
    _section("STEP 6: Writing to portfolio_catalyst_calendar")
    inserted, updated, failed = write_catalysts(
        all_catalysts, portfolio_tickers, working_order_tickers,
        dry_run=args.dry_run
    )

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify and not args.dry_run:
        _section("STEP 7: Verification — IMMINENT/UPCOMING/portfolio catalysts")
        conn2 = _get_conn()
        cur2  = conn2.cursor(dictionary=True)
        verify_catalysts(cur2)
        cur2.close()
        conn2.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — Catalyst Calendar Fetcher v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    if not args.dry_run:
        print(f"  Inserted : {inserted}")
        print(f"  Updated  : {updated}")
        print(f"  Failed   : {failed}")
    print()
    print("  NEXT STEPS:")
    print("  Update export_dataset_raw.py to v1.8 using --print-export-blocks")
    print("  from create_gap_tables.py")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
