"""
BlueLotus Digital Institution — V2.0
mid/seed_ece_events.py

PURPOSE
-------
    One-time (idempotent) seed script that populates the ece_named_events
    table with named seasonal market events.

    This encodes institutional knowledge from the Research Team directly
    into the ECE (Event Correlation Engine) registry. The data comes from:

        INTELLIGENCE_GAP_REPORT_20260602.txt — Gap 5
        Gap Report ID: gap_report_20260602_230000

    Initial seed contains:
        1. COMPUTEX_HUANG_KEYNOTE     — fully calibrated (2024/2025/2026 data)
        2. NVIDIA_GTC_SILICON_VALLEY  — annual March keynote
        3. CES_LAS_VEGAS              — January consumer tech
        4. APPLE_WWDC                 — June developer conference
        5. AWS_REINVENT               — November/December cloud
        6. FOMC_DECISION              — 8x per year Fed rate decisions
        7. JPMORGAN_HEALTHCARE        — January biotech/pharma catalyst
        8. GOLDMAN_FINANCIALS         — June financials sector catalyst

DOCTRINE
--------
    - This table is RESEARCHER-MAINTAINED. No automated scraping.
    - Add new events by adding to the EVENTS list below and re-running.
    - Update historical_years after each event resolves.
    - Re-running is fully idempotent: INSERT ... ON DUPLICATE KEY UPDATE
      so existing records are refreshed, not duplicated.
    - next_occurrence is computed automatically by this script.

USAGE
-----
    cd C:\\bluelotus2
    python mid\\seed_ece_events.py

    Flags:
    --dry-run     Print what would be inserted without writing to DB
    --verify      After seeding, SELECT and print all rows from ece_named_events

NEXT STEPS
----------
    After this script: run fetch_tech_publications.py

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial seed — gap_report_20260602_230000

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
from datetime import datetime, date
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


# ── next_occurrence calculator ─────────────────────────────────────────────────
def compute_next_occurrence(event: dict, from_date: date) -> date | None:
    """
    Compute the next trigger date for a named event.

    ANNUAL_DATE    — same calendar day/month each year
    ANNUAL_WEEKDAY — Nth weekday of a given month each year
    MANUAL         — no auto-compute; Research Team sets manually
    """
    trigger_type = event.get("trigger_type")
    month        = event.get("trigger_month")

    if trigger_type == "ANNUAL_DATE":
        day = event.get("trigger_day_of_month")
        if not (month and day):
            return None
        candidate = date(from_date.year, month, day)
        if candidate <= from_date:
            candidate = date(from_date.year + 1, month, day)
        return candidate

    elif trigger_type == "ANNUAL_WEEKDAY":
        # Nth weekday of month — e.g. first Monday of June
        week_of_month = event.get("trigger_week_of_month")  # 1-based
        day_of_week   = event.get("trigger_day_of_week")    # 0=Mon ... 6=Sun
        if not (month and week_of_month is not None and day_of_week is not None):
            return None

        def nth_weekday(year, month, nth, weekday):
            """Return the date of the nth occurrence of weekday in month/year."""
            first = date(year, month, 1)
            # days until target weekday
            delta = (weekday - first.weekday()) % 7
            first_occurrence = date(year, month, 1 + delta)
            target = date(year, month, first_occurrence.day + (nth - 1) * 7)
            return target

        candidate = nth_weekday(from_date.year, month, week_of_month, day_of_week)
        if candidate <= from_date:
            candidate = nth_weekday(from_date.year + 1, month, week_of_month, day_of_week)
        return candidate

    return None  # MANUAL — Research Team sets next_occurrence manually


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT SEED DATA
#
# Each dict maps directly to ece_named_events columns.
# JSON fields (lists/dicts) are stored as Python objects here —
# the writer serialises them with json.dumps() before INSERT.
#
# To add a new event: append a new dict to this list and re-run.
# To update historical data: edit the historical_years list and re-run.
# ═══════════════════════════════════════════════════════════════════════════════

EVENTS = [

    # ──────────────────────────────────────────────────────────────────────────
    # 1. COMPUTEX_HUANG_KEYNOTE
    #    Source: gap_report_20260602_230000 Section 1 Gap 5
    #    Fully calibrated: 3 years of historical data (2024/2025/2026)
    #    The primary event that triggered this entire gap remediation.
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "COMPUTEX_HUANG_KEYNOTE",
        "event_name":              "Computex Jensen Huang Keynote",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual Computex Taipei keynote by Nvidia CEO Jensen Huang. "
            "Historically the single highest-impact recurring tech event for "
            "AI infrastructure, semiconductor, and quantum names. "
            "First identified as a signal gap on 2026-06-02 when Huang made a "
            "surprise appearance at Marvell's keynote driving MRVL +19%, "
            "NVDA +6.26%, and S&P 500 to all-time high 7,617.66. "
            "Gap Report: gap_report_20260602_230000."
        ),
        # Trigger: first Monday of June (Taipei time)
        "trigger_type":            "ANNUAL_WEEKDAY",
        "trigger_month":           6,
        "trigger_week_of_month":   1,
        "trigger_day_of_week":     0,   # 0 = Monday
        "trigger_day_of_month":    None,
        "trigger_description":     "First Monday of June (Taipei time, Asia/Taipei)",

        # Impact model — calibrated from 3 years of data
        "base_case_sectors":       ["SEMICONDUCTOR", "AI", "QUANTUM", "SPACE"],
        "base_case_impact_pct":    2.50,
        "base_case_duration_days": 1,

        "bull_trigger": (
            "Surprise product announcement OR unscheduled appearance at a "
            "partner keynote (e.g. Marvell, TSMC). Extends rally by one "
            "additional trading session."
        ),
        "bull_case_impact_pct":    6.26,
        "bull_case_tickers":       ["NVDA", "MRVL", "AMD", "TSM", "AMAT"],
        "bull_duration_days":      2,

        "bear_trigger": (
            "Keynote meets but does not beat expectations. "
            "Buy-the-rumour sell-the-news pattern. Day 1 fades by session end."
        ),
        "bear_case_impact_pct":    -1.20,
        "bear_duration_days":      1,

        "sector_impact_map": {
            "NVDA":  "DIRECT_PRIMARY",
            "MRVL":  "DIRECT_PRIMARY",
            "AMD":   "DIRECT_SECONDARY",
            "TSM":   "DIRECT_SECONDARY",
            "AMAT":  "DIRECT_SECONDARY",
            "CDNS":  "DIRECT_SECONDARY",
            "SNPS":  "DIRECT_SECONDARY",
            "AVGO":  "DIRECT_SECONDARY",
            "QBTS":  "QUANTUM_SPILLOVER",
            "QUBT":  "QUANTUM_SPILLOVER",
            "IONQ":  "QUANTUM_SPILLOVER",
            "RGTI":  "QUANTUM_SPILLOVER",
            "BAC":   "INDIRECT_SENTIMENT",
            "WFC":   "INDIRECT_SENTIMENT",
            "RKLB":  "INDIRECT_SENTIMENT",
            "ASTS":  "INDIRECT_SENTIMENT",
        },

        # Historical calibration — 3 years confirmed
        "historical_years": [
            {
                "year":      2024,
                "outcome":   "BULL",
                "nvda_pct":  10.4,
                "sp500_pct": 1.4,
                "notes":     "Blackwell architecture reveal + GPU cadence surprise. "
                             "Broader tech rally sustained 2-3 days."
            },
            {
                "year":      2025,
                "outcome":   "BEAR",
                "nvda_pct":  -1.2,
                "sp500_pct": 0.1,
                "notes":     "Keynote met but did not beat expectations. "
                             "Buy-the-rumour sell-the-news Day 1 fade. "
                             "Huang/Zuckerberg quantum comments crashed quantum sector same week."
            },
            {
                "year":      2026,
                "outcome":   "BULL",
                "nvda_pct":  6.26,
                "sp500_pct": 0.8,
                "notes":     "Huang surprise appearance at Marvell keynote Day 2. "
                             "MRVL +19%, S&P 500 all-time high 7,617.66. "
                             "System had zero visibility — triggered gap_report_20260602_230000."
            },
        ],
        "years_tracked":   3,
        "last_occurrence": date(2026, 6, 2),
        "is_active":       True,
        "authored_by":     "BlueLotus Research Department",
        "notes": (
            "Bank impact: Indirect +0.5-1.0% via broad sentiment lift. "
            "NOT a fundamental re-rating. Fades within 48 hours. "
            "Quantum impact: Huang comments on quantum are binary — "
            "positive (Jun 2026) or negative (Jan 2025 Zuckerberg comments). "
            "Monitor Huang quantum sentiment specifically."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 2. NVIDIA_GTC_SILICON_VALLEY
    #    Annual March GTC conference — primary Nvidia product roadmap event.
    #    Typically larger than Computex for product announcements.
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "NVIDIA_GTC_SILICON_VALLEY",
        "event_name":              "Nvidia GTC Silicon Valley",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual Nvidia GPU Technology Conference in Silicon Valley (March). "
            "Primary venue for Nvidia product roadmap announcements — GPU architecture "
            "reveals, AI infrastructure partnerships, and quantum computing updates. "
            "Typically higher product significance than Computex."
        ),
        "trigger_type":            "ANNUAL_WEEKDAY",
        "trigger_month":           3,
        "trigger_week_of_month":   2,   # typically mid-March
        "trigger_day_of_week":     0,   # Monday
        "trigger_day_of_month":    None,
        "trigger_description":     "Second Monday of March (San Jose / Silicon Valley)",

        "base_case_sectors":       ["SEMICONDUCTOR", "AI", "QUANTUM"],
        "base_case_impact_pct":    3.00,
        "base_case_duration_days": 1,

        "bull_trigger":            "New GPU architecture reveal or major AI partnership announcement.",
        "bull_case_impact_pct":    8.00,
        "bull_case_tickers":       ["NVDA", "AMD", "AMAT", "TSM"],
        "bull_duration_days":      2,

        "bear_trigger":            "Incremental update only, no new architecture. Fade pattern.",
        "bear_case_impact_pct":    -2.00,
        "bear_duration_days":      1,

        "sector_impact_map": {
            "NVDA":  "DIRECT_PRIMARY",
            "AMD":   "DIRECT_SECONDARY",
            "AMAT":  "DIRECT_SECONDARY",
            "TSM":   "DIRECT_SECONDARY",
            "IONQ":  "QUANTUM_SPILLOVER",
            "QBTS":  "QUANTUM_SPILLOVER",
            "QUBT":  "QUANTUM_SPILLOVER",
        },

        "historical_years":        [],   # Research Team to populate after each event
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes":                   "Historical years to be populated by Research Team after March 2027 event.",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 3. CES_LAS_VEGAS
    #    January consumer electronics — AI PC, edge AI, consumer sentiment
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "CES_LAS_VEGAS",
        "event_name":              "CES Las Vegas",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual Consumer Electronics Show in Las Vegas (January). "
            "Key catalyst for AI PC, edge AI, consumer tech, and semiconductor names. "
            "AMD, Intel, Qualcomm, and Nvidia typically make major consumer product "
            "announcements. Sets the tech sentiment tone for Q1."
        ),
        "trigger_type":            "ANNUAL_DATE",
        "trigger_month":           1,
        "trigger_day_of_month":    7,   # CES typically opens first full week of January
        "trigger_week_of_month":   None,
        "trigger_day_of_week":     None,
        "trigger_description":     "First full week of January, typically Jan 7-10 (Las Vegas)",

        "base_case_sectors":       ["SEMICONDUCTOR", "AI", "CONSUMER_TECH"],
        "base_case_impact_pct":    1.50,
        "base_case_duration_days": 1,

        "bull_trigger":            "Surprise AI PC or edge AI breakthrough announcement.",
        "bull_case_impact_pct":    4.00,
        "bull_case_tickers":       ["NVDA", "AMD", "INTC", "QCOM", "AAPL"],
        "bull_duration_days":      2,

        "bear_trigger":            "Incremental product refreshes only. Market shrugs.",
        "bear_case_impact_pct":    -0.50,
        "bear_duration_days":      1,

        "sector_impact_map": {
            "NVDA":  "DIRECT_PRIMARY",
            "AMD":   "DIRECT_PRIMARY",
            "INTC":  "DIRECT_SECONDARY",
            "AAPL":  "INDIRECT_SENTIMENT",
            "MSFT":  "INDIRECT_SENTIMENT",
        },

        "historical_years":        [],
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes":                   "Qualcomm Snapdragon announcements also move QCOM significantly at CES.",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 4. APPLE_WWDC
    #    June developer conference — AI software, iOS, macOS
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "APPLE_WWDC",
        "event_name":              "Apple WWDC",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual Apple Worldwide Developers Conference (June). "
            "Primary venue for Apple AI software announcements, iOS/macOS updates, "
            "and Apple Silicon roadmap. Overlaps temporally with Computex — "
            "both occur in June, creating compounded tech sentiment weeks."
        ),
        "trigger_type":            "ANNUAL_WEEKDAY",
        "trigger_month":           6,
        "trigger_week_of_month":   2,   # typically second Monday of June
        "trigger_day_of_week":     0,
        "trigger_day_of_month":    None,
        "trigger_description":     "Second Monday of June (Cupertino / online)",

        "base_case_sectors":       ["CONSUMER_TECH", "AI", "SOFTWARE"],
        "base_case_impact_pct":    1.50,
        "base_case_duration_days": 1,

        "bull_trigger":            "Major AI feature reveal or new Apple Silicon architecture.",
        "bull_case_impact_pct":    5.00,
        "bull_case_tickers":       ["AAPL", "MSFT", "GOOGL"],
        "bull_duration_days":      2,

        "bear_trigger":            "Incremental software updates. No hardware surprise.",
        "bear_case_impact_pct":    -1.50,
        "bear_duration_days":      1,

        "sector_impact_map": {
            "AAPL":  "DIRECT_PRIMARY",
            "MSFT":  "INDIRECT_SENTIMENT",
            "GOOGL": "INDIRECT_SENTIMENT",
            "META":  "INDIRECT_SENTIMENT",
        },

        "historical_years":        [],
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes":                   "Note: WWDC and Computex both fall in June — compound tech sentiment weeks possible.",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 5. AWS_REINVENT
    #    November/December — cloud, AI infrastructure, enterprise software
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "AWS_REINVENT",
        "event_name":              "AWS re:Invent",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual Amazon Web Services re:Invent conference (November/December, Las Vegas). "
            "Primary catalyst for cloud infrastructure, AI services, and enterprise software. "
            "Andy Jassy (Amazon CEO) and AWS CEO typically announce major AI infrastructure "
            "expansions. Moves AMZN, MSFT (Azure competitive response), and GOOGL (GCP)."
        ),
        "trigger_type":            "ANNUAL_WEEKDAY",
        "trigger_month":           12,
        "trigger_week_of_month":   1,   # first week of December
        "trigger_day_of_week":     0,
        "trigger_day_of_month":    None,
        "trigger_description":     "First Monday of December (Las Vegas Convention Center)",

        "base_case_sectors":       ["CLOUD", "AI", "SOFTWARE", "SEMICONDUCTOR"],
        "base_case_impact_pct":    1.50,
        "base_case_duration_days": 1,

        "bull_trigger":            "Major AI infrastructure or chip partnership announcement (e.g. AWS Trainium).",
        "bull_case_impact_pct":    4.00,
        "bull_case_tickers":       ["AMZN", "NVDA", "MSFT", "GOOGL"],
        "bull_duration_days":      2,

        "bear_trigger":            "Incremental service launches. No major AI or infra surprise.",
        "bear_case_impact_pct":    -1.00,
        "bear_duration_days":      1,

        "sector_impact_map": {
            "AMZN":  "DIRECT_PRIMARY",
            "NVDA":  "DIRECT_SECONDARY",
            "MSFT":  "INDIRECT_SENTIMENT",
            "GOOGL": "INDIRECT_SENTIMENT",
            "ORCL":  "INDIRECT_SENTIMENT",
            "PLTR":  "INDIRECT_SENTIMENT",
        },

        "historical_years":        [],
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes":                   "AWS re:Invent is the Q4 equivalent of Computex for cloud names.",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 6. FOMC_DECISION
    #    8x per year — macro override, rate policy, all-sector impact
    #    NOTE: trigger_type = MANUAL — dates set by Fed calendar each year.
    #    Research Team updates next_occurrence manually from Fed schedule.
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "FOMC_DECISION",
        "event_name":              "FOMC Interest Rate Decision",
        "event_category":          "FED_DECISION",
        "description": (
            "Federal Open Market Committee interest rate decision. "
            "Occurs 8 times per year — dates published by Federal Reserve at "
            "federalreserve.gov/monetarypolicy/fomccalendars.htm. "
            "Jerome Powell press conference follows each decision. "
            "MACRO OVERRIDE event — overrides all sector-level signals. "
            "Impacts every position in the portfolio simultaneously."
        ),
        "trigger_type":            "MANUAL",
        "trigger_month":           None,
        "trigger_week_of_month":   None,
        "trigger_day_of_week":     None,
        "trigger_day_of_month":    None,
        "trigger_description":     "8x per year — Research Team sets next_occurrence from Fed calendar",

        "base_case_sectors":       ["ALL"],
        "base_case_impact_pct":    0.50,
        "base_case_duration_days": 1,

        "bull_trigger":            "Rate cut or dovish pivot signal from Powell press conference.",
        "bull_case_impact_pct":    2.50,
        "bull_case_tickers":       ["BAC", "WFC", "C", "SOFI", "TLT"],
        "bull_duration_days":      3,

        "bear_trigger":            "Rate hike or hawkish surprise. Risk-off across all sectors.",
        "bear_case_impact_pct":    -3.00,
        "bear_duration_days":      2,

        "sector_impact_map": {
            "TLT":  "DIRECT_PRIMARY",
            "BAC":  "DIRECT_PRIMARY",
            "WFC":  "DIRECT_PRIMARY",
            "C":    "DIRECT_PRIMARY",
            "SOFI": "DIRECT_PRIMARY",
            "NVDA": "INDIRECT_SENTIMENT",
            "AMZN": "INDIRECT_SENTIMENT",
            "GOOGL":"INDIRECT_SENTIMENT",
        },

        "historical_years":        [],
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes": (
            "FOMC dates for 2026 from federalreserve.gov/monetarypolicy/fomccalendars.htm. "
            "Research Team must update next_occurrence manually after each decision. "
            "Powell press conference tone (hawkish/dovish) is more impactful than the "
            "rate decision itself — monitor Fed_Press and Fed_Speeches signals on decision day."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 7. JPMORGAN_HEALTHCARE
    #    January — biotech/pharma sector catalyst (LLY, MRNA, ABBV, PFE)
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "JPMORGAN_HEALTHCARE",
        "event_name":              "JPMorgan Healthcare Conference",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual JPMorgan Healthcare Conference (January, San Francisco). "
            "Primary catalyst for biotech and pharma sector. "
            "Directly relevant to BlueLotus holdings: LLY (GLP-1/Ozempic), "
            "MRNA (mRNA pipeline), ABBV (immunology/oncology), PFE (broad pharma). "
            "CEO presentations and pipeline updates move individual names 5-15%."
        ),
        "trigger_type":            "ANNUAL_WEEKDAY",
        "trigger_month":           1,
        "trigger_week_of_month":   2,   # second Monday of January
        "trigger_day_of_week":     0,
        "trigger_day_of_month":    None,
        "trigger_description":     "Second Monday of January (San Francisco)",

        "base_case_sectors":       ["BIOTECH", "PHARMA"],
        "base_case_impact_pct":    2.00,
        "base_case_duration_days": 2,

        "bull_trigger":            "Positive pipeline data or partnership announcement from a held name.",
        "bull_case_impact_pct":    10.00,
        "bull_case_tickers":       ["LLY", "MRNA", "ABBV", "PFE"],
        "bull_duration_days":      3,

        "bear_trigger":            "Pipeline failure or negative clinical data disclosed at conference.",
        "bear_case_impact_pct":    -12.00,
        "bear_duration_days":      2,

        "sector_impact_map": {
            "LLY":  "DIRECT_PRIMARY",
            "MRNA": "DIRECT_PRIMARY",
            "ABBV": "DIRECT_PRIMARY",
            "PFE":  "DIRECT_PRIMARY",
        },

        "historical_years":        [],
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes":                   "Individual stock moves at JPM Healthcare can be 5-15% on pipeline news.",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 8. GOLDMAN_FINANCIALS
    #    June — financials sector catalyst (BAC, WFC, C, SOFI)
    #    NOTE: Gap report specifically flagged WFC presented at Morgan Stanley
    #    U.S. Financials Conference — this event tracks the Goldman equivalent.
    # ──────────────────────────────────────────────────────────────────────────
    {
        "event_slug":              "GOLDMAN_FINANCIALS",
        "event_name":              "Goldman Sachs U.S. Financial Services Conference",
        "event_category":          "SEASONAL_TECH",
        "description": (
            "Annual Goldman Sachs U.S. Financial Services Conference (June). "
            "Key catalyst for financials sector — BAC, WFC, C, SOFI. "
            "Gap report noted WFC presented at the Morgan Stanley U.S. Financials "
            "Conference (same week as Computex 2026) and was flagged as news but "
            "NOT as a catalyst date. This event ensures financials conference "
            "appearances are properly tracked as forward catalysts."
        ),
        "trigger_type":            "ANNUAL_WEEKDAY",
        "trigger_month":           12,  # Goldman typically December
        "trigger_week_of_month":   2,
        "trigger_day_of_week":     1,   # Tuesday
        "trigger_day_of_month":    None,
        "trigger_description":     "Second Tuesday of December (New York)",

        "base_case_sectors":       ["FINANCIALS", "FINTECH"],
        "base_case_impact_pct":    1.00,
        "base_case_duration_days": 1,

        "bull_trigger":            "Positive NIM outlook or loan growth guidance from CEO.",
        "bull_case_impact_pct":    3.00,
        "bull_case_tickers":       ["BAC", "WFC", "C", "SOFI"],
        "bull_duration_days":      2,

        "bear_trigger":            "Credit quality concerns or NIM compression guidance.",
        "bear_case_impact_pct":    -3.00,
        "bear_duration_days":      2,

        "sector_impact_map": {
            "BAC":  "DIRECT_PRIMARY",
            "WFC":  "DIRECT_PRIMARY",
            "C":    "DIRECT_PRIMARY",
            "SOFI": "DIRECT_SECONDARY",
            "HOOD": "DIRECT_SECONDARY",
            "COIN": "INDIRECT_SENTIMENT",
        },

        "historical_years":        [],
        "years_tracked":           0,
        "last_occurrence":         None,
        "is_active":               True,
        "authored_by":             "BlueLotus Research Department",
        "notes": (
            "Gap report Section 1 Gap 3: WFC Morgan Stanley Financials Conference "
            "appearance was in dataset as news item but NOT as a catalyst date. "
            "This event type must be tracked as a forward catalyst, not reactive news."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# DB WRITER
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


def seed_events(events: list, dry_run: bool = False) -> tuple[int, int, int]:
    """
    Upsert all events into ece_named_events.
    Returns (inserted, updated, failed) counts.
    """
    now      = datetime.now()
    today    = now.date()
    inserted = updated = failed = 0

    if not dry_run:
        conn = _get_conn()
        cur  = conn.cursor()

    sql = """
        INSERT INTO ece_named_events (
            event_slug, event_name, event_category, description,
            trigger_type, trigger_month, trigger_week_of_month,
            trigger_day_of_week, trigger_day_of_month, trigger_description,
            base_case_sectors, base_case_impact_pct, base_case_duration_days,
            bull_trigger, bull_case_impact_pct, bull_case_tickers, bull_duration_days,
            bear_trigger, bear_case_impact_pct, bear_duration_days,
            sector_impact_map, historical_years, years_tracked,
            is_active, last_occurrence, next_occurrence,
            source, authored_by, created_at, updated_at, notes
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            event_name               = VALUES(event_name),
            event_category           = VALUES(event_category),
            description              = VALUES(description),
            trigger_type             = VALUES(trigger_type),
            trigger_month            = VALUES(trigger_month),
            trigger_week_of_month    = VALUES(trigger_week_of_month),
            trigger_day_of_week      = VALUES(trigger_day_of_week),
            trigger_day_of_month     = VALUES(trigger_day_of_month),
            trigger_description      = VALUES(trigger_description),
            base_case_sectors        = VALUES(base_case_sectors),
            base_case_impact_pct     = VALUES(base_case_impact_pct),
            base_case_duration_days  = VALUES(base_case_duration_days),
            bull_trigger             = VALUES(bull_trigger),
            bull_case_impact_pct     = VALUES(bull_case_impact_pct),
            bull_case_tickers        = VALUES(bull_case_tickers),
            bull_duration_days       = VALUES(bull_duration_days),
            bear_trigger             = VALUES(bear_trigger),
            bear_case_impact_pct     = VALUES(bear_case_impact_pct),
            bear_duration_days       = VALUES(bear_duration_days),
            sector_impact_map        = VALUES(sector_impact_map),
            historical_years         = VALUES(historical_years),
            years_tracked            = VALUES(years_tracked),
            is_active                = VALUES(is_active),
            last_occurrence          = VALUES(last_occurrence),
            next_occurrence          = VALUES(next_occurrence),
            authored_by              = VALUES(authored_by),
            updated_at               = VALUES(updated_at),
            notes                    = VALUES(notes)
    """

    for ev in events:
        next_occ = compute_next_occurrence(ev, today)
        slug     = ev["event_slug"]

        params = (
            slug,
            ev["event_name"],
            ev["event_category"],
            ev.get("description"),
            ev["trigger_type"],
            ev.get("trigger_month"),
            ev.get("trigger_week_of_month"),
            ev.get("trigger_day_of_week"),
            ev.get("trigger_day_of_month"),
            ev.get("trigger_description"),
            json.dumps(ev.get("base_case_sectors") or []),
            ev.get("base_case_impact_pct"),
            ev.get("base_case_duration_days"),
            ev.get("bull_trigger"),
            ev.get("bull_case_impact_pct"),
            json.dumps(ev.get("bull_case_tickers") or []),
            ev.get("bull_duration_days"),
            ev.get("bear_trigger"),
            ev.get("bear_case_impact_pct"),
            ev.get("bear_duration_days"),
            json.dumps(ev.get("sector_impact_map") or {}),
            json.dumps(ev.get("historical_years") or []),
            ev.get("years_tracked", 0),
            ev.get("is_active", True),
            ev.get("last_occurrence"),
            next_occ,
            "Manual_ECE",
            ev.get("authored_by"),
            now,
            now,
            ev.get("notes"),
        )

        if dry_run:
            print(f"\n  [DRY RUN] Would upsert: {slug}")
            print(f"            next_occurrence = {next_occ}")
            print(f"            trigger         = {ev.get('trigger_description')}")
            continue

        try:
            cur.execute(sql, params)
            if cur.rowcount == 1:
                _ok(f"Inserted : {slug:<40} next={next_occ}")
                inserted += 1
            else:
                _ok(f"Updated  : {slug:<40} next={next_occ}")
                updated += 1
        except Exception as e:
            _fail(f"Failed   : {slug} — {e}")
            failed += 1

    if not dry_run:
        conn.commit()
        cur.close()
        conn.close()

    return inserted, updated, failed


def verify_seed(cur) -> None:
    """SELECT all rows and print a summary table."""
    cur.execute("""
        SELECT event_slug, event_category, trigger_description,
               last_occurrence, next_occurrence, years_tracked, is_active
        FROM ece_named_events
        ORDER BY next_occurrence ASC
    """)
    rows = cur.fetchall()
    print(f"\n  {'event_slug':<35} {'category':<16} {'next_occurrence':<14} {'calibrated'}")
    print(f"  {'─'*35} {'─'*16} {'─'*14} {'─'*10}")
    for r in rows:
        if isinstance(r, dict):
            slug     = r.get("event_slug", "")
            cat      = r.get("event_category", "")
            next_occ = str(r.get("next_occurrence") or "MANUAL")
            yrs      = r.get("years_tracked", 0)
            active   = "✅" if r.get("is_active") else "❌"
            cal      = f"{yrs} yrs" if yrs else "—"
            print(f"  {slug:<35} {cat:<16} {next_occ:<14} {cal}  {active}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — ECE Named Events Seeder v1.0"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print what would be inserted without writing to DB")
    parser.add_argument("--verify",   action="store_true",
                        help="After seeding, SELECT and print all rows")
    args = parser.parse_args()

    now = datetime.now()

    print()
    print("=" * 66)
    print("  BLUELOTUS MID — ECE Named Events Seeder v1.0")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Events to seed : {len(EVENTS)}")
    print(f"  Mode           : {'DRY RUN' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 66)

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        _info(f".env loaded from {env_path}")

    # ── Seed ──────────────────────────────────────────────────────────────────
    _section("Seeding ece_named_events")
    inserted, updated, failed = seed_events(EVENTS, dry_run=args.dry_run)

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify and not args.dry_run:
        _section("Verification — ece_named_events contents")
        conn = _get_conn()
        cur  = conn.cursor(dictionary=True)
        verify_seed(cur)
        cur.close()
        conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — ECE Named Events Seeder v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    if not args.dry_run:
        print(f"  Inserted : {inserted}")
        print(f"  Updated  : {updated}")
        print(f"  Failed   : {failed}")
    print()
    print("  NEXT STEPS:")
    print("  1. python mid\\fetch_tech_publications.py")
    print("     → Populates tech_publication_signals from 8 free RSS feeds")
    print("  2. python mid\\fetch_conference_calendar.py")
    print("     → Populates conference_calendar")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
