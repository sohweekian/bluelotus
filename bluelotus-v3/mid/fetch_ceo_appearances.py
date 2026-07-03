"""
BlueLotus Digital Institution — V2.0
mid/fetch_ceo_appearances.py

PURPOSE
-------
    Populates the ceo_appearance_tracker table with scheduled and confirmed
    executive public appearances. Implements Gap 2 of gap_report_20260602_230000.

    Gap 2 identified: Tier 1 and Tier 2 executives were tracked REACTIVELY
    via X_Signals (trust 0.40) — not proactively via a structured forward
    calendar. Jensen Huang's Marvell keynote on 2026-06-02 was announced on
    2026-05-26 but never surfaced as a CATALYST ALERT.

TWO DATA SOURCES
----------------
    1. CONFERENCE CALENDAR CROSS-REFERENCE (primary forward signal)
       Reads conference_calendar table — any conference with a known speaker
       in the EXECUTIVE_ROSTER generates a scheduled appearance row.
       is_confirmed = TRUE if speaker is in keynote_speakers JSON.
       is_confirmed = FALSE if speaker is inferred from conference slug only.

    2. RSS SIGNAL SCAN (secondary enrichment)
       Scans tech_publication_signals for executive name mentions within
       14 days of a known conference. Detects surprise appearances and
       off-conference media interviews.

ALERT FLAGS
-----------
    alert_72h_flag = TRUE if appearance_date within 72h of today
    alert_24h_flag = TRUE if appearance_date within 24h of today
    These flags drive the CATALYST ALERT logic in the analyst report.

EXECUTIVE ROSTER
----------------
    TIER 1 — Market-moving on any public statement:
        Jensen Huang (NVDA), Elon Musk (TSLA), Tim Cook (AAPL),
        Satya Nadella (MSFT), Andy Jassy (AMZN), Sundar Pichai (GOOGL),
        Sam Altman (OpenAI — no ticker)

    TIER 2 — Sector-specific market movers:
        Lisa Su (AMD), Pat Gelsinger (INTC), Cristiano Amon (QCOM),
        Jerome Powell (Fed — macro override), Scott Bessent (Treasury)

USAGE
-----
    cd C:\\bluelotus2
    python mid\\fetch_ceo_appearances.py

    Flags:
    --dry-run     Print what would be written, skip DB write
    --verify      After write, SELECT and print all upcoming appearances
    --days        Forward window in days to scan (default: 90)

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial — Gap 2 remediation, gap_report_20260602_230000

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
from datetime import datetime, date, timedelta
from pathlib import Path


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
# EXECUTIVE ROSTER
#
# Source of truth for Tier 1 and Tier 2 executives.
# Research Team maintained — add new executives here and re-run.
# ═══════════════════════════════════════════════════════════════════════════════

EXECUTIVE_ROSTER = [

    # ── TIER 1 — Market-moving on any public statement ─────────────────────────
    {
        "executive_name":  "Jensen Huang",
        "executive_slug":  "JENSEN_HUANG",
        "company":         "Nvidia",
        "ticker":          "NVDA",
        "tier":            1,
        "regex_pattern":   r"jensen\s+huang",
        "affected_tickers": ["NVDA", "MRVL", "AMD", "TSM", "AMAT", "QBTS", "QUBT", "IONQ"],
        "topics_expected": ["AI infrastructure", "Blackwell", "Rubin", "quantum", "Computex"],
        "notes": (
            "Single highest-impact executive for AI/semiconductor/quantum sector. "
            "Surprise appearances at partner keynotes (e.g. Marvell 2026-06-02) "
            "extend market rally by one additional session. "
            "Quantum comments are binary: positive or negative sector-wide."
        ),
    },
    {
        "executive_name":  "Elon Musk",
        "executive_slug":  "ELON_MUSK",
        "company":         "Tesla / xAI",
        "ticker":          "TSLA",
        "tier":            1,
        "regex_pattern":   r"elon\s+musk",
        "affected_tickers": ["TSLA", "NVDA", "COIN"],
        "topics_expected": ["AI", "robotics", "autonomous", "crypto", "xAI"],
        "notes":           "Moves Tesla, crypto sentiment, and broad risk appetite on any statement.",
    },
    {
        "executive_name":  "Tim Cook",
        "executive_slug":  "TIM_COOK",
        "company":         "Apple",
        "ticker":          "AAPL",
        "tier":            1,
        "regex_pattern":   r"tim\s+cook",
        "affected_tickers": ["AAPL", "MSFT", "GOOGL"],
        "topics_expected": ["Apple Intelligence", "Apple Silicon", "iOS", "WWDC"],
        "notes":           "WWDC keynote June 8 2026 — IMMINENT.",
    },
    {
        "executive_name":  "Satya Nadella",
        "executive_slug":  "SATYA_NADELLA",
        "company":         "Microsoft",
        "ticker":          "MSFT",
        "tier":            1,
        "regex_pattern":   r"satya\s+nadella",
        "affected_tickers": ["MSFT", "NVDA", "ORCL", "PLTR"],
        "topics_expected": ["Copilot", "Azure AI", "OpenAI partnership", "enterprise"],
        "notes":           "Microsoft Build annual keynote. Azure AI capex signal for NVDA.",
    },
    {
        "executive_name":  "Andy Jassy",
        "executive_slug":  "ANDY_JASSY",
        "company":         "Amazon",
        "ticker":          "AMZN",
        "tier":            1,
        "regex_pattern":   r"andy\s+jassy",
        "affected_tickers": ["AMZN", "NVDA", "MSFT", "GOOGL"],
        "topics_expected": ["AWS", "Trainium", "Inferentia", "cloud AI", "re:Invent"],
        "notes":           "AWS re:Invent December keynote. AI infrastructure capex = NVDA demand.",
    },
    {
        "executive_name":  "Sundar Pichai",
        "executive_slug":  "SUNDAR_PICHAI",
        "company":         "Alphabet",
        "ticker":          "GOOGL",
        "tier":            1,
        "regex_pattern":   r"sundar\s+pichai",
        "affected_tickers": ["GOOGL", "META", "MSFT"],
        "topics_expected": ["Gemini", "Google AI", "Search", "quantum", "Google I/O"],
        "notes":           "Google I/O annual keynote. Gemini model updates move GOOGL directly.",
    },
    {
        "executive_name":  "Sam Altman",
        "executive_slug":  "SAM_ALTMAN",
        "company":         "OpenAI",
        "ticker":          None,   # OpenAI not publicly traded
        "tier":            1,
        "regex_pattern":   r"sam\s+altman",
        "affected_tickers": ["MSFT", "NVDA", "GOOGL", "META"],
        "topics_expected": ["AGI", "GPT", "AI policy", "OpenAI funding", "o3"],
        "notes":           "No ticker but moves MSFT (OpenAI partner) and AI sector broadly.",
    },

    # ── TIER 2 — Sector-specific market movers ─────────────────────────────────
    {
        "executive_name":  "Lisa Su",
        "executive_slug":  "LISA_SU",
        "company":         "AMD",
        "ticker":          "AMD",
        "tier":            2,
        "regex_pattern":   r"lisa\s+su",
        "affected_tickers": ["AMD", "NVDA", "INTC"],
        "topics_expected": ["Instinct GPU", "EPYC", "MI300", "AI accelerator"],
        "notes":           "AMD GPU/AI chip competitive positioning vs NVDA.",
    },
    {
        "executive_name":  "Pat Gelsinger",
        "executive_slug":  "PAT_GELSINGER",
        "company":         "Intel",
        "ticker":          "INTC",
        "tier":            2,
        "regex_pattern":   r"pat\s+gelsinger",
        "affected_tickers": ["INTC", "AMD", "NVDA"],
        "topics_expected": ["Intel Foundry", "18A", "CHIPS Act", "process node"],
        "notes":           "Intel turnaround narrative. Foundry progress = sector confidence.",
    },
    {
        "executive_name":  "Cristiano Amon",
        "executive_slug":  "CRISTIANO_AMON",
        "company":         "Qualcomm",
        "ticker":          "QCOM",
        "tier":            2,
        "regex_pattern":   r"cristiano\s+amon",
        "affected_tickers": ["QCOM", "AAPL", "AMD"],
        "topics_expected": ["Snapdragon", "Windows on Arm", "edge AI", "mobile"],
        "notes":           "Qualcomm Snapdragon Summit October. Mobile/edge AI narrative.",
    },
    {
        "executive_name":  "Jerome Powell",
        "executive_slug":  "JEROME_POWELL",
        "company":         "Federal Reserve",
        "ticker":          None,
        "tier":            2,
        "regex_pattern":   r"jerome\s+powell|fed\s+chair|federal\s+reserve\s+chair",
        "affected_tickers": ["TLT", "BAC", "WFC", "C", "SOFI"],
        "topics_expected": ["interest rates", "FOMC", "inflation", "rate cuts", "dot plot"],
        "notes": (
            "MACRO OVERRIDE — overrides all sector signals when speaking. "
            "Press conference tone (hawkish/dovish) more impactful than rate decision. "
            "FOMC 8x per year — Research Team manually sets appearance_date from Fed calendar."
        ),
    },
    {
        "executive_name":  "Scott Bessent",
        "executive_slug":  "SCOTT_BESSENT",
        "company":         "US Treasury",
        "ticker":          None,
        "tier":            2,
        "regex_pattern":   r"scott\s+bessent",
        "affected_tickers": ["TLT", "GLD", "BAC", "WFC"],
        "topics_expected": ["tariffs", "dollar policy", "fiscal deficit", "Treasury"],
        "notes":           "Treasury Secretary. Tariff and dollar policy statements move macro.",
    },
]

# Build fast lookup: regex_pattern → executive entry
EXECUTIVE_MAP = {ev["regex_pattern"]: ev for ev in EXECUTIVE_ROSTER}


# ═══════════════════════════════════════════════════════════════════════════════
# CONFERENCE → DEFAULT APPEARANCE TYPE MAP
# ═══════════════════════════════════════════════════════════════════════════════

CONFERENCE_APPEARANCE_TYPE = {
    "COMPUTEX":              "KEYNOTE",
    "NVIDIA_GTC":            "KEYNOTE",
    "CES":                   "KEYNOTE",
    "APPLE_WWDC":            "KEYNOTE",
    "AWS_REINVENT":          "KEYNOTE",
    "GOOGLE_IO":             "KEYNOTE",
    "MICROSOFT_BUILD":       "KEYNOTE",
    "JPMORGAN_HEALTHCARE":   "INVESTOR_DAY",
    "GOLDMAN_FINANCIALS":    "INVESTOR_DAY",
    "QUALCOMM_SNAPDRAGON":   "KEYNOTE",
    "SALESFORCE_DREAMFORCE": "KEYNOTE",
}


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
# SOURCE 1: CONFERENCE CALENDAR CROSS-REFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

def appearances_from_conferences(cur, today: date, forward_days: int) -> list[dict]:
    """
    Read conference_calendar, find confirmed speakers, generate appearance rows.
    Only generates rows for conferences within forward_days window.
    """
    cutoff = today + timedelta(days=forward_days)
    cur.execute("""
        SELECT conference_slug, conference_name, keynote_date, event_date_start,
               keynote_speakers, impact_tier, catalyst_flag, days_until_event
        FROM conference_calendar
        WHERE event_date_start <= %s
          AND catalyst_flag != 'PAST'
        ORDER BY event_date_start ASC
    """, (cutoff,))
    conferences = cur.fetchall()

    appearances = []
    now = datetime.now()

    for conf in conferences:
        slug      = conf.get("conference_slug", "")
        conf_name = conf.get("conference_name", "")
        app_date  = conf.get("keynote_date") or conf.get("event_date_start")
        if not app_date:
            continue

        # Parse keynote_speakers JSON
        raw_speakers = conf.get("keynote_speakers") or "[]"
        if isinstance(raw_speakers, str):
            try:
                confirmed_speakers = json.loads(raw_speakers)
            except Exception:
                confirmed_speakers = []
        else:
            confirmed_speakers = raw_speakers

        # For each executive in roster, check if confirmed or inferred
        for exec_entry in EXECUTIVE_ROSTER:
            exec_name = exec_entry["executive_name"]
            is_confirmed = exec_name in confirmed_speakers

            # Skip unconfirmed appearances unless it's their own company's event
            own_company_event = (
                (exec_entry["ticker"] == "NVDA" and slug in ("COMPUTEX", "NVIDIA_GTC")) or
                (exec_entry["ticker"] == "AAPL" and slug == "APPLE_WWDC") or
                (exec_entry["ticker"] == "AMZN" and slug == "AWS_REINVENT") or
                (exec_entry["ticker"] == "GOOGL" and slug == "GOOGLE_IO") or
                (exec_entry["ticker"] == "MSFT" and slug == "MICROSOFT_BUILD") or
                (exec_entry["ticker"] == "QCOM" and slug == "QUALCOMM_SNAPDRAGON")
            )

            if not is_confirmed and not own_company_event:
                continue

            # Compute alert flags
            if isinstance(app_date, date):
                days_to = (app_date - today).days
            else:
                days_to = 999

            alert_72h = days_to <= 3 and days_to >= 0
            alert_24h = days_to <= 1 and days_to >= 0

            # Sentiment bias
            if exec_entry["tier"] == 1 and conf.get("impact_tier", 3) <= 2:
                sentiment_bias = "BULLISH"
            else:
                sentiment_bias = "UNKNOWN"

            appearances.append({
                "executive_name":   exec_name,
                "executive_slug":   exec_entry["executive_slug"],
                "company":          exec_entry["company"],
                "ticker":           exec_entry["ticker"],
                "tier":             exec_entry["tier"],
                "appearance_type":  CONFERENCE_APPEARANCE_TYPE.get(slug, "KEYNOTE"),
                "event_name":       f"{exec_name} at {conf_name}",
                "conference_slug":  slug,
                "appearance_date":  app_date,
                "appearance_time_utc": None,
                "is_scheduled":     True,
                "is_confirmed":     is_confirmed,
                "topics_expected":  exec_entry.get("topics_expected", []),
                "sentiment_bias":   sentiment_bias,
                "affected_tickers": exec_entry.get("affected_tickers", []),
                "alert_72h_flag":   alert_72h,
                "alert_24h_flag":   alert_24h,
                "source_url":       None,
                "source":           "Conference_Calendar",
                "fetched_at":       now,
                "snapshot_date":    today,
                "cycle_ts":         now,
            })

    return appearances


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2: RSS SIGNAL SCAN
# ═══════════════════════════════════════════════════════════════════════════════

def appearances_from_rss(cur, today: date, forward_days: int) -> list[dict]:
    """
    Scan tech_publication_signals for executive mentions near known conferences.
    Generates appearance rows for surprise/unconfirmed appearances detected via RSS.
    Only processes signals from last 30 days.
    """
    cur.execute("""
        SELECT headline, summary, article_url, published_at, source
        FROM tech_publication_signals
        WHERE snapshot_date >= %s
        ORDER BY published_at DESC
    """, (today - timedelta(days=30),))
    signals = cur.fetchall()

    appearances = []
    now = datetime.now()

    for sig in signals:
        text = f"{sig.get('headline','')} {sig.get('summary','') or ''}".lower()
        url  = sig.get("article_url", "")
        pub  = sig.get("published_at")

        for exec_entry in EXECUTIVE_ROSTER:
            pattern = exec_entry["regex_pattern"]
            if not re.search(pattern, text, re.IGNORECASE):
                continue

            # Determine conference context from text
            conf_slug = None
            for slug, keywords in {
                "COMPUTEX":       ["computex", "taipei"],
                "NVIDIA_GTC":     ["gtc", "gpu technology conference"],
                "APPLE_WWDC":     ["wwdc", "apple developer"],
                "AWS_REINVENT":   ["re:invent", "reinvent"],
                "GOOGLE_IO":      ["google i/o", "google io"],
                "MICROSOFT_BUILD":["microsoft build"],
            }.items():
                if any(kw in text for kw in keywords):
                    conf_slug = slug
                    break

            # Use published_at as approximate appearance date if known
            if pub and isinstance(pub, datetime):
                app_date = pub.date()
            elif pub and isinstance(pub, date):
                app_date = pub
            else:
                app_date = today

            days_to   = (app_date - today).days
            alert_72h = 0 <= days_to <= 3
            alert_24h = 0 <= days_to <= 1

            exec_name = exec_entry["executive_name"]

            appearances.append({
                "executive_name":   exec_name,
                "executive_slug":   exec_entry["executive_slug"],
                "company":          exec_entry["company"],
                "ticker":           exec_entry["ticker"],
                "tier":             exec_entry["tier"],
                "appearance_type":  "KEYNOTE" if conf_slug else "INTERVIEW",
                "event_name":       f"{exec_name} — {conf_slug or 'Media appearance'} (RSS detected)",
                "conference_slug":  conf_slug,
                "appearance_date":  app_date,
                "appearance_time_utc": None,
                "is_scheduled":     False,   # RSS-detected = not on forward calendar
                "is_confirmed":     True,    # Appeared in press = confirmed
                "topics_expected":  exec_entry.get("topics_expected", []),
                "sentiment_bias":   "UNKNOWN",
                "affected_tickers": exec_entry.get("affected_tickers", []),
                "alert_72h_flag":   alert_72h,
                "alert_24h_flag":   alert_24h,
                "source_url":       url,
                "source":           f"RSS_{sig.get('source','Unknown')}",
                "fetched_at":       now,
                "snapshot_date":    today,
                "cycle_ts":         now,
            })

    return appearances


# ═══════════════════════════════════════════════════════════════════════════════
# DB WRITER
# ═══════════════════════════════════════════════════════════════════════════════

def write_appearances(appearances: list[dict], dry_run: bool = False) -> tuple[int, int, int]:
    """
    Upsert appearances into ceo_appearance_tracker.
    UNIQUE KEY: (executive_slug, event_name[100], appearance_date)
    Returns (inserted, updated, failed).
    """
    if not appearances:
        _warn("No appearances to write.")
        return 0, 0, 0

    inserted = updated = failed = 0

    if not dry_run:
        conn = _get_conn()
        cur  = conn.cursor()

    sql = """
        INSERT INTO ceo_appearance_tracker (
            executive_name, executive_slug, company, ticker, tier,
            appearance_type, event_name, conference_slug,
            appearance_date, appearance_time_utc,
            is_scheduled, is_confirmed,
            topics_expected, sentiment_bias, affected_tickers,
            alert_72h_flag, alert_24h_flag,
            source_url, source, fetched_at, snapshot_date, cycle_ts
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            is_confirmed      = VALUES(is_confirmed),
            sentiment_bias    = VALUES(sentiment_bias),
            alert_72h_flag    = VALUES(alert_72h_flag),
            alert_24h_flag    = VALUES(alert_24h_flag),
            topics_expected   = VALUES(topics_expected),
            affected_tickers  = VALUES(affected_tickers),
            fetched_at        = VALUES(fetched_at),
            snapshot_date     = VALUES(snapshot_date),
            cycle_ts          = VALUES(cycle_ts)
    """

    for a in appearances:
        alert_flag = "⚡" if a["alert_24h_flag"] else ("🔔" if a["alert_72h_flag"] else " ")

        if dry_run:
            confirmed_str = "CONFIRMED" if a["is_confirmed"] else "inferred"
            print(f"\n  [DRY RUN] {alert_flag} {a['executive_name']:<20} "
                  f"T{a['tier']} | {a['appearance_date']} | "
                  f"{a['appearance_type']:<12} | {confirmed_str}")
            print(f"            event   : {a['event_name'][:60]}")
            print(f"            tickers : {a['affected_tickers']}")
            continue

        try:
            cur.execute(sql, (
                a["executive_name"],
                a["executive_slug"],
                a["company"],
                a["ticker"],
                a["tier"],
                a["appearance_type"],
                a["event_name"][:200],
                a["conference_slug"],
                a["appearance_date"],
                a["appearance_time_utc"],
                a["is_scheduled"],
                a["is_confirmed"],
                json.dumps(a["topics_expected"]),
                a["sentiment_bias"],
                json.dumps(a["affected_tickers"]),
                a["alert_72h_flag"],
                a["alert_24h_flag"],
                a["source_url"],
                a["source"],
                a["fetched_at"],
                a["snapshot_date"],
                a["cycle_ts"],
            ))
            label = "Inserted" if cur.rowcount == 1 else "Updated "
            _ok(f"{label}: {alert_flag} {a['executive_name']:<20} "
                f"{str(a['appearance_date']):<12} "
                f"{a['appearance_type']:<12} "
                f"{'CONFIRMED' if a['is_confirmed'] else 'inferred'}")
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            _fail(f"Failed: {a['executive_name']} {a['appearance_date']} — {e}")
            failed += 1

    if not dry_run:
        conn.commit()
        cur.close()
        conn.close()

    return inserted, updated, failed


def verify_appearances(cur) -> None:
    """Print all upcoming appearances ordered by date."""
    cur.execute("""
        SELECT executive_name, tier, appearance_date, appearance_type,
               is_confirmed, alert_72h_flag, conference_slug,
               ticker, source
        FROM ceo_appearance_tracker
        WHERE appearance_date >= CURDATE()
        ORDER BY alert_72h_flag DESC, appearance_date ASC
        LIMIT 30
    """)
    rows = cur.fetchall()
    print(f"\n  {'Executive':<22} T  {'Date':<12} {'Type':<14} {'Conf':<20} {'Status'}")
    print(f"  {'─'*22} ─  {'─'*12} {'─'*14} {'─'*20} {'─'*10}")
    for r in rows:
        if isinstance(r, dict):
            alert = "⚡" if r.get("alert_72h_flag") else " "
            conf  = str(r.get("conference_slug") or "—")[:18]
            status = "CONFIRMED" if r.get("is_confirmed") else "inferred"
            print(f"  {alert}{r.get('executive_name',''):<21} "
                  f"{r.get('tier','')}  "
                  f"{str(r.get('appearance_date','')):<12} "
                  f"{r.get('appearance_type',''):<14} "
                  f"{conf:<20} "
                  f"{status}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — CEO Appearance Tracker v1.0"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written, skip DB write")
    parser.add_argument("--verify",  action="store_true",
                        help="After write, SELECT and print all upcoming appearances")
    parser.add_argument("--days",    type=int, default=90,
                        help="Forward window in days (default: 90)")
    args = parser.parse_args()

    now   = datetime.now()
    today = now.date()

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    print()
    print("=" * 66)
    print(f"  BLUELOTUS MID — CEO Appearance Tracker v1.0")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Executives : {len(EXECUTIVE_ROSTER)} "
          f"(Tier1={sum(1 for e in EXECUTIVE_ROSTER if e['tier']==1)} "
          f"Tier2={sum(1 for e in EXECUTIVE_ROSTER if e['tier']==2)})")
    print(f"  Window     : {args.days} days forward")
    print(f"  Mode       : {'DRY RUN' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 66)

    conn = _get_conn()
    cur  = conn.cursor(dictionary=True)

    # ── Source 1: Conference calendar ─────────────────────────────────────────
    _section("STEP 1: Conference calendar cross-reference")
    conf_appearances = appearances_from_conferences(cur, today, args.days)
    _ok(f"Generated {len(conf_appearances)} appearances from conference_calendar")

    # ── Source 2: RSS scan ────────────────────────────────────────────────────
    _section("STEP 2: RSS signal scan")
    rss_appearances = appearances_from_rss(cur, today, args.days)
    _ok(f"Generated {len(rss_appearances)} appearances from RSS signals")

    cur.close()
    conn.close()

    # Combine — conference calendar first (higher trust), then RSS
    all_appearances = conf_appearances + rss_appearances
    _info(f"Total appearances to write: {len(all_appearances)}")

    # ── Write ─────────────────────────────────────────────────────────────────
    _section("STEP 3: Writing to ceo_appearance_tracker")
    inserted, updated, failed = write_appearances(all_appearances, dry_run=args.dry_run)

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify and not args.dry_run:
        _section("STEP 4: Verification — upcoming appearances")
        conn2 = _get_conn()
        cur2  = conn2.cursor(dictionary=True)
        verify_appearances(cur2)
        cur2.close()
        conn2.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — CEO Appearance Tracker v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    if not args.dry_run:
        print(f"  Inserted : {inserted}")
        print(f"  Updated  : {updated}")
        print(f"  Failed   : {failed}")
    print()
    print("  NEXT STEPS:")
    print("  1. python mid\\fetch_catalyst_calendar.py")
    print("  2. Update export_dataset_raw.py to v1.8")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
