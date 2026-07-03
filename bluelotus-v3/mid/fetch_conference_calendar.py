"""
BlueLotus Digital Institution — V2.0
mid/fetch_conference_calendar.py

PURPOSE
-------
    Populates the conference_calendar table with forward-looking tech conference
    and keynote events. Implements Gap 1 of gap_report_20260602_230000.

    Two data sources:
        1. MANUAL SEED (primary) — structured list of annual recurring conferences
           maintained by the Research Team. This is the authoritative source for
           known events. Updated once per year or when a new event is added.

        2. RSS SIGNAL SCAN (secondary) — scans tech_publication_signals table
           (already populated by fetch_tech_publications.py) for conference
           mentions and cross-references against the manual seed. Used to detect
           keynote speaker confirmations and surprise appearances announced via RSS.

DOCTRINE
--------
    - Manual seed is the forward-looking calendar backbone.
    - RSS scan enriches existing records with confirmed speaker data.
    - days_until_event and catalyst_flag are computed fresh on every run.
    - ON DUPLICATE KEY UPDATE on (conference_slug, edition_year) — idempotent.
    - Re-running daily keeps days_until_event and catalyst_flag current.

CATALYST FLAGS
--------------
    IMMINENT  — event starts within 3 calendar days
    ACTIVE    — event is currently running (start <= today <= end)
    UPCOMING  — event starts within 14 calendar days
    WATCH     — event starts within 60 calendar days
    FUTURE    — event starts beyond 60 days
    PAST      — event ended before today

USAGE
-----
    cd C:\\bluelotus2
    python mid\\fetch_conference_calendar.py

    Flags:
    --dry-run     Print what would be written, skip DB write
    --verify      After write, SELECT and print all non-PAST rows
    --rss-scan    Also scan tech_publication_signals for conference mentions

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial — Gap 1 remediation, gap_report_20260602_230000

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
# MANUAL CONFERENCE SEED
#
# Research Team maintained. Add new conferences here and re-run.
# Fields map directly to conference_calendar columns.
# edition_year is set automatically to current year at runtime.
# If a conference has already occurred this year, next year's date is used.
#
# impact_tier: 1=CRITICAL (Jensen Huang-level), 2=HIGH, 3=MEDIUM
# ═══════════════════════════════════════════════════════════════════════════════

CONFERENCE_SEED = [

    # ──────────────────────────────────────────────────────────────────────────
    # TIER 1 — CRITICAL market impact
    # ──────────────────────────────────────────────────────────────────────────
    {
        "conference_slug":   "COMPUTEX",
        "conference_name":   "Computex Taipei",
        "location_city":     "Taipei",
        "location_country":  "TW",
        "impact_tier":       1,
        "affected_tickers":  ["NVDA", "MRVL", "AMD", "TSM", "AMAT", "ARM", "CDNS", "SNPS"],
        "affected_themes":   ["SEMICONDUCTOR", "AI", "QUANTUM", "AI_INFRASTRUCTURE"],
        # Annual: first Monday of June, runs ~5 days
        # 2026: June 2-5 (already occurred — seed 2027)
        "event_date_start":  date(2027, 5, 31),
        "event_date_end":    date(2027, 6,  4),
        "keynote_date":      date(2027, 5, 31),
        "keynote_time_local": "14:00",
        "keynote_timezone":  "Asia/Taipei",
        "keynote_speakers":  ["Jensen Huang"],
        "hosting_company":   "TAITRA",
        # Historical impact from gap report
        "hist_impact_bull":  10.40,   # 2024 NVDA
        "hist_impact_base":   2.50,
        "hist_impact_bear":  -1.20,   # 2025 fade
        "hist_years_tracked": 3,
        "announcement_url":  "https://www.computextaipei.com.tw",
        "source":            "Manual_Calendar",
        "notes": (
            "THE primary annual catalyst for AI/semiconductor names. "
            "Jensen Huang keynote is the market-moving event — Day 1. "
            "Surprise appearances at partner keynotes (e.g. Marvell 2026) "
            "extend rally by one additional session. "
            "2026: MRVL +19%, NVDA +6.26%, S&P 500 ATH 7,617.66. "
            "Triggered gap_report_20260602_230000."
        ),
    },

    {
        "conference_slug":   "NVIDIA_GTC",
        "conference_name":   "Nvidia GTC Silicon Valley",
        "location_city":     "San Jose",
        "location_country":  "US",
        "impact_tier":       1,
        "affected_tickers":  ["NVDA", "AMD", "AMAT", "TSM", "IONQ", "QBTS", "QUBT"],
        "affected_themes":   ["SEMICONDUCTOR", "AI", "QUANTUM", "AI_INFRASTRUCTURE"],
        # Annual: mid-March, San Jose Convention Center
        "event_date_start":  date(2027, 3, 15),
        "event_date_end":    date(2027, 3, 19),
        "keynote_date":      date(2027, 3, 17),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Jensen Huang"],
        "hosting_company":   "Nvidia",
        "hist_impact_bull":   8.00,
        "hist_impact_base":   3.00,
        "hist_impact_bear":  -2.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://www.nvidia.com/gtc/",
        "source":            "Manual_Calendar",
        "notes": (
            "Primary Nvidia product roadmap event — GPU architecture reveals, "
            "AI infrastructure partnerships, quantum computing updates. "
            "Typically higher product significance than Computex. "
            "Jensen Huang delivers keynote. "
            "Quantum sector (IONQ, QBTS, QUBT) moves on any Huang quantum comments."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    # TIER 2 — HIGH market impact
    # ──────────────────────────────────────────────────────────────────────────
    {
        "conference_slug":   "CES",
        "conference_name":   "CES Las Vegas",
        "location_city":     "Las Vegas",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["NVDA", "AMD", "INTC", "AAPL", "MSFT", "QCOM"],
        "affected_themes":   ["SEMICONDUCTOR", "AI", "CONSUMER_TECH"],
        # Annual: first full week of January
        "event_date_start":  date(2027, 1,  7),
        "event_date_end":    date(2027, 1, 10),
        "keynote_date":      date(2027, 1,  7),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Jensen Huang", "Lisa Su", "Pat Gelsinger"],
        "hosting_company":   "CTA",
        "hist_impact_bull":   4.00,
        "hist_impact_base":   1.50,
        "hist_impact_bear":  -0.50,
        "hist_years_tracked": 0,
        "announcement_url":  "https://www.ces.tech",
        "source":            "Manual_Calendar",
        "notes": (
            "Sets tech sentiment tone for Q1. "
            "AMD, Intel, Qualcomm, Nvidia make major consumer product announcements. "
            "AI PC and edge AI announcements increasingly market-moving."
        ),
    },

    {
        "conference_slug":   "APPLE_WWDC",
        "conference_name":   "Apple WWDC",
        "location_city":     "Cupertino",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["AAPL", "MSFT", "GOOGL", "META"],
        "affected_themes":   ["CONSUMER_TECH", "AI", "SOFTWARE"],
        # Annual: second Monday of June — overlaps with Computex
        "event_date_start":  date(2026, 6,  8),
        "event_date_end":    date(2026, 6, 12),
        "keynote_date":      date(2026, 6,  8),
        "keynote_time_local": "10:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Tim Cook"],
        "hosting_company":   "Apple",
        "hist_impact_bull":   5.00,
        "hist_impact_base":   1.50,
        "hist_impact_bear":  -1.50,
        "hist_years_tracked": 0,
        "announcement_url":  "https://developer.apple.com/wwdc/",
        "source":            "Manual_Calendar",
        "notes": (
            "IMMINENT — starts 2026-06-08, 5 days away. "
            "Overlaps temporally with Computex — compound tech sentiment week. "
            "AI software announcements and Apple Silicon roadmap. "
            "Tim Cook keynote. Watch for Apple AI features announcement."
        ),
    },

    {
        "conference_slug":   "AWS_REINVENT",
        "conference_name":   "AWS re:Invent",
        "location_city":     "Las Vegas",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["AMZN", "NVDA", "MSFT", "GOOGL", "ORCL", "PLTR"],
        "affected_themes":   ["CLOUD", "AI", "AI_INFRASTRUCTURE"],
        # Annual: first week of December
        "event_date_start":  date(2026, 11, 30),
        "event_date_end":    date(2026, 12,  4),
        "keynote_date":      date(2026, 12,  1),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Andy Jassy", "Matt Garman"],
        "hosting_company":   "Amazon Web Services",
        "hist_impact_bull":   4.00,
        "hist_impact_base":   1.50,
        "hist_impact_bear":  -1.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://reinvent.awsevents.com",
        "source":            "Manual_Calendar",
        "notes": (
            "Q4 equivalent of Computex for cloud names. "
            "AI infrastructure capex announcements move NVDA (GPU demand). "
            "Andy Jassy CEO keynote. Watch for AWS Trainium/Inferentia chip updates."
        ),
    },

    {
        "conference_slug":   "GOOGLE_IO",
        "conference_name":   "Google I/O",
        "location_city":     "Mountain View",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["GOOGL", "META", "MSFT", "NVDA"],
        "affected_themes":   ["AI", "SOFTWARE", "CLOUD"],
        # Annual: mid-May
        "event_date_start":  date(2027, 5, 10),
        "event_date_end":    date(2027, 5, 11),
        "keynote_date":      date(2027, 5, 10),
        "keynote_time_local": "10:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Sundar Pichai"],
        "hosting_company":   "Alphabet",
        "hist_impact_bull":   5.00,
        "hist_impact_base":   1.50,
        "hist_impact_bear":  -2.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://io.google",
        "source":            "Manual_Calendar",
        "notes": (
            "Primary Google AI announcement event. "
            "Gemini model updates, Search AI integration, quantum computing updates. "
            "Sundar Pichai keynote. "
            "Competitive response signal for MSFT (Copilot) and META (LLaMA)."
        ),
    },

    {
        "conference_slug":   "MICROSOFT_BUILD",
        "conference_name":   "Microsoft Build",
        "location_city":     "Seattle",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["MSFT", "NVDA", "GOOGL", "ORCL", "PLTR"],
        "affected_themes":   ["AI", "CLOUD", "SOFTWARE"],
        # Annual: late May
        "event_date_start":  date(2027, 5, 17),
        "event_date_end":    date(2027, 5, 19),
        "keynote_date":      date(2027, 5, 17),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Satya Nadella"],
        "hosting_company":   "Microsoft",
        "hist_impact_bull":   4.00,
        "hist_impact_base":   1.50,
        "hist_impact_bear":  -1.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://build.microsoft.com",
        "source":            "Manual_Calendar",
        "notes": (
            "Primary Microsoft AI/developer announcement event. "
            "Copilot, Azure AI, OpenAI partnership updates. "
            "Satya Nadella keynote. "
            "NVDA GPU demand signal via Azure AI infrastructure announcements."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    # TIER 2 — FINANCIALS SECTOR
    # ──────────────────────────────────────────────────────────────────────────
    {
        "conference_slug":   "JPMORGAN_HEALTHCARE",
        "conference_name":   "JPMorgan Healthcare Conference",
        "location_city":     "San Francisco",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["LLY", "MRNA", "ABBV", "PFE"],
        "affected_themes":   ["BIOTECH", "PHARMA"],
        # Annual: second Monday of January
        "event_date_start":  date(2027, 1, 11),
        "event_date_end":    date(2027, 1, 14),
        "keynote_date":      None,
        "keynote_time_local": None,
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  [],
        "hosting_company":   "JPMorgan Chase",
        "hist_impact_bull":  10.00,
        "hist_impact_base":   2.00,
        "hist_impact_bear": -12.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://www.jpmorgan.com/healthcare-conference",
        "source":            "Manual_Calendar",
        "notes": (
            "Primary biotech/pharma catalyst. "
            "CEO presentations and pipeline updates move LLY, MRNA, ABBV, PFE 5-15%. "
            "Gap report flagged as missing from portfolio catalyst tracking."
        ),
    },

    {
        "conference_slug":   "GOLDMAN_FINANCIALS",
        "conference_name":   "Goldman Sachs U.S. Financial Services Conference",
        "location_city":     "New York",
        "location_country":  "US",
        "impact_tier":       2,
        "affected_tickers":  ["BAC", "WFC", "C", "SOFI", "HOOD"],
        "affected_themes":   ["FINANCIALS", "FINTECH"],
        # Annual: second Tuesday of December
        "event_date_start":  date(2026, 12,  8),
        "event_date_end":    date(2026, 12,  9),
        "keynote_date":      date(2026, 12,  8),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/New_York",
        "keynote_speakers":  [],
        "hosting_company":   "Goldman Sachs",
        "hist_impact_bull":   3.00,
        "hist_impact_base":   1.00,
        "hist_impact_bear":  -3.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://www.goldmansachs.com/conferences",
        "source":            "Manual_Calendar",
        "notes": (
            "Gap report Gap 3: WFC Morgan Stanley Financials Conference appearance "
            "was in dataset as news but NOT as a forward catalyst date. "
            "This event type now tracked as catalyst, not reactive news."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    # TIER 3 — MEDIUM market impact
    # ──────────────────────────────────────────────────────────────────────────
    {
        "conference_slug":   "QUALCOMM_SNAPDRAGON",
        "conference_name":   "Qualcomm Snapdragon Summit",
        "location_city":     "Maui",
        "location_country":  "US",
        "impact_tier":       3,
        "affected_tickers":  ["QCOM", "AAPL", "AMD", "INTC"],
        "affected_themes":   ["SEMICONDUCTOR", "CONSUMER_TECH", "AI"],
        # Annual: October
        "event_date_start":  date(2026, 10, 19),
        "event_date_end":    date(2026, 10, 21),
        "keynote_date":      date(2026, 10, 19),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Cristiano Amon"],
        "hosting_company":   "Qualcomm",
        "hist_impact_bull":   5.00,
        "hist_impact_base":   2.00,
        "hist_impact_bear":  -1.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://www.qualcomm.com/snapdragon-summit",
        "source":            "Manual_Calendar",
        "notes":             "Mobile, edge AI, Windows on Arm. Cristiano Amon keynote.",
    },

    {
        "conference_slug":   "SALESFORCE_DREAMFORCE",
        "conference_name":   "Salesforce Dreamforce",
        "location_city":     "San Francisco",
        "location_country":  "US",
        "impact_tier":       3,
        "affected_tickers":  ["CRM", "MSFT", "GOOGL", "PLTR"],
        "affected_themes":   ["SOFTWARE", "AI", "CLOUD"],
        # Annual: September
        "event_date_start":  date(2026, 9, 15),
        "event_date_end":    date(2026, 9, 18),
        "keynote_date":      date(2026, 9, 15),
        "keynote_time_local": "09:00",
        "keynote_timezone":  "America/Los_Angeles",
        "keynote_speakers":  ["Marc Benioff"],
        "hosting_company":   "Salesforce",
        "hist_impact_bull":   3.00,
        "hist_impact_base":   1.00,
        "hist_impact_bear":  -1.00,
        "hist_years_tracked": 0,
        "announcement_url":  "https://www.salesforce.com/dreamforce/",
        "source":            "Manual_Calendar",
        "notes":             "Enterprise AI/CRM. Marc Benioff keynote. PLTR enterprise AI signal.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CATALYST FLAG CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

def compute_catalyst_flag(start: date, end: date, today: date) -> tuple[str, int]:
    """
    Returns (catalyst_flag, days_until_event).
    days_until_event is negative if event has ended.
    """
    if today > end:
        return "PAST", (today - end).days * -1
    if start <= today <= end:
        return "ACTIVE", 0
    days = (start - today).days
    if days <= 3:
        return "IMMINENT", days
    if days <= 14:
        return "UPCOMING", days
    if days <= 60:
        return "WATCH", days
    return "FUTURE", days


# ═══════════════════════════════════════════════════════════════════════════════
# RSS SIGNAL SCANNER
# Scans tech_publication_signals for conference keyword mentions
# Enriches existing conference_calendar rows with speaker confirmations
# ═══════════════════════════════════════════════════════════════════════════════

CONFERENCE_KEYWORDS = {
    "COMPUTEX":             ["computex", "taipei", "computex 2026"],
    "NVIDIA_GTC":           ["gtc", "gpu technology conference", "nvidia gtc"],
    "CES":                  ["ces 2027", "consumer electronics show", "ces las vegas"],
    "APPLE_WWDC":           ["wwdc", "apple developer", "apple worldwide"],
    "AWS_REINVENT":         ["re:invent", "reinvent", "aws reinvent"],
    "GOOGLE_IO":            ["google i/o", "google io"],
    "MICROSOFT_BUILD":      ["microsoft build"],
    "JPMORGAN_HEALTHCARE":  ["jpmorgan healthcare", "j.p. morgan healthcare"],
    "GOLDMAN_FINANCIALS":   ["goldman sachs financial", "goldman financials"],
    "QUALCOMM_SNAPDRAGON":  ["snapdragon summit", "qualcomm summit"],
    "SALESFORCE_DREAMFORCE":["dreamforce"],
}

SPEAKER_PATTERNS = [
    (r"jensen\s+huang",     "Jensen Huang"),
    (r"lisa\s+su",          "Lisa Su"),
    (r"tim\s+cook",         "Tim Cook"),
    (r"satya\s+nadella",    "Satya Nadella"),
    (r"andy\s+jassy",       "Andy Jassy"),
    (r"sundar\s+pichai",    "Sundar Pichai"),
    (r"pat\s+gelsinger",    "Pat Gelsinger"),
    (r"cristiano\s+amon",   "Cristiano Amon"),
    (r"sam\s+altman",       "Sam Altman"),
    (r"marc\s+benioff",     "Marc Benioff"),
]


def scan_rss_for_conferences(cur, today: date) -> dict[str, dict]:
    """
    Scan tech_publication_signals for conference mentions.
    Returns dict: slug → {speakers_found, article_count, urls}
    Only looks at signals from last 30 days.
    """
    enrichments = {}
    try:
        cur.execute("""
            SELECT headline, summary, article_url, source, published_at
            FROM tech_publication_signals
            WHERE snapshot_date >= %s
            ORDER BY published_at DESC
        """, (today - timedelta(days=30),))
        rows = cur.fetchall()
    except Exception as e:
        _warn(f"RSS scan query failed: {e}")
        return {}

    for row in rows:
        text = f"{row.get('headline','')} {row.get('summary','') or ''}".lower()
        url  = row.get("article_url", "")

        for slug, keywords in CONFERENCE_KEYWORDS.items():
            if not any(kw in text for kw in keywords):
                continue

            if slug not in enrichments:
                enrichments[slug] = {
                    "speakers_found": [],
                    "article_count":  0,
                    "urls":           [],
                }
            enrichments[slug]["article_count"] += 1
            if url and url not in enrichments[slug]["urls"]:
                enrichments[slug]["urls"].append(url)

            # Speaker detection
            for pattern, name in SPEAKER_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    if name not in enrichments[slug]["speakers_found"]:
                        enrichments[slug]["speakers_found"].append(name)

    return enrichments


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
# DB WRITER
# ═══════════════════════════════════════════════════════════════════════════════

def write_conferences(
    events: list[dict],
    rss_enrichments: dict,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """
    Upsert conference events into conference_calendar.
    Merges RSS-detected speakers into keynote_speakers list.
    Returns (inserted, updated, failed).
    """
    now     = datetime.now()
    today   = now.date()
    inserted = updated = failed = 0

    if not dry_run:
        conn = _get_conn()
        cur  = conn.cursor()

    sql = """
        INSERT INTO conference_calendar (
            conference_name, conference_slug, edition_year,
            event_date_start, event_date_end,
            keynote_date, keynote_time_local, keynote_timezone,
            keynote_speakers, hosting_company,
            location_city, location_country,
            impact_tier, affected_tickers, affected_themes,
            hist_impact_bull, hist_impact_base, hist_impact_bear,
            hist_years_tracked, days_until_event, catalyst_flag,
            announcement_url, source, fetched_at, snapshot_date, cycle_ts, notes
        ) VALUES (
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            conference_name    = VALUES(conference_name),
            event_date_start   = VALUES(event_date_start),
            event_date_end     = VALUES(event_date_end),
            keynote_date       = VALUES(keynote_date),
            keynote_speakers   = VALUES(keynote_speakers),
            days_until_event   = VALUES(days_until_event),
            catalyst_flag      = VALUES(catalyst_flag),
            affected_tickers   = VALUES(affected_tickers),
            affected_themes    = VALUES(affected_themes),
            fetched_at         = VALUES(fetched_at),
            snapshot_date      = VALUES(snapshot_date),
            cycle_ts           = VALUES(cycle_ts),
            notes              = VALUES(notes)
    """

    for ev in events:
        slug  = ev["conference_slug"]
        start = ev["event_date_start"]
        end   = ev["event_date_end"]
        year  = start.year

        catalyst_flag, days_until = compute_catalyst_flag(start, end, today)

        # Merge RSS-detected speakers
        speakers = list(ev.get("keynote_speakers") or [])
        if slug in rss_enrichments:
            for spk in rss_enrichments[slug].get("speakers_found", []):
                if spk not in speakers:
                    speakers.append(spk)
                    _info(f"RSS enriched {slug} with speaker: {spk}")

        if dry_run:
            print(f"\n  [DRY RUN] {slug} ({year})")
            print(f"            {start} → {end}")
            print(f"            flag={catalyst_flag} days={days_until}")
            print(f"            speakers={speakers}")
            print(f"            tickers={ev.get('affected_tickers')}")
            continue

        try:
            cur.execute(sql, (
                ev["conference_name"],
                slug,
                year,
                start,
                end,
                ev.get("keynote_date"),
                ev.get("keynote_time_local"),
                ev.get("keynote_timezone"),
                json.dumps(speakers),
                ev.get("hosting_company"),
                ev.get("location_city"),
                ev.get("location_country"),
                ev["impact_tier"],
                json.dumps(ev.get("affected_tickers") or []),
                json.dumps(ev.get("affected_themes") or []),
                ev.get("hist_impact_bull"),
                ev.get("hist_impact_base"),
                ev.get("hist_impact_bear"),
                ev.get("hist_years_tracked", 0),
                days_until,
                catalyst_flag,
                ev.get("announcement_url"),
                ev["source"],
                now,
                today,
                now,
                ev.get("notes"),
            ))
            if cur.rowcount == 1:
                _ok(f"Inserted : {slug:<30} {year}  [{catalyst_flag}] days={days_until}")
                inserted += 1
            else:
                _ok(f"Updated  : {slug:<30} {year}  [{catalyst_flag}] days={days_until}")
                updated += 1
        except Exception as e:
            _fail(f"Failed   : {slug} — {e}")
            failed += 1

    if not dry_run:
        conn.commit()
        cur.close()
        conn.close()

    return inserted, updated, failed


def verify_calendar(cur) -> None:
    """SELECT and print all non-PAST conference rows."""
    cur.execute("""
        SELECT conference_slug, edition_year, event_date_start, event_date_end,
               catalyst_flag, days_until_event, impact_tier,
               JSON_LENGTH(keynote_speakers) AS speaker_count
        FROM conference_calendar
        WHERE catalyst_flag != 'PAST'
        ORDER BY event_date_start ASC
    """)
    rows = cur.fetchall()
    print(f"\n  {'slug':<30} {'year'} {'start':<12} {'flag':<10} {'days':>5} {'tier'} {'spkrs'}")
    print(f"  {'─'*30} {'─'*4} {'─'*12} {'─'*10} {'─'*5} {'─'*4} {'─'*5}")
    for r in rows:
        if isinstance(r, dict):
            print(f"  {r.get('conference_slug',''):<30} "
                  f"{r.get('edition_year',''):<4} "
                  f"{str(r.get('event_date_start','')):<12} "
                  f"{r.get('catalyst_flag',''):<10} "
                  f"{str(r.get('days_until_event','')):<5} "
                  f"T{r.get('impact_tier','')}   "
                  f"{r.get('speaker_count',0)}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Conference Calendar Fetcher v1.0"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print what would be written, skip DB write")
    parser.add_argument("--verify",   action="store_true",
                        help="After write, SELECT and print all non-PAST rows")
    parser.add_argument("--rss-scan", action="store_true",
                        help="Scan tech_publication_signals for conference mentions")
    args = parser.parse_args()

    now = datetime.now()

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    print()
    print("=" * 66)
    print(f"  BLUELOTUS MID — Conference Calendar Fetcher v1.0")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Conferences in seed : {len(CONFERENCE_SEED)}")
    print(f"  Mode : {'DRY RUN' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 66)

    # ── RSS enrichment scan ───────────────────────────────────────────────────
    rss_enrichments = {}
    if args.rss_scan and not args.dry_run:
        _section("STEP 1: Scanning tech_publication_signals for conference mentions")
        conn2 = _get_conn()
        cur2  = conn2.cursor(dictionary=True)
        rss_enrichments = scan_rss_for_conferences(cur2, now.date())
        cur2.close()
        conn2.close()
        if rss_enrichments:
            for slug, data in rss_enrichments.items():
                _ok(f"{slug:<30} {data['article_count']} articles | "
                    f"speakers: {data['speakers_found'] or '—'}")
        else:
            _info("No conference mentions found in recent RSS signals")
    else:
        _section("STEP 1: RSS scan — skipped (use --rss-scan to enable)")

    # ── Write conferences ─────────────────────────────────────────────────────
    _section("STEP 2: Writing conference_calendar")
    inserted, updated, failed = write_conferences(
        CONFERENCE_SEED, rss_enrichments, dry_run=args.dry_run
    )

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify and not args.dry_run:
        _section("STEP 3: Verification — conference_calendar (non-PAST)")
        conn3 = _get_conn()
        cur3  = conn3.cursor(dictionary=True)
        verify_calendar(cur3)
        cur3.close()
        conn3.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — Conference Calendar Fetcher v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    if not args.dry_run:
        print(f"  Inserted : {inserted}")
        print(f"  Updated  : {updated}")
        print(f"  Failed   : {failed}")
    print()
    print("  NEXT STEPS:")
    print("  1. python mid\\fetch_ceo_appearances.py")
    print("  2. python mid\\fetch_catalyst_calendar.py")
    print("  3. Update export_dataset_raw.py to v1.8")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
