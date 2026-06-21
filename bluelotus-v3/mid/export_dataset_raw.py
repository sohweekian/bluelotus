"""
BlueLotus Digital Institution -- V2.0
mid/export_dataset_raw.py v1.0

Purpose
-------
Export a single consolidated dataset_raw.json from raw_signal_archive
for consumption by claude_analyst.py and the frontend dashboard.

This is a focused, fast export — one file, one purpose.
It does NOT replace the full diagnostic exporters (export_mid_raw_json.py,
export_bluelotus_intelligence_snapshot.py). Those remain for audit/debug use.

Output
------
  data/frontend/dataset_raw.json

Structure
---------
{
  "meta": {
    "generated_at": "...",
    "ingest_version": "v2.6",
    "sources_expected": 50,
    "sources_active": N,
    "total_signals": N,
    "latest_signal_at": "...",
    "export_version": "v1.0"
  },
  "regime": { ... },          -- latest Regime_Detection record (parsed)
  "portfolio": { ... },       -- latest Portfolio_Snapshot record (parsed)
  "live_prices": { ... },     -- latest LivePrices_Moomoo record (parsed)
  "fear_greed": { ... },      -- latest CNN_FearGreed record (parsed)
  "analyst_targets": { ... }, -- all Analyst_Targets records (parsed)
  "moomoo_intel": [ ... ],    -- latest Moomoo_Intel signals (raw_text lines)
  "event_correlations": [...],-- latest Event_Correlation records (parsed)
  "signals": {                -- per-source, latest N signals each
    "Fed_Press":   [ {id, received_at, raw_text, quality_score, source_url}, ... ],
    "FT_Economy":  [ ... ],
    ...
  }
}

Doctrine
--------
  Database is private. Python extracts. JSON publishes. HTML displays.
  This script is READ-ONLY. No INSERT, UPDATE, or DELETE.

Run
---
  cd C:\\bluelotus2
  python mid\\export_dataset_raw.py

Environment variables (from .env)
----------------------------------
  MYSQL_HOST / DB_HOST         (default: 127.0.0.1)
  MYSQL_PORT / DB_PORT         (default: 3306)
  MYSQL_USER / DB_USER         (required)
  MYSQL_PASSWORD / DB_PASSWORD (default: "")
  MYSQL_DATABASE / DB_NAME     (required)

Optional overrides
------------------
  BL_RAW_SIGNALS_PER_SOURCE    signals per source (default: 10)
  BL_RAW_LATEST_LIMIT          signals in signals_latest (default: 200)

CIO:    Kian Soh
Author: Claude -- Market Intelligence Department
Date:   May 2026
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from ticker_universe import ETF_TICKERS as CENTRAL_ETF_TICKERS, NASDAQ_TICKERS as CENTRAL_NASDAQ_TICKERS

PROJECT_ROOT_PATH = Path(r"C:\bluelotus3")
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

try:
    from canonical.canonical_data_contract import build_v3_1_to_v3_4_payload
except Exception:
    build_v3_1_to_v3_4_payload = None

try:
    from db_efficiency.public_dataset import build_public_dataset
except Exception:
    build_public_dataset = None

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

EXPORT_VERSION      = "v2.0u"  # v2.0u: adds portfolio_readonly, historical risk model,
                               # thesis lifecycle, monitoring/audit/lineage blocks.
                               # v1.9u: adds compact P1/P2/P3 priority_intelligence export blocks
                               # v1.8u: WSJ/FT added, Reuters fixed, DEFECT-07/08 Phase 1.5
                               #       Added: conference_calendar, ceo_appearances,
                               #       catalyst_calendar, tech_pub_signals, ece_named_events
INGEST_VERSION      = "v2.6"
EXPORT_FILENAME     = "dataset_raw.json"
SIGNALS_PER_SOURCE  = int(os.getenv("BL_RAW_SIGNALS_PER_SOURCE", "10"))
LATEST_LIMIT        = int(os.getenv("BL_RAW_LATEST_LIMIT", "200"))
PROJECT_ROOT        = Path(r"C:\bluelotus3")
AUDIT_DIR           = PROJECT_ROOT / "data" / "audit"
DETERMINISTIC_OPERATORS_LATEST = AUDIT_DIR / "deterministic_operators_latest.json"

# 54 sources as of ingest_u.py v2.6u (WSJ_Markets/Technology added, Reuters URLs fixed 03 Jun 2026)
SOURCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tier 1 -- Official Central Banks & Government
    "Fed_Press":               {"tier": 1, "trust": 0.98, "signal_type": "macro"},
    "Fed_Speeches":            {"tier": 1, "trust": 0.97, "signal_type": "macro"},
    "Fed_FOMC_Minutes":        {"tier": 1, "trust": 0.98, "signal_type": "macro"},
    "ECB_Press":               {"tier": 1, "trust": 0.95, "signal_type": "macro"},
    "BIS_PressReleases":       {"tier": 1, "trust": 0.94, "signal_type": "macro"},
    "BIS_CentralBankSpeeches": {"tier": 1, "trust": 0.93, "signal_type": "macro"},
    "BOJ_Press":               {"tier": 1, "trust": 0.95, "signal_type": "macro"},
    "MAS_Press":               {"tier": 1, "trust": 0.93, "signal_type": "macro"},
    "PBOC_Policy":             {"tier": 1, "trust": 0.87, "signal_type": "macro"},
    "PBOC_LPR":                {"tier": 1, "trust": 0.88, "signal_type": "macro"},
    "PBOC_CNY":                {"tier": 1, "trust": 0.86, "signal_type": "geopolitical"},
    "WorldBank_Macro":         {"tier": 1, "trust": 0.93, "signal_type": "macro"},
    "BLS_API":                 {"tier": 1, "trust": 0.97, "signal_type": "macro"},
    "BEA_GDP_PCE":             {"tier": 1, "trust": 0.97, "signal_type": "macro"},
    "SEC_EDGAR_8K":            {"tier": 1, "trust": 0.96, "signal_type": "earnings"},
    # Tier 1 -- Commodity & Market Data
    "EIA_Petroleum":           {"tier": 1, "trust": 0.96, "signal_type": "commodity"},
    "EIA_NatGas":              {"tier": 1, "trust": 0.96, "signal_type": "commodity"},
    "CFTC_COT":                {"tier": 1, "trust": 0.95, "signal_type": "sentiment"},
    "USDA_WASDE":              {"tier": 1, "trust": 0.85, "signal_type": "commodity"},
    # Tier 1 -- Geopolitical
    "IAEA_News":               {"tier": 1, "trust": 0.88, "signal_type": "geopolitical"},
    "OPEC_News":               {"tier": 1, "trust": 0.87, "signal_type": "commodity"},
    "IMF_News":                {"tier": 1, "trust": 0.87, "signal_type": "macro"},
    "WhiteHouse_RSS":          {"tier": 1, "trust": 0.90, "signal_type": "geopolitical"},
    "Treasury_Press":          {"tier": 1, "trust": 0.91, "signal_type": "macro"},
    "USGS_Minerals":           {"tier": 1, "trust": 0.88, "signal_type": "commodity"},
    "ArabNews_Business":       {"tier": 2, "trust": 0.78, "signal_type": "geopolitical"},
    # Tier 2 -- Journalism
    "Reuters_Business":        {"tier": 2, "trust": 0.87, "signal_type": "news"},
    "Reuters_Markets":         {"tier": 2, "trust": 0.87, "signal_type": "news"},
    "Reuters_Technology":      {"tier": 2, "trust": 0.87, "signal_type": "news"},
    "Reuters_Commodities":     {"tier": 2, "trust": 0.86, "signal_type": "commodity"},
    "CNBC_Markets":            {"tier": 2, "trust": 0.82, "signal_type": "news"},
    "CNBC_Finance":            {"tier": 2, "trust": 0.82, "signal_type": "news"},
    "CNA_Business":            {"tier": 2, "trust": 0.85, "signal_type": "news"},
    # FT direct RSS -- confirmed v2.5, active since v2.6
    "FT_Markets":              {"tier": 2, "trust": 0.88, "signal_type": "news"},
    "FT_Economy":              {"tier": 2, "trust": 0.88, "signal_type": "macro"},
    "FT_World":                {"tier": 2, "trust": 0.87, "signal_type": "geopolitical"},
    # WSJ added v2.6u -- probe_rss_news_v2.py confirmed 03 Jun 2026
    "WSJ_Markets":             {"tier": 2, "trust": 0.88, "signal_type": "news"},
    "WSJ_Technology":          {"tier": 2, "trust": 0.88, "signal_type": "news"},
    # Tier 3 -- Specialist
    "Defense_News":            {"tier": 3, "trust": 0.85, "signal_type": "geopolitical"},
    "Breaking_Defense":        {"tier": 3, "trust": 0.84, "signal_type": "geopolitical"},
    "WarOnTheRocks":           {"tier": 3, "trust": 0.85, "signal_type": "geopolitical"},
    "WorldNuclearNews":        {"tier": 3, "trust": 0.86, "signal_type": "commodity"},
    "OilPrice_RSS":            {"tier": 3, "trust": 0.78, "signal_type": "commodity"},
    "Mining_RSS":              {"tier": 3, "trust": 0.78, "signal_type": "commodity"},
    "NASA_News":               {"tier": 3, "trust": 0.88, "signal_type": "news"},
    "NASA_SpaceStation":       {"tier": 3, "trust": 0.83, "signal_type": "news"},
    "Space_Industry":          {"tier": 3, "trust": 0.75, "signal_type": "news"},
    "CNN_FearGreed":           {"tier": 3, "trust": 0.85, "signal_type": "sentiment"},
    # Tier 4 -- Velocity & Sentiment
    "MarketWatch_RSS":         {"tier": 4, "trust": 0.65, "signal_type": "sentiment"},
    "Yahoo_Finance_RSS":       {"tier": 4, "trust": 0.60, "signal_type": "sentiment"},
    "GDELT_API":               {"tier": 4, "trust": 0.72, "signal_type": "news"},
    "X_Signals":               {"tier": 4, "trust": 0.40, "signal_type": "sentiment"},
}

# Internal cognition sources -- extracted separately with full payload parsing
COGNITION_SOURCES = [
    "Regime_Detection",
    "Portfolio_Snapshot",
    "LivePrices_Moomoo",
    "CNN_FearGreed",
    "Analyst_Targets",
    "Moomoo_Intel",
    "Event_Correlation",
    "Ticker_Sentiment",
]

ETF_TICKERS = set(CENTRAL_ETF_TICKERS)

NASDAQ_TICKERS = set(CENTRAL_NASDAQ_TICKERS)

SECURITY_PROFILE_OVERRIDES: Dict[str, Dict[str, str]] = {
    "AAPL": {"sector": "Technology", "industry": "Consumer Electronics"},
    "ADBE": {"sector": "Technology", "industry": "Application Software"},
    "AMD": {"sector": "Technology", "industry": "Semiconductors"},
    "AMAT": {"sector": "Technology", "industry": "Semiconductor Equipment"},
    "AMZN": {"sector": "Consumer Cyclical", "industry": "Internet Retail"},
    "ARM": {"sector": "Technology", "industry": "Semiconductor IP"},
    "ASML": {"sector": "Technology", "industry": "Semiconductor Equipment"},
    "AVGO": {"sector": "Technology", "industry": "Semiconductors"},
    "AXON": {"sector": "Industrials", "industry": "Public Safety Technology"},
    "BAC": {"sector": "Financial Services", "industry": "Banks"},
    "CCJ": {"sector": "Energy", "industry": "Uranium"},
    "CDNS": {"sector": "Technology", "industry": "EDA Software"},
    "CRWD": {"sector": "Technology", "industry": "Cybersecurity"},
    "ENPH": {"sector": "Energy", "industry": "Solar"},
    "FCX": {"sector": "Basic Materials", "industry": "Copper"},
    "GOOGL": {"sector": "Communication Services", "industry": "Internet Content"},
    "INTC": {"sector": "Technology", "industry": "Semiconductors"},
    "IONQ": {"sector": "Technology", "industry": "Quantum Computing"},
    "JPM": {"sector": "Financial Services", "industry": "Banks"},
    "META": {"sector": "Communication Services", "industry": "Internet Content"},
    "MRVL": {"sector": "Technology", "industry": "Semiconductors"},
    "MSFT": {"sector": "Technology", "industry": "Software Infrastructure"},
    "MU": {"sector": "Technology", "industry": "Memory Semiconductors"},
    "NEM": {"sector": "Basic Materials", "industry": "Gold"},
    "NVDA": {"sector": "Technology", "industry": "Semiconductors"},
    "ORCL": {"sector": "Technology", "industry": "Software Infrastructure"},
    "PLTR": {"sector": "Technology", "industry": "Data Analytics Software"},
    "QBTS": {"sector": "Technology", "industry": "Quantum Computing"},
    "QUBT": {"sector": "Technology", "industry": "Quantum Computing"},
    "RGTI": {"sector": "Technology", "industry": "Quantum Computing"},
    "SEDG": {"sector": "Energy", "industry": "Solar"},
    "SMCI": {"sector": "Technology", "industry": "Computer Hardware"},
    "SNPS": {"sector": "Technology", "industry": "EDA Software"},
    "TSLA": {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
    "TSM": {"sector": "Technology", "industry": "Semiconductors"},
    "WFC": {"sector": "Financial Services", "industry": "Banks"},
    "AU": {"sector": "Basic Materials", "industry": "Gold"},
    "AEM": {"sector": "Basic Materials", "industry": "Gold"},
    "B": {"sector": "Basic Materials", "industry": "Gold"},
    "VIXY": {"sector": "VOLATILITY", "industry": "VOLATILITY_ETP"},
}

SECURITY_THEME_PROFILE_GROUPS: Dict[Tuple[str, str], set] = {
    ("Technology", "Semiconductors / AI Infrastructure"): {
        "NVDA", "AMD", "AVGO", "MRVL", "MU", "TSM", "AMAT", "ARM",
        "CDNS", "SNPS", "INTC", "AMKR", "ASML", "QCOM", "TXN", "LRCX",
        "KLAC", "DELL", "SMCI", "VRT", "ANET",
    },
    ("Technology", "Software / Cybersecurity"): {
        "MSFT", "ORCL", "CRM", "NOW", "ADBE", "FTNT", "ZS", "INTU",
        "SNOW", "OKTA", "S", "CRWD", "PANW", "PLTR",
    },
    ("Communication Services", "Internet / Media Platforms"): {
        "GOOGL", "META", "NFLX", "DIS",
    },
    ("Consumer Cyclical", "Platform / Retail / Mobility"): {
        "AMZN", "TSLA", "UBER", "NKE", "SBUX", "TGT", "HD", "LOW", "MCD",
    },
    ("Financial Services", "Banks / Brokers / Payments / Insurance"): {
        "BAC", "WFC", "C", "SOFI", "HOOD", "COIN", "JPM", "GS", "MS",
        "BLK", "SCHW", "AXP", "CB", "MCO", "PGR", "ALL", "V", "MA",
        "PYPL", "MSTR",
    },
    ("Healthcare", "Biotech / Pharma / Managed Care"): {
        "LLY", "MRNA", "ABBV", "PFE", "JNJ", "UNH", "MRK", "AMGN",
        "BMY", "GILD", "REGN", "BIIB",
    },
    ("Industrials", "Defense / Aerospace / Space"): {
        "RTX", "NOC", "LMT", "HII", "LDOS", "BA", "LHX", "HON", "TDG",
        "HEI", "KTOS", "ASTS", "RKLB", "LUNR", "BKSY", "SATS", "RDW",
        "SIDU", "IRDM", "VSAT", "GSAT", "SPIR", "PL", "SPCE",
    },
    ("Real Estate", "Communications REIT"): {"AMT", "O"},
    ("Basic Materials", "Precious Metals"): {
        "NEM", "AU", "CDE", "HL", "AG", "PAAS",
    },
    ("Basic Materials", "Copper / Industrial Metals / Steel"): {
        "FCX", "SCCO", "BHP", "RIO", "HBM", "TECK", "VALE", "NUE",
        "AA", "CLF",
    },
    ("Basic Materials", "Agriculture / Fertilizers"): {"NTR", "MOS", "ADM"},
    ("Basic Materials", "Rare Earth / Lithium"): {"MP", "USAR", "ALB"},
    ("Utilities", "Nuclear / Grid / Power"): {
        "CEG", "VST", "OKLO", "SMR", "BWXT", "DUK", "GEV", "NEE",
        "ETN", "EMR", "AWK", "BE",
    },
    ("Energy", "Uranium"): {"CCJ", "UUUU"},
    ("Utilities", "Renewables / Solar"): {
        "ENPH", "FSLR", "FCEL", "PLUG", "SEDG", "ARRY", "RUN", "BEP",
    },
    ("Energy", "Oil / Gas / Midstream"): {
        "WMB", "KMI", "XOM", "OXY", "EOG", "FANG", "CVX", "COP", "DVN",
        "LNG", "VLO", "PSX", "MPC", "EPD", "ENB",
    },
    ("Consumer Defensive", "Staples / Retail"): {
        "KO", "PG", "WMT", "COST", "PEP", "CL",
    },
    ("Industrials", "Transport / Machinery / Logistics"): {
        "UPS", "FDX", "UNP", "CSX", "DAL", "DE", "CAT", "GE",
    },
    ("Communication Services", "Telecom"): {"VZ", "T"},
    ("Technology", "Quantum Computing"): {"IONQ", "QBTS", "QUBT", "RGTI"},
}

SECURITY_THEME_PROFILE_OVERRIDES: Dict[str, Dict[str, str]] = {}
for (_sector, _industry), _tickers in SECURITY_THEME_PROFILE_GROUPS.items():
    for _ticker in _tickers:
        SECURITY_THEME_PROFILE_OVERRIDES[_ticker] = {
            "sector": _sector,
            "industry": _industry,
        }

TICKER_ENTITY_ALIASES: Dict[str, set[str]] = {
    # Gold miners / portfolio
    "AU":    {"AU", "ANGLOGOLD", "ANGLOGOLD ASHANTI"},
    "NEM":   {"NEM", "NEWMONT"},
    "GLD":   {"GLD", "SPDR GOLD", "GOLD ETF"},
    "GDX":   {"GDX", "VANECK GOLD MINERS", "GOLD MINERS ETF"},
    "GDXJ":  {"GDXJ", "VANECK JUNIOR GOLD MINERS", "JUNIOR GOLD MINERS"},
    # Quantum / portfolio
    "QBTS":  {"QBTS", "D-WAVE", "D WAVE"},
    "QUBT":  {"QUBT", "QUANTUM COMPUTING INC", "QUANTUM COMPUTING"},
    "IONQ":  {"IONQ", "IONQ INC"},
    "RGTI":  {"RGTI", "RIGETTI", "RIGETTI COMPUTING"},
    # Space / portfolio
    "ASTS":  {"ASTS", "AST SPACEMOBILE", "SPACEMOBILE"},
    "RKLB":  {"RKLB", "ROCKET LAB"},
    "PL":    {"PL", "PLANET LABS", "PLANET"},
    "LUNR":  {"LUNR", "INTUITIVE MACHINES"},
    # Mega-cap tech — known regression failure: Meta headlines assigned to GOOGL/MSFT
    "NVDA":  {"NVDA", "NVIDIA"},
    "GOOGL": {"GOOGL", "GOOG", "ALPHABET", "GOOGLE"},
    "MSFT":  {"MSFT", "MICROSOFT"},
    "AAPL":  {"AAPL", "APPLE INC", "APPLE"},
    "META":  {"META", "META PLATFORMS", "FACEBOOK"},
    "AMZN":  {"AMZN", "AMAZON"},
    "TSLA":  {"TSLA", "TESLA"},
    # Banks — known regression failure: WFC barbecue / BAC DraftKings
    "WFC":   {"WFC", "WELLS FARGO"},
    "BAC":   {"BAC", "BANK OF AMERICA", "BOFA", "BOFА"},
    "JPM":   {"JPM", "JPMORGAN", "JP MORGAN", "CHASE"},
    "GS":    {"GS", "GOLDMAN SACHS", "GOLDMAN"},
    "MS":    {"MS", "MORGAN STANLEY"},
    "C":     {"C", "CITIGROUP", "CITI"},
}

MACRO_EVENT_RISKS = [
    {"category": "Macro catalysts", "event": "BOJ June 16 event risk", "event_date": "2026-06-16", "impact_class": "MACRO_RATE_FX"},
    {"category": "Macro catalysts", "event": "FOMC June 16-17 risk", "event_date": "2026-06-16", "impact_class": "MACRO_RATE"},
    {"category": "Macro catalysts", "event": "Fed press conference", "event_date": "2026-06-17", "impact_class": "MACRO_RATE"},
    {"category": "Geopolitical catalysts", "event": "Yen carry-trade unwind risk", "event_date": "2026-06-16", "impact_class": "FX_LIQUIDITY"},
    {"category": "Liquidity / IPO catalysts", "event": "SpaceX / SPCX liquidity-drain risk", "event_date": "2026-06-16", "impact_class": "LIQUIDITY_PRIVATE_MARKET"},
]

SOURCE_TYPE_SLA_MINUTES = {
    "macro": 1440,
    "commodity": 1440,
    "earnings": 1440,
    "geopolitical": 360,
    "news": 360,
    "sentiment": 180,
}

SOURCE_SLA_OVERRIDES_MINUTES = {
    # Scheduled / low-frequency official sources.
    "BEA_GDP_PCE": 45 * 1440,
    "Fed_FOMC_Minutes": 45 * 1440,
    "WorldBank_Macro": 30 * 1440,
    "CFTC_COT": 10 * 1440,
    "EIA_NatGas": 10 * 1440,
    "EIA_Petroleum": 10 * 1440,
    "USDA_WASDE": 35 * 1440,
    "BLS_API": 35 * 1440,
    "SEC_EDGAR_8K": 7 * 1440,
    # Central-bank and official press feeds are event-driven, not hourly feeds.
    "BIS_CentralBankSpeeches": 7 * 1440,
    "BIS_PressReleases": 14 * 1440,
    "ECB_Press": 7 * 1440,
    "Fed_Press": 7 * 1440,
    "Fed_Speeches": 7 * 1440,
    "MAS_Press": 14 * 1440,
    "BOJ_Press": 14 * 1440,
    "PBOC_LPR": 35 * 1440,
    "WorldNuclearNews": 7 * 1440,
    # Market sentiment is not actionable while US cash market is closed.
    "CNN_FearGreed": 3 * 1440,
}

WEEKEND_GRACE_SIGNAL_TYPES = {"news", "geopolitical", "sentiment"}
WEEKEND_GRACE_MINUTES = 24 * 60

MARKET_CLOSED_FRESHNESS_GRACE_MINUTES = 72 * 60
MARKET_CLOSED_GRACE_SECTIONS = {
    "live_prices",
    "fear_greed",
    "ticker_sentiment",
    "capital_flow",
}

PORTFOLIO_CONSTRAINTS_DEFAULT = {
    "source": "export_dataset_raw.py",
    "version": "v0.1",
    "max_single_name_weight": 0.30,
    "max_theme_weight": 0.45,
    "min_cash_weight": 0.05,
    "max_unclassified_weight": 0.20,
    "max_position_daily_volume_pct": 0.10,
    "notes": "Risk-control defaults for reporting and institutional readiness checks; not an order instruction.",
}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DEFECT-03 FIX: Single freshness engine — meta.freshness is authoritative.
# _add_fg_staleness() second engine removed per WO-RD-20260603-001 Option A.
# This function now strips the independent stale/age fields from the
# fear_greed object so consumers read only meta.freshness for staleness.
# ---------------------------------------------------------------------------
def _add_fg_staleness(fg: Any) -> Any:
    """Strip independent staleness fields — meta.freshness is authoritative."""
    if not isinstance(fg, dict):
        return fg
    # Remove fields from the old second engine to prevent contradiction
    for key in ("stale", "age_hours", "stale_threshold_hours"):
        fg.pop(key, None)
    return fg


# ---------------------------------------------------------------------------
# BUG-010: Section freshness grading helper
# ---------------------------------------------------------------------------
def _compute_freshness(sections: dict) -> dict:
    """
    Compute age_minutes and freshness grade for each dataset section.
    Grade thresholds (minutes):
      FRESH          : <= 60
      SAME_DAY_STALE : <= 480
      STALE          : > 480

    BUG-MID-004 FIX: UTC vs SGT timezone confusion.
    ingest.py writes all DB timestamps as local SGT time (naive datetime, no tzinfo).
    Previous code used datetime.now(timezone.utc).replace(tzinfo=None) as "now",
    which is 8 hours BEHIND SGT — making SGT timestamps appear 8h in the future,
    producing negative age_minutes and incorrect FRESH grades for all sources.
    Fix: use datetime.now() (local wall-clock time = SGT on the Singapore server)
    to match the timezone convention used by ingest.py when writing timestamps.
    Validation: age_minutes must be >= 0; negative values raise a warning and
    force grade = UNKNOWN to prevent false FRESH classification.
    """
    THRESHOLDS = {
        "FRESH": 60,
        "SAME_DAY_STALE": 480,
        "MARKET_CLOSED_OK": MARKET_CLOSED_FRESHNESS_GRACE_MINUTES,
        "STALE": 9999,
    }
    # BUG-MID-004 FIX: use local time (SGT) — matches ingest.py timestamp convention
    now = datetime.now()
    result = {}
    for section, ts_str in sections.items():
        if not ts_str:
            result[section] = {"age_minutes": None, "grade": "UNKNOWN"}
            continue
        try:
            ts_clean = str(ts_str).replace("+00:00","").replace("Z","")[:19]
            dt = datetime.fromisoformat(ts_clean)
            age_m = int((now - dt).total_seconds() / 60)
            # BUG-MID-004 FIX: negative age_minutes = timestamp in future = timezone error
            # Block FRESH grade; expose the anomaly for pipeline diagnosis
            if age_m < 0:
                result[section] = {
                    "age_minutes": age_m,
                    "grade": "UNKNOWN",
                    "warning": f"negative_age_minutes: timestamp appears {abs(age_m)}m in the future — possible timezone mismatch"
                }
                continue
            if age_m <= 60:
                grade = "FRESH"
            elif age_m <= 480:
                grade = "SAME_DAY_STALE"
            elif (
                section in MARKET_CLOSED_GRACE_SECTIONS
                and now.weekday() >= 5
                and age_m <= MARKET_CLOSED_FRESHNESS_GRACE_MINUTES
            ):
                grade = "MARKET_CLOSED_OK"
            else:
                grade = "STALE"
            item = {"age_minutes": age_m, "grade": grade}
            if grade == "MARKET_CLOSED_OK":
                item["note"] = "Weekend/closed-market grace window; not an actionable freshness breach."
            result[section] = item
        except Exception:
            result[section] = {"age_minutes": None, "grade": "UNKNOWN"}
    result["thresholds"] = THRESHOLDS
    return result


def _project_root() -> Path:
    p = Path.cwd()
    if (p / "core").exists() or (p / "mid").exists():
        return p
    if p.name.lower() == "mid":
        return p.parent
    return p


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except Exception:
            return obj.hex()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _parse_payload(value: Any) -> Any:
    """Attempt to parse raw_payload as JSON; return as-is if not parseable."""
    if value is None:
        return None
    value = _json_safe(value)
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if (s.startswith("{") and s.endswith("}")) or \
           (s.startswith("[") and s.endswith("]")):
            try:
                return _json_safe(json.loads(s))
            except Exception:
                pass
    return value


def _parse_published_at(row: Dict[str, Any]) -> Optional[str]:
    """Extract the RSS pubDate from raw_payload and return as ISO-8601 UTC string."""
    payload = row.get("raw_payload")
    if not payload:
        return None
    if isinstance(payload, str):
        try:
            import json as _json
            payload = _json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    pub = payload.get("published") or payload.get("pubDate") or payload.get("pub_date")
    if not pub:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(pub))
        # Normalise to UTC naive ISO string so comparisons are timezone-consistent
        import datetime as _dt
        utc = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return utc.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _signal_row(row: Dict[str, Any], ts_col: str) -> Dict[str, Any]:
    """Compact a raw_signal_archive row into the standard export shape."""
    return {
        "id":               row.get("id"),
        "received_at":      _json_safe(row.get(ts_col)),
        "published_at":     _parse_published_at(row),   # RSS pubDate (UTC ISO); None if absent
        "source":           row.get("source"),
        "signal_type":      row.get("signal_type"),
        "quality_score":    _json_safe(row.get("quality_score")),
        "raw_text":         row.get("raw_text"),
        "source_url":       row.get("source_url"),
        "source_feed":      row.get("source_feed"),
    }


def _q(cur, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def _scalar(cur, sql: str, params: tuple = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(dict(row).values())) if isinstance(row, dict) else row[0]


def _table_cols(cur, table: str) -> List[str]:
    cur.execute(f"DESCRIBE {table}")
    rows = cur.fetchall()
    return [
        (r.get("Field") or r.get("field") or next(iter(r.values())))
        if isinstance(r, dict) else r[0]
        for r in rows
    ]


def _pick(cols: List[str], candidates: List[str]) -> Optional[str]:
    low = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    return None


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table,),
    )
    row = cur.fetchone()
    if not row:
        return False
    return bool((row.get("n") if isinstance(row, dict) else row[0]) or 0)


def _sql_ident(identifier: str) -> str:
    """Backtick a DB identifier discovered from DESCRIBE/table allowlists."""
    return "`" + str(identifier).replace("`", "``") + "`"


def _fetch_p1_earnings_intelligence(cur) -> Dict[str, Any]:
    """Daily P1 block: compact earnings/catalyst data, not raw histories."""
    block: Dict[str, Any] = {
        "priority": "P1",
        "name": "earnings_calendar_and_surprise",
        "daily_export": True,
        "source_tables": [],
        "status": "not_populated",
        "policy": "export compact upcoming/recent rows only",
        "window_days_forward": 45,
        "window_days_back": 3,
        "catalysts": [],
        "earnings_estimates": [],
        "source_errors": [],
        "summary": {
            "upcoming_7d": 0,
            "upcoming_14d": 0,
            "upcoming_45d": 0,
            "imminent_count": 0,
            "confirmed_count": 0,
            "surprise_rows": 0,
        },
    }

    if _table_exists(cur, "portfolio_catalyst_calendar"):
        block["source_tables"].append("portfolio_catalyst_calendar")
        try:
            rows = _q(cur, """
                SELECT ticker, catalyst_type, catalyst_date, catalyst_time_et,
                       is_confirmed, is_estimate,
                       event_name, eps_estimate, eps_prior, revenue_estimate,
                       in_portfolio, has_working_order,
                       days_until_catalyst, alert_flag,
                       source, snapshot_date
                FROM portfolio_catalyst_calendar
                WHERE catalyst_type = 'EARNINGS'
                  AND catalyst_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 3 DAY)
                                      AND DATE_ADD(CURDATE(), INTERVAL 45 DAY)
                ORDER BY catalyst_date ASC, ticker ASC
                LIMIT 250
            """)
            block["catalysts"] = [_json_safe(r) for r in rows]
        except Exception as e:
            block["source_errors"].append({"table": "portfolio_catalyst_calendar", "error": str(e)})

    if _table_exists(cur, "ticker_earnings"):
        block["source_tables"].append("ticker_earnings")
        try:
            rows = _q(cur, """
                SELECT ticker, next_earnings_date, days_to_earnings,
                       earnings_quarter, earnings_time,
                       eps_estimate, eps_estimate_high, eps_estimate_low,
                       revenue_estimate, eps_actual_last, eps_surprise_pct,
                       revenue_actual_last, source, snapshot_date
                FROM ticker_earnings
                WHERE next_earnings_date BETWEEN CURDATE()
                                            AND DATE_ADD(CURDATE(), INTERVAL 45 DAY)
                ORDER BY next_earnings_date ASC, ticker ASC
                LIMIT 250
            """)
            block["earnings_estimates"] = [_json_safe(r) for r in rows]
        except Exception as e:
            block["source_errors"].append({"table": "ticker_earnings", "error": str(e)})

    catalysts = block.get("catalysts", [])
    estimates = block.get("earnings_estimates", [])
    all_days = [
        r.get("days_until_catalyst")
        for r in catalysts
        if isinstance(r.get("days_until_catalyst"), int)
    ] + [
        r.get("days_to_earnings")
        for r in estimates
        if isinstance(r.get("days_to_earnings"), int)
    ]
    block["summary"] = {
        "upcoming_7d": len([d for d in all_days if 0 <= d <= 7]),
        "upcoming_14d": len([d for d in all_days if 0 <= d <= 14]),
        "upcoming_45d": len([d for d in all_days if 0 <= d <= 45]),
        "imminent_count": len([r for r in catalysts if str(r.get("alert_flag", "")).upper() == "IMMINENT"]),
        "confirmed_count": len([r for r in catalysts if bool(r.get("is_confirmed"))]),
        "surprise_rows": len([r for r in estimates if r.get("eps_surprise_pct") is not None]),
    }
    if catalysts or estimates:
        block["status"] = "active"
    elif block["source_tables"]:
        block["status"] = "no_current_rows"
    return block


def _fetch_p2_transcript_thesis_confirmation(cur) -> Dict[str, Any]:
    """Daily P2 block: transcript-derived thesis confirmations only."""
    block: Dict[str, Any] = {
        "priority": "P2",
        "name": "transcript_thesis_confirmation",
        "daily_export": True,
        "source_tables": [],
        "status": "not_populated",
        "policy": "export summaries/evidence pointers only; raw transcripts stay in DB",
        "confirmations": [],
        "source_errors": [],
    }
    for table in (
        "transcript_thesis_confirmation",
        "earnings_transcript_thesis",
        "ticker_transcript_thesis",
    ):
        if not _table_exists(cur, table):
            continue
        block["source_tables"].append(table)
        try:
            cols = _table_cols(cur, table)
            wanted = {
                "ticker": _pick(cols, ["ticker", "symbol"]),
                "event_date": _pick(cols, ["transcript_date", "earnings_date", "event_date", "published_at", "created_at"]),
                "quarter": _pick(cols, ["fiscal_quarter", "earnings_quarter", "quarter"]),
                "thesis_status": _pick(cols, ["thesis_status", "confirmation_label", "confirmation_status", "status"]),
                "confirmation_score": _pick(cols, ["confirmation_score", "thesis_score", "score"]),
                "confidence": _pick(cols, ["confidence", "confidence_score"]),
                "summary": _pick(cols, ["summary", "thesis_summary", "management_summary"]),
                "evidence": _pick(cols, ["evidence", "evidence_summary", "key_quotes", "supporting_evidence"]),
                "risk_flags": _pick(cols, ["risk_flags", "contradictions", "bear_points"]),
                "source_ref": _pick(cols, ["transcript_id", "source_ref", "source_url", "url"]),
            }
            selected = [(alias, col) for alias, col in wanted.items() if col]
            if not selected:
                continue
            select_sql = ", ".join(f"{_sql_ident(col)} AS {_sql_ident(alias)}" for alias, col in selected)
            order_col = wanted.get("event_date") or selected[0][1]
            rows = _q(cur, f"""
                SELECT {select_sql}
                FROM {_sql_ident(table)}
                ORDER BY {_sql_ident(order_col)} DESC
                LIMIT 80
            """)
            block["confirmations"].extend(_json_safe(rows))
        except Exception as e:
            block["source_errors"].append({"table": table, "error": str(e)})
    if block["confirmations"]:
        block["status"] = "active"
    elif block["source_tables"]:
        block["status"] = "no_current_rows"
    return block


def _fetch_p3_etf_exposure_decomposition(cur, security_master: Dict[str, Any]) -> Dict[str, Any]:
    """Daily P3 block: compact ETF look-through exposure; full holdings stay in DB."""
    tracked_etfs = sorted(
        t for t, rec in (security_master or {}).items()
        if t in ETF_TICKERS or (isinstance(rec, dict) and rec.get("asset_type") == "ETF")
    )
    block: Dict[str, Any] = {
        "priority": "P3",
        "name": "etf_exposure_decomposition",
        "daily_export": True,
        "source_tables": [],
        "status": "tracked_only" if tracked_etfs else "not_populated",
        "policy": "export tracked ETFs and top holdings only; full constituents stay in DB",
        "tracked_etfs": tracked_etfs,
        "top_holdings_by_etf": {},
        "source_errors": [],
    }
    for table in ("etf_exposure_decomposition", "etf_holdings", "etf_constituents"):
        if not _table_exists(cur, table):
            continue
        block["source_tables"].append(table)
        try:
            cols = _table_cols(cur, table)
            wanted = {
                "etf": _pick(cols, ["etf_ticker", "etf_symbol", "fund_ticker", "ticker"]),
                "holding": _pick(cols, ["holding_ticker", "constituent_ticker", "underlying_ticker", "symbol"]),
                "holding_name": _pick(cols, ["holding_name", "constituent_name", "name", "company_name"]),
                "weight_pct": _pick(cols, ["weight_pct", "weight", "holding_weight_pct", "market_value_weight"]),
                "sector": _pick(cols, ["sector", "holding_sector"]),
                "snapshot_date": _pick(cols, ["snapshot_date", "as_of_date", "fetched_at", "updated_at"]),
            }
            selected = [(alias, col) for alias, col in wanted.items() if col]
            if not wanted["etf"] or not wanted["holding"] or not selected:
                continue
            select_sql = ", ".join(f"{_sql_ident(col)} AS {_sql_ident(alias)}" for alias, col in selected)
            order_parts = []
            if wanted["snapshot_date"]:
                order_parts.append(f"{_sql_ident(wanted['snapshot_date'])} DESC")
            order_parts.append(f"{_sql_ident(wanted['etf'])} ASC")
            if wanted["weight_pct"]:
                order_parts.append(f"{_sql_ident(wanted['weight_pct'])} DESC")
            rows = _q(cur, f"""
                SELECT {select_sql}
                FROM {_sql_ident(table)}
                ORDER BY {", ".join(order_parts)}
                LIMIT 500
            """)
            for row in _json_safe(rows):
                etf = str(row.get("etf") or "").upper()
                if not etf:
                    continue
                bucket = block["top_holdings_by_etf"].setdefault(etf, [])
                if len(bucket) < 10:
                    bucket.append(row)
        except Exception as e:
            block["source_errors"].append({"table": table, "error": str(e)})
    if block["top_holdings_by_etf"]:
        block["status"] = "active"
    return block


def _build_priority_intelligence(cur, security_master: Dict[str, Any]) -> Dict[str, Any]:
    """P1/P2/P3 daily export; P4/P5 are intentionally database-only."""
    return {
        "version": "v0.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "daily_export_priorities": ["P1", "P2", "P3"],
        "database_only_priorities": ["P4", "P5"],
        "noise_control": {
            "P4_social_sentiment": "database_only_unless_explicitly_requested",
            "P5_deep_factor_history": "database_only_unless_explicitly_requested",
            "reason": "avoid polluting the daily intelligence engine with noisy or heavy historical data",
        },
        "P1": _fetch_p1_earnings_intelligence(cur),
        "P2": _fetch_p2_transcript_thesis_confirmation(cur),
        "P3": _fetch_p3_etf_exposure_decomposition(cur, security_master),
    }


def _latest_institutional_quant_layer(cur) -> Dict[str, Any]:
    """Return the latest completed institutional quant run, if configured."""
    required = (
        "institutional_quant_runs",
        "institutional_quant_process_results",
    )
    if not all(_table_exists(cur, t) for t in required):
        return {
            "status": "not_configured",
            "reason": "institutional quant process tables have not been created",
        }

    rows = _q(cur, """
        SELECT *
        FROM institutional_quant_runs
        WHERE run_status LIKE 'COMPLETED%'
        ORDER BY completed_at DESC, id DESC
        LIMIT 1
    """)
    if not rows:
        return {
            "status": "no_completed_run",
            "reason": "no institutional quant process run has been stored yet",
        }

    run = _json_safe(rows[0])
    process_rows = _q(cur, """
        SELECT process_name, process_version, process_status,
               readiness_score, readiness_label,
               result_json, metrics_json, warnings_json, created_at
        FROM institutional_quant_process_results
        WHERE run_id = %s
        ORDER BY readiness_score ASC, process_name ASC
    """, (run.get("run_id"),))

    processes = {}
    for row in process_rows:
        row = _json_safe(row)
        name = row.pop("process_name")
        processes[name] = {
            "process_version": row.get("process_version"),
            "status": row.get("process_status"),
            "readiness_score": row.get("readiness_score"),
            "readiness_label": row.get("readiness_label"),
            "result": _parse_payload(row.get("result_json")),
            "metrics": _parse_payload(row.get("metrics_json")),
            "warnings": _parse_payload(row.get("warnings_json")) or [],
            "created_at": row.get("created_at"),
        }

    return {
        "status": run.get("run_status"),
        "run_id": run.get("run_id"),
        "run_version": run.get("run_version"),
        "completed_at": run.get("completed_at"),
        "snapshot_id": run.get("snapshot_id"),
        "dataset_generated_at": run.get("dataset_generated_at"),
        "dataset_export_version": run.get("dataset_export_version"),
        "dataset_ingest_version": run.get("dataset_ingest_version"),
        "dataset_sha256": run.get("dataset_sha256"),
        "readiness_score": run.get("readiness_score"),
        "readiness_label": run.get("readiness_label"),
        "summary": _parse_payload(run.get("summary_json")) or {},
        "processes": processes,
    }


def _latest_research_forecasting_layer(cur) -> Dict[str, Any]:
    """Return latest compact BlueLotus forecast/Brier layer for daily reporting."""
    if not _table_exists(cur, "ticker_forecasts"):
        return {
            "status": "not_configured",
            "reason": "ticker_forecasts table has not been created",
        }

    rows = _q(cur, """
        SELECT snapshot_id, forecast_date, dataset_generated_at, dataset_sha256,
               COUNT(*) AS forecast_count,
               COUNT(DISTINCT ticker) AS ticker_count,
               COUNT(DISTINCT prediction_method) AS method_count
        FROM ticker_forecasts
        GROUP BY snapshot_id, forecast_date, dataset_generated_at, dataset_sha256
        ORDER BY forecast_date DESC, snapshot_id DESC
        LIMIT 1
    """)
    if not rows:
        return {
            "status": "no_forecasts",
            "reason": "no BlueLotus forecasts have been stored yet",
        }

    latest = _json_safe(rows[0])
    snapshot_id = latest.get("snapshot_id")
    forecast_rows = _q(cur, """
        SELECT forecast_id, ticker, prediction_method, forecast_direction,
               current_price,
               target_price_7d, target_price_14d, target_price_30d,
               target_price_60d, target_price_90d,
               probability_7d, probability_14d, probability_30d,
               probability_60d, probability_90d,
               expected_return_7d, expected_return_14d, expected_return_30d,
               expected_return_60d, expected_return_90d,
               confidence, bluelotus_score, analyst_target, analyst_upside_pct,
               regime, sector_theme, method_basis, risk_notes
        FROM ticker_forecasts
        WHERE snapshot_id = %s
        ORDER BY ticker ASC, prediction_method ASC
        LIMIT 600
    """, (snapshot_id,))

    forecasts_by_ticker: Dict[str, Any] = {}
    top_bluelotus = []
    for row in _json_safe(forecast_rows):
        ticker = str(row.get("ticker") or "").upper()
        method = str(row.get("prediction_method") or "")
        if not ticker or not method:
            continue
        compact = {
            "forecast_id": row.get("forecast_id"),
            "direction": row.get("forecast_direction"),
            "current_price": row.get("current_price"),
            "target_price_7d": row.get("target_price_7d"),
            "target_price_14d": row.get("target_price_14d"),
            "target_price_30d": row.get("target_price_30d"),
            "target_price_60d": row.get("target_price_60d"),
            "target_price_90d": row.get("target_price_90d"),
            "probability_7d": row.get("probability_7d"),
            "probability_14d": row.get("probability_14d"),
            "probability_30d": row.get("probability_30d"),
            "probability_60d": row.get("probability_60d"),
            "probability_90d": row.get("probability_90d"),
            "expected_return_7d": row.get("expected_return_7d"),
            "expected_return_14d": row.get("expected_return_14d"),
            "expected_return_30d": row.get("expected_return_30d"),
            "expected_return_60d": row.get("expected_return_60d"),
            "expected_return_90d": row.get("expected_return_90d"),
            "confidence": row.get("confidence"),
            "bluelotus_score": row.get("bluelotus_score"),
            "analyst_target": row.get("analyst_target"),
            "analyst_upside_pct": row.get("analyst_upside_pct"),
            "regime": row.get("regime"),
            "sector_theme": row.get("sector_theme"),
            "method_basis": row.get("method_basis"),
            "risk_notes": row.get("risk_notes"),
        }
        forecasts_by_ticker.setdefault(ticker, {})[method] = compact
        if method == "BLUELOTUS_CONSERVATIVE":
            top_bluelotus.append({
                "ticker": ticker,
                "direction": compact["direction"],
                "current_price": compact["current_price"],
                "target_price_90d": compact["target_price_90d"],
                "expected_return_90d": compact["expected_return_90d"],
                "probability_90d": compact["probability_90d"],
                "confidence": compact["confidence"],
                "sector_theme": compact["sector_theme"],
            })

    top_bluelotus.sort(key=lambda r: abs(_num(r.get("expected_return_90d"), 0) or 0), reverse=True)

    accuracy_summary = []
    if _table_exists(cur, "forecast_resolutions"):
        accuracy_summary = _json_safe(_q(cur, """
            SELECT prediction_method, horizon_days,
                   COUNT(*) AS resolved_count,
                   AVG(brier_score) AS avg_brier_score,
                   AVG(percentage_error) AS avg_percentage_error,
                   AVG(directional_correct) AS directional_accuracy
            FROM forecast_resolutions
            GROUP BY prediction_method, horizon_days
            ORDER BY horizon_days ASC, avg_brier_score ASC
        """))

    return {
        "status": "operational",
        "version": "v1.0",
        "source": "BlueLotus_Superforecast_Engine",
        "snapshot_id": latest.get("snapshot_id"),
        "forecast_date": latest.get("forecast_date"),
        "dataset_generated_at": latest.get("dataset_generated_at"),
        "dataset_sha256": latest.get("dataset_sha256"),
        "forecast_count": latest.get("forecast_count"),
        "ticker_count": latest.get("ticker_count"),
        "method_count": latest.get("method_count"),
        "methods": sorted({str(r.get("prediction_method")) for r in forecast_rows if r.get("prediction_method")}),
        "horizons_days": [7, 14, 30, 60, 90],
        "house_method": "BLUELOTUS_CONSERVATIVE",
        "benchmark_method": "ANALYST_CONSENSUS",
        "brier_status": "resolved_history_available" if accuracy_summary else "collecting",
        "accuracy_summary": accuracy_summary,
        "top_bluelotus_90d": top_bluelotus[:25],
        "forecasts_by_ticker": forecasts_by_ticker,
        "doctrine": "BlueLotus is the house method; analyst consensus is measured as benchmark opponent. Forecasts are research records, not CIO execution orders.",
    }


def _latest_portfolio_readonly_layer(cur) -> Dict[str, Any]:
    """Return latest read-only broker portfolio snapshot from dedicated tables."""
    if not (_table_exists(cur, "portfolio_readonly_snapshots") and _table_exists(cur, "portfolio_readonly_positions")):
        return {"status": "not_configured", "reason": "portfolio_readonly tables have not been created"}
    rows = _q(cur, """
        SELECT *
        FROM portfolio_readonly_snapshots
        ORDER BY cycle_ts DESC, id DESC
        LIMIT 1
    """)
    if not rows:
        return {"status": "no_snapshot", "reason": "no read-only portfolio snapshot stored yet"}
    snap = _json_safe(rows[0])
    snapshot_id = snap.get("snapshot_id")
    pos_rows = _json_safe(_q(cur, """
        SELECT ticker, code, qty, average_cost, cost_price, diluted_cost,
               price, market_value, cost_basis, unrealized_pnl,
               unrealized_pnl_pct, day_change_pct
        FROM portfolio_readonly_positions
        WHERE snapshot_id = %s
        ORDER BY market_value DESC, ticker ASC
    """, (snapshot_id,)))
    positions = {}
    for row in pos_rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            positions[ticker] = row
    return {
        "status": "operational",
        "version": "v1.0",
        "snapshot_id": snapshot_id,
        "cycle_ts": snap.get("cycle_ts"),
        "broker": snap.get("broker"),
        "data_source": snap.get("data_source"),
        "account_currency": snap.get("account_currency"),
        "position_count": snap.get("position_count"),
        "total_assets": snap.get("total_assets"),
        "cash": snap.get("cash"),
        "buying_power": snap.get("buying_power"),
        "market_value": snap.get("market_value"),
        "total_cost": snap.get("total_cost"),
        "total_pnl": snap.get("total_pnl"),
        "total_pnl_pct": snap.get("total_pnl_pct"),
        "integrity_flag": bool(snap.get("integrity_flag")),
        "integrity_reason": snap.get("integrity_reason"),
        "read_only_protocol": _parse_payload(snap.get("read_only_protocol_json")),
        "positions": positions,
    }


def _historical_price_coverage_layer(cur) -> Dict[str, Any]:
    """Summarise historical_prices table coverage."""
    if not _table_exists(cur, "historical_prices"):
        return {"status": "not_configured", "reason": "historical_prices table has not been created"}
    rows = _q(cur, """
        SELECT ticker,
               COUNT(*) AS row_count,
               MIN(bar_date) AS first_date,
               MAX(bar_date) AS last_date,
               MAX(fetched_at) AS latest_fetch
        FROM historical_prices
        WHERE ktype = 'K_DAY'
        GROUP BY ticker
        ORDER BY ticker ASC
    """)
    rows = _json_safe(rows)
    if not rows:
        return {"status": "no_history", "reason": "historical_prices table has no K_DAY rows"}
    coverage = {
        str(r.get("ticker")).upper(): {
            "row_count": r.get("row_count"),
            "first_date": r.get("first_date"),
            "last_date": r.get("last_date"),
            "latest_fetch": r.get("latest_fetch"),
        }
        for r in rows
        if r.get("ticker")
    }
    row_counts = [int(r.get("row_count") or 0) for r in rows]
    return {
        "status": "operational",
        "version": "v1.0",
        "source": "historical_prices",
        "ticker_count": len(rows),
        "total_rows": sum(row_counts),
        "min_rows_per_ticker": min(row_counts) if row_counts else 0,
        "max_rows_per_ticker": max(row_counts) if row_counts else 0,
        "first_date": min(str(r.get("first_date")) for r in rows if r.get("first_date")),
        "last_date": max(str(r.get("last_date")) for r in rows if r.get("last_date")),
        "latest_fetch": max(str(r.get("latest_fetch")) for r in rows if r.get("latest_fetch")),
        "coverage_by_ticker": coverage,
    }


def _latest_risk_model_layer(cur) -> Dict[str, Any]:
    """Return latest formal history-based risk model run."""
    if not _table_exists(cur, "risk_model_runs"):
        return {"status": "not_configured", "reason": "risk_model_runs table has not been created"}
    rows = _q(cur, """
        SELECT *
        FROM risk_model_runs
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
    """)
    if not rows:
        return {"status": "no_run", "reason": "no risk model run stored yet"}
    row = _json_safe(rows[0])
    metrics = _parse_payload(row.get("metrics_json")) or {}
    if isinstance(metrics, dict):
        metrics.setdefault("run_id", row.get("run_id"))
        metrics.setdefault("status", "operational")
        metrics.setdefault("generated_at", row.get("generated_at"))
    return metrics if isinstance(metrics, dict) else {
        "status": "extract_error",
        "reason": "risk_model metrics_json was not an object",
        "run_id": row.get("run_id"),
    }


def _latest_portfolio_optimizer_layer(cur) -> Dict[str, Any]:
    """Return latest research-only portfolio target weights."""
    if not _table_exists(cur, "portfolio_optimizer_runs"):
        return {"status": "not_configured", "reason": "portfolio_optimizer_runs table has not been created"}
    rows = _q(cur, """
        SELECT *
        FROM portfolio_optimizer_runs
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
    """)
    if not rows:
        return {"status": "no_run", "reason": "no portfolio optimizer run stored yet"}
    row = _json_safe(rows[0])
    return {
        "status": row.get("status") or "research_only",
        "version": "v1.0",
        "run_id": row.get("run_id"),
        "generated_at": row.get("generated_at"),
        "source_snapshot_id": row.get("source_snapshot_id"),
        "objective": row.get("objective"),
        "current_weights": _parse_payload(row.get("current_weights_json")) or {},
        "target_weights": _parse_payload(row.get("target_weights_json")) or {},
        "constraints": _parse_payload(row.get("constraints_json")) or {},
        "actions": _parse_payload(row.get("actions_json")) or [],
        "notes": row.get("notes"),
        "execution_protocol": {
            "orders_generated": False,
            "order_instruction": "NONE",
            "execution_authority": "CIO_ONLY",
        },
    }


def _latest_thesis_lifecycle_layer(cur) -> Dict[str, Any]:
    """Return active thesis lifecycle records and ticker links."""
    if not _table_exists(cur, "thesis_lifecycle"):
        return {"status": "not_configured", "reason": "thesis_lifecycle table has not been created"}
    thesis_rows = _json_safe(_q(cur, """
        SELECT thesis_id, thesis_name, version, status, priority,
               base_probability, current_probability, confidence,
               direction, horizon_days, thesis_json, evidence_json,
               contradiction_json, kill_condition, updated_at
        FROM thesis_lifecycle
        ORDER BY FIELD(priority, 'P1','P2','P3','P4','P5'), thesis_id
    """))
    if not thesis_rows:
        return {"status": "no_theses", "reason": "no thesis records stored yet"}
    links = []
    if _table_exists(cur, "thesis_ticker_links"):
        links = _json_safe(_q(cur, """
            SELECT thesis_id, ticker, role, weight, rationale
            FROM thesis_ticker_links
            ORDER BY thesis_id, ticker
        """))
    links_by_thesis: Dict[str, List[Dict[str, Any]]] = {}
    by_ticker: Dict[str, List[str]] = {}
    for link in links:
        tid = str(link.get("thesis_id") or "")
        ticker = str(link.get("ticker") or "").upper()
        links_by_thesis.setdefault(tid, []).append(link)
        if ticker:
            by_ticker.setdefault(ticker, []).append(tid)
    theses = []
    counts: Dict[str, int] = {}
    for row in thesis_rows:
        tid = row.get("thesis_id")
        evidence = _parse_payload(row.get("evidence_json")) or []
        contradictions = _parse_payload(row.get("contradiction_json")) or []
        thesis = _parse_payload(row.get("thesis_json")) if row.get("thesis_json") else {}
        compact = {
            "thesis_id": tid,
            "thesis_name": row.get("thesis_name"),
            "version": row.get("version"),
            "status": row.get("status"),
            "priority": row.get("priority"),
            "base_probability": row.get("base_probability"),
            "current_probability": row.get("current_probability"),
            "confidence": row.get("confidence"),
            "direction": row.get("direction"),
            "horizon_days": row.get("horizon_days"),
            "evidence": evidence,
            "contradictions": contradictions,
            "kill_condition": row.get("kill_condition"),
            "linked_tickers": links_by_thesis.get(str(tid), []),
            "updated_at": row.get("updated_at"),
            "details": thesis if isinstance(thesis, dict) else {},
        }
        counts[str(row.get("status") or "UNKNOWN")] = counts.get(str(row.get("status") or "UNKNOWN"), 0) + 1
        theses.append(compact)
    return {
        "status": "operational",
        "version": "v1.0",
        "source": "thesis_lifecycle",
        "generated_at": max(str(r.get("updated_at")) for r in thesis_rows if r.get("updated_at")),
        "thesis_count": len(theses),
        "status_counts": counts,
        "theses": theses,
        "by_ticker": by_ticker,
        "doctrine": "Thesis lifecycle is research accountability, not execution instruction.",
    }


def _latest_monitoring_governance_layer(cur) -> Dict[str, Any]:
    """Return recent monitoring alerts and latest lineage event."""
    alerts: List[Dict[str, Any]] = []
    lineage: Dict[str, Any] = {}
    if _table_exists(cur, "monitoring_alerts"):
        latest_cycle = _scalar(cur, "SELECT MAX(cycle_ts) FROM monitoring_alerts")
        alerts = _json_safe(_q(cur, """
            SELECT alert_id, cycle_ts, severity, layer_name, alert_type,
                   title, message, related_ticker, payload_json, resolved, created_at
            FROM monitoring_alerts
            WHERE cycle_ts = %s
            ORDER BY FIELD(severity, 'CRITICAL', 'WARNING', 'INFO'), id DESC
            LIMIT 200
        """, (latest_cycle,))) if latest_cycle else []
        for alert in alerts:
            alert["payload"] = _parse_payload(alert.pop("payload_json", None)) or {}
    if _table_exists(cur, "data_lineage_events"):
        rows = _q(cur, """
            SELECT event_id, cycle_ts, stage, input_refs_json, output_refs_json,
                   dataset_sha256, notes, created_at
            FROM data_lineage_events
            ORDER BY cycle_ts DESC, id DESC
            LIMIT 1
        """)
        if rows:
            lineage = _json_safe(rows[0])
            lineage["input_refs"] = _parse_payload(lineage.pop("input_refs_json", None)) or {}
            lineage["output_refs"] = _parse_payload(lineage.pop("output_refs_json", None)) or {}
    severity_counts: Dict[str, int] = {}
    for alert in alerts:
        sev = str(alert.get("severity") or "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
    return {
        "status": "operational" if alerts or lineage else "no_alerts",
        "version": "v1.0",
        "generated_at": (
            alerts[0].get("cycle_ts") if alerts else lineage.get("cycle_ts") if isinstance(lineage, dict) else None
        ),
        "alert_count": len(alerts),
        "severity_counts": severity_counts,
        "alerts": alerts,
        "lineage": lineage,
    }


def _latest_report_archive_layer(cur) -> Dict[str, Any]:
    """Return latest archived research report metadata if archive table exists."""
    if not _table_exists(cur, "research_report_archive"):
        return {"status": "not_configured", "reason": "research_report_archive table has not been created"}
    rows = _q(cur, """
        SELECT id, report_type, report_version, generated_at, dataset_generated_at,
               market_session, export_version, ingest_version, regime, regime_score,
               regime_action, cio_action, confidence, confidence_label,
               blind_spot_status, causal_explanation_status, total_signals,
               latest_signal_at, report_sha256, source_file_path, created_at
        FROM research_report_archive
        ORDER BY id DESC
        LIMIT 1
    """)
    if not rows:
        return {"status": "no_archive", "reason": "no research report archive row stored yet"}
    row = _json_safe(rows[0])
    row["status"] = "operational"
    row["source"] = "research_report_archive"
    return row


def _latest_listing_status_map(cur) -> Dict[str, Dict[str, Any]]:
    """Return latest Moomoo listing-status rows keyed by ticker."""
    if not _table_exists(cur, "security_listing_status"):
        return {}
    snapshot_date = _scalar(cur, "SELECT MAX(snapshot_date) FROM security_listing_status")
    if not snapshot_date:
        return {}
    rows = _q(cur, """
        SELECT ticker, code, snapshot_date, name, security_type, exchange_type,
               owner_market, listing_date, delisting_flag, listing_status, fetched_at
        FROM security_listing_status
        WHERE snapshot_date = %s
        ORDER BY ticker ASC
    """, (snapshot_date,))
    return {
        str(row.get("ticker") or "").upper(): _json_safe(row)
        for row in rows
        if row.get("ticker")
    }


def _latest_dataset_snapshot_archive_layer(cur) -> Dict[str, Any]:
    """Return point-in-time dataset snapshot archive status."""
    if not _table_exists(cur, "institutional_dataset_snapshots"):
        return {"status": "not_configured", "reason": "institutional_dataset_snapshots table has not been created"}
    rows = _q(cur, """
        SELECT snapshot_id, captured_at, dataset_generated_at, export_version,
               ingest_version, dataset_sha256, dataset_path, created_at
        FROM institutional_dataset_snapshots
        ORDER BY captured_at DESC, id DESC
        LIMIT 1
    """)
    count = _scalar(cur, "SELECT COUNT(*) AS n FROM institutional_dataset_snapshots") or 0
    if not rows:
        return {"status": "no_snapshots", "snapshot_count": 0}
    latest = _json_safe(rows[0])
    return {
        "status": "operational",
        "version": "v1.0",
        "source": "institutional_dataset_snapshots",
        "generated_at": latest.get("captured_at"),
        "snapshot_count": int(count or 0),
        "latest_snapshot": latest,
        "doctrine": "Immutable point-in-time dataset archive for reconstruction and audit.",
    }


def _latest_freshness_recovery_layer(cur) -> Dict[str, Any]:
    """Return latest freshness recovery operator run."""
    if not _table_exists(cur, "freshness_recovery_runs"):
        return {"status": "not_configured", "reason": "freshness_recovery_runs table has not been created"}
    rows = _q(cur, """
        SELECT run_id, cycle_ts, dataset_generated_at, market_session, status,
               stale_sections_json, market_closed_deferred_json,
               attempted_modules_json, unresolved_sections_json, summary_json,
               created_at
        FROM freshness_recovery_runs
        ORDER BY cycle_ts DESC, id DESC
        LIMIT 1
    """)
    if not rows:
        return {"status": "no_runs", "reason": "no freshness recovery run stored yet"}
    row = _json_safe(rows[0])
    return {
        "status": row.get("status") or "unknown",
        "version": "v1.0",
        "source": "freshness_recovery_runs",
        "generated_at": row.get("cycle_ts"),
        "run_id": row.get("run_id"),
        "market_session": row.get("market_session"),
        "stale_sections": _parse_payload(row.get("stale_sections_json")) or [],
        "market_closed_deferred": _parse_payload(row.get("market_closed_deferred_json")) or [],
        "attempted_modules": _parse_payload(row.get("attempted_modules_json")) or [],
        "unresolved_sections": _parse_payload(row.get("unresolved_sections_json")) or [],
        "summary": _parse_payload(row.get("summary_json")) or {},
    }


def _latest_historical_backfill_layer(cur) -> Dict[str, Any]:
    """Return latest staged historical backfill scheduler status."""
    if not _table_exists(cur, "historical_backfill_queue"):
        return {"status": "not_configured", "reason": "historical_backfill_queue table has not been created"}
    counts = _q(cur, """
        SELECT status, COUNT(*) AS n
        FROM historical_backfill_queue
        GROUP BY status
    """)
    queue_counts = {str(r.get("status") or "UNKNOWN"): int(r.get("n") or 0) for r in counts}
    incomplete = _json_safe(_q(cur, """
        SELECT ticker, universe_source, priority, desired_days, min_rows,
               row_count, first_bar_date, latest_bar_date, latest_fetch_at,
               status, attempt_count, last_attempt_at, last_success_at, last_error
        FROM historical_backfill_queue
        WHERE status != 'COMPLETE'
        ORDER BY priority ASC, last_attempt_at ASC, ticker ASC
        LIMIT 40
    """))
    latest_run: Dict[str, Any] = {}
    if _table_exists(cur, "historical_backfill_runs"):
        rows = _q(cur, """
            SELECT run_id, cycle_ts, status, batch_size, selected_tickers_json,
                   command_exit_code, summary_json, created_at
            FROM historical_backfill_runs
            ORDER BY cycle_ts DESC, id DESC
            LIMIT 1
        """)
        if rows:
            latest_run = _json_safe(rows[0])
            latest_run["selected_tickers"] = _parse_payload(latest_run.pop("selected_tickers_json", None)) or []
            latest_run["summary"] = _parse_payload(latest_run.pop("summary_json", None)) or {}
    return {
        "status": latest_run.get("status") or ("QUEUE_COMPLETE" if not incomplete else "QUEUE_ACTIVE"),
        "version": "v1.0",
        "source": "historical_backfill_scheduler",
        "generated_at": latest_run.get("cycle_ts"),
        "queue_counts": queue_counts,
        "incomplete_sample": incomplete,
        "latest_run": latest_run,
        "read_only_protocol": True,
    }


def _latest_cio_decisions_layer(cur) -> Dict[str, Any]:
    """Return research-only CIO decision journal state."""
    if not _table_exists(cur, "cio_decision_journal"):
        return {"status": "not_configured", "reason": "cio_decision_journal table has not been created"}
    rows = _json_safe(_q(cur, """
        SELECT decision_id, decision_ts, source_run_id, decision_type, status,
               priority, ticker, thesis_id, current_weight, target_weight,
               delta_weight, research_recommendation_json, cio_decision,
               cio_notes, execution_authority, order_generated, updated_at
        FROM cio_decision_journal
        ORDER BY decision_ts DESC, FIELD(priority,'P1','P2','P3','P4','P5'), id DESC
        LIMIT 100
    """))
    status_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    pending = 0
    orders_generated = 0
    for row in rows:
        row["research_recommendation"] = _parse_payload(row.pop("research_recommendation_json", None)) or {}
        status = str(row.get("status") or "UNKNOWN")
        dtype = str(row.get("decision_type") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        type_counts[dtype] = type_counts.get(dtype, 0) + 1
        if status.startswith("RESEARCH_PENDING"):
            pending += 1
        if row.get("order_generated"):
            orders_generated += 1
    latest_ts = rows[0].get("decision_ts") if rows else None
    return {
        "status": "operational" if rows else "no_decisions",
        "version": "v1.0",
        "source": "cio_decision_journal",
        "generated_at": latest_ts,
        "decision_count_exported": len(rows),
        "pending_review_count": pending,
        "status_counts": status_counts,
        "decision_type_counts": type_counts,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_generation_enabled": False,
        "orders_generated": orders_generated,
        "decisions": rows,
        "doctrine": "Research ledger only. No broker orders are created, routed, modified, or cancelled.",
    }


def _latest_cio_cognition_layer(cur) -> Dict[str, Any]:
    """Return CIO-authored/auto-captured Strategic Thinking / Planning / Execution journal."""
    if not _table_exists(cur, "cio_cognition_journal"):
        return {"status": "not_configured", "reason": "cio_cognition_journal table has not been created"}

    journals = _json_safe(_q(cur, """
        SELECT journal_id, journal_ts, source_cycle_ts, source_report_archive_id,
               source_dataset_sha256, entry_type, status, priority, regime,
               cio_action, confidence, strategic_thinking, planning,
               execution_intent, non_execution_rationale, key_risks_json,
               evidence_refs_json, linked_theses_json, linked_decisions_json,
               follow_up_json, author, execution_authority, order_generated,
               created_at, updated_at
        FROM cio_cognition_journal
        ORDER BY journal_ts DESC, id DESC
        LIMIT 20
    """))
    if not journals:
        return {"status": "no_journal", "reason": "no CIO cognition journal rows stored yet"}

    for row in journals:
        row["key_risks"] = _parse_payload(row.pop("key_risks_json", None)) or []
        row["evidence_refs"] = _parse_payload(row.pop("evidence_refs_json", None)) or {}
        row["linked_theses"] = _parse_payload(row.pop("linked_theses_json", None)) or []
        row["linked_decisions"] = _parse_payload(row.pop("linked_decisions_json", None)) or []
        row["follow_up"] = _parse_payload(row.pop("follow_up_json", None)) or []

    latest_id = journals[0].get("journal_id")
    reviews: List[Dict[str, Any]] = []
    if latest_id and _table_exists(cur, "cio_thesis_reviews"):
        reviews = _json_safe(_q(cur, """
            SELECT review_id, journal_id, thesis_id, review_ts, status_at_review,
                   probability_at_review, confidence_at_review, cio_assessment,
                   strategic_note, planning_note, execution_note,
                   kill_condition_review, repeatability_hypothesis, mistake_risk,
                   evidence_json, contradiction_json, follow_up_json,
                   author, execution_authority, order_generated, updated_at
            FROM cio_thesis_reviews
            WHERE journal_id = %s
            ORDER BY thesis_id
        """, (latest_id,)))
        for row in reviews:
            row["evidence"] = _parse_payload(row.pop("evidence_json", None)) or []
            row["contradictions"] = _parse_payload(row.pop("contradiction_json", None)) or []
            row["follow_up"] = _parse_payload(row.pop("follow_up_json", None)) or []

    status_counts: Dict[str, int] = {}
    action_counts: Dict[str, int] = {}
    orders_generated = 0
    for row in journals:
        status = str(row.get("status") or "UNKNOWN")
        action = str(row.get("cio_action") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
        if row.get("order_generated"):
            orders_generated += 1

    assessment_counts: Dict[str, int] = {}
    for row in reviews:
        assessment = str(row.get("cio_assessment") or "UNKNOWN")
        assessment_counts[assessment] = assessment_counts.get(assessment, 0) + 1

    return {
        "status": "operational",
        "version": "v1.0",
        "source": "cio_cognition_journal / cio_thesis_reviews",
        "generated_at": journals[0].get("journal_ts"),
        "journal_count_exported": len(journals),
        "latest_journal_id": latest_id,
        "latest_journals": journals,
        "latest_thesis_reviews": reviews,
        "review_count": len(reviews),
        "status_counts": status_counts,
        "action_counts": action_counts,
        "assessment_counts": assessment_counts,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_generation_enabled": False,
        "orders_generated": orders_generated,
        "doctrine": "CIO Strategic Thinking / Planning / Execution ledger only. Records cognition and thesis reviews; never routes broker orders.",
    }


def _build_execution_control_layers(
    cio_decisions: Dict[str, Any],
    portfolio_targets: Dict[str, Any],
    risk_model: Dict[str, Any],
    portfolio_readonly: Dict[str, Any],
    orders_layer: Optional[Dict[str, Any]] = None,
    fills_layer: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Build CIO-only execution governance blocks without broker order routing."""
    now = datetime.now().isoformat(timespec="seconds")
    cio_decisions = cio_decisions if isinstance(cio_decisions, dict) else {}
    portfolio_targets = portfolio_targets if isinstance(portfolio_targets, dict) else {}
    risk_model = risk_model if isinstance(risk_model, dict) else {}
    portfolio_readonly = portfolio_readonly if isinstance(portfolio_readonly, dict) else {}
    orders_layer = orders_layer if isinstance(orders_layer, dict) else {}
    fills_layer = fills_layer if isinstance(fills_layer, dict) else {}

    pending_review = int(cio_decisions.get("pending_review_count") or 0)
    exported_decisions = int(cio_decisions.get("decision_count_exported") or 0)
    orders_generated = int(cio_decisions.get("orders_generated") or 0)
    target_actions = portfolio_targets.get("actions") if isinstance(portfolio_targets.get("actions"), list) else []
    risk_breaches = risk_model.get("constraint_breaches") if isinstance(risk_model.get("constraint_breaches"), list) else []
    read_only_protocol = portfolio_readonly.get("read_only_protocol") if isinstance(portfolio_readonly.get("read_only_protocol"), dict) else {}
    order_history_ready = orders_layer.get("status") in {"operational", "no_records", "partial_error"}
    fill_history_ready = fills_layer.get("status") in {"operational", "no_records", "partial_error"}

    execution = {
        "status": "manual_cio_control_operational",
        "version": "v1.0",
        "source": "export_dataset_raw.py / cio_decision_journal / portfolio_targets / risk_model",
        "generated_at": now,
        "execution_authority": "CIO_ONLY_MANUAL",
        "broker_extract_only": True,
        "order_routing_enabled": False,
        "orders_generated_by_pipeline": False,
        "orders_generated": orders_generated,
        "broker_execution_methods_called": [],
        "read_only_broker_methods_called": read_only_protocol.get("allowed_methods_called", []),
        "read_only_order_history_extraction": order_history_ready,
        "read_only_deal_history_extraction": fill_history_ready,
        "manual_execution_required": True,
        "execution_records": {
            "orders_status": orders_layer.get("status"),
            "fills_status": fills_layer.get("status"),
            "snapshot_id": orders_layer.get("snapshot_id") or fills_layer.get("snapshot_id"),
            "open_order_count": orders_layer.get("open_order_count", 0),
            "historical_order_count": orders_layer.get("historical_order_count", 0),
            "open_deal_count": fills_layer.get("open_deal_count", 0),
            "historical_deal_count": fills_layer.get("historical_deal_count", 0),
            "orders_generated_by_pipeline": False,
        },
        "decision_control": {
            "cio_decision_journal_status": cio_decisions.get("status"),
            "decision_count_exported": exported_decisions,
            "pending_review_count": pending_review,
            "status_counts": cio_decisions.get("status_counts") or {},
            "decision_type_counts": cio_decisions.get("decision_type_counts") or {},
        },
        "pre_trade_controls": {
            "target_weight_review_present": bool(portfolio_targets),
            "research_only_target_actions": len(target_actions),
            "risk_model_present": bool(risk_model),
            "constraint_breaches_present": bool(risk_breaches),
            "cash_weight": risk_model.get("cash_weight"),
            "portfolio_beta_to_spy": risk_model.get("beta_to_spy"),
            "historical_var_present": bool(risk_model.get("historical_var")),
        },
        "manual_fill_import_contract": {
            "status": "historical_deals_extracted" if fills_layer.get("historical_deal_count") else "ready_for_manual_fill_import",
            "required_fields": [
                "decision_id",
                "ticker",
                "side",
                "quantity",
                "manual_execution_ts",
                "execution_price",
                "broker",
                "commission",
                "cio_notes",
            ],
            "database_table_status": "not_created_yet",
            "reason": "CIO execution remains outside broker API. Manual fill import can be added without enabling order routing.",
        },
        "doctrine": "Research control and audit layer only. No broker orders are created, routed, modified, cancelled, or unlocked.",
    }

    trade_lifecycle = {
        "status": "manual_cio_lifecycle_control",
        "version": "v1.0",
        "generated_at": now,
        "execution_authority": "CIO_ONLY_MANUAL",
        "orders_generated_by_pipeline": False,
        "stages": [
            {"stage": "research_signal", "owner": "BlueLotus", "system_record": "dataset_raw.signals_latest"},
            {"stage": "risk_review", "owner": "BlueLotus", "system_record": "dataset_raw.risk_model"},
            {"stage": "target_weight_review", "owner": "BlueLotus", "system_record": "dataset_raw.portfolio_targets"},
            {"stage": "cio_decision", "owner": "CIO", "system_record": "dataset_raw.cio_decisions"},
            {"stage": "manual_broker_execution", "owner": "CIO", "system_record": "outside_pipeline"},
            {"stage": "manual_fill_import", "owner": "CIO / Research Ops", "system_record": "future_manual_import"},
            {"stage": "post_trade_tca_review", "owner": "BlueLotus", "system_record": "dataset_raw.transaction_cost_analysis"},
        ],
        "open_review_count": pending_review,
        "decision_count_exported": exported_decisions,
        "manual_fill_import_contract": True,
        "doctrine": "Lifecycle maps research to CIO review. It is not an order ticket and not an execution instruction.",
    }

    transaction_cost_analysis = {
        "status": "broker_history_ready" if fill_history_ready else "research_proxy_ready",
        "version": "v1.0",
        "generated_at": now,
        "source": "risk_model / portfolio_targets / cio_decision_journal",
        "execution_authority": "CIO_ONLY_MANUAL",
        "orders_generated_by_pipeline": False,
        "actual_fills_available": bool(fills_layer.get("historical_deal_count") or fills_layer.get("open_deal_count")),
        "method": "Read-only broker order/deal extraction plus pre-trade TCA contract. No order routing is enabled.",
        "pre_trade_proxy_inputs": {
            "portfolio_value": risk_model.get("portfolio_value"),
            "cash_weight": risk_model.get("cash_weight"),
            "historical_var": risk_model.get("historical_var"),
            "target_action_count": len(target_actions),
            "risk_constraint_breach_count": len(risk_breaches),
        },
        "broker_history_inputs": {
            "open_order_count": orders_layer.get("open_order_count", 0),
            "historical_order_count": orders_layer.get("historical_order_count", 0),
            "open_deal_count": fills_layer.get("open_deal_count", 0),
            "historical_deal_count": fills_layer.get("historical_deal_count", 0),
            "fee_record_count": orders_layer.get("fee_record_count", 0),
        },
        "post_trade_metrics_contract": [
            "arrival_price",
            "execution_price",
            "slippage_pct",
            "commission",
            "spread_cost_proxy",
            "market_impact_proxy",
            "implementation_shortfall",
        ],
        "manual_fill_import_required": True,
        "doctrine": "TCA is a research-control contract until manual fills are imported by CIO/research operations.",
    }

    return execution, trade_lifecycle, transaction_cost_analysis


def _latest_execution_readonly_layer(cur) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return read-only Moomoo order/deal history extraction blocks."""
    if not _table_exists(cur, "execution_readonly_snapshots"):
        reason = "execution_readonly_snapshots table has not been created"
        empty_orders = {
            "status": "not_configured",
            "version": "v1.0",
            "source": "Execution_ReadOnly_Moomoo",
            "reason": reason,
            "orders_generated_by_pipeline": False,
            "order_routing_enabled": False,
            "read_only_protocol": True,
        }
        empty_fills = {
            "status": "not_configured",
            "version": "v1.0",
            "source": "Execution_ReadOnly_Moomoo",
            "reason": reason,
            "orders_generated_by_pipeline": False,
            "read_only_protocol": True,
        }
        return empty_orders, empty_fills

    rows = _json_safe(_q(cur, """
        SELECT snapshot_id, cycle_ts, broker, data_source, trd_env, market,
               start_date, end_date, open_order_count, historical_order_count,
               open_deal_count, historical_deal_count, fee_record_count,
               query_errors_json, read_only_protocol_json, summary_json
        FROM execution_readonly_snapshots
        ORDER BY cycle_ts DESC, id DESC
        LIMIT 1
    """))
    if not rows:
        empty = {
            "status": "no_records",
            "version": "v1.0",
            "source": "Execution_ReadOnly_Moomoo",
            "orders_generated_by_pipeline": False,
            "order_routing_enabled": False,
            "read_only_protocol": True,
        }
        return dict(empty), dict(empty)

    snap = rows[0]
    snapshot_id = snap.get("snapshot_id")
    query_errors = _parse_payload(snap.pop("query_errors_json", None)) or {}
    protocol = _parse_payload(snap.pop("read_only_protocol_json", None)) or {}
    summary = _parse_payload(snap.pop("summary_json", None)) or {}
    status = "operational" if not query_errors else "partial_error"

    order_rows = _json_safe(_q(cur, """
        SELECT order_scope, order_id, code, ticker, trd_side, order_type,
               order_status, qty, price, dealt_qty, dealt_avg_price,
               create_time, updated_time, raw_order_json
        FROM execution_readonly_orders
        WHERE snapshot_id = %s
        ORDER BY FIELD(order_scope,'OPEN','HISTORICAL'), COALESCE(create_time, updated_time) DESC, id DESC
        LIMIT 300
    """, (snapshot_id,))) if snapshot_id else []
    deal_rows = _json_safe(_q(cur, """
        SELECT deal_scope, deal_id, order_id, code, ticker, trd_side,
               qty, price, deal_time, raw_deal_json
        FROM execution_readonly_deals
        WHERE snapshot_id = %s
        ORDER BY FIELD(deal_scope,'OPEN','HISTORICAL'), deal_time DESC, id DESC
        LIMIT 300
    """, (snapshot_id,))) if snapshot_id else []
    fee_rows = _json_safe(_q(cur, """
        SELECT order_id, fee_record_json
        FROM execution_readonly_fees
        WHERE snapshot_id = %s
        ORDER BY id DESC
        LIMIT 100
    """, (snapshot_id,))) if snapshot_id else []

    for row in order_rows:
        row["raw_order"] = _parse_payload(row.pop("raw_order_json", None)) or {}
    for row in deal_rows:
        row["raw_deal"] = _parse_payload(row.pop("raw_deal_json", None)) or {}
    for row in fee_rows:
        row["fee_record"] = _parse_payload(row.pop("fee_record_json", None)) or {}

    open_orders = [r for r in order_rows if r.get("order_scope") == "OPEN"]
    historical_orders = [r for r in order_rows if r.get("order_scope") == "HISTORICAL"]
    open_deals = [r for r in deal_rows if r.get("deal_scope") == "OPEN"]
    historical_deals = [r for r in deal_rows if r.get("deal_scope") == "HISTORICAL"]

    orders = {
        "status": status,
        "version": "v1.0",
        "source": "Execution_ReadOnly_Moomoo",
        "snapshot_id": snapshot_id,
        "cycle_ts": snap.get("cycle_ts"),
        "broker": snap.get("broker"),
        "data_source": snap.get("data_source"),
        "trd_env": snap.get("trd_env"),
        "market": snap.get("market"),
        "start_date": snap.get("start_date"),
        "end_date": snap.get("end_date"),
        "open_order_count": snap.get("open_order_count"),
        "historical_order_count": snap.get("historical_order_count"),
        "fee_record_count": snap.get("fee_record_count"),
        "orders_generated_by_pipeline": False,
        "order_routing_enabled": False,
        "query_errors": query_errors,
        "read_only_protocol": protocol,
        "summary": summary,
        "open_orders": open_orders,
        "historical_orders_recent": historical_orders,
        "fees": fee_rows,
        "doctrine": "Read-only extraction from Moomoo. No orders are created, routed, modified, or cancelled.",
    }
    fills = {
        "status": status,
        "version": "v1.0",
        "source": "Execution_ReadOnly_Moomoo",
        "snapshot_id": snapshot_id,
        "cycle_ts": snap.get("cycle_ts"),
        "broker": snap.get("broker"),
        "data_source": snap.get("data_source"),
        "trd_env": snap.get("trd_env"),
        "market": snap.get("market"),
        "start_date": snap.get("start_date"),
        "end_date": snap.get("end_date"),
        "open_deal_count": snap.get("open_deal_count"),
        "historical_deal_count": snap.get("historical_deal_count"),
        "orders_generated_by_pipeline": False,
        "query_errors": query_errors,
        "read_only_protocol": protocol,
        "open_deals": open_deals,
        "historical_deals_recent": historical_deals,
        "doctrine": "Read-only deal/fill extraction from Moomoo. CIO owns execution.",
    }
    return orders, fills


def _latest_corporate_actions_layer(cur) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return Moomoo corporate actions plus listing/delisting status."""
    if not (_table_exists(cur, "security_listing_status") and _table_exists(cur, "corporate_actions")):
        empty = {"status": "not_configured", "reason": "corporate action/listing tables have not been created"}
        return empty, empty
    snapshot_date = _scalar(cur, "SELECT MAX(snapshot_date) FROM security_listing_status")
    listing_rows = _json_safe(_q(cur, """
        SELECT ticker, code, snapshot_date, name, security_type, exchange_type,
               owner_market, listing_date, delisting_flag, listing_status,
               fetched_at
        FROM security_listing_status
        WHERE snapshot_date = %s
        ORDER BY ticker ASC
    """, (snapshot_date,))) if snapshot_date else []
    action_rows = _json_safe(_q(cur, """
        SELECT ticker, code, action_type, event_date, ex_date, record_date,
               pay_date, statement, ratio_text, amount, currency, fetched_at
        FROM corporate_actions
        WHERE fetched_at >= DATE_SUB(NOW(), INTERVAL 2 DAY)
           OR event_date >= DATE_SUB(CURDATE(), INTERVAL 365 DAY)
        ORDER BY COALESCE(event_date, ex_date, fetched_at) DESC, ticker ASC
        LIMIT 1000
    """))
    delisting_rows = [r for r in listing_rows if r.get("delisting_flag")]
    by_ticker: Dict[str, Any] = {}
    for row in listing_rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            by_ticker[ticker] = row
    corporate_actions = {
        "status": "operational",
        "version": "v1.0",
        "source": "Corporate_Actions_Moomoo",
        "generated_at": max(str(r.get("fetched_at")) for r in listing_rows if r.get("fetched_at")) if listing_rows else None,
        "snapshot_date": snapshot_date,
        "listing_status_count": len(listing_rows),
        "action_count": len(action_rows),
        "split_count": sum(1 for r in action_rows if r.get("action_type") == "SPLIT"),
        "dividend_count": sum(1 for r in action_rows if r.get("action_type") == "DIVIDEND"),
        "listing_status_by_ticker": by_ticker,
        "recent_actions": action_rows,
        "read_only_protocol": True,
    }
    delistings = {
        "status": "operational",
        "version": "v1.0",
        "source": "security_listing_status",
        "generated_at": corporate_actions.get("generated_at"),
        "snapshot_date": snapshot_date,
        "delisting_flag_count": len(delisting_rows),
        "delisted_or_flagged": delisting_rows,
        "survivorship_bias_control": "ACTIVE - latest Moomoo listing status exported for current universe.",
    }
    return corporate_actions, delistings


def _build_signal_validation_blocks(cur, research_forecasting: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build compact signal validation and backtest blocks from forecast tables."""
    validation: Dict[str, Any] = {
        "status": "collecting",
        "version": "v1.0",
        "source": "ticker_forecasts / forecast_resolutions",
        "doctrine": "Skill is measured only after horizons mature; collecting status must not be read as proven alpha.",
    }
    backtests: Dict[str, Any] = {
        "status": "collecting",
        "version": "v1.0",
        "source": "forecast_resolutions",
        "method": "Brier score, directional accuracy, and target price error by forecast method and horizon.",
    }
    if not _table_exists(cur, "ticker_forecasts"):
        validation["status"] = "not_configured"
        validation["reason"] = "ticker_forecasts table missing"
        backtests["status"] = "not_configured"
        return validation, backtests

    forecast_counts = _json_safe(_q(cur, """
        SELECT prediction_method, COUNT(*) AS forecast_count, COUNT(DISTINCT ticker) AS ticker_count
        FROM ticker_forecasts
        GROUP BY prediction_method
        ORDER BY prediction_method
    """))
    validation.update({
        "forecast_count": sum(int(r.get("forecast_count") or 0) for r in forecast_counts),
        "method_counts": forecast_counts,
        "latest_snapshot_id": research_forecasting.get("snapshot_id") if isinstance(research_forecasting, dict) else None,
        "horizons_days": [7, 14, 30, 60, 90],
    })
    if _table_exists(cur, "forecast_resolutions"):
        rows = _json_safe(_q(cur, """
            SELECT prediction_method, horizon_days,
                   COUNT(*) AS resolved_count,
                   AVG(brier_score) AS avg_brier_score,
                   AVG(percentage_error) AS avg_percentage_error,
                   AVG(directional_correct) AS directional_accuracy
            FROM forecast_resolutions
            GROUP BY prediction_method, horizon_days
            ORDER BY horizon_days, prediction_method
        """))
        resolved = sum(int(r.get("resolved_count") or 0) for r in rows)
        validation["resolved_count"] = resolved
        validation["status"] = "resolved_history_available" if resolved else "collecting"
        validation["accuracy_summary"] = rows
        backtests["status"] = "resolved_history_available" if resolved else "collecting"
        backtests["resolved_count"] = resolved
        backtests["results"] = rows
    else:
        validation["resolved_count"] = 0
        backtests["resolved_count"] = 0
        backtests["reason"] = "forecast_resolutions table missing or not yet created"
    return validation, backtests


def _build_portfolio_mandates(portfolio: Dict[str, Any], security_master: Dict[str, Any]) -> Dict[str, Any]:
    """Build conservative mandate labels for current portfolio positions."""
    positions = portfolio.get("positions") if isinstance(portfolio, dict) else {}
    positions = positions if isinstance(positions, dict) else {}
    baseline = {"AU", "NEM", "BAC", "WFC", "JPM", "GLD", "TLT"}
    satellite = {"QBTS", "QUBT", "RGTI", "IONQ", "ENPH", "FSLR", "SEDG", "RUN"}
    mandates: Dict[str, Any] = {}
    for ticker, pos in positions.items():
        t = str(ticker).upper()
        sec = security_master.get(t) if isinstance(security_master, dict) else {}
        if t in baseline:
            mandate = "BASELINE"
        elif t in satellite:
            mandate = "SATELLITE"
        else:
            mandate = "TACTICAL"
        mandates[t] = {
            "ticker": t,
            "mandate": mandate,
            "sector": (sec or {}).get("sector") if isinstance(sec, dict) else None,
            "asset_type": (sec or {}).get("asset_type") if isinstance(sec, dict) else None,
            "position_value": (pos or {}).get("mkt_val") if isinstance(pos, dict) else None,
            "research_only": True,
            "execution_authority": "CIO_ONLY",
        }
    return mandates


def _portfolio_from_readonly(portfolio_readonly: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the dedicated read-only portfolio block to legacy portfolio shape."""
    if not isinstance(portfolio_readonly, dict) or portfolio_readonly.get("status") != "operational":
        return {}
    positions = {}
    for ticker, row in (portfolio_readonly.get("positions") or {}).items():
        if not isinstance(row, dict):
            continue
        t = str(ticker).upper()
        positions[t] = {
            "qty": row.get("qty"),
            "avg_cost": row.get("average_cost"),
            "price": row.get("price"),
            "chg_pct": row.get("day_change_pct"),
            "mkt_val": row.get("market_value"),
            "cost_basis": row.get("cost_basis"),
            "unrealized": row.get("unrealized_pnl"),
            "unrealized_p": row.get("unrealized_pnl_pct"),
            "stale": False,
        }
        # ── P/L arithmetic integrity check ───────────────────────────────────
        _PNL_CONFLICT_THRESHOLD = 5.0
        _qty       = float(positions[t].get("qty") or 0)
        _avg_cost  = float(positions[t].get("avg_cost") or 0)
        _price     = float(positions[t].get("price") or 0)
        _broker_ur = float(positions[t].get("unrealized") or 0)
        if _qty and _avg_cost and _price:
            _computed = round((_price - _avg_cost) * _qty, 2)
            _delta    = abs(_broker_ur - _computed)
            positions[t]["computed_unrealized"] = _computed
            if _delta > _PNL_CONFLICT_THRESHOLD:
                positions[t]["pnl_integrity_status"] = "BROKER_PNL_SOURCE_CONFLICT"
                positions[t]["pnl_conflict_delta"]   = round(_delta, 2)
            else:
                positions[t]["pnl_integrity_status"] = "OK"
        else:
            positions[t]["pnl_integrity_status"] = "INSUFFICIENT_DATA"
    cash = _num(portfolio_readonly.get("cash"), 0) or 0
    buying_power = _num(portfolio_readonly.get("buying_power"), 0) or 0
    bp_delta = cash - buying_power
    return {
        "source": "Portfolio_Snapshot",
        "data_source": "moomoo_readonly_dedicated_table",
        "snapshot_id": portfolio_readonly.get("snapshot_id"),
        "cycle_ts": portfolio_readonly.get("cycle_ts"),
        "total_value": portfolio_readonly.get("market_value"),
        "market_val": portfolio_readonly.get("market_value"),
        "total_assets": portfolio_readonly.get("total_assets"),
        "total_cost": portfolio_readonly.get("total_cost"),
        "total_pnl": portfolio_readonly.get("total_pnl"),
        "total_pnl_pct": portfolio_readonly.get("total_pnl_pct"),
        "cash": portfolio_readonly.get("cash"),
        "buying_power": portfolio_readonly.get("buying_power"),
        "positions": positions,
        "stale": False,
        "integrity_flag": bool(portfolio_readonly.get("integrity_flag")),
        "integrity_flag_reason": portfolio_readonly.get("integrity_reason"),
        "buying_power_delta": round(bp_delta, 2),
        "buying_power_delta_flag": buying_power > 0 and abs(bp_delta) > 1000,
        "read_only_protocol": portfolio_readonly.get("read_only_protocol"),
    }


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _parse_dt_local(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).replace("SGT", "").replace("Z", "").strip()
    if s.endswith("+00:00"):
        s = s[:-6]
    s = s[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _market_cap_tier(market_cap: Any) -> str:
    cap = _num(market_cap, 0) or 0
    if cap >= 200_000_000_000:
        return "mega_cap"
    if cap >= 10_000_000_000:
        return "large_cap"
    if cap >= 2_000_000_000:
        return "mid_cap"
    if cap > 0:
        return "small_cap"
    return "unknown"


def _asset_type(ticker: str, fundamentals: Dict[str, Any]) -> str:
    t = ticker.upper()
    if t.startswith("^"):
        return "INDEX"
    if t in ETF_TICKERS:
        return "ETF"
    f = fundamentals.get(t) or {}
    if isinstance(f, dict) and f.get("asset_type"):
        return str(f.get("asset_type"))
    return "EQUITY"


def _exchange(ticker: str, asset_type: str) -> str:
    t = ticker.upper()
    if asset_type == "INDEX":
        return "INDEX"
    if asset_type == "ETF":
        return "US_ETF"
    if t in NASDAQ_TICKERS:
        return "NASDAQ"
    return "NYSE_OR_US_LISTED"


def _security_profile(ticker: str, asset_type: str) -> Dict[str, str]:
    t = ticker.upper()
    if t in SECURITY_PROFILE_OVERRIDES:
        return dict(SECURITY_PROFILE_OVERRIDES[t])
    if t in SECURITY_THEME_PROFILE_OVERRIDES:
        return dict(SECURITY_THEME_PROFILE_OVERRIDES[t])
    if asset_type == "ETF":
        return {"sector": "Multi-Asset", "industry": "Exchange Traded Fund"}
    if asset_type == "INDEX":
        return {"sector": "Market Index", "industry": "Index"}
    return {"sector": "UNKNOWN", "industry": "UNKNOWN"}


def _market_status_label(live_prices: Dict[str, Any], regime: Dict[str, Any]) -> str:
    raw = str((live_prices or {}).get("market_session") or "UNKNOWN").upper()
    session_flag = str((regime or {}).get("session_flag") or "").upper()
    now = datetime.now()
    if now.weekday() >= 5 or session_flag == "CLOSED":
        return "WEEKEND SNAPSHOT / LAST REGULAR CLOSE"
    return raw


def _sentiment_relevance(ticker: str, payload: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    t = str(ticker or "").upper()
    haystack = " ".join(
        str(payload.get(k) or "")
        for k in ("headline", "title", "company", "name", "summary", "article", "raw_text")
    )
    haystack = f"{haystack} {raw_text}".upper()
    aliases = TICKER_ENTITY_ALIASES.get(t, {t})
    matched = sorted(alias for alias in aliases if alias and alias in haystack)
    if matched:
        return {"relevance": "DIRECT", "matched_terms": matched, "discarded": False}
    return {"relevance": "LOW_RELEVANCE / DISCARD", "matched_terms": [], "discarded": True}


def _security_universe(*sections: Any) -> List[str]:
    out = set()
    skip = {
        "vix", "market_session", "top_movers", "cycle_ts", "ticker_count",
        "source", "prices",
    }
    for section in sections:
        if isinstance(section, dict):
            for k, v in section.items():
                key = str(k)
                if key.startswith("_") or key.lower() in skip:
                    continue
                if isinstance(v, dict):
                    out.add(key.upper())
    return sorted(out)


def _build_security_master(
    live_prices_flat: Dict[str, Any],
    fundamentals: Dict[str, Any],
    analyst_targets: Dict[str, Any],
    capital_flow: Dict[str, Any],
    portfolio: Dict[str, Any],
    listing_status: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    positions = portfolio.get("positions") if isinstance(portfolio, dict) else {}
    listing_status = listing_status if isinstance(listing_status, dict) else {}
    tickers = _security_universe(
        live_prices_flat,
        fundamentals,
        analyst_targets,
        capital_flow,
        positions if isinstance(positions, dict) else {},
        listing_status,
    )
    out: Dict[str, Any] = {}
    unknown_sector = 0
    moomoo_listing_count = 0
    for ticker in tickers:
        f = fundamentals.get(ticker) if isinstance(fundamentals, dict) else {}
        f = f if isinstance(f, dict) else {}
        listing = listing_status.get(ticker) if isinstance(listing_status, dict) else {}
        listing = listing if isinstance(listing, dict) else {}
        asset_type = _asset_type(ticker, fundamentals if isinstance(fundamentals, dict) else {})
        if listing.get("security_type"):
            sec_type = str(listing.get("security_type") or "").upper()
            if "ETF" in sec_type:
                asset_type = "ETF"
            elif "INDEX" in sec_type:
                asset_type = "INDEX"
        profile = _security_profile(ticker, asset_type)
        if profile.get("sector") == "UNKNOWN":
            unknown_sector += 1
        if listing:
            moomoo_listing_count += 1
        out[ticker] = {
            "ticker": ticker,
            "name": listing.get("name"),
            "exchange": listing.get("exchange_type") or _exchange(ticker, asset_type),
            "moomoo_code": listing.get("code"),
            "moomoo_exchange_type": listing.get("exchange_type"),
            "moomoo_owner_market": listing.get("owner_market"),
            "moomoo_security_type": listing.get("security_type"),
            "listing_date": listing.get("listing_date"),
            "listing_status": listing.get("listing_status"),
            "delisting_flag": bool(listing.get("delisting_flag")) if listing else False,
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "market_cap_tier": _market_cap_tier(f.get("total_market_val")),
            "currency": "USD",
            "country": "US",
            "asset_type": asset_type,
            "classification_source": (
                "static_override" if ticker in SECURITY_PROFILE_OVERRIDES
                else "blue_lotus_theme_override" if ticker in SECURITY_THEME_PROFILE_OVERRIDES
                else "asset_type_inference"
            ),
            "instrument_role": "HEDGE_INSTRUMENT" if ticker in {"VXX", "VIXY", "UVXY"} else None,
            "equity_kelly_eligible": False if ticker in {"VXX", "VIXY", "UVXY"} else asset_type == "EQUITY",
            "listing_source": "moomoo_security_listing_status" if listing else "inferred",
        }
    out["_meta"] = {
        "version": "v0.2",
        "source": "export_dataset_raw.py + moomoo security_listing_status",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ticker_count": len(tickers),
        "unknown_sector_count": unknown_sector,
        "moomoo_listing_count": moomoo_listing_count,
        "classification_sources": {
            "static_override": sum(1 for k in out if k != "_meta" and out[k].get("classification_source") == "static_override"),
            "blue_lotus_theme_override": sum(1 for k in out if k != "_meta" and out[k].get("classification_source") == "blue_lotus_theme_override"),
            "asset_type_inference": sum(1 for k in out if k != "_meta" and out[k].get("classification_source") == "asset_type_inference"),
        },
        "coverage_note": "Moomoo supplies listing/exchange/type status; BlueLotus supplies research theme classification where sector/industry are not available from the listing endpoint.",
    }
    return out


def _enrich_live_prices_relative_volume(
    live_prices_flat: Dict[str, Any],
    fundamentals: Dict[str, Any],
) -> Dict[str, Any]:
    enriched = dict(live_prices_flat) if isinstance(live_prices_flat, dict) else {}
    enriched_count = 0
    spike_count = 0
    for ticker, row in list(enriched.items()):
        if not isinstance(row, dict) or "price" not in row:
            continue
        f = fundamentals.get(str(ticker).upper()) if isinstance(fundamentals, dict) else {}
        avg_volume = _num((f or {}).get("avg_volume_30d") if isinstance(f, dict) else None)
        volume = _num(row.get("volume"))
        if avg_volume and avg_volume > 0 and volume is not None:
            rv = round(volume / avg_volume, 4)
            row["avg_volume_30d"] = avg_volume
            row["relative_volume"] = rv
            row["volume_spike_flag"] = rv >= 2.0
            row["volume_sla_source"] = "ticker_fundamentals.avg_volume_30d"
            enriched_count += 1
            if rv >= 2.0:
                spike_count += 1
        else:
            row.setdefault("relative_volume", None)
            row.setdefault("volume_spike_flag", False)
    enriched["_relative_volume_meta"] = {
        "version": "v0.1",
        "source": "export_dataset_raw.py",
        "method": "volume / ticker_fundamentals.avg_volume_30d",
        "enriched_tickers": enriched_count,
        "volume_spike_threshold": 2.0,
        "volume_spike_count": spike_count,
    }
    return enriched


def _build_data_quality_sla(source_health: List[Dict[str, Any]]) -> Dict[str, Any]:
    now = datetime.now()
    rows = []
    breached = []
    warning = []
    for src in source_health:
        source_type = str(src.get("signal_type") or "unknown")
        source_name = str(src.get("source") or "")
        expected = SOURCE_SLA_OVERRIDES_MINUTES.get(
            source_name,
            SOURCE_TYPE_SLA_MINUTES.get(source_type, 720),
        )
        if datetime.now().weekday() >= 5 and source_type in WEEKEND_GRACE_SIGNAL_TYPES:
            expected = max(expected, WEEKEND_GRACE_MINUTES)
        last_seen = src.get("last_seen")
        dt = _parse_dt_local(last_seen)
        age = int((now - dt).total_seconds() / 60) if dt else None
        status = "UNKNOWN"
        if not src.get("active"):
            status = "NO_ROWS"
        elif age is not None:
            if age <= expected:
                status = "OK"
            elif age <= expected * 2:
                status = "WARN"
                warning.append(src.get("source"))
            else:
                status = "BREACH"
                breached.append(src.get("source"))
        rows.append({
            "source": source_name,
            "signal_type": source_type,
            "tier": src.get("tier"),
            "active": src.get("active"),
            "last_seen": last_seen,
            "age_minutes": age,
            "expected_refresh_minutes": expected,
            "sla_policy": (
                "source_override" if source_name in SOURCE_SLA_OVERRIDES_MINUTES
                else "weekend_grace" if datetime.now().weekday() >= 5 and source_type in WEEKEND_GRACE_SIGNAL_TYPES
                else "source_type_default"
            ),
            "sla_status": status,
        })
    return {
        "version": "v0.1",
        "generated_at": now.isoformat(timespec="seconds"),
        "policy": "source_type_expected_refresh_minutes",
        "summary": {
            "sources_checked": len(rows),
            "ok": sum(1 for r in rows if r["sla_status"] == "OK"),
            "warn": sum(1 for r in rows if r["sla_status"] == "WARN"),
            "breach": sum(1 for r in rows if r["sla_status"] == "BREACH"),
            "unknown": sum(1 for r in rows if r["sla_status"] in ("UNKNOWN", "NO_ROWS")),
            "breached_sources": breached,
            "warning_sources": warning,
        },
        "sources": rows,
    }


def _read_json_artifact(path: Path, missing_status: str = "not_available") -> Dict[str, Any]:
    if not path.exists():
        return {
            "status": missing_status,
            "reason": f"{path.name} has not been generated yet",
            "source_file_path": str(path),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {
                "status": "invalid_artifact",
                "reason": f"{path.name} did not contain a JSON object",
                "source_file_path": str(path),
            }
        data.setdefault("source_file_path", str(path))
        return _json_safe(data)
    except Exception as exc:
        return {
            "status": "artifact_read_error",
            "reason": str(exc),
            "source_file_path": str(path),
        }


def _build_risk_metrics(
    portfolio: Dict[str, Any],
    live_prices_flat: Dict[str, Any],
    fundamentals: Dict[str, Any],
    security_master: Dict[str, Any],
) -> Dict[str, Any]:
    positions = portfolio.get("positions") if isinstance(portfolio, dict) else {}
    positions = positions if isinstance(positions, dict) else {}
    total_assets = _num(portfolio.get("total_assets") if isinstance(portfolio, dict) else None, 0) or 0
    cash = _num(portfolio.get("cash") if isinstance(portfolio, dict) else None, 0) or 0
    rows = []
    sector_exposure: Dict[str, float] = {}
    asset_type_exposure: Dict[str, float] = {}
    weighted_beta_num = 0.0
    weighted_beta_den = 0.0
    daily_move_proxy = 0.0
    liquidity_flags = []
    largest = {"ticker": None, "weight": 0.0}

    # First pass: collect values for equity-only metrics
    equity_values: list = []
    pnl_integrity_conflicts: list = []
    for ticker, pos in positions.items():
        t = str(ticker).upper()
        value = _num((pos or {}).get("mkt_val"), 0) or 0
        if value > 0:
            equity_values.append((t, value))
        pnl_status = str((pos or {}).get("pnl_integrity_status", "OK"))
        if pnl_status == "BROKER_PNL_SOURCE_CONFLICT":
            pnl_integrity_conflicts.append({
                "ticker": t,
                "broker_unrealized": _num((pos or {}).get("unrealized")),
                "computed_unrealized": _num((pos or {}).get("computed_unrealized")),
                "conflict_delta": _num((pos or {}).get("pnl_conflict_delta")),
                "note": "broker_unrealized differs from (price-avg_cost)*qty by more than $5; verify cost basis in moomoo",
            })

    equity_capital = sum(v for _, v in equity_values)

    for ticker, pos in positions.items():
        t = str(ticker).upper()
        value = _num((pos or {}).get("mkt_val"), 0) or 0
        weight = value / total_assets if total_assets else 0.0
        # Weight relative to invested equity only (excludes cash) — used for HHI and concentration
        weight_equity = value / equity_capital if equity_capital else 0.0
        price_row = live_prices_flat.get(t) if isinstance(live_prices_flat, dict) else {}
        fund = fundamentals.get(t) if isinstance(fundamentals, dict) else {}
        sec = security_master.get(t) if isinstance(security_master, dict) else {}
        beta = _num((fund or {}).get("beta") if isinstance(fund, dict) else None)
        avg_volume = _num((fund or {}).get("avg_volume_30d") if isinstance(fund, dict) else None)
        price = _num((price_row or {}).get("price") if isinstance(price_row, dict) else (pos or {}).get("price"))
        chg = _num((price_row or {}).get("chg_pct") if isinstance(price_row, dict) else (pos or {}).get("chg_pct"), 0) or 0
        # unrealized_pnl_pct_from_cost: cumulative % gain/loss since purchase (NOT daily volatility)
        unrealized_pnl_pct = _num((pos or {}).get("unrealized_p"))
        dollar_volume = avg_volume * price if avg_volume and price else None
        position_to_adv = value / dollar_volume if dollar_volume else None
        if position_to_adv is not None and position_to_adv > PORTFOLIO_CONSTRAINTS_DEFAULT["max_position_daily_volume_pct"]:
            liquidity_flags.append(t)
        if weight > largest["weight"]:
            largest = {"ticker": t, "weight": weight}
        sector = str((sec or {}).get("sector") or "UNKNOWN")
        asset_type = str((sec or {}).get("asset_type") or "UNKNOWN")
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + weight
        asset_type_exposure[asset_type] = asset_type_exposure.get(asset_type, 0.0) + weight
        if beta is not None:
            weighted_beta_num += beta * weight
            weighted_beta_den += weight
        daily_move_proxy += weight * abs(chg) / 100.0
        rows.append({
            "ticker": t,
            "market_value": round(value, 2),
            "weight_vs_total_aum": round(weight, 4),
            # IMPORTANT: use weight_vs_equity for concentration analysis, not weight_vs_total_aum
            "weight_vs_equity_capital": round(weight_equity, 4),
            "sector": sector,
            "asset_type": asset_type,
            "beta": beta,
            "daily_change_pct": chg,
            # unrealized_pnl_pct_from_cost = cumulative gain/loss % from average cost basis — NOT daily volatility
            "unrealized_pnl_pct_from_cost": unrealized_pnl_pct,
            "avg_volume_30d": avg_volume,
            "dollar_volume_30d": round(dollar_volume, 2) if dollar_volume else None,
            "position_to_avg_daily_dollar_volume": round(position_to_adv, 4) if position_to_adv is not None else None,
        })

    # HHI vs total AUM (includes cash effect — will be very small when portfolio is mostly cash)
    hhi = sum((r["weight_vs_total_aum"] or 0) ** 2 for r in rows)
    # HHI vs equity capital only (correct concentration measure within invested positions)
    hhi_equity = sum((r["weight_vs_equity_capital"] or 0) ** 2 for r in rows)
    weighted_beta = weighted_beta_num / weighted_beta_den if weighted_beta_den else None
    cash_weight = cash / total_assets if total_assets else None
    largest_vs_equity = largest["ticker"]
    largest_equity_weight = (
        round(next((r["weight_vs_equity_capital"] for r in rows if r["ticker"] == largest["ticker"]), 0.0), 4)
        if rows else 0.0
    )
    breaches = []
    if largest["weight"] > PORTFOLIO_CONSTRAINTS_DEFAULT["max_single_name_weight"]:
        breaches.append("max_single_name_weight")
    if cash_weight is not None and cash_weight < PORTFOLIO_CONSTRAINTS_DEFAULT["min_cash_weight"]:
        breaches.append("min_cash_weight")
    for sector, weight in sector_exposure.items():
        if weight > PORTFOLIO_CONSTRAINTS_DEFAULT["max_theme_weight"]:
            breaches.append(f"max_theme_weight:{sector}")

    return {
        "version": "v0.2",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "computed_from_current_portfolio_prices_fundamentals",
        "total_assets": round(total_assets, 2),
        "equity_invested_capital": round(equity_capital, 2),
        "cash_weight": round(cash_weight, 4) if cash_weight is not None else None,
        "largest_position": {
            "ticker": largest["ticker"],
            # weight_vs_total_aum: position as % of ALL assets (cash + equity) — small number when portfolio is cash-heavy
            "weight_vs_total_aum": round(largest["weight"], 4),
            # weight_vs_equity_capital: position as % of invested equity only — correct concentration measure
            "weight_vs_equity_capital": largest_equity_weight,
            "note": "Use weight_vs_equity_capital for concentration analysis; weight_vs_total_aum is diluted by cash.",
        },
        "top3_position_weight_vs_total_aum": round(sum(sorted([r["weight_vs_total_aum"] for r in rows], reverse=True)[:3]), 4),
        "top3_position_weight_vs_equity": round(sum(sorted([r["weight_vs_equity_capital"] for r in rows], reverse=True)[:3]), 4),
        # concentration_hhi_vs_total_aum: HHI using total AUM as denominator; near-zero when mostly cash (misleading)
        "concentration_hhi_vs_total_aum": round(hhi, 4),
        # concentration_hhi_equity_only: HHI using invested equity as denominator — CORRECT for equity concentration
        # Values: <0.10 = well diversified, 0.10-0.25 = moderate, >0.25 = concentrated
        "concentration_hhi_equity_only": round(hhi_equity, 4),
        "hhi_interpretation": (
            "CONCENTRATED" if hhi_equity > 0.25
            else "MODERATE" if hhi_equity > 0.10
            else "DIVERSIFIED"
        ),
        "weighted_beta": round(weighted_beta, 4) if weighted_beta is not None else None,
        "var_proxy": {
            "method": "current_absolute_daily_move_weighted_proxy",
            "portfolio_abs_move_proxy_pct": round(daily_move_proxy * 100, 4),
            "note": "Not a historical VaR substitute; use as interim risk telemetry until history-based VaR is implemented.",
        },
        "sector_exposure": {k: round(v, 4) for k, v in sorted(sector_exposure.items())},
        "asset_type_exposure": {k: round(v, 4) for k, v in sorted(asset_type_exposure.items())},
        "constraint_breaches": sorted(set(breaches)),
        "liquidity_flags": liquidity_flags,
        # pnl_integrity_conflicts: positions where broker unrealized != computed (price-avg_cost)*qty
        "pnl_integrity_conflicts": pnl_integrity_conflicts,
        "positions": rows,
    }


# ---------------------------------------------------------------------------
# MAIN EXPORT
# ---------------------------------------------------------------------------

def export_dataset_raw(
    signals_per_source: int = SIGNALS_PER_SOURCE,
    latest_limit: int = LATEST_LIMIT,
) -> Dict[str, Any]:

    root = _project_root()
    sys.path.insert(0, str(root))

    from dotenv import load_dotenv
    load_dotenv(root / ".env")

    from core.db import get_connection
    conn = get_connection()

    try:
        cur = conn.cursor(dictionary=True)

        # -- Schema discovery --------------------------------------------------
        cols    = _table_cols(cur, "raw_signal_archive")
        ts_col  = _pick(cols, ["received_at", "archived_at", "ingested_at", "created_at"])
        id_col  = _pick(cols, ["id"])
        src_col = _pick(cols, ["source"])
        if not all([ts_col, id_col, src_col]):
            raise RuntimeError(f"Cannot find required columns. Got: {cols}")

        # -- Totals ------------------------------------------------------------
        total_signals   = int(_scalar(cur, "SELECT COUNT(*) FROM raw_signal_archive") or 0)
        latest_signal_at = _json_safe(
            _scalar(cur, f"SELECT MAX({ts_col}) FROM raw_signal_archive")
        )

        # -- Source activity ---------------------------------------------------
        source_counts = _q(cur, f"""
            SELECT source, COUNT(*) AS n, MAX({ts_col}) AS last_seen
            FROM raw_signal_archive
            GROUP BY source
            ORDER BY source
        """)
        activity = {r["source"]: {"n": int(r["n"]), "last_seen": _json_safe(r["last_seen"])}
                    for r in source_counts}
        # BUG-001 FIX: split into external (in SOURCE_REGISTRY) vs derived internal sources
        # Internal derived: LivePrices_Moomoo, Portfolio_Snapshot, Regime_Detection,
        # Event_Correlation, Ticker_Sentiment, Moomoo_Intel, Analyst_Targets, ECE_Probe etc.
        INTERNAL_DERIVED = {
            "LivePrices_Moomoo","Portfolio_Snapshot","Regime_Detection","Event_Correlation",
            "Ticker_Sentiment","Moomoo_Intel","Analyst_Targets","ECE_Probe",
            "LivePrices_Fallback","Moomoo_CapitalFlow","Moomoo_Fundamentals","FRED_StLouis",
            "Cross_Market_Confirmation","Portfolio_ReadOnly_Moomoo","Historical_Prices_Moomoo",
            "Historical_Risk_Model","Thesis_Lifecycle","Monitoring_Governance",
            "Corporate_Actions_Moomoo",
        }
        external_active = len([s for s in activity if s in SOURCE_REGISTRY])
        derived_active  = len([s for s in activity if s not in SOURCE_REGISTRY])
        sources_active  = len(activity)

        # -- COGNITION: Regime -------------------------------------------------
        regime = None
        rows = _q(cur, f"""
            SELECT * FROM raw_signal_archive
            WHERE source = 'Regime_Detection'
            ORDER BY {ts_col} DESC LIMIT 1
        """)
        if rows:
            regime = _parse_payload(rows[0].get("raw_payload")) or rows[0].get("raw_text")

        # -- COGNITION: Portfolio ----------------------------------------------
        portfolio = None
        rows = _q(cur, f"""
            SELECT * FROM raw_signal_archive
            WHERE source = 'Portfolio_Snapshot'
            ORDER BY {ts_col} DESC LIMIT 1
        """)
        if rows:
            portfolio = _parse_payload(rows[0].get("raw_payload")) or rows[0].get("raw_text")

        # -- COGNITION: Live Prices --------------------------------------------
        live_prices = None
        rows = _q(cur, f"""
            SELECT * FROM raw_signal_archive
            WHERE source = 'LivePrices_Moomoo'
            ORDER BY {ts_col} DESC LIMIT 1
        """)
        if rows:
            live_prices = _parse_payload(rows[0].get("raw_payload")) or rows[0].get("raw_text")

        # -- COGNITION: Fear & Greed -------------------------------------------
        fear_greed = None
        rows = _q(cur, f"""
            SELECT * FROM raw_signal_archive
            WHERE source = 'CNN_FearGreed'
            ORDER BY {ts_col} DESC LIMIT 1
        """)
        if rows:
            fear_greed = _parse_payload(rows[0].get("raw_payload")) or rows[0].get("raw_text")

        # -- COGNITION: Analyst Targets ----------------------------------------
        analyst_targets = {}
        rows = _q(cur, f"""
            SELECT raw_text, raw_payload FROM raw_signal_archive
            WHERE source = 'Analyst_Targets'
            ORDER BY {ts_col} DESC LIMIT 250
        """)
        for r in rows:
            payload = _parse_payload(r.get("raw_payload"))
            if isinstance(payload, dict) and payload.get("ticker"):
                ticker = payload["ticker"]
                if ticker not in analyst_targets:
                    # Normalise: DB stores avg_target, expose as average for consumers
                    if "avg_target" in payload and "average" not in payload:
                        payload["average"] = payload["avg_target"]
                    analyst_targets[ticker] = payload

        # -- COGNITION: Moomoo Intel -------------------------------------------
        # BUG-007 FIX: DB has duplicates from multiple ingest cycles
        # Fetch latest 300, deduplicate on text content, keep 100 unique
        moomoo_intel = []
        rows = _q(cur, f"""
            SELECT raw_text FROM raw_signal_archive
            WHERE source = 'Moomoo_Intel'
            ORDER BY {ts_col} DESC, id DESC LIMIT 300
        """)
        import re as _re
        _seen_mi = set()
        for _r in rows:
            _txt = _r.get("raw_text", "")
            if _txt:
                # BUG-004 FIX: strip fabricated analyst headcount from DB records
                # Moomoo only returns percentages — "— N analysts surveyed" is wrong
                # Strip "— N analysts surveyed" suffix (fabricated headcount)
                if " analysts surveyed" in _txt:
                    _txt = _txt[:_txt.rfind(" — ")].rstrip() if " — " in _txt else _txt
                _key = _txt.strip()[:200]
                if _key not in _seen_mi:
                    _seen_mi.add(_key)
                    moomoo_intel.append(_txt)
                    if len(moomoo_intel) >= 100:
                        break

        # -- COGNITION: Event Correlations -------------------------------------
        event_correlations     = []
        event_correlations_all = []
        rows = _q(cur, f"""
            SELECT * FROM raw_signal_archive
            WHERE source = 'Event_Correlation'
            ORDER BY {ts_col} DESC LIMIT 10
        """)
        # Only use the LATEST cycle's correlations to avoid duplicates across cycles
        latest_ec = None
        for r in rows:
            parsed = _parse_payload(r.get("raw_payload"))
            if isinstance(parsed, dict) and "correlations" in parsed:
                latest_ec = parsed
                break  # rows ordered DESC -- first hit is latest cycle
        # Canonical 23-theme universe — must match EVENT_THEMES in ingest_u.py exactly.
        # Themes with no signals this cycle are padded with NO SIGNAL entries
        # so the research report always sees all 23 rows — never a silent gap.
        # Must match ECE_THEME_UNIVERSE in research_report_generator.py exactly
        _CANONICAL_23 = [
            "AI / SEMIS", "BANKS / LIQUIDITY", "CONSUMER TECH / APPLE",
            "CLEAN ENERGY / SOLAR", "ENERGY / URANIUM", "NUCLEAR / POWER GRID",
            "COPPER / INDUSTRIAL METALS", "RARE EARTH / METALS", "GOLD / SAFE HAVEN",
            "SPACE / DEFENSE", "QUANTUM", "SOFTWARE / CYBERSECURITY",
            "FINTECH / CRYPTO", "IPO / MOMENTUM", "BIOTECH / PHARMA",
            "DEFENSE / AEROSPACE", "OIL / GAS", "UTILITIES / POWER",
            "MAG7 / BIG TECH", "GEOPOLITICAL", "TRUMP / TRADE",
            "EARNINGS CATALYST", "MACRO / FED",
        ]

        if latest_ec:
            for corr in latest_ec["correlations"]:
                corr["cycle_ts"] = latest_ec.get("cycle_ts", "")
                event_correlations.append(corr)
                event_correlations_all.append(corr)

        # Pad missing themes — ensure all 23 always present
        active_themes = {c["theme"] for c in event_correlations}
        cycle_ts      = latest_ec.get("cycle_ts", "") if latest_ec else ""
        for theme in _CANONICAL_23:
            if theme not in active_themes:
                no_signal = {
                    "theme":                    theme,
                    "layers":                   [],
                    "source_count":             0,
                    "basket_move":              0.0,
                    "confidence":               0.0,
                    "evidence_tier":            None,
                    "evidence_tier_label":      None,
                    "direction":                "NO SIGNAL",
                    # ECE v2 canonical fields (WO-ECE-20260613-001) — all themes must carry these
                    "sector_direction":         "NEUTRAL",
                    "global_regime_context":    "",
                    "catalyst_polarity":        "NEUTRAL",
                    "review_flags":             [],
                    "governing_logic_version":  "ECE_v2",
                    "broad_rally_confirmed":    False,
                    "why":                      "No active ECE signal this cycle.",
                    "analyst_rating_integrity": "N/A",
                    "cycle_ts":                 cycle_ts,
                }
                event_correlations.append(no_signal)
                event_correlations_all.append(no_signal)

        # Sort: active themes by confidence desc, then NO SIGNAL themes at bottom
        event_correlations.sort(key=lambda x: (
            0 if x["direction"] == "NO SIGNAL" else -1,
            -x.get("confidence", 0)
        ))
        event_correlations_all.sort(key=lambda x: (
            0 if x["direction"] == "NO SIGNAL" else -1,
            -x.get("confidence", 0)
        ))

        # -- COGNITION: Ticker Sentiment ---------------------------------------
        # Ticker_Sentiment is not in SOURCE_REGISTRY so per-source query returns 0.
        # Query directly from raw_signal_archive like other cognition sources.
        ticker_sentiment = {}
        rows = _q(cur, f"""
            SELECT raw_text, raw_payload FROM raw_signal_archive
            WHERE source = 'Ticker_Sentiment'
            ORDER BY {ts_col} DESC, id DESC LIMIT 200
        """)
        for r in rows:
            payload = _parse_payload(r.get("raw_payload"))
            if isinstance(payload, dict) and payload.get("ticker"):
                t = str(payload["ticker"]).upper()
                if t not in ticker_sentiment:
                    # BUG-006 FIX: strip all processing flags from label
                    # Flags [OK], [DUP], [OPEN] are metadata not sentiment
                    raw_label = payload.get("label", "NEUTRAL")
                    import re as _re
                    clean_label = _re.sub(r"^\[\w+\]\s*", "", raw_label).strip()
                    # Extract flag values into separate fields
                    dup_flag     = "[DUP]"  in raw_label
                    open_flag    = "[OPEN]" in raw_label
                    payload["sentiment_label"]       = clean_label or "NEUTRAL"
                    payload["label"]                 = clean_label or "NEUTRAL"
                    payload["duplicate_flag"]        = dup_flag
                    payload["market_session_flag"]   = "OPEN" if open_flag else None
                    relevance = _sentiment_relevance(t, payload, r.get("raw_text") or "")
                    payload["ticker_relevance"]      = relevance["relevance"]
                    payload["matched_entity_terms"]  = relevance["matched_terms"]
                    payload["discarded_for_institutional_sentiment"] = relevance["discarded"]
                    # Canonical field name for report rendering and audit checks
                    payload["sentiment_relevance_status"] = (
                        "PASS" if not relevance["discarded"] else "LOW_RELEVANCE / DISCARD"
                    )
                    if relevance["discarded"]:
                        payload["sentiment_label"] = "LOW_RELEVANCE / DISCARD"
                        payload["label"] = "LOW_RELEVANCE / DISCARD"
                    # Governance Hardening Patch: headline-level filtering
                    # Even when ticker-level status = PASS, filter the headlines list
                    # to remove individual dirty headlines (e.g. WFC barbecue, BAC DraftKings)
                    _raw_headlines = payload.get("headlines") or []
                    if isinstance(_raw_headlines, list) and _raw_headlines:
                        _ticker_aliases = TICKER_ENTITY_ALIASES.get(t, {t})
                        _clean_hl, _dirty_hl = [], []
                        for _hl in _raw_headlines:
                            _hl_up = str(_hl).upper()
                            if any(_a in _hl_up for _a in _ticker_aliases):
                                _clean_hl.append(_hl)
                            else:
                                _dirty_hl.append(_hl)
                        payload["headlines"] = _clean_hl          # Only relevant headlines shown in report
                        payload["headlines_raw"] = _raw_headlines  # Preserved for audit
                        payload["dirty_headlines"] = _dirty_hl
                        payload["clean_headline_count"] = len(_clean_hl)
                        payload["dirty_headline_count"] = len(_dirty_hl)
                    ticker_sentiment[t] = payload

        # -- SIGNALS: per source -----------------------------------------------
        signals: Dict[str, List[Dict[str, Any]]] = {}
        for source_id in SOURCE_REGISTRY:
            rows = _q(cur, f"""
                SELECT * FROM raw_signal_archive
                WHERE source = %s
                ORDER BY {ts_col} DESC, id DESC
                LIMIT %s
            """, (source_id, signals_per_source))
            signals[source_id] = [_signal_row(r, ts_col) for r in rows]

        # -- SIGNALS: latest across all sources --------------------------------
        latest_id_rows = _q(cur, """
            SELECT id
            FROM raw_signal_archive
            ORDER BY id DESC
            LIMIT %s
        """, (latest_limit,))
        latest_ids = [r.get("id") for r in latest_id_rows if r.get("id") is not None]
        signals_latest = []
        if latest_ids:
            placeholders = ",".join(["%s"] * len(latest_ids))
            latest_rows = _q(cur, f"""
                SELECT *
                FROM raw_signal_archive
                WHERE id IN ({placeholders})
            """, tuple(latest_ids))
            latest_rows.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
            signals_latest = [_signal_row(r, ts_col) for r in latest_rows]

        # -- Source health summary ---------------------------------------------
        source_health = []
        for src_id, meta in SOURCE_REGISTRY.items():
            act = activity.get(src_id, {})
            source_health.append({
                "source":       src_id,
                "tier":         meta["tier"],
                "trust":        meta["trust"],
                "signal_type":  meta["signal_type"],
                "active":       src_id in activity,
                "signal_count": act.get("n", 0),
                "last_seen":    act.get("last_seen"),
            })
        source_health.sort(key=lambda x: (x["tier"], x["source"]))

        # -- FUNDAMENTALS: from ticker_fundamentals table ----------------------
        fundamentals: Dict[str, Any] = {}
        try:
            rows = _q(cur, """
                SELECT ticker, snapshot_date, cycle_ts,
                       pe_ttm, pe_forward, pb_ratio, eps_ttm, eps_forward,
                       dividend_yield, market_cap, shares_outstanding,
                       beta, avg_volume_30d,
                       high_52w, low_52w, pct_from_52w_high, pct_from_52w_low,
                       earnings_yield, net_income_ttm
                FROM ticker_fundamentals
                WHERE (ticker, snapshot_date) IN (
                    SELECT ticker, MAX(snapshot_date)
                    FROM ticker_fundamentals
                    GROUP BY ticker
                )
                ORDER BY ticker
            """)
            for r in rows:
                t = r.pop("ticker", None)
                if t:
                    rec = _json_safe(r)
                    # Rename DB column names → spec field names
                    # (MID_DATA_INTELLIGENCE_REQUEST_VERIFIED.md field names)
                    # Primary renames — DB column → spec field name
                    rec["pe_ttm_ratio"]         = rec.pop("pe_ttm",         None)
                    rec["pe_ratio"]             = rec.pop("pe_forward",     None)
                    rec["net_asset_per_share"]  = rec.pop("eps_forward",    None)
                    rec["earning_per_share"]    = rec.pop("eps_ttm",        None)
                    rec["dividend_ratio_ttm"]   = rec.pop("dividend_yield",  None)
                    rec["total_market_val"]     = rec.pop("market_cap",      None)
                    rec["net_profit"]           = rec.pop("net_income_ttm",  None)
                    # ey_ratio = earnings_yield (keep both for compatibility)
                    rec["ey_ratio"]             = rec.get("earnings_yield",  None)
                    # 52-week field names — spec uses full names
                    rec["highest52weeks_price"] = rec.pop("high_52w",        None)
                    rec["lowest52weeks_price"]  = rec.pop("low_52w",         None)
                    # equity_valid: True if equity (has PE), False if ETF (all nulls)
                    rec["equity_valid"] = rec.get("pe_ttm_ratio") is not None
                    # BUG-011 FIX: add asset_type and fundamental_applicability
                    _ETF_TICKERS = {"GLD","SLV","TLT","QTUM","GDX","GDXJ","IAU","SLV","USO"}
                    if not rec["equity_valid"]:
                        rec["asset_type"]                = "ETF" if t in _ETF_TICKERS else "FUND_OR_INDEX"
                        rec["fundamental_applicability"] = "not_applicable"
                    else:
                        rec["asset_type"]                = "EQUITY"
                        rec["fundamental_applicability"] = "applicable"
                    fundamentals[t] = rec
        except Exception as e:
            fundamentals = {"_error": str(e)}

        # -- CAPITAL FLOW: from ticker_capital_flow table -----------------------
        capital_flow: Dict[str, Any] = {}
        try:
            rows = _q(cur, """
                SELECT ticker, snapshot_date, cycle_ts,
                       main_net, super_large_net, large_net, medium_net, small_net,
                       super_large_in, super_large_out,
                       large_in, large_out, medium_in, medium_out,
                       small_in, small_out, institutional_bias
                FROM ticker_capital_flow
                WHERE (ticker, snapshot_date) IN (
                    SELECT ticker, MAX(snapshot_date)
                    FROM ticker_capital_flow
                    GROUP BY ticker
                )
                ORDER BY ticker
            """)
            for r in rows:
                t = r.pop("ticker", None)
                if t:
                    rec = _json_safe(r)
                    # Compute in_flow = total net flow across all lot sizes
                    # This matches spec field name from MID_DATA_INTELLIGENCE_REQUEST_VERIFIED.md
                    # in_flow = super_large + large + medium + small (all lot sizes combined)
                    super_n = rec.get("super_large_net") or 0
                    large_n = rec.get("large_net")       or 0
                    medium_n= rec.get("medium_net")      or 0
                    small_n = rec.get("small_net")       or 0
                    rec["in_flow"] = round(super_n + large_n + medium_n + small_n, 2)
                    capital_flow[t] = rec
        except Exception as e:
            capital_flow = {"_error": str(e)}

        # -- TREASURY YIELDS: from macro_yields table ---------------------------
        treasury_yields: Dict[str, Any] = {}
        try:
            rows = _q(cur, """
                SELECT snapshot_date, cycle_ts, source,
                       yield_10y, yield_2y, yield_30y, yield_3m,
                       ffr_target, ffr_upper, ffr_lower,
                       yield_spread_10_2, yield_spread_10_3m,
                       curve_status, nim_proxy
                FROM macro_yields
                ORDER BY snapshot_date DESC
                LIMIT 1
            """)
            if rows:
                treasury_yields = _json_safe(rows[0])
        except Exception as e:
            treasury_yields = {"_error": str(e)}

        # -- CROSS-MARKET CONFIRMATION: from raw_signal_archive ----------------
        cross_market_confirmation: Dict[str, Any] = {}
        try:
            rows = _q(cur, f"""
                SELECT raw_payload, raw_text, {ts_col} AS received_at
                FROM raw_signal_archive
                WHERE source = 'Cross_Market_Confirmation'
                ORDER BY {ts_col} DESC, id DESC
                LIMIT 1
            """)
            if rows:
                cross_market_confirmation = _parse_payload(rows[0].get("raw_payload")) or {}
                if isinstance(cross_market_confirmation, dict):
                    cross_market_confirmation.setdefault("received_at", _json_safe(rows[0].get("received_at")))
        except Exception as e:
            cross_market_confirmation = {"status": "extract_error", "reason": str(e)}

        # ── GAP REPORT REMEDIATION v1.8 ─────────────────────────────────────────
        # gap_report_20260602_230000 — 5 new intelligence layers

        # -- GAP 1: CONFERENCE CALENDAR -----------------------------------------
        conference_calendar: List[Any] = []
        try:
            rows = _q(cur, """
                SELECT conference_name, conference_slug, edition_year,
                       event_date_start, event_date_end, keynote_date,
                       keynote_time_local, keynote_timezone,
                       keynote_speakers, hosting_company,
                       location_city, location_country,
                       impact_tier, affected_tickers, affected_themes,
                       hist_impact_bull, hist_impact_base, hist_impact_bear,
                       hist_years_tracked, days_until_event, catalyst_flag,
                       announcement_url, source, fetched_at, snapshot_date, notes
                FROM conference_calendar
                WHERE catalyst_flag != 'PAST'
                   OR event_date_start >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                ORDER BY event_date_start ASC
            """)
            conference_calendar = [_json_safe(r) for r in rows]
        except Exception as e:
            conference_calendar = [{"_error": str(e)}]

        # -- GAP 2: CEO APPEARANCE TRACKER --------------------------------------
        ceo_appearances: List[Any] = []
        try:
            rows = _q(cur, """
                SELECT executive_name, executive_slug, company, ticker, tier,
                       appearance_type, event_name, conference_slug,
                       appearance_date, is_scheduled, is_confirmed,
                       topics_expected, sentiment_bias, affected_tickers,
                       alert_72h_flag, alert_24h_flag,
                       source_url, source, fetched_at, snapshot_date
                FROM ceo_appearance_tracker
                WHERE appearance_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
                ORDER BY alert_72h_flag DESC, appearance_date ASC
            """)
            ceo_appearances = [_json_safe(r) for r in rows]
        except Exception as e:
            ceo_appearances = [{"_error": str(e)}]

        # -- GAP 3: PORTFOLIO CATALYST CALENDAR ---------------------------------
        catalyst_calendar: Dict[str, Any] = {"all": [], "portfolio_only": [], "working_orders": []}
        try:
            rows = _q(cur, """
                SELECT pcc.ticker, pcc.catalyst_type, pcc.catalyst_date, pcc.catalyst_time_et,
                       pcc.is_confirmed, pcc.is_estimate,
                       pcc.event_name, pcc.event_venue, pcc.event_url,
                       pcc.eps_estimate, pcc.eps_prior, pcc.revenue_estimate,
                       pcc.in_portfolio, pcc.has_working_order,
                       DATEDIFF(pcc.catalyst_date, CURDATE()) AS days_until_catalyst,
                       CASE
                           WHEN pcc.catalyst_date < CURDATE()                    THEN 'PAST'
                           WHEN pcc.catalyst_date = CURDATE()                    THEN 'ACTIVE'
                           WHEN DATEDIFF(pcc.catalyst_date, CURDATE()) <= 3      THEN 'IMMINENT'
                           WHEN DATEDIFF(pcc.catalyst_date, CURDATE()) <= 14     THEN 'UPCOMING'
                           ELSE 'FUTURE'
                       END AS alert_flag,
                       pcc.source, pcc.snapshot_date
                FROM portfolio_catalyst_calendar pcc
                INNER JOIN (
                    SELECT ticker, MAX(snapshot_date) AS latest_snap
                    FROM portfolio_catalyst_calendar
                    WHERE catalyst_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
                    GROUP BY ticker
                ) latest ON pcc.ticker = latest.ticker
                         AND pcc.snapshot_date = latest.latest_snap
                WHERE pcc.catalyst_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
                ORDER BY pcc.catalyst_date ASC, pcc.ticker ASC
            """)
            all_cats = [_json_safe(r) for r in rows]
            catalyst_calendar["all"]            = all_cats
            catalyst_calendar["portfolio_only"] = [r for r in all_cats if r.get("in_portfolio")]
            catalyst_calendar["working_orders"] = [r for r in all_cats if r.get("has_working_order")]
        except Exception as e:
            catalyst_calendar = {"_error": str(e)}

        # -- GAP 4: TECH PUBLICATION SIGNALS ------------------------------------
        tech_pub_signals: Dict[str, Any] = {}
        try:
            rows = _q(cur, """
                SELECT source, tier, trust_score,
                       headline, summary, article_url, published_at,
                       tickers_mentioned, themes_detected,
                       vader_score, sentiment_label, signal_type,
                       fetched_at, snapshot_date
                FROM tech_publication_signals
                WHERE snapshot_date >= DATE_SUB(CURDATE(), INTERVAL 2 DAY)
                ORDER BY published_at DESC
                LIMIT 200
            """)
            for r in rows:
                src = r.get("source", "UNKNOWN")
                if src not in tech_pub_signals:
                    tech_pub_signals[src] = []
                tech_pub_signals[src].append(_json_safe(r))
        except Exception as e:
            tech_pub_signals = {"_error": str(e)}

        # -- GAP 5: ECE NAMED EVENTS --------------------------------------------
        ece_named_events: List[Any] = []
        try:
            rows = _q(cur, """
                SELECT event_slug, event_name, event_category, description,
                       trigger_type, trigger_description,
                       base_case_sectors, base_case_impact_pct, base_case_duration_days,
                       bull_trigger, bull_case_impact_pct, bull_case_tickers, bull_duration_days,
                       bear_trigger, bear_case_impact_pct, bear_duration_days,
                       sector_impact_map, historical_years, years_tracked,
                       is_active, last_occurrence, next_occurrence,
                       source, authored_by, updated_at, notes
                FROM ece_named_events
                WHERE is_active = TRUE
                ORDER BY next_occurrence ASC
            """)
            ece_named_events = [_json_safe(r) for r in rows]
        except Exception as e:
            ece_named_events = [{"_error": str(e)}]

        # -- INSTITUTIONAL QUANT PROCESS LAYER ---------------------------------
        try:
            institutional_quant = _latest_institutional_quant_layer(cur)
        except Exception as e:
            institutional_quant = {
                "status": "extract_error",
                "reason": str(e),
            }

        # -- BLUELOTUS SUPERFORECAST / BRIER LAYER ---------------------------
        try:
            research_forecasting = _latest_research_forecasting_layer(cur)
        except Exception as e:
            research_forecasting = {
                "status": "extract_error",
                "reason": str(e),
            }

        # -- INSTITUTIONAL READINESS EXPORT BLOCKS -----------------------------
        live_prices_export = {
            **(live_prices.get("prices", {}) if isinstance(live_prices, dict) else {}),
            "vix":            live_prices.get("vix")            if isinstance(live_prices, dict) else None,
            "market_session": live_prices.get("market_session") if isinstance(live_prices, dict) else None,
            "top_movers":     live_prices.get("top_movers")     if isinstance(live_prices, dict) else None,
            "cycle_ts":       live_prices.get("cycle_ts")       if isinstance(live_prices, dict) else None,
            "ticker_count":   live_prices.get("ticker_count")   if isinstance(live_prices, dict) else None,
            "source":         live_prices.get("source")         if isinstance(live_prices, dict) else None,
        } if isinstance(live_prices, dict) else live_prices
        if isinstance(live_prices_export, dict):
            live_prices_export = _enrich_live_prices_relative_volume(live_prices_export, fundamentals)
        try:
            listing_status_map = _latest_listing_status_map(cur)
        except Exception:
            listing_status_map = {}
        try:
            portfolio_readonly = _latest_portfolio_readonly_layer(cur)
        except Exception as e:
            portfolio_readonly = {"status": "extract_error", "reason": str(e)}
        portfolio_effective = _portfolio_from_readonly(portfolio_readonly)
        if portfolio_effective:
            portfolio = portfolio_effective
        security_master = _build_security_master(
            live_prices_export if isinstance(live_prices_export, dict) else {},
            fundamentals if isinstance(fundamentals, dict) else {},
            analyst_targets if isinstance(analyst_targets, dict) else {},
            capital_flow if isinstance(capital_flow, dict) else {},
            portfolio if isinstance(portfolio, dict) else {},
            listing_status_map,
        )
        priority_intelligence = _build_priority_intelligence(cur, security_master)
        data_quality_sla = _build_data_quality_sla(source_health)
        portfolio_constraints = dict(PORTFOLIO_CONSTRAINTS_DEFAULT)
        risk_metrics = _build_risk_metrics(
            portfolio if isinstance(portfolio, dict) else {},
            live_prices_export if isinstance(live_prices_export, dict) else {},
            fundamentals if isinstance(fundamentals, dict) else {},
            security_master,
        )
        try:
            historical_price_coverage = _historical_price_coverage_layer(cur)
        except Exception as e:
            historical_price_coverage = {"status": "extract_error", "reason": str(e)}
        try:
            risk_model = _latest_risk_model_layer(cur)
        except Exception as e:
            risk_model = {"status": "extract_error", "reason": str(e)}
        try:
            portfolio_optimizer = _latest_portfolio_optimizer_layer(cur)
        except Exception as e:
            portfolio_optimizer = {"status": "extract_error", "reason": str(e)}
        portfolio_targets = portfolio_optimizer
        portfolio_mandates = _build_portfolio_mandates(
            portfolio if isinstance(portfolio, dict) else {},
            security_master,
        )
        try:
            thesis_lifecycle = _latest_thesis_lifecycle_layer(cur)
        except Exception as e:
            thesis_lifecycle = {"status": "extract_error", "reason": str(e)}
        try:
            monitoring_governance = _latest_monitoring_governance_layer(cur)
        except Exception as e:
            monitoring_governance = {"status": "extract_error", "reason": str(e)}
        try:
            report_archive = _latest_report_archive_layer(cur)
        except Exception as e:
            report_archive = {"status": "extract_error", "reason": str(e)}
        try:
            dataset_snapshot_archive = _latest_dataset_snapshot_archive_layer(cur)
        except Exception as e:
            dataset_snapshot_archive = {"status": "extract_error", "reason": str(e)}
        try:
            freshness_recovery = _latest_freshness_recovery_layer(cur)
        except Exception as e:
            freshness_recovery = {"status": "extract_error", "reason": str(e)}
        try:
            historical_backfill = _latest_historical_backfill_layer(cur)
        except Exception as e:
            historical_backfill = {"status": "extract_error", "reason": str(e)}
        try:
            cio_decisions = _latest_cio_decisions_layer(cur)
        except Exception as e:
            cio_decisions = {"status": "extract_error", "reason": str(e)}
        try:
            cio_cognition = _latest_cio_cognition_layer(cur)
        except Exception as e:
            cio_cognition = {"status": "extract_error", "reason": str(e)}
        try:
            orders_layer, fills_layer = _latest_execution_readonly_layer(cur)
        except Exception as e:
            orders_layer = {
                "status": "extract_error",
                "source": "Execution_ReadOnly_Moomoo",
                "reason": str(e),
                "orders_generated_by_pipeline": False,
                "order_routing_enabled": False,
            }
            fills_layer = {
                "status": "extract_error",
                "source": "Execution_ReadOnly_Moomoo",
                "reason": str(e),
                "orders_generated_by_pipeline": False,
            }
        execution, trade_lifecycle, transaction_cost_analysis = _build_execution_control_layers(
            cio_decisions,
            portfolio_targets,
            risk_model,
            portfolio_readonly,
            orders_layer,
            fills_layer,
        )
        deterministic_operators = _read_json_artifact(DETERMINISTIC_OPERATORS_LATEST)
        try:
            corporate_actions, delistings = _latest_corporate_actions_layer(cur)
        except Exception as e:
            corporate_actions = {"status": "extract_error", "reason": str(e)}
            delistings = {"status": "extract_error", "reason": str(e)}
        signal_validation, backtest_results = _build_signal_validation_blocks(cur, research_forecasting)
        audit = {
            "status": "operational",
            "version": "v1.0",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "monitoring": monitoring_governance,
            "report_archive": report_archive,
            "dataset_snapshot_archive": dataset_snapshot_archive,
            "freshness_recovery": freshness_recovery,
            "historical_backfill": historical_backfill,
            "cio_decisions": {
                "pending_review_count": cio_decisions.get("pending_review_count") if isinstance(cio_decisions, dict) else None,
                "orders_generated": cio_decisions.get("orders_generated") if isinstance(cio_decisions, dict) else None,
                "execution_authority": cio_decisions.get("execution_authority") if isinstance(cio_decisions, dict) else None,
            },
            "cio_cognition": {
                "latest_journal_id": cio_cognition.get("latest_journal_id") if isinstance(cio_cognition, dict) else None,
                "review_count": cio_cognition.get("review_count") if isinstance(cio_cognition, dict) else None,
                "orders_generated": cio_cognition.get("orders_generated") if isinstance(cio_cognition, dict) else None,
                "execution_authority": cio_cognition.get("execution_authority") if isinstance(cio_cognition, dict) else None,
            },
            "execution_protocol": {
                "broker_extract_only": True,
                "orders_generated_by_pipeline": False,
                "execution_authority": "CIO_ONLY",
            },
            "execution": {
                "status": execution.get("status"),
                "orders_generated_by_pipeline": execution.get("orders_generated_by_pipeline"),
                "order_routing_enabled": execution.get("order_routing_enabled"),
                "read_only_order_history_extraction": execution.get("read_only_order_history_extraction"),
                "read_only_deal_history_extraction": execution.get("read_only_deal_history_extraction"),
            },
            "deterministic_operators": {
                "status": deterministic_operators.get("status") if isinstance(deterministic_operators, dict) else None,
                "readiness": deterministic_operators.get("readiness") if isinstance(deterministic_operators, dict) else None,
                "llm_used": deterministic_operators.get("llm_used") if isinstance(deterministic_operators, dict) else None,
                "orders_generated": deterministic_operators.get("orders_generated") if isinstance(deterministic_operators, dict) else None,
                "blocked_actions": (
                    (deterministic_operators.get("summary") or {}).get("blocked_actions")
                    if isinstance(deterministic_operators, dict) and isinstance(deterministic_operators.get("summary"), dict)
                    else []
                ),
            },
        }
        data_lineage = (
            monitoring_governance.get("lineage")
            if isinstance(monitoring_governance, dict) and isinstance(monitoring_governance.get("lineage"), dict)
            else {}
        )
        if isinstance(data_lineage, dict):
            data_lineage.setdefault("status", "operational" if data_lineage else "pending_first_monitoring_run")
            data_lineage.setdefault("exporter", "export_dataset_raw.py")

        # -- BUG-010: Build freshness input dict from section timestamps ------
        def _ts(obj, key="cycle_ts"):
            """Extract timestamp string from a section dict or list.
            DEFECT-05 FIX: gap tables store fetched_at not cycle_ts.
            Check all three keys: key arg, fetched_at, timestamp.
            """
            if isinstance(obj, dict):
                return str(
                    obj.get(key) or obj.get("fetched_at") or
                    obj.get("cycle_ts") or obj.get("timestamp") or ""
                )
            if isinstance(obj, list) and obj: return _ts(obj[0], key)
            return ""
        dataset_for_freshness = {
            "portfolio":       _ts(portfolio),
            "capital_flow":    _ts(next(iter(capital_flow.values()), {})) if capital_flow else "",
            "fundamentals":    _ts(next(iter(fundamentals.values()), {})) if fundamentals else "",
            "ticker_sentiment":_ts(next(iter(ticker_sentiment.values()), {})) if ticker_sentiment else "",
            "treasury_yields": _ts(treasury_yields) if isinstance(treasury_yields, dict) else "",
            "cross_market_confirmation": _ts(cross_market_confirmation) if isinstance(cross_market_confirmation, dict) else "",
            "fear_greed":      str(fear_greed.get("timestamp","")) if isinstance(fear_greed, dict) else "",
            "live_prices":     _ts(live_prices) if isinstance(live_prices, dict) else "",
            # v1.8 gap report additions
            "conference_calendar": _ts(next(iter(conference_calendar), {})) if conference_calendar else "",
            "ceo_appearances":     _ts(next(iter(ceo_appearances), {})) if ceo_appearances else "",
            # DEFECT-05 FIX: tech_pub_signals is Dict[source, List[row]]
            # Flatten to get first row across all sources, then extract timestamp
            "tech_pub_signals":    _ts(
                next(
                    (row for rows in tech_pub_signals.values()
                     if isinstance(rows, list)
                     for row in rows if isinstance(row, dict)),
                    {}
                )
            ) if tech_pub_signals and not tech_pub_signals.get("_error") else "",
            "research_forecasting": _ts(research_forecasting, "forecast_date") if isinstance(research_forecasting, dict) else "",
            "portfolio_readonly": _ts(portfolio_readonly) if isinstance(portfolio_readonly, dict) else "",
            "historical_price_coverage": _ts(historical_price_coverage, "latest_fetch") if isinstance(historical_price_coverage, dict) else "",
            "risk_model": _ts(risk_model, "generated_at") if isinstance(risk_model, dict) else "",
            "portfolio_targets": _ts(portfolio_targets, "generated_at") if isinstance(portfolio_targets, dict) else "",
            "thesis_lifecycle": _ts(thesis_lifecycle, "generated_at") if isinstance(thesis_lifecycle, dict) else "",
            "monitoring_governance": _ts(monitoring_governance, "generated_at") if isinstance(monitoring_governance, dict) else "",
            "dataset_snapshot_archive": _ts(dataset_snapshot_archive, "generated_at") if isinstance(dataset_snapshot_archive, dict) else "",
            "freshness_recovery": _ts(freshness_recovery, "generated_at") if isinstance(freshness_recovery, dict) else "",
            "historical_backfill": _ts(historical_backfill, "generated_at") if isinstance(historical_backfill, dict) else "",
            "cio_decisions": _ts(cio_decisions, "generated_at") if isinstance(cio_decisions, dict) else "",
            "cio_cognition": _ts(cio_cognition, "generated_at") if isinstance(cio_cognition, dict) else "",
            "orders": _ts(orders_layer, "cycle_ts") if isinstance(orders_layer, dict) else "",
            "fills": _ts(fills_layer, "cycle_ts") if isinstance(fills_layer, dict) else "",
            "execution": _ts(execution, "generated_at") if isinstance(execution, dict) else "",
            "trade_lifecycle": _ts(trade_lifecycle, "generated_at") if isinstance(trade_lifecycle, dict) else "",
            "transaction_cost_analysis": _ts(transaction_cost_analysis, "generated_at") if isinstance(transaction_cost_analysis, dict) else "",
            "corporate_actions": _ts(corporate_actions, "generated_at") if isinstance(corporate_actions, dict) else "",
            "delistings": _ts(delistings, "generated_at") if isinstance(delistings, dict) else "",
        }

        # -- Assemble ----------------------------------------------------------
        dataset = {
            "meta": {
                "export_version":    EXPORT_VERSION,
                "ingest_version":    INGEST_VERSION,
                "generated_at":      datetime.now().isoformat(timespec="seconds"),
                # DEFECT-07 FIX: market_session surfaced at meta level.
                # Source: live_prices.market_session written by ingest_u.py v2.6u.
                # Values: PRE_MARKET / REGULAR / POST_MARKET / CLOSED / UNKNOWN
                "market_session":    _market_status_label(
                    live_prices if isinstance(live_prices, dict) else {},
                    regime if isinstance(regime, dict) else {},
                ),
                "sources_expected":       len(SOURCE_REGISTRY),
                "external_sources_active": external_active,
                "derived_sources_active":  derived_active,
                "sources_active":          sources_active,
                "freshness":               _compute_freshness(dataset_for_freshness),
                "total_signals":     total_signals,
                "latest_signal_at":  latest_signal_at,
                "signals_per_source": signals_per_source,
                "latest_limit":       latest_limit,
            },
            "source_health":      source_health,
            "regime":             regime,
            "portfolio":          portfolio,
            # OPTION A FIX (WO-RD-20260604-002 Problem 1):
            # Flatten live_prices so tickers are accessible at top level.
            # Old: live_prices.prices.NVDA.price  (nested -- consumers failing)
            # New: live_prices.NVDA.price          (flat -- all consumers work)
            # Metadata fields (market_session, vix, top_movers etc.) preserved.
            # DB payload and ingest_u.py are unchanged -- fix is export-only.
            "live_prices":        live_prices_export,
            # BUG-014 FIX: attach staleness flag to fear_greed
            "fear_greed":         _add_fg_staleness(fear_greed),
            "analyst_targets":    analyst_targets,
            "moomoo_intel":       moomoo_intel,
            "event_correlations":     event_correlations,
            "event_correlations_all": event_correlations_all,
            "ticker_sentiment":   ticker_sentiment,
            "fundamentals":       fundamentals,
            "capital_flow":       capital_flow,
            "treasury_yields":    treasury_yields,
            "cross_market_confirmation": cross_market_confirmation,
            "security_master":    security_master,
            "data_quality_sla":   data_quality_sla,
            "portfolio_constraints": portfolio_constraints,
            "risk_metrics":       risk_metrics,
            "portfolio_readonly":  portfolio_readonly,
            "historical_price_coverage": historical_price_coverage,
            "risk_model":         risk_model,
            "portfolio_targets":  portfolio_targets,
            "target_weights":     portfolio_targets.get("target_weights") if isinstance(portfolio_targets, dict) else {},
            "portfolio_optimizer": portfolio_optimizer,
            "portfolio_mandates": portfolio_mandates,
            "thesis_lifecycle":   thesis_lifecycle,
            "signal_validation":  signal_validation,
            "backtest_results":   backtest_results,
            "monitoring":         monitoring_governance,
            "audit":              audit,
            "data_lineage":       data_lineage,
            "report_archive":     report_archive,
            "dataset_snapshot_archive": dataset_snapshot_archive,
            "freshness_recovery": freshness_recovery,
            "historical_backfill": historical_backfill,
            "cio_decisions":      cio_decisions,
            "cio_decision_journal": cio_decisions,
            "cio_cognition":      cio_cognition,
            "cio_cognition_journal": cio_cognition,
            "orders":             orders_layer,
            "fills":              fills_layer,
            "execution":          execution,
            "trade_lifecycle":    trade_lifecycle,
            "transaction_cost_analysis": transaction_cost_analysis,
            "deterministic_operators": deterministic_operators,
            "corporate_actions":  corporate_actions,
            "delistings":         delistings,
            # v1.8 gap report additions — gap_report_20260602_230000
            "conference_calendar": conference_calendar,
            "ceo_appearances":     ceo_appearances,
            "catalyst_calendar":   catalyst_calendar,
            "macro_event_risks":    MACRO_EVENT_RISKS,
            "tech_pub_signals":    tech_pub_signals,
            "ece_named_events":    ece_named_events,
            "priority_intelligence": priority_intelligence,
            "institutional_quant":  institutional_quant,
            "research_forecasting": research_forecasting,
            "signals":            signals,
            "signals_latest":     signals_latest,
        }

        if build_v3_1_to_v3_4_payload is not None:
            dataset = build_v3_1_to_v3_4_payload(dataset)
        else:
            dataset["v3_1_to_v3_4_upgrade_error"] = {
                "status": "IMPORT_FAILED",
                "module": "canonical.canonical_data_contract",
            }
        if build_public_dataset is not None:
            try:
                public_dataset = build_public_dataset(dataset)
                public_path = PROJECT_ROOT / "data" / "frontend" / "dataset_public.json"
                public_path.write_text(json.dumps(_json_safe(public_dataset), indent=2, ensure_ascii=False), encoding="utf-8")
                dataset["public_dataset_manifest"] = {
                    "status": "WRITTEN",
                    "path": str(public_path),
                    "source_size_bytes": len(json.dumps(_json_safe(dataset), ensure_ascii=False).encode("utf-8")),
                    "public_size_bytes": public_path.stat().st_size,
                }
            except Exception as exc:
                dataset["public_dataset_manifest"] = {"status": "FAILED", "failure_mode": str(exc)}

        return _json_safe(dataset)

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def main() -> None:
    signals_per_source = int(os.getenv("BL_RAW_SIGNALS_PER_SOURCE", str(SIGNALS_PER_SOURCE)))
    latest_limit       = int(os.getenv("BL_RAW_LATEST_LIMIT",        str(LATEST_LIMIT)))

    root    = _project_root()
    out_dir = root / "data" / "frontend"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / EXPORT_FILENAME

    print()
    print("─" * 62)
    print("  BlueLotus MID — dataset_raw.json exporter")
    print(f"  ingest {INGEST_VERSION} | export {EXPORT_VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print("─" * 62)
    print(f"  Signals per source : {signals_per_source}")
    print(f"  Latest limit       : {latest_limit}")
    print(f"  Output             : {out_path}")
    print()

    try:
        t0      = datetime.now()
        dataset = export_dataset_raw(
            signals_per_source=signals_per_source,
            latest_limit=latest_limit,
        )
        elapsed = round((datetime.now() - t0).total_seconds(), 2)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)

        size_kb = round(out_path.stat().st_size / 1024, 1)
        meta    = dataset["meta"]

        print(f"  ✅  Export complete in {elapsed}s")
        print(f"  ✅  {out_path.name}  ({size_kb} KB)")
        print()
        print(f"  Total signals      : {meta['total_signals']:,}")
        print(f"  Sources expected   : {meta['sources_expected']}")
        print(f"  Sources active     : {meta['sources_active']}")
        print(f"  Latest signal at   : {meta['latest_signal_at']}")
        print()

        # Source health summary
        inactive = [s for s in dataset["source_health"] if not s["active"]]
        if inactive:
            print(f"  ⚠️   Sources with no rows yet ({len(inactive)}):")
            for s in inactive:
                print(f"        [{s['tier']}] {s['source']}")
        else:
            print(f"  ✅  All {meta['sources_expected']} sources have rows in DB")

        print()
        print("─" * 62)

    except Exception as e:
        err = {
            "status":         "error",
            "exporter":       "export_dataset_raw.py",
            "export_version": EXPORT_VERSION,
            "generated_at":   datetime.now().isoformat(timespec="seconds"),
            "error_type":     type(e).__name__,
            "error":          str(e),
            "traceback":      traceback.format_exc(),
        }
        err_path = out_dir / "dataset_raw_error.json"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(err, f, indent=2)
        print("ERROR: export_dataset_raw.py failed.")
        print(json.dumps(err, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
