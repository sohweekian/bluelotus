"""
BlueLotus Digital Institution -- V2.0
mid/ingest_u.py v2.6u -- Market Intelligence Signal Ingestion Engine
WO-RD-20260604-002 Phase 1.5 fixes applied:
  DEFECT-07: Session-aware price capture (pre/post market + volume)
  DEFECT-08: avg_cost field corrected (average_cost not cost_price)
WO-RD-20260603-001 Phase 1 fixes (retained):
  DEFECT-01: ECE analyst % assertion gate
  DEFECT-02: Regime label pollution fixed (session_flag separated)
  DEFECT-04: Portfolio integrity_flag_reason always populated
  DEFECT-06: ECE evidence tier tagging + confidence cap
Under test -- do not rename to ingest.py until confirmed stable.

DOCTRINE: Reality must be observed clearly before it can be interpreted wisely.
          100% Deterministic. No AI. No decisions. Pure pipeline.

ARCHITECTURE:
  +- Circuit Breaker per source (CLOSED/OPEN/HALF_OPEN)
  |- Cycle Connection for all DB writes (eliminates pool exhaustion)
  |- Universal exception handler -- catches Python 3.13 SSL TimeoutError
  |- Exponential backoff with jitter for transient failures
  +- Pre-flight checks for RSS sources

CHANGELOG v2.4 -- based on probe_sources.py v5 confirmed results:

  BOJ_Press   : boj.or.jp/en/rss/whatsnew.xml -- 53 entries, 1.51s
                Governor Ueda speeches, rate decisions, JGB schedules
                Probe: TCP OK, HTTP 200, feedparser OK

  MAS_Press   : Google News site:mas.gov.sg -- 100 entries, 0.72s
                MAS eservices API blocked from Singapore network (Akamai CDN)
                Google News is the reliable path (same as USDA/OPEC pattern)
                Probe: 100 entries confirmed, latest = Asian Monetary Policy Forum

  PBOC_Policy : Google News PBOC monetary -- 54 entries, 0.64s
  PBOC_LPR    : Google News China LPR     -- 34 entries, 0.59s
  PBOC_CNY    : Google News PBOC CNY/RRR  -- 26 entries, 0.53s
                pbc.gov.cn/en/ has no RSS/API -- Google News is the only method
                Probe: all 3 confirmed, latest LPR unchanged for 12th month

CHANGELOG v2.3 -- based on probe_sources.py v4 confirmed results:

  FRED REPLACED ? World Bank Open Data API
    Problem:  fred.stlouisfed.org times out from Singapore (CDN geo-block).
              Both api.stlouisfed.org and fredgraph.csv unreachable.
    Solution: https://api.worldbank.org/v2/country/US/indicator/{code}
              No API key. No auth. Free. Global. Proven: 6/7 indicators in
              0.3?0.7s from Singapore. Confirmed in probe_sources.py v4.
    Covers:   GDP growth, CPI inflation, unemployment, interest rates,
              GDP per capita, central govt debt.
    Source:   datahelpdesk.worldbank.org/knowledgebase/articles/898581
              github.com/lucasdoan1211/Macroeconomic-Data-via-World-Bank-Group

  SpaceNews REPLACED ? NASA RSS + Space Google News
    Problem:  SpaceNews CDN (Atomic) rate-limits Singapore IP aggressively.
              429 with no Retry-After header. Indefinite block.
    Solution: NASA News Releases:   nasa.gov/news-release/feed/       (10 entries, 0.26s)
              NASA Breaking News:   nasa.gov/rss/dyn/breaking_news.rss (10 entries, 0.47s)
              Space Google News:    Google News space query            (39 entries, 0.61s)
    Source:   probe_sources.py v4 confirmed all three working.

  EXCEPTION HANDLING -- universal pattern for Python 3.13 Windows
    Problem:  Python 3.13 ssl.py raises TimeoutError that does NOT inherit
              from requests.exceptions.Timeout -- was crashing the cycle.
    Solution: All fetches now catch:
              (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
               TimeoutError, OSError, Exception)
    Source:   github.com/boto/boto3/issues/185
              nominatim commit b3a2b3d -- "Python<=3.10 TimeoutError != socket.timeout"

CIO    : Kian Soh
Date   : May 2026
"""

import os
import sys
import json
import time
import random
import logging
import zipfile
from io import BytesIO
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict

# Ensure both mid/ (for ticker_universe) and project root (for core.db)
# are on sys.path regardless of how this script is invoked.
_HERE = Path(__file__).parent          # C:\bluelotus3\mid
_ROOT = _HERE.parent                   # C:\bluelotus3
for _p in (_HERE, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import feedparser
import requests
from dotenv import load_dotenv
from ticker_universe import get_universe

load_dotenv()

from core.db import (
    write_raw_signal, write_extraction_audit,
    get_cycle_conn, close_cycle_conn,
)

logger = logging.getLogger("bluelotus.mid.ingest")

# ── Warsh entity matcher (word-boundary safe) ──────────────────────────────
import re as _re_warsh

_WARSH_ENTITY_PATTERN = _re_warsh.compile(
    r'\bWarsh\b',
    _re_warsh.IGNORECASE
)
_WARSH_NEGATIVE_TERMS = frozenset([
    "warship", "warships", "naval", "fleet",
    "shots fired", "english channel", "russian warship",
])

def _matches_warsh_entity(text: str) -> bool:
    """Return True only if text contains 'Warsh' as a word boundary AND
    does not match military/naval false-positive terms UNLESS it also
    explicitly contains 'Kevin Warsh' or 'Federal Reserve'."""
    lower = text.lower()
    if not _WARSH_ENTITY_PATTERN.search(text):
        return False
    has_negative = any(neg in lower for neg in _WARSH_NEGATIVE_TERMS)
    if not has_negative:
        return True
    has_anchor = "kevin warsh" in lower or "federal reserve" in lower
    return has_anchor

# ---------------------------------------------------------------------
# TIMEOUTS -- probe-validated values (all in seconds)
# ---------------------------------------------------------------------
DEFAULT_TIMEOUT  = 10
GDELT_TIMEOUT    = 20
CFTC_TIMEOUT     = 20
WB_TIMEOUT       = 12   # World Bank -- confirmed 0.3-0.7s, 12s is generous
BLS_TIMEOUT      = 15   # BLS POST -- confirmed 1.9s
EIA_TIMEOUT      = 12   # EIA -- confirmed 3.86s

SOURCE_TIMEOUT = {
    "WorldBank_Macro": WB_TIMEOUT,
    "BLS_API":         BLS_TIMEOUT,
    "CFTC_COT":        CFTC_TIMEOUT,
    "GDELT_API":       GDELT_TIMEOUT,
    "EIA_Petroleum":   EIA_TIMEOUT,
    "EIA_NatGas":      EIA_TIMEOUT,
    "BEA_GDP_PCE":     12,
    "SEC_EDGAR_8K":    12,
}

MAX_RSS_ENTRIES   = 10
PREFLIGHT_TIMEOUT = 5

# ---------------------------------------------------------------------
# HEADERS
# ---------------------------------------------------------------------
BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

AGENT_HEADER = {
    "User-Agent":      BROWSER_AGENT,
    "Accept":          "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",  # prevents gzip hang on Windows Python 3.13
    "Connection":      "close",     # no stale keepalive connections
}

RSS_HEADER = {
    "User-Agent":      BROWSER_AGENT,
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection":      "close",
}

# ---------------------------------------------------------------------
# API KEYS
# ---------------------------------------------------------------------
EIA_API_KEY      = os.getenv("EIA_API_KEY",      "")
BEA_API_KEY      = os.getenv("BEA_API_KEY",      "")
BLS_API_KEY      = os.getenv("BLS_API_KEY",      "")
USDA_FAS_API_KEY = os.getenv("USDA_FAS_API_KEY", "")

# ---------------------------------------------------------------------
# WORLD BANK INDICATORS -- FRED replacement
# Confirmed working from probe_sources.py v4 (Singapore, 30 May 2026)
# Source: datahelpdesk.worldbank.org/knowledgebase/articles/898581
# ---------------------------------------------------------------------
WORLDBANK_INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": "GDP Growth Rate (annual %)",
    "FP.CPI.TOTL.ZG":    "Inflation CPI (annual %)",
    "SL.UEM.TOTL.ZS":    "Unemployment Rate (%)",
    "FR.INR.LEND":       "Lending Interest Rate (%)",
    "NY.GDP.PCAP.KD.ZG": "GDP Per Capita Growth (%)",
    "GC.DOD.TOTL.GD.ZS": "Central Govt Debt (% GDP)",
    "BN.CAB.XOKA.GD.ZS": "Current Account Balance (% GDP)",
}

# ---------------------------------------------------------------------
# BLS SERIES -- POST API confirmed working (1.9s, REQUEST_SUCCEEDED)
# Source: bls.gov/developers/api_python.htm
# ---------------------------------------------------------------------
BLS_SERIES = [
    "CUUR0000SA0",     # CPI All Urban Consumers -- confirmed 333.020 for 2026-M04
    "LNS14000000",     # Unemployment Rate
    "CES0000000001",   # Total Nonfarm Payroll
    "CUUR0000SA0L1E",  # Core CPI (less food and energy)
]

# ---------------------------------------------------------------------
# CFTC COT KEYWORDS -- confirmed 252 filtered contracts
# ---------------------------------------------------------------------
COT_KEYWORDS = [
    "GOLD", "SILVER", "CRUDE OIL", "NATURAL GAS",
    "S&P 500", "NASDAQ", "U.S. DOLLAR", "EURO FX",
    "COPPER", "CORN", "SOYBEANS", "WHEAT",
]

# ---------------------------------------------------------------------
# SOURCE REGISTRY -- probe-verified endpoints, globally accessible
# ---------------------------------------------------------------------
SOURCE_REGISTRY = {

    # -- TIER 1: OFFICIAL CENTRAL BANKS & GOVERNMENT ------------------
    "Fed_Press": {
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "method": "rss", "tier": 1, "trust": 0.98,
        "signal_type": "macro", "source_feed": "fed_press",
        "preflight": True,
    },
    "Fed_Speeches": {
        "url": "https://www.federalreserve.gov/feeds/speeches.xml",
        "method": "rss", "tier": 1, "trust": 0.97,
        "signal_type": "macro", "source_feed": "fed_speeches",
        "preflight": True,
    },
    "Fed_FOMC_Minutes": {
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "method": "rss", "tier": 1, "trust": 0.98,
        "signal_type": "macro", "source_feed": "fed_fomc",
        "preflight": True,
    },
    "ECB_Press": {
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "method": "rss", "tier": 1, "trust": 0.95,
        "signal_type": "macro", "source_feed": "ecb_press",
        "preflight": True,
    },
    # BOJ: probe confirmed 53 entries, 1.51s, Governor speeches + rate decisions
    # URL confirmed: rss.feedspot.com/central_banks_rss_feeds/
    # Latest entry: JGB purchase schedule May 29 2026 -- live data
    "BOJ_Press": {
        "url": "https://www.boj.or.jp/en/rss/whatsnew.xml",
        "method": "rss", "tier": 1, "trust": 0.95,
        "signal_type": "macro", "source_feed": "boj_press",
        "preflight": True,
    },
    # MAS: Google News site:mas.gov.sg -- 100 entries, 0.72s (probe confirmed)
    # eservices.mas.gov.sg API blocked from this network (same Akamai CDN as FRED)
    # Google News is the reliable path -- same pattern as USDA_WASDE / OPEC
    "MAS_Press": {
        "url": "https://news.google.com/rss/search?q=site:mas.gov.sg+monetary+policy+OR+financial+stability+OR+interest+rate&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.93,
        "signal_type": "macro", "source_feed": "mas_press",
        "preflight": True,
    },
    # PBOC Policy: 54 entries, 0.64s (probe confirmed)
    # "China leaves lending benchmarks unchanged for 12th month in May"
    "PBOC_Policy": {
        "url": "https://news.google.com/rss/search?q=PBOC+People%27s+Bank+China+monetary+policy+interest+rate+LPR&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.87,
        "signal_type": "macro", "source_feed": "pboc_policy",
        "preflight": True,
    },
    # PBOC LPR: 34 entries, 0.59s (probe confirmed)
    # Loan Prime Rate published monthly on the 20th -- critical China rate signal
    "PBOC_LPR": {
        "url": "https://news.google.com/rss/search?q=China+LPR+loan+prime+rate+PBOC+decision&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.88,
        "signal_type": "macro", "source_feed": "pboc_lpr",
        "preflight": True,
    },
    # PBOC CNY: 26 entries, 0.53s (probe confirmed)
    # "China signals flexible use of monetary tools in 2026"
    "PBOC_CNY": {
        "url": "https://news.google.com/rss/search?q=PBOC+yuan+CNY+RRR+reserve+requirement+China+central+bank&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.86,
        "signal_type": "geopolitical", "source_feed": "pboc_cny",
        "preflight": True,
    },
    "BIS_PressReleases": {
        "url": "https://www.bis.org/doclist/all_pressrels.rss",
        "method": "rss", "tier": 1, "trust": 0.94,
        "signal_type": "macro", "source_feed": "bis_pressrels",
        "preflight": True,
    },
    "BIS_CentralBankSpeeches": {
        "url": "https://www.bis.org/doclist/cbspeeches.rss",
        "method": "rss", "tier": 1, "trust": 0.93,
        "signal_type": "macro", "source_feed": "bis_speeches",
        "preflight": True,
    },
    # FRED ? World Bank (probe confirmed: 6/7 indicators, 0.3-0.7s)
    "WorldBank_Macro": {
        "url": "https://api.worldbank.org/v2/country/US/indicator/",
        "method": "api_worldbank", "tier": 1, "trust": 0.93,
        "signal_type": "macro", "source_feed": "worldbank_macro",
        "preflight": False,
    },
    # BLS POST API (probe confirmed: 1.9s, REQUEST_SUCCEEDED)
    "BLS_API": {
        "url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        "method": "api_bls", "tier": 1, "trust": 0.97,
        "signal_type": "macro", "source_feed": "bls_api",
        "preflight": False,
    },
    "SEC_EDGAR_8K": {
        "url": "https://efts.sec.gov/LATEST/search-index?q=%228-K%22&forms=8-K",
        "method": "api_sec", "tier": 1, "trust": 0.96,
        "signal_type": "earnings", "source_feed": "sec_edgar",
        "preflight": False,
    },
    "EIA_Petroleum": {
        "url": "https://api.eia.gov/v2/petroleum/sum/sndw/data/",
        "method": "api_eia", "tier": 1, "trust": 0.96,
        "signal_type": "commodity", "source_feed": "eia_petroleum",
        "label": "US Petroleum Supply", "preflight": False,
    },
    "EIA_NatGas": {
        "url": "https://api.eia.gov/v2/natural-gas/stor/wkly/data/",
        "method": "api_eia", "tier": 1, "trust": 0.96,
        "signal_type": "commodity", "source_feed": "eia_natgas",
        "label": "US Natural Gas Storage", "preflight": False,
    },
    # CFTC ZIP confirmed: fut_fin_txt_{year}.zip, 1780 rows, 252 contracts
    "CFTC_COT": {
        "url": "https://www.cftc.gov/files/dea/history/",
        "method": "api_cftc", "tier": 1, "trust": 0.95,
        "signal_type": "sentiment", "source_feed": "cftc_cot",
        "preflight": False,
    },
    # USDA: Google News WASDE (100 entries confirmed)
    "USDA_WASDE": {
        "url": "https://news.google.com/rss/search?q=USDA+WASDE+crop+supply+demand+report&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.85,
        "signal_type": "commodity", "source_feed": "usda_wasde",
        "preflight": True,
    },
    "BEA_GDP_PCE": {
        "url": "https://apps.bea.gov/api/data",
        "method": "api_bea", "tier": 1, "trust": 0.97,
        "signal_type": "macro", "source_feed": "bea_api",
        "preflight": False,
    },

    # -- TIER 2: JOURNALISM --------------------------------------------
    # Reuters via Google News -- probe_rss_news_v2.py confirmed 03 Jun 2026
    # allinurl: operator stopped returning results -- replaced with keyword queries
    "Reuters_Business": {
        "url": "https://news.google.com/rss/search?q=when:24h+reuters+business&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.87,
        "signal_type": "news", "source_feed": "reuters_biz",
        "preflight": True,
    },
    "Reuters_Markets": {
        "url": "https://news.google.com/rss/search?q=reuters+markets+equities+bonds&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.87,
        "signal_type": "news", "source_feed": "reuters_mkts",
        "preflight": True,
    },
    "Reuters_Technology": {
        "url": "https://news.google.com/rss/search?q=reuters+technology+artificial+intelligence&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.87,
        "signal_type": "news", "source_feed": "reuters_tech",
        "preflight": True,
    },
    "Reuters_Commodities": {
        "url": "https://news.google.com/rss/search?q=when:24h+site:reuters.com+commodities&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.86,
        "signal_type": "commodity", "source_feed": "reuters_commod",
        "preflight": True,
    },
    "CNBC_Markets": {
        "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "method": "rss", "tier": 2, "trust": 0.82,
        "signal_type": "news", "source_feed": "cnbc_markets",
        "preflight": True,
    },
    "CNBC_Finance": {
        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "method": "rss", "tier": 2, "trust": 0.82,
        "signal_type": "news", "source_feed": "cnbc_finance",
        "preflight": True,
    },
    "CNA_Business": {
        "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511",
        "method": "rss", "tier": 2, "trust": 0.85,
        "signal_type": "news", "source_feed": "cna_biz",
        "preflight": True,
    },

    # -- TIER 1 via Google News proxy ----------------------------------
    "IMF_News": {
        "url": "https://news.google.com/rss/search?q=when:7d+site:imf.org+economy+policy&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.87,
        "signal_type": "macro", "source_feed": "imf_gnews",
        "preflight": True,
    },
    "OPEC_News": {
        "url": "https://news.google.com/rss/search?q=when:7d+OPEC+oil+production+quota&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.87,
        "signal_type": "commodity", "source_feed": "opec_gnews",
        "preflight": True,
    },
    "WhiteHouse_RSS": {
        "url": "https://news.google.com/rss/search?q=when:3d+White+House+executive+order+policy&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.90,
        "signal_type": "geopolitical", "source_feed": "whitehouse_gnews",
        "preflight": True,
    },
    "Treasury_Press": {
        "url": "https://news.google.com/rss/search?q=when:3d+US+Treasury+sanctions+fiscal+policy&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.91,
        "signal_type": "macro", "source_feed": "treasury_gnews",
        "preflight": True,
    },
    "IAEA_News": {
        "url": "https://news.google.com/rss/search?q=when:7d+IAEA+nuclear+Iran+inspection&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.88,
        "signal_type": "geopolitical", "source_feed": "iaea_gnews",
        "preflight": True,
    },
    "USGS_Minerals": {
        "url": "https://news.google.com/rss/search?q=when:7d+rare+earth+minerals+critical+supply&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 1, "trust": 0.88,
        "signal_type": "commodity", "source_feed": "usgs_gnews",
        "preflight": True,
    },
    "ArabNews_Business": {
        "url": "https://news.google.com/rss/search?q=when:24h+Saudi+Arabia+oil+Middle+East+economy&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.78,
        "signal_type": "geopolitical", "source_feed": "arabnews_gnews",
        "preflight": True,
    },
    # WSJ via Google News -- probe_rss_news_v2.py confirmed 03 Jun 2026
    # wsj.com/xml/rss/ paths return HTTP 401 (paywall). Google News site: queries work.
    # Headlines only -- no article content (paywall). Tier 2 per editorial quality.
    "WSJ_Markets": {
        "url": "https://news.google.com/rss/search?q=when:24h+site:wsj.com+markets&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.88,
        "signal_type": "news", "source_feed": "wsj_markets",
        "preflight": True,
    },
    "WSJ_Technology": {
        "url": "https://news.google.com/rss/search?q=when:24h+site:wsj.com+technology&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.88,
        "signal_type": "news", "source_feed": "wsj_tech",
        "preflight": True,
    },
    # FT via Google News and direct RSS -- probe_rss_news_v2.py confirmed 03 Jun 2026
    # ft.com direct RSS feeds return headers only (no full article -- paywall).
    # GNews site: query returns 100 entries; direct ft.com RSS returns 25 -- both used.
    "FT_Markets": {
        "url": "https://news.google.com/rss/search?q=when:24h+site:ft.com+markets&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 2, "trust": 0.88,
        "signal_type": "news", "source_feed": "ft_markets",
        "preflight": True,
    },
    "FT_World": {
        "url": "https://www.ft.com/world?format=rss",
        "method": "rss", "tier": 2, "trust": 0.87,
        "signal_type": "news", "source_feed": "ft_world",
        "preflight": True,
    },

    # -- TIER 3: SPECIALIST --------------------------------------------
    "Defense_News": {
        "url": "https://news.google.com/rss/search?q=when:3d+defense+military+procurement+Pentagon&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 3, "trust": 0.85,
        "signal_type": "geopolitical", "source_feed": "defense_news",
        "preflight": True,
    },
    "Breaking_Defense": {
        "url": "https://news.google.com/rss/search?q=when:3d+US+defense+budget+weapons+contracts&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 3, "trust": 0.84,
        "signal_type": "geopolitical", "source_feed": "breaking_defense",
        "preflight": True,
    },
    "WarOnTheRocks": {
        "url": "https://warontherocks.com/feed/",
        "method": "rss", "tier": 3, "trust": 0.85,
        "signal_type": "geopolitical", "source_feed": "wotr_rss",
        "preflight": True,
    },
    "WorldNuclearNews": {
        "url": "https://www.world-nuclear-news.org/rss",
        "method": "rss", "tier": 3, "trust": 0.86,
        "signal_type": "commodity", "source_feed": "wnn_rss",
        "preflight": True,
    },
    "OilPrice_RSS": {
        "url": "https://oilprice.com/rss/main",
        "method": "rss", "tier": 3, "trust": 0.78,
        "signal_type": "commodity", "source_feed": "oilprice_rss",
        "preflight": True,
    },
    "Mining_RSS": {
        "url": "https://www.mining.com/feed/",
        "method": "rss", "tier": 3, "trust": 0.78,
        "signal_type": "commodity", "source_feed": "mining_rss",
        "preflight": True,
    },
    # SpaceNews REPLACED ? NASA RSS (probe confirmed: 10 entries, 0.26s)
    "NASA_News": {
        "url": "https://www.nasa.gov/news-release/feed/",
        "method": "rss", "tier": 3, "trust": 0.88,
        "signal_type": "news", "source_feed": "nasa_news",
        "preflight": True,
    },
    "NASA_SpaceStation": {
        "url": "https://blogs.nasa.gov/spacestation/feed/",
        "method": "rss", "tier": 3, "trust": 0.83,
        "signal_type": "news", "source_feed": "nasa_station",
        "preflight": True,
    },
    # Space industry via Google News (probe confirmed: 39 entries, 0.61s)
    "Space_Industry": {
        "url": "https://news.google.com/rss/search?q=when:24h+space+launch+satellite+SpaceX+rocket&ceid=US:en&hl=en-US&gl=US",
        "method": "rss", "tier": 3, "trust": 0.75,
        "signal_type": "news", "source_feed": "space_gnews",
        "preflight": True,
    },

    # -- TIER 4: VELOCITY / SENTIMENT ---------------------------------
    "MarketWatch_RSS": {
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
        "method": "rss", "tier": 4, "trust": 0.65,
        "signal_type": "sentiment", "source_feed": "marketwatch_rss",
        "preflight": True,
    },
    "Yahoo_Finance_RSS": {
        "url": "https://finance.yahoo.com/rss/topstories",
        "method": "rss", "tier": 4, "trust": 0.60,
        "signal_type": "sentiment", "source_feed": "yahoo_fin_rss",
        "preflight": True,
    },
    "GDELT_API": {
        "url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "method": "api_gdelt", "tier": 4, "trust": 0.72,
        "signal_type": "news", "source_feed": "gdelt_api",
        "preflight": False,
    },
    # CNN Equity Fear/Greed -- production.dataviz.cnn.io confirmed 60.1 (Greed)
    # Crypto (alternative.me) removed by CIO directive -- not monitored
    "CNN_FearGreed": {
        "url": "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        "method": "api_feargreed", "tier": 3, "trust": 0.85,
        "signal_type": "sentiment", "source_feed": "cnn_feargreed",
        "preflight": False,
    },
}

SOURCE_TRUST = {k: v["trust"] for k, v in SOURCE_REGISTRY.items()}


# ---------------------------------------------------------------------
# CIRCUIT BREAKER
# ---------------------------------------------------------------------
class CBState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, source_id, failure_threshold=3, recovery_cycles=2):
        self.source_id         = source_id
        self.failure_threshold = failure_threshold
        self.recovery_cycles   = recovery_cycles
        self.state             = CBState.CLOSED
        self.failures          = 0
        self.skipped_cycles    = 0
        self.permanent_skip    = False

    def can_execute(self):
        if self.permanent_skip: return False
        if self.state == CBState.CLOSED: return True
        if self.state == CBState.OPEN:
            self.skipped_cycles += 1
            if self.skipped_cycles >= self.recovery_cycles:
                self.state = CBState.HALF_OPEN
                self.skipped_cycles = 0
                logger.info("CB %s ? HALF_OPEN (testing)", self.source_id)
                return True
            return False
        return True  # HALF_OPEN

    def on_success(self):
        if self.state == CBState.HALF_OPEN:
            logger.info("CB %s ? CLOSED (recovered)", self.source_id)
        self.state    = CBState.CLOSED
        self.failures = 0

    def on_failure(self, permanent=False):
        if permanent:
            self.permanent_skip = True
            logger.warning("CB %s ? PERMANENT SKIP", self.source_id)
            return
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = CBState.OPEN
            logger.warning("CB %s ? OPEN (%d failures)", self.source_id, self.failures)

_cb_registry: Dict[str, CircuitBreaker] = {}

def _get_cb(sid): 
    if sid not in _cb_registry:
        _cb_registry[sid] = CircuitBreaker(sid)
    return _cb_registry[sid]


# ---------------------------------------------------------------------
# INGEST RESULT
# ---------------------------------------------------------------------
class IngestResult:
    def __init__(self):
        self.cycle_timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.start_time       = datetime.now()
        self.total_fetched    = 0
        self.total_written    = 0
        self.total_duplicates = 0
        self.total_errors     = 0
        self.total_timeouts   = 0
        self.total_skipped    = 0
        self.by_source: Dict[str, dict] = {}

    def record(self, sid, status):
        if sid not in self.by_source:
            self.by_source[sid] = {
                "fetched":0,"written":0,"duplicates":0,
                "errors":0,"timeouts":0,"skipped":0,
            }
        self.by_source[sid]["fetched"] += 1
        self.total_fetched += 1
        key = {"written":"written","duplicate":"duplicates",
               "timeout":"timeouts","skipped":"skipped"}.get(status,"errors")
        self.by_source[sid][key] += 1
        if   status == "written":   self.total_written    += 1
        elif status == "duplicate": self.total_duplicates += 1
        elif status == "timeout":   self.total_timeouts   += 1
        elif status == "skipped":   self.total_skipped    += 1
        else:                       self.total_errors     += 1

    def to_dict(self):
        dur  = (datetime.now() - self.start_time).total_seconds()
        ok   = sum(1 for s in self.by_source.values() if s["written"] > 0)
        dup  = sum(1 for s in self.by_source.values()
                   if s["written"]==0 and s["duplicates"]>0)
        fail = sum(1 for s in self.by_source.values()
                   if s["errors"]>0 or s["timeouts"]>0)
        skip = sum(1 for s in self.by_source.values() if s["skipped"]>0)
        return {
            "cycle_timestamp":  self.cycle_timestamp,
            "duration_seconds": round(dur, 1),
            "total_fetched":    self.total_fetched,
            "total_written":    self.total_written,
            "total_duplicates": self.total_duplicates,
            "total_errors":     self.total_errors,
            "total_timeouts":   self.total_timeouts,
            "total_skipped":    self.total_skipped,
            "sources_ok":       ok,
            "sources_dup_only": dup,
            "sources_failed":   fail,
            "sources_skipped":  skip,
            "by_source":        self.by_source,
        }

    def log_summary(self):
        d = self.to_dict()
        logger.info("-"*62)
        logger.info("MID INGEST COMPLETE  [v2.6]  %s", d["cycle_timestamp"])
        logger.info("  Duration : %.1fs | Written: %d | Dup: %d | Err: %d | TO: %d",
                    d["duration_seconds"], d["total_written"],
                    d["total_duplicates"], d["total_errors"], d["total_timeouts"])
        logger.info("  Sources  : OK=%d | Dup=%d | Failed=%d | CB-skip=%d",
                    d["sources_ok"], d["sources_dup_only"],
                    d["sources_failed"], d["sources_skipped"])
        logger.info("-"*62)


# ---------------------------------------------------------------------
# UNIVERSAL SAFE FETCH
# Catches ALL exception types including Python 3.13 Windows SSL TimeoutError.
# This is the single fetch function used by ALL sources.
# Source: github.com/boto/boto3/issues/185 + nominatim commit b3a2b3d
# ---------------------------------------------------------------------
def _safe_fetch(url, source_id, params=None, headers=None,
                timeout=None, max_retries=2):
    """
    Fetch URL with full exception coverage + exponential backoff.
    Returns requests.Response on success, None on any failure.
    Permanent failures (404/405/410): opens CB, returns None immediately.
    Transient (429/403/500/503): retries with backoff.
    """
    hdrs    = {**AGENT_HEADER, **(headers or {})}
    timeout = timeout or SOURCE_TIMEOUT.get(source_id, DEFAULT_TIMEOUT)
    cb      = _get_cb(source_id)

    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, params=params, headers=hdrs,
                             timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                cb.on_success()
                return r
            if r.status_code in (404, 405, 410):
                logger.warning("SOURCE %s HTTP %d (permanent) ? CB open",
                               source_id, r.status_code)
                cb.on_failure(permanent=True)
                return None
            # Transient: 403, 429, 500, 503 ? retry with backoff
            if attempt < max_retries:
                wait = (2 ** attempt) * (1 + random.uniform(-0.3, 0.3))
                logger.warning("SOURCE %s HTTP %d ? retry %d/%d in %.1fs",
                               source_id, r.status_code,
                               attempt+1, max_retries, wait)
                time.sleep(wait)
            else:
                logger.warning("SOURCE %s HTTP %d ? max retries",
                               source_id, r.status_code)
                cb.on_failure()
                return None

        # -- Full exception hierarchy for Python 3.13 Windows ----------
        except requests.exceptions.Timeout as e:
            ename = type(e).__name__
            if attempt < max_retries:
                wait = 1.5 ** attempt * (1 + random.uniform(-0.2, 0.2))
                logger.warning("SOURCE %s %s attempt %d/%d ? retry %.1fs",
                               source_id, ename, attempt+1, max_retries+1, wait)
                time.sleep(wait)
            else:
                logger.warning("SOURCE %s %s ? giving up", source_id, ename)
                cb.on_failure()
                return None

        except TimeoutError as e:
            # Python 3.13 ssl.py raises this -- NOT subclass of requests.Timeout
            logger.warning("SOURCE %s TimeoutError(SSL/socket) ? skip: %s",
                           source_id, str(e)[:80])
            cb.on_failure()
            return None

        except OSError as e:
            logger.warning("SOURCE %s OSError(socket) ? skip: %s",
                           source_id, str(e)[:80])
            cb.on_failure()
            return None

        except requests.exceptions.ConnectionError as e:
            logger.warning("SOURCE %s ConnectionError ? skip: %s",
                           source_id, str(e)[:80])
            cb.on_failure()
            return None

        except Exception as e:
            # Catch-all -- logs the actual type so we can classify new errors
            logger.warning("SOURCE %s %s ? skip: %s",
                           source_id, type(e).__name__, str(e)[:80])
            cb.on_failure()
            return None

    return None


# ---------------------------------------------------------------------
# PREFLIGHT CHECK
# ---------------------------------------------------------------------
def _preflight(sid, url):
    try:
        r = requests.head(url, headers=RSS_HEADER,
                          timeout=PREFLIGHT_TIMEOUT, allow_redirects=True)
        return r.status_code < 400
    except Exception:
        try:
            r = requests.get(url, headers={**RSS_HEADER, "Range":"bytes=0-0"},
                             timeout=PREFLIGHT_TIMEOUT, allow_redirects=True)
            return r.status_code < 400
        except Exception:
            return False

def run_preflight(sources):
    check = {k: v for k, v in sources.items() if v.get("preflight", False)}
    logger.info("  [PREFLIGHT] Checking %d sources...", len(check))
    ok_count = 0
    for sid, cfg in check.items():
        if _preflight(sid, cfg["url"]):
            ok_count += 1
        else:
            logger.warning("  PREFLIGHT [FAIL] %s", sid)
    logger.info("  [PREFLIGHT] %d OK / %d unreachable",
                ok_count, len(check)-ok_count)


# ---------------------------------------------------------------------
# SAFE DB WRITE -- uses cycle connection
# ---------------------------------------------------------------------
def _write(result, sid, method, raw_payload, raw_text="",
           source_url="", signal_type="news", source_feed=""):
    quality = SOURCE_TRUST.get(sid, 0.60)
    try:
        iid = write_raw_signal(
            source=sid, ingestion_method=method,
            raw_payload=raw_payload,
            raw_text=raw_text[:2000] if raw_text else None,
            source_url=source_url or None,
            source_feed=source_feed or None,
            ingestion_agent="mid_ingest_v2.6u",
            signal_type=signal_type,
            quality_score=quality,
            use_cycle_conn=True,
        )
        if iid:
            write_extraction_audit(
                raw_ingestion_id=iid,
                extraction_model=f"mid_{method}_v2.6",
                extraction_version="2.6",
                extracted_category=signal_type,
                extracted_trust_score=quality,
                validation_passed=True,
                use_cycle_conn=True,
            )
            result.record(sid, "written")
        else:
            result.record(sid, "duplicate")
    except Exception as e:
        logger.error("_write [%s]: %s", sid, e)
        result.record(sid, "error")


# ---------------------------------------------------------------------
# RSS FETCH
# ---------------------------------------------------------------------
def _fetch_rss(sid, config, result):
    cb = _get_cb(sid)
    if not cb.can_execute():
        result.record(sid, "skipped"); return

    r = _safe_fetch(config["url"], sid, headers=RSS_HEADER)
    if r is None:
        result.record(sid, "error"); return

    feed = feedparser.parse(r.content)
    if not feed.entries:
        logger.info("RSS %s -- empty feed", sid); return

    for entry in feed.entries[:MAX_RSS_ENTRIES]:
        title   = (entry.get("title") or "").strip()
        link    = entry.get("link", "")
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        pub     = entry.get("published", "")
        if not title or len(title) < 5: continue
        raw_payload = {
            "title": title, "link": link,
            "summary": summary[:800], "published": pub,
            "source_id": sid, "tier": config["tier"],
        }
        # BUG-ECE-005 FIX: Treasury_Press assigns "macro" to all signals.
        # Apply content-based override: if title contains geo keywords, use "geopolitical".
        _GEO_KEYWORDS_TITLE = [
            "TRUMP","TARIFF","IRAN","CHINA","WAR","SANCTION","TAIWAN",
            "EXPORT RESTRICT","HORMUZ","CEASEFIRE","NUCLEAR","MISSILE",
            "INVASION","AIRSTRIKE","STRIKE","CONFLICT","TEHRAN","UAE",
            "RUSSIA","UKRAINE","NORTH KOREA","GEOPOLIT","MILITARY",
        ]
        _sig_type = config["signal_type"]
        if sid == "Treasury_Press":
            _title_upper = title.upper()
            if any(kw in _title_upper for kw in _GEO_KEYWORDS_TITLE):
                _sig_type = "geopolitical"
        _write(result, sid, "rss", raw_payload,
               f"{title}. {summary[:300]}",
               source_url=link,
               signal_type=_sig_type,
               source_feed=config["source_feed"])
        time.sleep(0.03)

    logger.debug("RSS %s -- done", sid)
    cb.on_success()

def _fetch_rss_group(result):
    rss_sources = {k: v for k, v in SOURCE_REGISTRY.items()
                   if v["method"] == "rss"}
    logger.info("  [RSS] %d sources...", len(rss_sources))
    for sid, cfg in rss_sources.items():
        _fetch_rss(sid, cfg, result)
        time.sleep(0.15)


# ---------------------------------------------------------------------
# WORLD BANK API -- FRED replacement
# Probe confirmed: 6/7 indicators, 0.3-0.7s, from Singapore
# Structure: r.json() = [metadata_dict, data_array]
# Source: datahelpdesk.worldbank.org/knowledgebase/articles/898581
# ---------------------------------------------------------------------
def _fetch_worldbank(result):
    cb = _get_cb("WorldBank_Macro")
    if not cb.can_execute():
        result.record("WorldBank_Macro", "skipped"); return

    written = 0
    for code, label in WORLDBANK_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/US/indicator/{code}"
        r = _safe_fetch(url, "WorldBank_Macro",
                        params={"format": "json", "mrv": 5, "per_page": 5},
                        timeout=WB_TIMEOUT)
        if r is None: continue

        try:
            payload  = r.json()
            if not isinstance(payload, list) or len(payload) < 2:
                logger.warning("WorldBank %s: unexpected structure", code)
                continue

            data_arr = payload[1]
            if not data_arr:
                logger.debug("WorldBank %s: empty data (reporting lag)", code)
                continue

            # Find most recent non-null value
            latest = None
            for obs in data_arr:
                if obs.get("value") is not None:
                    latest = obs
                    break

            if not latest:
                logger.debug("WorldBank %s: all values null", code)
                continue

            raw_payload = {
                "indicator_code":  code,
                "indicator_label": label,
                "country":         latest.get("country", {}).get("value", "US"),
                "date":            latest.get("date", ""),
                "value":           latest.get("value", ""),
                "unit":            latest.get("unit", "") or "",
                "decimal":         latest.get("decimal", ""),
                "source":          "WorldBank_API",
            }
            raw_text = (
                f"World Bank {label}: "
                f"{latest.get('value')} "
                f"({latest.get('date')})"
            )
            _write(result, "WorldBank_Macro", "api_worldbank",
                   raw_payload, raw_text,
                   source_url=url,
                   signal_type="macro",
                   source_feed="worldbank_macro")
            written += 1

        except Exception as e:
            logger.warning("WorldBank %s parse: %s", code, e)

        time.sleep(0.3)  # polite pacing

    if written > 0:
        logger.info("WorldBank_Macro -- %d/%d indicators written",
                    written, len(WORLDBANK_INDICATORS))
        cb.on_success()
    else:
        logger.warning("WorldBank_Macro -- 0 indicators written")
        cb.on_failure()


# ---------------------------------------------------------------------
# BLS API -- POST v2
# Probe confirmed: 1.9s, REQUEST_SUCCEEDED, CPI=333.020 for 2026-M04
# Source: bls.gov/developers/api_python.htm
# ---------------------------------------------------------------------
def _fetch_bls(result):
    cb = _get_cb("BLS_API")
    if not cb.can_execute():
        result.record("BLS_API", "skipped"); return

    url     = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    headers = {"Content-Type": "application/json"}
    year    = datetime.now().year
    payload = {
        "seriesid":  BLS_SERIES,
        "startyear": str(year - 1),
        "endyear":   str(year),
    }
    if BLS_API_KEY:
        payload["registrationkey"] = BLS_API_KEY

    try:
        r = requests.post(url, headers=headers,
                          data=json.dumps(payload), timeout=BLS_TIMEOUT)
        if r.status_code != 200:
            logger.warning("BLS_API HTTP %d", r.status_code)
            cb.on_failure(); return

        data   = r.json()
        status = data.get("status", "")
        if status != "REQUEST_SUCCEEDED":
            logger.warning("BLS_API status: %s | %s",
                           status, data.get("message", ""))
            cb.on_failure(); return

        series = data.get("Results", {}).get("series", [])
        written = 0
        for s in series:
            sid = s.get("seriesID", "")
            obs = s.get("data", [])
            if not obs: continue
            latest = obs[0]
            raw_payload = {
                "series_id": sid,
                "year":      latest.get("year"),
                "period":    latest.get("period"),
                "value":     latest.get("value"),
                "footnotes": [f.get("text","") for f in latest.get("footnotes",[])],
                "source":    "BLS_API_v2",
            }
            _write(result, "BLS_API", "api_bls", raw_payload,
                   f"BLS {sid}: {latest.get('value')} for "
                   f"{latest.get('year')}-{latest.get('period')}",
                   signal_type="macro", source_feed="bls_api")
            written += 1

        if written > 0:
            logger.info("BLS_API -- %d series written", written)
            cb.on_success()
        else:
            cb.on_failure()

    except (requests.exceptions.Timeout, TimeoutError, OSError,
            requests.exceptions.ConnectionError, Exception) as e:
        logger.warning("BLS_API %s: %s", type(e).__name__, e)
        cb.on_failure()


# ---------------------------------------------------------------------
# EIA API
# ---------------------------------------------------------------------
def _fetch_eia(sid, result):
    if not EIA_API_KEY:
        logger.warning("%s -- no EIA_API_KEY", sid); return
    cb = _get_cb(sid)
    if not cb.can_execute():
        result.record(sid, "skipped"); return

    config = SOURCE_REGISTRY[sid]
    r = _safe_fetch(config["url"], sid, params={
        "api_key": EIA_API_KEY, "frequency": "weekly",
        "data[0]": "value", "sort[0][column]": "period",
        "sort[0][direction]": "desc", "length": 4,
    })
    if r is None: return
    try:
        entries = r.json().get("response", {}).get("data", [])
        for e in entries[:4]:
            raw_payload = {
                "source_id": sid,
                "label":     config.get("label", sid),
                "period":    e.get("period"),
                "value":     e.get("value"),
                "unit":      e.get("unit", ""),
            }
            _write(result, sid, "api_eia", raw_payload,
                   f"{config.get('label',sid)}: {e.get('value')} "
                   f"{e.get('unit','')} period {e.get('period')}",
                   signal_type=config["signal_type"],
                   source_feed=config["source_feed"])
        cb.on_success()
    except Exception as e:
        logger.warning("%s parse: %s", sid, e)
        cb.on_failure()


# ---------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------
def _fetch_sec_edgar(result):
    cb = _get_cb("SEC_EDGAR_8K")
    if not cb.can_execute():
        result.record("SEC_EDGAR_8K", "skipped"); return
    today = datetime.now().strftime("%Y-%m-%d")
    r = _safe_fetch(
        f"https://efts.sec.gov/LATEST/search-index?q=%228-K%22"
        f"&forms=8-K&dateRange=custom&startdt={today}",
        "SEC_EDGAR_8K"
    )
    if r is None: return
    try:
        filings = r.json().get("hits", {}).get("hits", [])
        for f in filings[:15]:
            src = f.get("_source", {})
            raw_payload = {
                "entity": src.get("entity_name", ""),
                "form":   src.get("form_type", "8-K"),
                "filed":  src.get("file_date", today),
                "source": "SEC_EDGAR",
            }
            _write(result, "SEC_EDGAR_8K", "api_sec", raw_payload,
                   f"SEC 8-K: {raw_payload['entity']} filed {raw_payload['filed']}",
                   signal_type="earnings", source_feed="sec_edgar")
        cb.on_success()
    except Exception as e:
        logger.warning("SEC_EDGAR parse: %s", e)
        cb.on_failure()


# ---------------------------------------------------------------------
# BEA
# ---------------------------------------------------------------------
def _fetch_bea(result):
    if not BEA_API_KEY:
        logger.warning("BEA -- no key"); return
    cb = _get_cb("BEA_GDP_PCE")
    if not cb.can_execute():
        result.record("BEA_GDP_PCE", "skipped"); return
    for ds in [
        {"TableName":"T10101","Frequency":"Q","label":"GDP Growth"},
        {"TableName":"T20306","Frequency":"M","label":"PCE Price"},
    ]:
        r = _safe_fetch("https://apps.bea.gov/api/data", "BEA_GDP_PCE", params={
            "UserID":BEA_API_KEY,"method":"GetData","DataSetName":"NIPA",
            "TableName":ds["TableName"],"Frequency":ds["Frequency"],
            "Year":"2025,2026","ResultFormat":"JSON",
        })
        if r is None: continue
        try:
            rows = (r.json().get("BEAAPI",{})
                            .get("Results",{})
                            .get("Data",[]))
            if not rows: continue
            latest = rows[-1]
            raw_payload = {
                "label":  ds["label"],
                "period": latest.get("TimePeriod"),
                "value":  latest.get("DataValue"),
                "source": "BEA",
            }
            _write(result, "BEA_GDP_PCE", "api_bea", raw_payload,
                   f"BEA {ds['label']}: {latest.get('DataValue')} "
                   f"for {latest.get('TimePeriod')}",
                   signal_type="macro", source_feed="bea_api")
        except Exception as e:
            logger.warning("BEA %s: %s", ds["label"], e)
        time.sleep(0.2)
    cb.on_success()


# ---------------------------------------------------------------------
# CFTC COT ZIP
# Probe confirmed: fut_fin_txt_{year}.zip -- 1,780 rows, 87 cols,
# 252 filtered contracts, latest 2026-05-26.
# Column names verified: Market_and_Exchange_Names,
# Report_Date_as_YYYY-MM-DD, Lev_Money_Positions_Long/Short_All,
# Open_Interest_All
# Source: github.com/NDelventhal/cot_reports (184 stars)
# ---------------------------------------------------------------------
def _fetch_cftc(result):
    cb = _get_cb("CFTC_COT")
    if not cb.can_execute():
        result.record("CFTC_COT", "skipped"); return

    year = datetime.now().year
    zip_sources = [
        {
            "url":       f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip",
            "label":     "TFF",
            "market_col":"Market_and_Exchange_Names",
            "date_col":  "Report_Date_as_YYYY-MM-DD",
            "long_col":  "Lev_Money_Positions_Long_All",
            "short_col": "Lev_Money_Positions_Short_All",
            "oi_col":    "Open_Interest_All",
        },
        {
            "url":       f"https://www.cftc.gov/files/dea/history/deacot{year}.zip",
            "label":     "Legacy",
            "market_col":"Market_and_Exchange_Names",
            "date_col":  "As_of_Date_In_Form_YYMMDD",
            "long_col":  "NonComm_Positions_Long_All",
            "short_col": "NonComm_Positions_Short_All",
            "oi_col":    "Open_Interest_All",
        },
    ]

    try:
        import pandas as pd
    except ImportError:
        logger.error("CFTC_COT -- pandas not installed")
        cb.on_failure(); return

    for src in zip_sources:
        try:
            r = requests.get(src["url"], headers=AGENT_HEADER,
                             timeout=CFTC_TIMEOUT, stream=True)
            if r.status_code != 200:
                logger.warning("CFTC %s ZIP HTTP %d", src["label"], r.status_code)
                continue

            zf    = zipfile.ZipFile(BytesIO(r.content))
            df    = pd.read_csv(zf.open(zf.namelist()[0]),
                                low_memory=False, encoding="latin-1")
            df.columns = [c.strip() for c in df.columns]

            mask = df[src["market_col"]].str.upper().str.contains(
                "|".join(COT_KEYWORDS), na=False, regex=True
            )
            filtered = df[mask].copy()
            if filtered.empty: continue

            filtered = filtered.sort_values(src["date_col"], ascending=False)
            latest_d = filtered[src["date_col"]].iloc[0]
            filtered = filtered[filtered[src["date_col"]] == latest_d]

            written = 0
            for _, row in filtered.iterrows():
                market = str(row.get(src["market_col"], "")).strip()
                rdate  = str(row.get(src["date_col"], "")).strip()
                try:
                    nc_long  = int(row.get(src["long_col"],  0) or 0)
                    nc_short = int(row.get(src["short_col"], 0) or 0)
                    oi       = int(row.get(src["oi_col"],    0) or 0)
                except (ValueError, TypeError):
                    nc_long = nc_short = oi = 0

                raw_payload = {
                    "contract":      market,
                    "as_of_date":    rdate,
                    "noncomm_long":  nc_long,
                    "noncomm_short": nc_short,
                    "net_noncomm":   nc_long - nc_short,
                    "open_interest": oi,
                    "dataset":       src["label"],
                    "source":        "CFTC_COT",
                }
                _write(result, "CFTC_COT", "api_cftc", raw_payload,
                       f"CFTC COT ({src['label']}) {market}: "
                       f"net {nc_long-nc_short:+,} as of {rdate}",
                       signal_type="sentiment",
                       source_feed="cftc_cot")
                written += 1

            if written > 0:
                logger.info("CFTC_COT (%s) -- %d contracts", src["label"], written)
                cb.on_success()
                return

        except zipfile.BadZipFile:
            logger.warning("CFTC %s -- bad ZIP (not yet published?)", src["label"])
        except Exception as e:
            logger.warning("CFTC %s: %s", src["label"], e)

    logger.warning("CFTC_COT -- all ZIP sources exhausted")
    cb.on_failure()


# ---------------------------------------------------------------------
# GDELT
# ---------------------------------------------------------------------
def _fetch_gdelt(result):
    cb = _get_cb("GDELT_API")
    if not cb.can_execute():
        result.record("GDELT_API", "skipped"); return
    r = _safe_fetch(
        "https://api.gdeltproject.org/api/v2/doc/doc", "GDELT_API",
        params={"query":"finance economy market inflation fed semiconductor",
                "mode":"artlist","maxrecords":10,
                "format":"json","timespan":"4h"},
        timeout=GDELT_TIMEOUT,
    )
    if r is None: return
    try:
        articles = r.json().get("articles", [])
        for a in articles[:10]:
            title = (a.get("title") or "").strip()
            if not title: continue
            raw_payload = {
                "title":    title,
                "url":      a.get("url",""),
                "domain":   a.get("domain",""),
                "seendate": a.get("seendate",""),
                "tone":     a.get("tone",""),
            }
            _write(result, "GDELT_API", "api_gdelt", raw_payload, title,
                   source_url=a.get("url",""),
                   signal_type="news", source_feed="gdelt_api")
        cb.on_success()
    except Exception as e:
        logger.warning("GDELT parse: %s", e)
        cb.on_failure()


# ---------------------------------------------------------------------
# FEAR/GREED -- CNN Equity Index (production.dataviz.cnn.io)
# Probe confirmed: score 23 (Extreme Fear), 0.97s
# ---------------------------------------------------------------------
def _fetch_feargreed(result: IngestResult):
    """
    CNN Equity Fear & Greed Index.
    Source: production.dataviz.cnn.io/index/fearandgreed/graphdata
    Confirmed working: probe_feargreed.py v2 -- score 60.17 (Greed)

    This is the EQUITY market Fear/Greed index -- measures stock market
    investor sentiment. Used by regime engine for Factor FG scoring.

    NOT crypto. alternative.me (crypto F/G) removed by CIO directive.
    Crypto is not monitored by BlueLotus.
    """
    cb = _get_cb("CNN_FearGreed")
    if not cb.can_execute():
        result.record("CNN_FearGreed", "skipped"); return

    headers = {
        "User-Agent": BROWSER_AGENT,
        "Accept":     "application/json, */*",
        "Referer":    "https://edition.cnn.com/",
        "Connection": "close",
    }

    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("CNN_FearGreed HTTP %d", r.status_code)
            cb.on_failure(); return

        data    = r.json()
        fg_data = data.get("fear_and_greed", {})
        score   = float(fg_data.get("score", 50))
        rating  = fg_data.get("rating", "neutral").upper()
        ts      = str(fg_data.get("timestamp", ""))

        # Label classification -- matching V1 regime factor thresholds
        if   score >= 75: label = "EXTREME GREED"
        elif score >= 55: label = "GREED"
        elif score >= 45: label = "NEUTRAL"
        elif score >= 25: label = "FEAR"
        else:             label = "EXTREME FEAR"

        raw_payload = {
            "score":      round(score, 1),
            "label":      label,
            "rating":     rating,
            "index_type": "equity_fear_greed",
            "source":     "CNN_production.dataviz",
            "timestamp":  ts,
        }
        _write(result, "CNN_FearGreed", "api_feargreed", raw_payload,
               f"CNN Equity Fear & Greed: {score:.1f}/100 -- {label}",
               signal_type="sentiment", source_feed="cnn_feargreed")
        cb.on_success()
        logger.info("CNN_FearGreed: %.1f -- %s", score, label)

    except (requests.exceptions.Timeout, TimeoutError, OSError,
            requests.exceptions.ConnectionError, Exception) as e:
        logger.warning("CNN_FearGreed %s: %s", type(e).__name__, e)
        cb.on_failure()

# ==========================================================================
# LAYER 1: LIVE PRICES -- len(WATCHLIST_83) TICKERS + VIX
# Source: moomoo_trader.py fetch_live_prices() + yfinance for VIX
# Output: {ticker: {price, chg_pct}} written to raw_signal_archive
# ==========================================================================


# ---------------------------------------------------------------------
# API GROUP DISPATCHER -- Layer 0 structured data sources
# ---------------------------------------------------------------------
def _fetch_api_group(result):
    logger.info("  [API] Fetching structured data sources...")
    _fetch_worldbank(result);           time.sleep(0.2)
    _fetch_bls(result);                 time.sleep(0.2)
    _fetch_eia("EIA_Petroleum", result); time.sleep(0.2)
    _fetch_eia("EIA_NatGas",    result); time.sleep(0.2)
    _fetch_sec_edgar(result);           time.sleep(0.2)
    _fetch_bea(result);                 time.sleep(0.2)
    _fetch_cftc(result);                time.sleep(0.2)
    _fetch_gdelt(result);               time.sleep(0.2)
    _fetch_feargreed(result)


# ---------------------------------------------------------------------
# ingest_all() -- Layer 0 only (original entry point, kept for compat)
# Call ingest_all_v2() for the full 8-layer cycle
# ---------------------------------------------------------------------
def ingest_all() -> dict:
    """Layer 0 only -- 47 external sources. Kept for compatibility."""
    result = IngestResult()
    logger.info("-"*62)
    logger.info("MID INGEST START  [v2.6]  %s", result.cycle_timestamp)
    logger.info("  Sources: %d | Default timeout: %ds",
                len(SOURCE_REGISTRY), DEFAULT_TIMEOUT)
    logger.info("-"*62)
    try:    run_preflight(SOURCE_REGISTRY)
    except Exception as e: logger.error("Preflight: %s", e)
    try:
        get_cycle_conn()
        logger.info("  [OK]  Cycle DB connection open")
    except Exception as e:
        logger.error("  [FAIL]  Cycle connection failed: %s -- abort", e)
        return result.to_dict()
    try:    _fetch_rss_group(result)
    except Exception as e: logger.error("RSS group: %s", e)
    try:    _fetch_api_group(result)
    except Exception as e: logger.error("API group: %s", e)
    try:
        close_cycle_conn()
        logger.info("  [OK]  Cycle DB connection closed")
    except Exception as e: logger.error("close_cycle_conn: %s", e)
    open_cb = [s for s, cb in _cb_registry.items()
               if cb.state == CBState.OPEN or cb.permanent_skip]
    if open_cb:
        logger.warning("  [CB]  Open circuits: %s", open_cb)
    result.log_summary()
    return result.to_dict()


# ====================================================================
# COGNITION LAYER CONSTANTS
# All defined at module level -- accessible by all layer functions
# ====================================================================

OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

PORTFOLIO_FALLBACK = {
    "BAC": {"qty": 150, "avg_cost": 50.344},
    "WFC": {"qty": 40,  "avg_cost": 75.000},
}

PORTFOLIO_VALUE_FLOOR = 6000

# WO-RD-20260607-003 v1.3: expanded 83 → 189 tickers
# All tickers receive identical pipeline treatment — same Moomoo get_market_snapshot() call
# get_market_snapshot() supports up to 400 codes per call — no architectural change needed
WATCHLIST_83 = get_universe()
WATCHLIST_78 = WATCHLIST_83  # backwards-compatible alias — now 189 tickers

TOP_MOVERS_COUNT   = 15
NEWS_TICKERS_COUNT = 20

# v2.6: expanded 9 → 23 themes (probe_ece_taxonomy.py confirmed)
EVENT_THEMES = {
    "MACRO / FED": ["fed","fomc","powell","rate hike","rate cut","hawkish","dovish","federal reserve","interest rate","rate decision","fed funds","monetary policy","taper","balance sheet","quantitative","beige book","cpi","pce","inflation","nonfarm","unemployment","gdp","jobs report","bls","core inflation","price index","consumer price","coca cola","procter gamble","walmart","costco","pepsico","mcdonalds","home depot","lowes","nike","starbucks","target","colgate","ups","fedex","union pacific","delta airlines","deere","verizon","att","realty income","consumer staples","defensive rotation","retail sales","consumer spending","logistics","freight"],
    "OIL / GAS": ["oil","crude","wti","brent","petroleum","opec","xom","oxy","eog","fang","barrel","rig count","refinery","pipeline","wmb","kmi","natural gas","lng","henry hub","natgas","midstream","energy infrastructure","shale","fracking","oil price","chevron","conoco","devon energy","cheniere","valero","phillips 66","marathon petroleum","enterprise products","enbridge","refinery margin","crack spread","lng terminal"],
    "TRUMP / TRADE": ["trump","tariff","trade deal","executive order","white house","sanctions","china deal","trade war","reciprocal tariff","section 301","import duty","trade deficit","export control","commerce dept"],
    "GEOPOLITICAL": ["iran","hormuz","taiwan","ukraine","russia","israel","middle east","south china sea","pboc","lpr","yuan","nato","north korea","strait","conflict","ceasefire","drone","missile","military strike","war","escalation"],
    "AI / SEMIS": ["nvidia","semiconductor","ai chip","tsmc","arm","quantum","amd","intel","marvell","broadcom","machine learning","artificial intelligence","hbm","memory","wafer","foundry","chip ban","export restriction","cdns","snps","asml","euv","lam research","klac","kla","qualcomm","snapdragon","texas instruments","analog chip","lrcx","amkor","amkr"],
    "SPACE / HIGH-BETA": ["space force","spacex","rocket","satellite","asts","rklb","lunr","space launch","orbit","payload","viasat","globalstar","spire","planet labs","virgin galactic","american tower","cell tower","5g infrastructure","leo satellite","satellite broadband"],
    "ENERGY / URANIUM": ["uranium","nuclear","oil","natgas","petroleum","eia","opec","ceg","ccj","vst","energy","lng","crude","wti","brent","natural gas","energy crisis","power plant","refinery","barrel","rig count","fang"],
    "RARE EARTH / METALS": ["rare earth","lithium","copper","gold","silver","mp materials","critical mineral","cobalt","aluminum","manganese","nickel","tungsten","supply chain mineral","china rare earth","export ban mineral","usar"],
    "BANKS / LIQUIDITY": ["bank","fed funds","repo","liquidity","credit","bac","wfc","jpmorgan","goldman","yield curve","lending","net interest margin","nim","deposit","loan growth","banking stress","capital ratio","stress test","morgan stanley","blackrock","schwab","jp morgan","american express","chubb","moody","progressive","allstate","berkshire","warren buffett","insurance","wealth management","asset management","investment banking"],
    "SOFTWARE / CYBERSECURITY": ["cybersecurity","software","cloud","crowdstrike","palantir","hack","breach","zero trust","saas","ransomware","malware","cyber attack","data breach","endpoint","firewall","panw","crwd","axon","msft","orcl","pltr","software license","recurring revenue","arr","salesforce","crm","servicenow","adobe","fortinet","zscaler","intuit","snowflake","okta","sentinelone","enterprise software","cloud security"],
    "QUANTUM": ["quantum","qubit","ionq","d-wave","rigetti","qbts","qubt","rgti","qtum","quantum advantage","quantum supremacy","error correction","quantum hardware","quantum software","ibm quantum","photonic","trapped ion","superconducting qubit","quantum computing"],
    "CLEAN ENERGY / SOLAR": ["solar","clean energy","renewable","enphase","first solar","fuel cell","bloom energy","plug power","enph","fslr","fcel","be","plug","wind","offshore wind","green hydrogen","inflation reduction act","ira","clean power","ev charging","solar panel","photovoltaic","net metering","solaredge","array technologies","sunrun","brookfield renewable","residential solar","solar inverter","solar tracker","renewable operator"],
    "DEFENSE / AEROSPACE PRIMES": ["raytheon","rtx","northrop","noc","lockheed","lmt","hii","ldos","axon","boeing","ba","defense contract","pentagon","military","weapons system","f-35","fighter jet","missile defense","navy","hypersonic","drone defense","aerospace","combat aircraft","l3harris","honeywell","transdigm","heico","kratos","drone","autonomous system","defense electronics","c4isr"],
    "CONSUMER TECH / APPLE": ["apple","iphone","amazon","google","meta","consumer","app store","antitrust","big tech","advertising","aapl","amzn","googl","streaming","subscription","hardware cycle","smartphone","tablet","wearable","ad revenue","digital advertising","privacy"],
    "GOLD / SAFE HAVEN": ["gold","safe haven","gld","silver","newmont","anglogold","precious metal","store of value","inflation hedge","gold price","bullion","central bank gold","gld etf","flight to safety","risk off gold","slv","nem","au","dollar weakness","real rate","tips","coeur mining","hecla mining","first majestic","pan american silver","silver miner","gold miner","precious metal miner"],
    "COPPER / INDUSTRIAL METALS": ["copper","freeport","southern copper","bhp","rio tinto","industrial metal","china demand","infrastructure spending","fcx","scco","bhp","rio","aluminum","steel","iron ore","china pmi","manufacturing","construction demand","ev copper","green copper","electrification","hudbay","teck","vale","nucor","alcoa","cleveland cliffs","caterpillar","nutrien","mosaic","archer daniels","potash","fertiliser","mining output"],
    "FINTECH / CRYPTO": ["bitcoin","crypto","coinbase","ethereum","defi","robinhood","fintech","sec crypto","stablecoin","digital asset","coin","hood","sofi","blockchain","nft","web3","crypto regulation","btc","spot etf","grayscale","payment rail","neobank","embedded finance","visa","mastercard","paypal","microstrategy","bitcoin etf","ibit","payments network","card network","digital wallet"],
    "UTILITIES / POWER": ["utility","utilities","duke","vst","vistra","duk","power grid","electricity","baseload","grid reliability","transmission","capacity market","load growth","power purchase","rate case","regulated utility","electric grid","power demand","renewable utility","green utility","ge vernova","nextera","eaton","emerson electric","american water works","water utility","grid equipment","power turbine","transmission infrastructure"],
    "BIOTECH / PHARMA": ["fda","clinical trial","drug approval","biotech","pharma","mrna","weight loss","ozempic","biosimilar","glp-1","drug manufacturer","patent cliff","regulatory approval","phase 3","nda","bla","anda","drug pricing","healthcare","medicare","cms","johnson johnson","unitedhealth","merck","amgen","bristol myers","gilead","regeneron","biogen","health insurer","managed care","oncology"],
    "MAG7 / BIG TECH": ["magnificent seven","mag7","big tech","mega cap","nvda","msft","aapl","googl","goog","meta","amzn","alphabet","microsoft","apple","amazon","antitrust big tech","big tech regulation","platform","app store","cloud monopoly","ai dominance","hyperscaler","tesla","tsla","netflix","nflx","uber","disney","streaming","platform economy"],
    "NUCLEAR / POWER GRID": ["nuclear","small modular reactor","smr","power grid","data center power","constellation","vistra","hyperscaler power","electricity demand","ceg","vst","load growth","utility rate case","power purchase","nuclear license","uranium demand","baseload","grid reliability","transmission","capacity market","oklo","nuscale","bwxt","microreactor","advanced reactor","nuclear fuel"],
    "IPO / MOMENTUM": ["ipo","lock-up expiry","secondary offering","short squeeze","meme","retail flow","options expiry","gamma squeeze","retail trading","wsb","wallstreetbets","yolo","short interest","hood","robinhood","coin","sofi","high volume","unusual volume"],
    "EARNINGS CATALYST": ["earnings","beat","miss","guidance","revenue","eps","results","q1","q2","q3","q4","avgo","dell earnings","quarterly results","full year","outlook","raised guidance","revenue beat","profit warning","consensus estimate","8-k","form 8k","material event","sec filing"],
}

INSTITUTIONAL_KEYWORDS = [
    "federal reserve","fed rate","powell","fomc","hawkish","dovish",
    "inflation","goldman sachs","jpmorgan","price target","upgrade","downgrade",
    "overweight","underweight","recession","stagflation","yield curve",
    "china trade","iran war","hormuz","oil supply","asts","mp materials",
    "nvidia","semiconductor","rare earth","quantum","ai chip",
]


def _fetch_moomoo_prices(tickers: list) -> dict:
    """
    Fetch live prices from Moomoo OpenD for all equity tickers.

    ARCHITECTURE NOTE (from V1 fetch_prices() -- portfolio_agent_v60 line 615):
      "Separate VIX from equity tickers -- Moomoo does not carry ^VIX"
      Moomoo OpenD get_market_snapshot() handles US.{TICKER} equity codes only.
      ^VIX is a CBOE volatility index -- not an equity -- Moomoo Singapore
      does not carry it. yfinance is the correct and only source for ^VIX.
      This was the deliberate design decision in V1 and is preserved here.

    Equity prices (len(WATCHLIST_83) tickers): Moomoo OpenD get_market_snapshot()
      - Uses _safe_float() pattern from moomoo_trader.py
      - Falls back to PORTFOLIO_FALLBACK avg_cost if Moomoo offline
      - Never zero-fills prices (prevents false -100% drawdown)

    VIX (^VIX only): yfinance -- 1h interval, period=2d
      - Matches V1 fetch_prices() VIX logic exactly
      - Falls back to 20.0 if yfinance unavailable
    """
    prices  = {}
    equity  = [t for t in set(tickers) if not t.startswith("^")]
    indices = [t for t in set(tickers) if t.startswith("^")]

    # -- EQUITY: Moomoo OpenD get_market_snapshot() ----------------
    # DEFECT-07 FIX (WO-RD-20260604-002):
    # Session-aware price capture using probe-confirmed field names:
    #   pre_price    = pre-market price  (confirmed: WFC 79.100 = UI 79.100)
    #   after_price  = post-market price (confirmed: WFC 78.4057)
    #   last_price   = regular session close
    #   volume       = regular session volume (covers P2-02 at zero extra cost)
    # Session detection: convert SGT (UTC+8) to ET (UTC-4 or UTC-5)
    # US ET = SGT - 12h (EDT, summer) / SGT - 13h (EST, winter)
    # Sessions (ET): PRE 04:00-09:30 | REGULAR 09:30-16:00 | POST 16:00-20:00
    try:
        import moomoo as ft
        import moomoo.common.ft_logger as _ftl
        _ftl.logger.enable_console_log(False)

        # Detect current market session based on ET time
        from datetime import timezone, timedelta
        _now_utc = datetime.now(timezone.utc)
        # US Eastern: UTC-4 during EDT (Mar-Nov), UTC-5 during EST (Nov-Mar)
        # Use UTC-4 (EDT) as default -- correct for Jun-Oct Singapore timezone
        _et_offset = timedelta(hours=-4)
        _now_et    = _now_utc + _et_offset
        _et_hour   = _now_et.hour + _now_et.minute / 60.0

        if 9.5 <= _et_hour < 16.0:
            _session = "REGULAR"
        elif 4.0 <= _et_hour < 9.5:
            _session = "PRE_MARKET"
        elif 16.0 <= _et_hour < 20.0:
            _session = "POST_MARKET"
        else:
            _session = "CLOSED"

        logger.info("  [LAYER 1] Market session: %s (ET %.2f)", _session, _et_hour)

        ctx   = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
        codes = [f"US.{t}" for t in equity]
        ret, data = ctx.get_market_snapshot(codes)
        ctx.close()

        if ret == ft.RET_OK and data is not None:
            for _, row in data.iterrows():
                ticker = str(row.get("code","")).replace("US.","")

                def _sf(col):
                    """Safe float extraction -- mirrors _safe_float from moomoo_trader.py"""
                    return float(str(row.get(col,"0")).strip()
                                 .replace("N/A","0").replace("--","0") or 0)

                last      = _sf("last_price")
                prev      = _sf("prev_close_price")
                pre_px    = _sf("pre_price")
                after_px  = _sf("after_price")
                volume    = int(float(str(row.get("volume","0")).replace("N/A","0") or 0))
                pre_chg   = _sf("pre_change_rate")    # % already
                after_chg = _sf("after_change_rate")  # % already
                pre_vol   = int(float(str(row.get("pre_volume","0")).replace("N/A","0") or 0))

                prev = prev if prev > 0 else last

                # Session-correct price: use most current available price
                if _session == "PRE_MARKET" and pre_px > 0:
                    session_price = pre_px
                    chg = round(pre_chg, 2)
                elif _session == "POST_MARKET" and after_px > 0:
                    session_price = after_px
                    chg = round(after_chg, 2)
                elif _session == "REGULAR" and last > 0:
                    session_price = last
                    chg = round((last - prev) / prev * 100, 2) if prev > 0 else 0.0
                else:
                    # CLOSED or missing extended data -- use last known close
                    session_price = last if last > 0 else prev
                    chg = round((last - prev) / prev * 100, 2) if prev > 0 else 0.0

                prices[ticker] = {
                    "price":         round(session_price, 4),
                    "chg_pct":       chg,
                    "session":        _session,
                    "regular_close": round(last, 4),
                    "prev_close":    round(prev, 4),
                    "pre_price":     round(pre_px, 4) if pre_px > 0 else None,
                    "pre_chg_pct":   round(pre_chg, 3) if pre_px > 0 else None,
                    "after_price":   round(after_px, 4) if after_px > 0 else None,
                    "after_chg_pct": round(after_chg, 3) if after_px > 0 else None,
                    "volume":        volume,
                    "pre_volume":    pre_vol if pre_vol > 0 else None,
                    "price_source":  _session.lower(),
                }

            logger.info("  [LAYER 1] Moomoo OpenD: %d equity prices [session=%s]",
                        len(prices), _session)
        else:
            logger.warning("  [LAYER 1] Moomoo get_market_snapshot failed: %s", data)
            # Stale fill -- never zero-fill (V1 BUG 1 FIX)
            for t in equity:
                fallback = PORTFOLIO_FALLBACK.get(t, {}).get("avg_cost", 0)
                if fallback > 0:
                    prices[t] = {"price": fallback, "chg_pct": 0, "stale": True,
                                 "session": "UNKNOWN", "price_source": "fallback"}

    except ImportError:
        logger.warning("  [LAYER 1] moomoo-api not installed -- pip install moomoo-api")
    except Exception as e:
        logger.warning("  [LAYER 1] Moomoo offline (%s) -- stale-fill from avg_cost",
                       type(e).__name__)
        for t in equity:
            fallback = PORTFOLIO_FALLBACK.get(t, {}).get("avg_cost", 0)
            if fallback > 0:
                prices[t] = {"price": fallback, "chg_pct": 0, "stale": True}

    # -- VIX: yfinance -- Moomoo does not carry CBOE index symbols --
    # V1 source: portfolio_agent_v60 line 615 explicitly documents this.
    # ^VIX is a CBOE volatility index, not a US equity.
    # Moomoo OpenD only handles US.{TICKER} equity codes.
    # yfinance is the correct source. 1h interval matches V1 exactly.
    for sym in indices:
        try:
            import yfinance as yf
            hist = yf.Ticker(sym).history(period="2d", interval="1h")
            if len(hist) >= 2:
                price = float(hist["Close"].iloc[-1])
                chg   = round((price - float(hist["Close"].iloc[-2]))
                              / float(hist["Close"].iloc[-2]) * 100, 2)
            elif len(hist) == 1:
                price = float(hist["Close"].iloc[-1]); chg = 0.0
            else:
                price = 20.0; chg = 0.0
            prices[sym] = {"price": round(price, 3), "chg_pct": round(chg, 2)}
            logger.info("  [LAYER 1] %s: %.2f (%+.2f%%) -- via yfinance "
                        "(Moomoo does not carry CBOE index symbols)", sym, price, chg)
        except ImportError:
            logger.warning("  [LAYER 1] yfinance not installed -- pip install yfinance")
            prices[sym] = {"price": 20.0, "chg_pct": 0.0}
        except Exception as e:
            logger.warning("  [LAYER 1] %s yfinance error: %s -- default 20.0", sym, e)
            prices[sym] = {"price": 20.0, "chg_pct": 0.0}

    return prices


def _classify_market_session(cycle_ts: str = None) -> str:
    """Return precise market session label based on current time."""
    try:
        import zoneinfo
        from datetime import datetime, time as dtime
        ET = zoneinfo.ZoneInfo("America/New_York")
        now_et = datetime.now(ET)
        wd = now_et.weekday()  # 0=Mon...6=Sun
        t = now_et.time()

        if wd >= 5:  # Saturday or Sunday
            return "WEEKEND_SNAPSHOT"
        if dtime(9, 30) <= t <= dtime(16, 0):
            return "REGULAR_SESSION"
        if dtime(4, 0) <= t < dtime(9, 30):
            return "PRE_MARKET"
        if dtime(16, 0) < t <= dtime(20, 0):
            return "POST_MARKET"
        return "MARKET_CLOSED_LAST_REGULAR_CLOSE"
    except Exception:
        return "MARKET_CLOSED_LAST_REGULAR_CLOSE"


def _write_prices_to_db(all_prices: dict, result: IngestResult):
    """Write full price snapshot to raw_signal_archive as single signal."""
    if not all_prices:
        return
    movers = sorted(
        [(t,d) for t,d in all_prices.items() if not t.startswith("^")],
        key=lambda x: abs(x[1].get("chg_pct",0)), reverse=True
    )[:TOP_MOVERS_COUNT]
    mover_text = " | ".join(
        f"{t} ${d.get('price',0):.2f} ({d.get('chg_pct',0):+.1f}%)"
        for t, d in movers
    )
    vix = all_prices.get("^VIX", {})
    # Derive market_session from wall-clock time (precise labels)
    _market_session = _classify_market_session()
    raw_payload = {
        "source":         "LivePrices_Moomoo",
        "ticker_count":   len(all_prices),
        "cycle_ts":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_session": _market_session,
        "vix":            vix,
        "prices":         all_prices,
        "top_movers":     [{"ticker":t,"price":d.get("price",0),"chg_pct":d.get("chg_pct",0),
                             "session":d.get("session",""),"volume":d.get("volume",0)}
                           for t,d in movers],
    }
    _write(result, "LivePrices_Moomoo", "moomoo_prices", raw_payload,
           f"LivePrices {len(all_prices)} tickers | VIX {vix.get('price',0):.1f} "
           f"({vix.get('chg_pct',0):+.1f}%) | Top movers: {mover_text[:300]}",
           signal_type="market_data", source_feed="moomoo_prices")


# ==========================================================================
# LAYER 2: PORTFOLIO SNAPSHOT
# Source: moomoo_trader.py get_live_positions() + get_account_info()
# Output: snapshot dict written to raw_signal_archive
# V1 rules preserved: stale price guard, PORTFOLIO_VALUE_FLOOR
# ==========================================================================

def _build_portfolio_snapshot(all_prices: dict) -> dict:
    """
    Build portfolio snapshot from Moomoo live positions.
    Falls back to PORTFOLIO_FALLBACK if Moomoo offline.
    RULE: price=0 ? substitute avg_cost (prevents false -100% drawdown).
    RULE: total_value < PORTFOLIO_VALUE_FLOOR ? set integrity_flag=True.
    """
    snapshot = {
        "positions": {}, "total_value": 0.0, "total_cost": 0.0,
        "total_pnl": 0.0, "total_pnl_pct": 0.0,
        "cash": 0.0, "buying_power": 0.0, "market_val": 0.0, "total_assets": 0.0,
        "stale": False, "integrity_flag": False,
        "source": "fallback",
    }
    raw_positions = {}

    # Try live Moomoo positions first
    try:
        import moomoo as ft
        import moomoo.common.ft_logger as _ftl
        _ftl.logger.enable_console_log(False)

        ctx = ft.OpenSecTradeContext(
            filter_trdmarket=ft.TrdMarket.US,
            host=OPEND_HOST, port=OPEND_PORT,
            security_firm=ft.SecurityFirm.FUTUSG,
        )
        ret, data = ctx.position_list_query(currency="USD")
        if ret == ft.RET_OK and data is not None and not data.empty:
            for _, row in data.iterrows():
                code = str(row.get("code","")).replace("US.","")
                qty  = int(float(row.get("qty", 0) or 0))
                # DEFECT-08 FIX (WO-RD-20260604-002):
                # Moomoo API doc v10.6 explicitly states:
                #   "It is recommended to use the fields of average_cost and
                #    diluted_cost to obtain the cost price"
                # cost_price = diluted cost (NOT the blended avg across all lots)
                # average_cost = blended avg cost (what Moomoo UI shows)
                # Probe confirmed: BAC average_cost=51.118 (UI=51.118) PASS
                #                  WFC average_cost=77.446 (UI=77.446) PASS
                #                  cost_price gave 47.014 and 72.169 -- WRONG
                cost = float(row.get("average_cost", 0) or 0)
                # Assertion gate: average_cost must be positive
                # If 0 or missing (older SDK), fall back to cost_price
                if cost <= 0:
                    cost = float(row.get("cost_price", 0) or 0)
                    logger.warning("  [LAYER 2] %s: average_cost=0, falling back to cost_price=%.4f", code, cost)
                if qty > 0:
                    raw_positions[code] = {"qty": qty, "avg_cost": round(cost, 4)}
            snapshot["source"] = "moomoo_live"
            logger.info("  [LAYER 2] Moomoo live positions: %d holdings", len(raw_positions))

        # Cash / buying power -- BUG-002 FIX + USD currency fix
        ret2, info = ctx.accinfo_query(
            trd_env=ft.TrdEnv.REAL, acc_id=0,
            refresh_cache=True, currency=ft.Currency.USD,
        )
        if ret2 == ft.RET_OK and info is not None and not info.empty:
            row = info.iloc[0]
            us_cash   = float(str(row.get("us_cash",     0) or 0).replace("N/A","0") or 0)
            usd_power = float(str(row.get("usd_net_cash_power", 0) or 0).replace("N/A","0") or 0)
            mkt_val   = float(str(row.get("market_val",  0) or 0).replace("N/A","0") or 0)
            usd_assets= float(str(row.get("usd_assets",  0) or 0).replace("N/A","0") or 0)
            leg_cash  = float(str(row.get("cash",        0) or 0).replace("N/A","0") or 0)
            snapshot["cash"]         = round(us_cash if us_cash > 0 else leg_cash, 2)
            snapshot["buying_power"] = round(max(usd_power, 0), 2)
            if usd_assets > 0:
                snapshot["usd_assets"] = round(usd_assets, 2)
            logger.info("  [LAYER 2] Cash: $%.2f | Power: $%.2f",
                        snapshot["cash"], snapshot["buying_power"])
        ctx.close()

    except ImportError:
        logger.warning("  [LAYER 2] moomoo not installed -- using PORTFOLIO_FALLBACK")
    except Exception as e:
        logger.warning("  [LAYER 2] Moomoo offline (%s) -- using PORTFOLIO_FALLBACK",
                       type(e).__name__)

    if not raw_positions:
        raw_positions = dict(PORTFOLIO_FALLBACK)
        snapshot["source"] = "fallback"

    # Build positions with stale price guard
    for ticker, pos in raw_positions.items():
        price_data = all_prices.get(ticker, {})
        price      = price_data.get("price", 0)
        chg_pct    = price_data.get("chg_pct", 0)
        avg_cost   = pos["avg_cost"]
        qty        = pos["qty"]
        stale      = False

        # STALE PRICE GUARD -- substitutes avg_cost if price=0
        if price <= 0:
            price  = avg_cost
            stale  = True
            snapshot["stale"] = True
            logger.warning("  [LAYER 2] STALE: %s -- using avg_cost $%.2f", ticker, avg_cost)

        mkt_val    = round(price * qty, 2)
        cost_basis = round(avg_cost * qty, 2)
        unrealized = round(mkt_val - cost_basis, 2)
        unreal_pct = round(unrealized / cost_basis * 100, 2) if cost_basis > 0 else 0.0

        snapshot["positions"][ticker] = {
            "qty": qty, "avg_cost": avg_cost, "price": price,
            "chg_pct": chg_pct, "mkt_val": mkt_val,
            "unrealized": unrealized, "unrealized_p": unreal_pct,
            "stale": stale,
        }
        snapshot["total_value"] += mkt_val
        snapshot["total_cost"]  += cost_basis

    snapshot["total_pnl"]    = round(snapshot["total_value"] - snapshot["total_cost"], 2)
    snapshot["total_pnl_pct"]= round(
        snapshot["total_pnl"] / snapshot["total_cost"] * 100
        if snapshot["total_cost"] > 0 else 0.0, 2)
    snapshot["total_assets"] = round(snapshot["total_value"] + snapshot["cash"], 2)

    # DATA INTEGRITY FLAG + REASON (DEFECT-04 FIX)
    # Rule: integrity_flag=True whenever total_value < PORTFOLIO_VALUE_FLOOR.
    # Reason must always be explicit so downstream report can display
    # "Portfolio Reconciled: NO -- [reason]" rather than a bare flag.
    # Secondary check: buying_power vs cash delta flagged if large (>$1,000).
    integrity_reason = None

    if snapshot["total_value"] < PORTFOLIO_VALUE_FLOOR:
        snapshot["integrity_flag"] = True
        # Detect cash-fortress mode: high cash = intentional defensive posture
        _total_assets_for_cfm = snapshot["total_value"] + snapshot.get("cash", 0)
        _cash_pct_for_cfm     = snapshot.get("cash", 0) / _total_assets_for_cfm if _total_assets_for_cfm else 0
        if _cash_pct_for_cfm >= 0.70:
            integrity_reason = (
                f"INFO_LOW_MARKET_EXPOSURE_INTENTIONAL: Portfolio market value "
                f"${snapshot['total_value']:,.2f} is below floor ${PORTFOLIO_VALUE_FLOOR:,} "
                f"but cash weight is {_cash_pct_for_cfm:.1%} — "
                f"low deployment is intentional under CIO cash-fortress / scout-mode posture"
            )
            logger.info(
                "  [LAYER 2] [INFO] Portfolio $%.0f < floor $%d but cash-fortress mode detected "
                "(cash %.1f%%) -- classifying as INFO_LOW_MARKET_EXPOSURE_INTENTIONAL",
                snapshot["total_value"], PORTFOLIO_VALUE_FLOOR, _cash_pct_for_cfm * 100
            )
        else:
            integrity_reason = (
                f"Portfolio market value ${snapshot['total_value']:,.2f} is below "
                f"minimum floor ${PORTFOLIO_VALUE_FLOOR:,} -- positions may be missing "
                f"or prices stale"
            )
            logger.warning("  [LAYER 2] [WARN] Portfolio $%.0f < floor $%d -- integrity flag set",
                           snapshot["total_value"], PORTFOLIO_VALUE_FLOOR)

    # Secondary check: buying_power vs cash delta
    # Large delta typically indicates unsettled funds, margin reservation, or open orders.
    # Only fires when we have real broker account data (buying_power > 0).
    cash         = snapshot.get("cash", 0)
    buying_power = snapshot.get("buying_power", 0)
    bp_delta     = round(cash - buying_power, 2)
    if buying_power > 0 and abs(bp_delta) > 1000:
        bp_reason = (
            f"Buying power ${buying_power:,.2f} is ${abs(bp_delta):,.2f} "
            f"{'below' if bp_delta > 0 else 'above'} cash ${cash:,.2f} -- "
            f"likely unsettled funds or margin reservation"
        )
        if not snapshot["integrity_flag"]:
            snapshot["integrity_flag"] = True
            integrity_reason = bp_reason
            logger.warning("  [LAYER 2] [WARN] BP delta $%.0f -- integrity flag set", bp_delta)
        else:
            integrity_reason = integrity_reason + "; " + bp_reason

    # Always populate integrity_flag_reason -- UNKNOWN if flag set but reason unknown.
    if snapshot["integrity_flag"] and not integrity_reason:
        integrity_reason = "UNKNOWN -- manual reconciliation required"
    snapshot["integrity_flag_reason"] = integrity_reason or None

    return snapshot


def _write_snapshot_to_db(snapshot: dict, result: IngestResult):
    """Write portfolio snapshot to raw_signal_archive."""
    raw_payload = {
        "source":         "Portfolio_Snapshot",
        "total_value":    snapshot["total_value"],
        "total_cost":     snapshot["total_cost"],
        "total_pnl":      snapshot["total_pnl"],
        "total_pnl_pct":  snapshot["total_pnl_pct"],
        "cash":           snapshot["cash"],
        "buying_power":   snapshot.get("buying_power", 0.0),
        "market_val":     snapshot["total_value"],  # BUG-002: arithmetic sum not accinfo
        "total_assets":   snapshot["total_assets"],
        "positions":      snapshot["positions"],
        "stale":                  snapshot["stale"],
        "integrity_flag":         snapshot["integrity_flag"],
        "integrity_flag_reason":  snapshot.get("integrity_flag_reason"),
        "data_source":            snapshot["source"],
        "cycle_ts":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    pos_summary = " | ".join(
        f"{t} ${d['price']:.2f} ({d['chg_pct']:+.1f}%) P/L ${d['unrealized']:+,.0f}"
        for t, d in snapshot["positions"].items()
    )
    _write(result, "Portfolio_Snapshot", "moomoo_snapshot", raw_payload,
           f"Portfolio: ${snapshot['total_value']:,.2f} | P/L: ${snapshot['total_pnl']:+,.2f} "
           f"({snapshot['total_pnl_pct']:+.2f}%) | Cash: ${snapshot['cash']:,.2f} | "
           f"Source: {snapshot['source']} | Positions: {pos_summary[:400]}",
           signal_type="portfolio", source_feed="moomoo_portfolio")


# ==========================================================================
# LAYER 3: MOOMOO INSTITUTIONAL INTELLIGENCE
# Source: moomoo_intelligence.py fetch_moomoo_intelligence()
# Covers: analyst ratings, options flow, insider trades, 13F changes,
#         Morningstar fair value, technical divergences
# Each signal line written individually to raw_signal_archive
# ==========================================================================

def _fetch_and_write_moomoo_intel(tickers: list, result: IngestResult) -> dict:
    """
    Pull all Moomoo institutional intelligence and write to DB.
    Runs: fetch_analyst_ratings + fetch_unusual_signals +
          fetch_insider_trades + fetch_institutional_holders

    Signal type per line:
      [WALL ST. ANALYSTS]  ? institutional
      [ANALYST RATINGS]    ? institutional
      [MORNINGSTAR]        ? institutional
      [OPTIONS FLOW]       ? sentiment
      [TECHNICAL]          ? sentiment
      [FINANCIAL]          ? sentiment
      [INSIDER]            ? institutional
      [13F]                ? institutional
      [DIVERGENCE]         ? institutional
    """
    mm_intel = {"summary":[], "analyst":{}, "unusual":{},
                "insider":{}, "institutional":{}}
    try:
        import sys as _sys
        # Add bluelotus2 root to path so moomoo_intelligence.py can be found
        _bl_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _bl_root not in _sys.path:
            _sys.path.insert(0, _bl_root)
        if os.getcwd() not in _sys.path:
            _sys.path.insert(0, os.getcwd())
        from moomoo_intelligence import fetch_moomoo_intelligence
        logger.info("  [LAYER 3] Fetching Moomoo intel for %d tickers...", len(tickers))
        mm_intel = fetch_moomoo_intelligence(tickers)

        written = 0
        for sig_line in mm_intel.get("summary", []):
            if not sig_line or len(sig_line.strip()) < 5:
                continue

            # Classify by prefix
            if "[OPTIONS FLOW]" in sig_line or "[TECHNICAL]" in sig_line or \
               "[FINANCIAL]" in sig_line:
                sig_type = "sentiment"
            else:
                sig_type = "institutional"

            _write(result, "Moomoo_Intel", "moomoo_intelligence",
                   {"signal_line": sig_line,
                    "source":     "Moomoo_Intel",
                    "cycle_ts":   datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                   sig_line,
                   signal_type=sig_type,
                   source_feed="moomoo_intelligence")
            written += 1

        logger.info("  [LAYER 3] Moomoo Intel: %d signals written", written)

    except ImportError:
        logger.warning("  [LAYER 3] moomoo_intelligence.py not found -- "
                       "place at C:\\bluelotus2\\moomoo_intelligence.py")
    except Exception as e:
        logger.warning("  [LAYER 3] Moomoo Intel error: %s: %s", type(e).__name__, e)

    return mm_intel


# ==========================================================================
# LAYER 4: ANALYST TARGETS
# Source: analyst_targets.json (pre-fetched by fetch_analyst_targets.py)
# Why pre-fetched: Moomoo requires batched 10-ticker calls with 10s pause
#                  cannot run inline without blocking the ingest cycle
# Writes: one DB row per ticker with avg/high/low target + buy/hold/sell
# ==========================================================================

def _write_analyst_targets_to_db(result: IngestResult):
    """
    Load analyst_targets.json and write each ticker's consensus to DB.
    Run fetch_analyst_targets.py separately to refresh the JSON.
    """
    import json as _json

    # Look for JSON in bluelotus2 root
    # Search in multiple locations -- works for both -m mid.ingest and direct run
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "analyst_targets.json"),         # C:\bluelotus3\analyst_targets.json
        os.path.join(os.getcwd(), "analyst_targets.json"),  # CWD
        "analyst_targets.json",                       # relative
    ]
    targets_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    base_dir = os.path.dirname(targets_path)

    if not os.path.exists(targets_path):
        logger.warning("  [LAYER 4] analyst_targets.json not found at %s", targets_path)
        logger.warning("  [LAYER 4] Run: python fetch_analyst_targets.py to generate")
        return

    try:
        with open(targets_path, "r", encoding="utf-8") as f:
            data = _json.load(f)

        targets   = data.get("targets", {})
        fetch_ts  = data.get("fetch_timestamp_sgt", "unknown")
        filled    = data.get("filled_count", 0)
        written   = 0

        logger.info("  [LAYER 4] analyst_targets.json: %d tickers, %d filled, fetched %s",
                    len(targets), filled, fetch_ts)

        for ticker, info in targets.items():
            avg = float(info.get("average", 0) or 0)
            if avg <= 0:
                continue  # No consensus target -- skip

            buy       = int(info.get("buy", 0) or 0)
            strong_buy= int(info.get("strong_buy", 0) or 0)
            hold      = int(info.get("hold", 0) or 0)
            sell      = int(info.get("sell", 0) or 0)
            total     = int(info.get("total", 0) or 0)
            rating    = str(info.get("rating", ""))
            high      = float(info.get("highest", 0) or 0)
            low       = float(info.get("lowest",  0) or 0)

            raw_payload = {
                "ticker":          ticker,
                "avg_target":      avg,
                "high_target":     high,
                "low_target":      low,
                "rating":          rating,
                "buy":             buy + strong_buy,
                "hold":            hold,
                "sell":            sell,
                "total_analysts":  total,
                "source":          "Moomoo_Analyst_Targets",
                "fetched_at":      fetch_ts,
                "cycle_ts":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # DEFECT-01 FIX: buy/hold/sell in analyst_targets.json are PERCENTAGES.
            # Confirmed: buy+hold+sell sums to ~100 for all 78 tickers.
            # total is analyst HEADCOUNT -- not a denominator for percentage calc.
            # Print directly -- no division.
            buy_pct  = buy + strong_buy   # already a percentage (0-100)
            hold_pct = hold               # already a percentage (0-100)
            sell_pct = sell               # already a percentage (0-100)

            _write(result, "Analyst_Targets", "moomoo_analyst_targets",
                   raw_payload,
                   f"[ANALYST CONSENSUS] {ticker}: Avg Target ${avg:.2f} "
                   f"(High ${high:.2f} / Low ${low:.2f}) | "
                   f"Buy {buy_pct}% Hold {hold_pct}% "
                   f"Sell {sell_pct}% | {total} analysts | Rating: {rating}",
                   signal_type="institutional",
                   source_feed="analyst_targets")
            written += 1

        logger.info("  [LAYER 4] Analyst Targets: %d tickers written to DB", written)

    except Exception as e:
        logger.warning("  [LAYER 4] analyst_targets.json error: %s: %s", type(e).__name__, e)


# ==========================================================================
# LAYER 5: REGIME DETECTION ENGINE
# Deterministic -- no AI. Copied exactly from V1 compute_risk_regime().
# Six factors scored: VIX + Fear/Greed + Gold/Tech + Inst + Macro + Rotation
# Output: RISK ON / RISK OFF / NEUTRAL with score, action, drivers
# ==========================================================================

def _compute_vader_avg(signals: list) -> float:
    """VADER sentiment average on list of text strings. Returns -1.0 to +1.0."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sia    = SentimentIntensityAnalyzer()
        scores = []
        for item in signals:
            text = item if isinstance(item, str) else str(item.get("raw_text","") or "")
            if len(text) > 5:
                scores.append(sia.polarity_scores(text)["compound"])
        return round(sum(scores)/len(scores), 4) if scores else 0.0
    except ImportError:
        logger.warning("  vaderSentiment not installed -- pip install vaderSentiment")
        return 0.0
    except Exception as e:
        logger.debug("VADER error: %s", e)
        return 0.0


def _compute_risk_regime(all_prices: dict, fg: dict,
                          inst_avg: float, macro_avg: float) -> dict:
    """
    Deterministic regime detection.
    No AI. No randomness. Pure signal scoring -10 to +9.

    Factor 1 -- VIX direction     : -2 to +2  (zeroed when market CLOSED)
    Factor 2 -- Fear & Greed      : -2 to +2  (always active — absolute level)
    Factor 3 -- Gold vs Tech       : -2 to +1  (zeroed when market CLOSED)
    Factor 4 -- Institutional avg  : -1 to +1  (always active — sentiment)
    Factor 5 -- Macro avg          : -1 to +1  (always active — sentiment)
    Factor 6 -- Sector rotation    : -2 to +2  (zeroed when market CLOSED)

    When market is CLOSED (weekend / after-hours), chg_pct values reflect
    the prior session's close-to-close move — stale history, not current
    signals. Factors 1, 3, 6 (all chg_pct-based) are zeroed to prevent a
    Friday selloff from haunting the regime score over the entire weekend.
    Sentiment-based factors (2, 4, 5) remain active.
    """
    score   = 0
    factors = {}
    drivers = []
    warns   = []

    # Detect market session: if every price with a session tag says CLOSED,
    # treat chg_pct factors as unreliable (stale prior-session data).
    sessions = [v.get("session", "") for v in all_prices.values()
                if isinstance(v, dict) and v.get("session")]
    market_closed = bool(sessions) and all(s == "CLOSED" for s in sessions)

    # -- Factor 1: VIX ----------------------------------------
    vix     = all_prices.get("^VIX", {})
    vix_chg = vix.get("chg_pct", 0)
    vix_lvl = vix.get("price", 20)
    if market_closed:
        factors["VIX"] = 0
        warns.append("Market CLOSED -- VIX direction factor suspended (stale chg_pct)")
    elif vix_chg <= -5: factors["VIX"]=+2; drivers.append(f"VIX -{abs(vix_chg):.1f}% falling")
    elif vix_chg <= -2: factors["VIX"]=+1; drivers.append(f"VIX easing {vix_chg:+.1f}%")
    elif vix_chg >=  5: factors["VIX"]=-2; warns.append(f"VIX +{vix_chg:.1f}% spiking -- RISK OFF")
    elif vix_chg >=  2: factors["VIX"]=-1; warns.append(f"VIX rising {vix_chg:+.1f}%")
    else:               factors["VIX"]= 0
    score += factors["VIX"]

    # -- Factor 2: Fear & Greed (absolute level — always active) -------
    fg_s = float(fg.get("score", 50))
    if   fg_s >= 75: factors["FG"]=+2; drivers.append(f"F/G {fg_s:.0f} -- EXTREME GREED")
    elif fg_s >= 55: factors["FG"]=+1; drivers.append(f"F/G {fg_s:.0f} -- GREED")
    elif fg_s <= 25: factors["FG"]=-2; warns.append(f"F/G {fg_s:.0f} -- EXTREME FEAR")
    elif fg_s <= 44: factors["FG"]=-1; warns.append(f"F/G {fg_s:.0f} -- FEAR")
    else:            factors["FG"]= 0
    score += factors["FG"]

    # -- Factor 3: Gold vs Tech (flight to safety) ------------
    gold_chg = all_prices.get("GLD",{}).get("chg_pct", 0)
    nvda_chg = all_prices.get("NVDA",{}).get("chg_pct", 0)
    if market_closed:
        factors["SH"] = 0
    elif gold_chg>1.0 and nvda_chg<-1.0: factors["SH"]=-2; warns.append("Gold UP + Tech DOWN -- flight to safety")
    elif gold_chg>0.5:                    factors["SH"]=-1; warns.append(f"Gold bid +{gold_chg:.1f}%")
    elif gold_chg<-0.5 and nvda_chg>1.0: factors["SH"]=+1; drivers.append("Gold fading + Tech rising -- risk-on")
    else:                                  factors["SH"]= 0
    score += factors["SH"]

    # -- Factor 4: Institutional news sentiment (always active) -------
    if   inst_avg >=  0.15: factors["Inst"]=+1; drivers.append(f"Inst sentiment {inst_avg:+.3f} bullish")
    elif inst_avg <= -0.15: factors["Inst"]=-1; warns.append(f"Inst sentiment {inst_avg:+.3f} bearish")
    else:                   factors["Inst"]= 0
    score += factors["Inst"]

    # -- Factor 5: Macro news sentiment (always active) ---------------
    if   macro_avg >=  0.10: factors["Macro"]=+1; drivers.append(f"Macro {macro_avg:+.3f} positive")
    elif macro_avg <= -0.10: factors["Macro"]=-1; warns.append(f"Macro {macro_avg:+.3f} negative")
    else:                    factors["Macro"]= 0
    score += factors["Macro"]

    # -- Factor 6: Sector rotation (growth vs defensives) -----
    growth_t    = ["NVDA","AMD","TSLA","RKLB","IONQ"]
    defensive_t = ["GLD","SLV","DUK","NEM","AU"]
    def basket_avg(ts):
        vals = [all_prices.get(t,{}).get("chg_pct",0) for t in ts
                if all_prices.get(t,{}).get("price",0) > 0]
        return sum(vals)/len(vals) if vals else 0.0
    diff = basket_avg(growth_t) - basket_avg(defensive_t)
    if market_closed:
        factors["Rot"] = 0
        diff = 0.0
    elif diff >=  1.5: factors["Rot"]=+2; drivers.append("Growth >> Defensives -- RISK ON")
    elif diff >=  0.5: factors["Rot"]=+1; drivers.append("Growth mild outperformance")
    elif diff <= -1.5: factors["Rot"]=-2; warns.append("Defensives >> Growth -- RISK OFF")
    elif diff <= -0.5: factors["Rot"]=-1; warns.append("Defensives mild outperformance")
    else:              factors["Rot"]= 0
    score += factors["Rot"]

    # -- Classify regime --------------------------------------
    # DEFECT-02 FIX: regime label must be clean (no session/CB flags).
    # session_flag is stored separately. Valid values: OPEN, PRE, POST, DUP, CLOSED, UNKNOWN.
    # The old "[DUP]", "[OK]", "[HALF]", "[WARN]", "[OPEN]" prefixes were circuit-breaker
    # state decorators repurposed as display labels -- they polluted every downstream consumer.
    if   score >=  3: regime,short,session_flag,action = "RISK ON",       "RISK ON",       "OPEN",   "Favour growth/cyclicals."
    elif score >=  1: regime,short,session_flag,action = "MILD RISK ON",  "MILD RISK ON",  "OPEN",   "Cautious growth. Keep defensive ballast."
    elif score ==  0: regime,short,session_flag,action = "NEUTRAL",       "NEUTRAL",       "CLOSED", "Hold positions. Wait for signal."
    elif score >= -2: regime,short,session_flag,action = "MILD RISK OFF", "MILD RISK OFF", "CLOSED", "Reduce growth. Add defensives."
    else:             regime,short,session_flag,action = "RISK OFF",      "RISK OFF",      "CLOSED", "Favour gold/defensives/cash."

    return {
        "regime":        regime,   "regime_short":  short,
        "session_flag":  session_flag,
        "score":         score,    "action":        action,
        "drivers":       drivers,  "warnings":      warns,
        "vix_level":     vix_lvl,  "fg_score":      fg_s,
        "inst_avg":      inst_avg, "macro_avg":     macro_avg,
        "sector_diff":   round(diff, 2), "factors": factors,
        "market_closed": market_closed,
    }


def _write_regime_to_db(regime: dict, result: IngestResult):
    """Write regime result to raw_signal_archive."""
    raw_payload = {**regime, "source": "Regime_Detection",
                   "cycle_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    _write(result, "Regime_Detection", "regime_engine", raw_payload,
           f"[REGIME] {regime['regime']} | Score {regime['score']:+d}/9 | "
           f"VIX {regime['vix_level']:.1f} | F/G {regime.get('fg_score',50):.0f} | "
           f"Action: {regime['action']} | "
           f"Drivers: {'; '.join(regime['drivers'][:3])}",
           signal_type="regime", source_feed="regime_detection")


# ==========================================================================
# LAYER 6: EVENT CORRELATION ENGINE
# Deterministic -- no AI. Copied exactly from V1.
# Correlates news themes ? source layers ? basket price movements
# Outputs top 6 correlations with confidence score and direction
# ==========================================================================

def _build_event_correlation(all_prices: dict, regime: dict,
                              recent_signals: list) -> list:
    """
    Group recent signals by EVENT_THEME.
    For each theme: score layer diversity ? basket price move ? regime.
    Returns top 6 correlations sorted by confidence.
    Basket definitions and confidence formula preserved exactly from V1.
    """
    theme_map = {}

    for item in recent_signals:
        if isinstance(item, dict):
            text   = str(item.get("raw_text","") or item.get("signal_line","") or "")
            source = str(item.get("source",""))
        else:
            text   = str(item)
            source = ""

        text_lower = text.lower()
        # Warsh entity: word-boundary safe (no warship false-positives)
        _warsh_hit = _matches_warsh_entity(text)
        for theme, keywords in EVENT_THEMES.items():
            _kw_match = any(kw in text_lower for kw in keywords)
            _theme_match = _kw_match or (theme == "MACRO / FED" and _warsh_hit)
            if _theme_match:
                rec = theme_map.setdefault(theme, {
                    "items":[], "layers":set(), "impact": 0.0
                })
                # Layer classification
                if source in ("Moomoo_Intel","Analyst_Targets"):
                    layer = "MARKET INTEL"
                elif source in ("Fed_Press","Fed_Speeches","Fed_FOMC_Minutes",
                                "BLS_API","WorldBank_Macro","BOJ_Press",
                                "MAS_Press","PBOC_Policy","PBOC_LPR","PBOC_CNY",
                                "ECB_Press","BIS_PressReleases","Treasury_Press",
                                "WhiteHouse_RSS","USDA_WASDE"):
                    layer = "MACRO CATALYST"
                else:
                    layer = "VERIFIED RSS"
                rec["items"].append(text[:180])
                rec["layers"].add(layer)
                rec["impact"] = max(rec["impact"], 0.5)

    # Basket definitions -- v2.6: expanded 5 → 23 baskets
    # Watchlist size: len(WATCHLIST_83) unique tickers across 23 themes
    # WO-RD-20260607-003 v1.3 — watchlist expansion
    # All tickers receive identical pipeline treatment
    baskets = {
        "AI / SEMIS":                   ["NVDA","AMD","AVGO","MRVL","MU","TSM","AMAT","ARM","CDNS","SNPS","INTC",
                                          "AMKR","ASML","QCOM","TXN","LRCX","KLAC"],
        "MAG7 / BIG TECH":              ["NVDA","MSFT","AAPL","GOOGL","META","AMZN","TSLA","NFLX","UBER","DIS"],
        "SOFTWARE / CYBERSECURITY":     ["MSFT","CRWD","PANW","AXON","PLTR","ORCL","CRM","NOW","ADBE",
                                          "FTNT","ZS","INTU","SNOW","OKTA","S"],
        "BANKS / LIQUIDITY":            ["BAC","WFC","C","SOFI","HOOD","COIN","JPM","GS","MS","BLK",
                                          "SCHW","AXP","CB","MCO","PGR","ALL",],
        "FINTECH / CRYPTO":             ["COIN","HOOD","SOFI","V","MA","PYPL","MSTR","IBIT"],
        "BIOTECH / PHARMA":             ["LLY","MRNA","ABBV","PFE","JNJ","UNH","MRK","AMGN",
                                          "BMY","GILD","REGN","BIIB"],
        "DEFENSE / AEROSPACE PRIMES":   ["RTX","NOC","LMT","HII","LDOS","AXON","BA","LHX",
                                          "HON","TDG","HEI","KTOS"],
        "SPACE / HIGH-BETA":            ["ASTS","RKLB","LUNR","BKSY","SATS","RDW","SIDU","IRDM",
                                          "LHX","VSAT","GSAT","SPIR","PL","SPCE","AMT"],
        "GOLD / SAFE HAVEN":            ["GLD","SLV","NEM","AU","CDE","HL","AG","PAAS"],
        "COPPER / INDUSTRIAL METALS":   ["FCX","SCCO","BHP","RIO","HBM","TECK","VALE","NUE",
                                          "AA","CLF","CAT","NTR","MOS","ADM"],
        "RARE EARTH / METALS":          ["MP","USAR","ALB"],
        "NUCLEAR / POWER GRID":         ["CEG","VST","CCJ","UUUU","OKLO","SMR","BWXT"],
        "UTILITIES / POWER":            ["VST","DUK","WMB","KMI","GEV","NEE","ETN","EMR","AWK"],
        "CLEAN ENERGY / SOLAR":         ["ENPH","FSLR","FCEL","BE","PLUG","SEDG","ARRY","RUN","BEP"],
        "OIL / GAS":                    ["XOM","OXY","EOG","FANG","WMB","KMI","CVX","COP","DVN",
                                          "LNG","VLO","PSX","MPC","EPD","ENB"],
        "MACRO / FED":                  ["WFC","BAC","DUK","C","TLT","GLD","XOM","WMB","ALB",
                                          "KO","PG","WMT","COST","PEP","MCD","HD","LOW","NKE",
                                          "SBUX","TGT","CL","UPS","FDX","UNP","CSX","DAL","DE",
                                          "VZ","T","O"],
        "GEOPOLITICAL":                 ["GLD","XOM","LMT","RTX","SLV","NEM"],
        "TRUMP / TRADE":                ["AAPL","TSM","XOM","ALB","MP","USAR"],
        "QUANTUM":                      ["IONQ","QBTS","QUBT","RGTI","QTUM"],
        "ENERGY / URANIUM":             ["CCJ","CEG","UUUU"],
        "IPO / MOMENTUM":               ["HOOD","COIN","SOFI","PLTR","RKLB"],
        "EARNINGS CATALYST":            ["NVDA","AMD","AVGO","DELL","ORCL","BAC","WFC","JPM","GS",
                                          "MS","LLY","JNJ","V","MA","MSFT","GOOGL","META","AMZN","TSLA"],
        "CONSUMER TECH / APPLE":        ["AAPL","AMZN","META","GOOGL"],
    }

    # ── THEME_EVIDENCE_MAP (WO-Final-PhD, Defect 1) ──────────────────────────
    # Pre-built reverse map: ticker_upper → set of theme names that own it.
    # Used for cross-theme contamination check after why_signal selection.
    # A why_signal mentioning ONLY foreign-basket tickers (with none from THIS
    # theme's basket) is contaminated and must be demoted to price-action-only.
    _TICKER_TO_THEMES: dict = {}
    for _th, _blist in baskets.items():
        for _tk in _blist:
            _TICKER_TO_THEMES.setdefault(_tk.upper(), set()).add(_th)

    def avg_chg(ts):
        vals = [all_prices.get(t,{}).get("chg_pct",0) for t in ts
                if all_prices.get(t,{}).get("price",0) > 0]
        return round(sum(vals)/len(vals), 2) if vals else 0.0

    def theme_catalyst_quality(theme_name: str, signals: list) -> str:
        """Assess catalyst verification quality for a theme's basket tickers.

        WO-Final-PhD Defect 5: ECE must not treat unexplained top-mover rallies
        as fully causal.  Checks whether large-move basket tickers have any
        causal signal in the recent signals pool.

        Returns one of:
          DIRECT_CAUSAL_SUPPORT     → matched causal signals found for top movers
          PARTIAL_CAUSAL_SUPPORT    → some movers have causal signals, some don't
          PRICE_ACTION_ONLY         → no causal signals, only price action
          INSUFFICIENT_DATA         → basket too small or no significant move to assess
        """
        basket_tickers_up = {t.upper() for t in baskets.get(theme_name, [])}
        if not basket_tickers_up:
            return "INSUFFICIENT_DATA"

        # Find basket tickers with significant moves (>2% intraday)
        big_movers = []
        for tk in basket_tickers_up:
            price_data = all_prices.get(tk) or all_prices.get(tk.lower()) or {}
            chg = abs(float(price_data.get("chg_pct") or 0))
            if chg >= 2.0:
                big_movers.append(tk)

        if not big_movers:
            return "INSUFFICIENT_DATA"

        import re as _re_cq
        # Check each big mover for causal signal coverage in recent_signals
        # signals may be dicts (raw DB rows) OR plain strings (from rec["items"])
        matched = 0
        unmatched = 0
        for mover in big_movers:
            has_causal = False
            for sig in signals:
                if isinstance(sig, dict):
                    text = str(sig.get("raw_text") or sig.get("signal_line") or "")
                else:
                    text = str(sig)
                if not _re_cq.search(r'(?<!\w)' + _re_cq.escape(mover) + r'(?!\w)', text, _re_cq.IGNORECASE):
                    continue
                # Signal mentions this ticker — is it causal?
                tl = text.lower()
                _ANALYST_TAGS = ("[analyst consensus]", "[analyst ratings]", "[wall st. analysts]", "[morningstar]")
                is_analyst = any(tag in tl for tag in _ANALYST_TAGS)
                if not is_analyst:
                    has_causal = True
                    break
            if has_causal:
                matched += 1
            else:
                unmatched += 1

        if matched > 0 and unmatched == 0:
            return "DIRECT_CAUSAL_SUPPORT"
        elif matched > unmatched:
            return "PARTIAL_CAUSAL_SUPPORT"
        elif matched > 0:
            return "PARTIAL_CAUSAL_SUPPORT"
        else:
            return "PRICE_ACTION_ONLY"

    correlations = []
    for theme, rec in theme_map.items():
        layers       = len(rec["layers"])
        basket_move  = avg_chg(baskets.get(theme, []))
        regime_bonus = 0.18 if "OFF" in regime.get("regime_short","") else 0.0
        # V1 confidence formula -- preserved exactly
        confidence   = min(0.95,
            0.35 + 0.15*layers + rec["impact"]*0.30
            + min(abs(basket_move),5)*0.03 + regime_bonus)

        # DEFECT-06 FIX: Evidence tier tagging + confidence cap (Phase 1).
        # Every ECE why entry must be tagged with a tier at computation time.
        # The highest-quality tier governs the cap when multiple tiers are present.
        # Tier classification is deterministic pattern matching on items text.
        #
        # Tier 0 : Government / regulatory / central bank / legal action  cap: 95%
        # Tier 1 : Earnings / CEO speech / product launch / macro release cap: 90%
        # Tier 2 : Confirmed news cluster from trusted sources            cap: 80%
        # Tier 3 : Price-volume / capital flow anomaly                    cap: 70%
        # Tier 4 : Analyst consensus / structural valuation context       cap: 55%
        #
        # Source: WO-RD-20260603-001 v1.1, DEFECT-06, Phase 1 scope.
        _TIER_CAPS  = {0: 0.95, 1: 0.90, 2: 0.80, 3: 0.70, 4: 0.55}
        _TIER_LABELS = {0: "T0:GOV/REG", 1: "T1:EARNINGS/MACRO", 2: "T2:NEWS",
                        3: "T3:PRICE/FLOW", 4: "T4:ANALYST_CONSENSUS"}

        def _classify_tier(items_list, layers_set, why_signal=""):
            """Return best (lowest) tier number found across all items.

            P2-05 FIX v2 (WO-RD-20260604-002):
            Analyst consensus tags must be checked against the SELECTED why_signal,
            not items_list[0]. The why_signal is the line chosen for display —
            it reflects the actual evidence quality of the correlation.

            If why_signal starts with an analyst consensus tag, that is definitive.
            No other signal line in the batch can override it upward to Tier 1/2.
            Analyst consensus is always Tier 4 — structural context,
            not a same-day catalyst.

            Check order:
              1. why_signal analyst gate (hard Tier 4 lock if why_signal matches)
              2. Tier 0 government/regulatory (highest authority)
              3. Tier 1 earnings/CEO/macro releases
              4. Tier 2 news cluster
              5. Tier 3 price/flow anomaly
              6. Tier 4 default
            """
            _ANALYST_TAGS = (
                "[analyst consensus]",
                "[analyst ratings]",
                "[wall st. analysts]",
                "[morningstar]",
            )

            best = 4  # default: analyst consensus

            # -- GATE: check the SELECTED why_signal for analyst tags --
            # why_signal is the line chosen for display — it is the authoritative
            # evidence descriptor for this correlation.
            # If it is an analyst consensus line, lock to Tier 4 immediately.
            # items_list[0] is NOT reliable — it may be a news line that happens
            # to be first in the batch even when the why is analyst consensus.
            _why_lower = why_signal.lower()
            if any(_why_lower.startswith(tag) for tag in _ANALYST_TAGS):
                return 4  # hard lock — why_signal is analyst consensus

            for txt in items_list:
                tl = txt.lower()
                # Tier 0: authoritative government/central bank/regulatory sources
                if any(src in layers_set for src in ("MACRO CATALYST",)) and any(
                    kw in tl for kw in ("fomc","fed rate decision","rate decision",
                                        "ecb decision","boj","mas statement",
                                        "sec enforcement","doj","executive order",
                                        "presidential","regulatory action","sanction")):
                    best = min(best, 0)
                # Tier 1: earnings, CEO speeches, product launches, macro data releases
                elif any(kw in tl for kw in ("earnings","eps beat","eps miss","revenue beat",
                                              "guidance","q1 results","q2 results","q3 results",
                                              "q4 results","quarterly results","ceo","keynote",
                                              "product launch","cpi release","nonfarm payroll",
                                              "gdp growth","unemployment rate","fed chair",
                                              "powell","investor day")):
                    best = min(best, 1)
                # Tier 2: confirmed news cluster from trusted journalism sources
                elif "VERIFIED RSS" in layers_set or "MACRO CATALYST" in layers_set:
                    best = min(best, 2)
                # Tier 3: price/volume anomaly, capital flow
                elif any(kw in tl for kw in ("unusual volume","unusual options","capital flow",
                                              "institutional buying","institutional selling",
                                              "short interest","gamma","options flow",
                                              "insider","13f","price target raised",
                                              "price target cut")):
                    best = min(best, 3)
                # Tier 4: analyst consensus (structural/valuation, not same-day catalyst)
                elif any(kw in tl for kw in ("[analyst consensus]","[analyst ratings]",
                                              "[wall st. analysts]","analyst consensus",
                                              "buy rating","hold rating","sell rating",
                                              "overweight","underweight","neutral rating",
                                              "consensus target","price target")):
                    best = min(best, 4)
            return best

        # why_signal is computed below — initialise here so it is always defined
        # even if the item selection block is skipped or raises an exception.
        # _classify_tier is called AFTER why_signal is assigned (moved below).
        why_signal = ""

        # ── ECE Sector Direction v2 — WO-ECE-20260612-001 ────────────────────
        # CRITICAL FIX: Sector direction is computed ONLY from live basket move +
        # broad-market tape confirmation.  Global regime state is stored separately
        # as global_regime_context and must NEVER overwrite sector basket behavior.
        #
        # Previous bug: `"OFF" in regime_short` caused every sector with a moderate
        # positive basket to be classified RISK-OFF during a MILD RISK OFF regime.
        # e.g. NUCLEAR +0.51%, URANIUM +0.46%, UTILITIES +0.44% → wrongly RISK-OFF.
        #
        # Governing thresholds:
        #   RISK_ON           : basket >= +0.50%
        #   SELECTIVE_RISK_ON : basket in [ +0.10%, +0.50% )
        #   NEUTRAL           : basket in ( -0.10%, +0.10% )
        #   SELECTIVE_RISK_OFF: basket in ( -0.50%, -0.10% ]
        #   RISK_OFF          : basket <= -0.50%
        _ECE_RON_STRONG  =  0.50
        _ECE_RON_SOFT    =  0.10
        _ECE_ROFF_STRONG = -0.50
        _ECE_ROFF_SOFT   = -0.10

        if   basket_move >= _ECE_RON_STRONG:  sector_direction = "RISK_ON"
        elif basket_move >= _ECE_RON_SOFT:    sector_direction = "SELECTIVE_RISK_ON"
        elif basket_move <= _ECE_ROFF_STRONG: sector_direction = "RISK_OFF"
        elif basket_move <= _ECE_ROFF_SOFT:   sector_direction = "SELECTIVE_RISK_OFF"
        else:                                  sector_direction = "NEUTRAL"

        # Broad-market tape confirmation overlay:
        # If SPY + (QQQ or IWM) are both positive AND VXX is not rising,
        # a positive-basket sector cannot be RISK_OFF.
        _spy_chg = float(all_prices.get("SPY", {}).get("chg_pct", 0) or 0)
        _qqq_chg = float(all_prices.get("QQQ", {}).get("chg_pct", 0) or 0)
        _iwm_chg = float(all_prices.get("IWM", {}).get("chg_pct", 0) or 0)
        _vxx_chg = float(all_prices.get("VXX", {}).get("chg_pct", 0) or 0)
        _broad_rally = (
            _spy_chg > 0
            and (_qqq_chg > 0 or _iwm_chg > 0)
            and _vxx_chg <= 0
        )
        if _broad_rally and basket_move > 0 and sector_direction in ("RISK_OFF", "SELECTIVE_RISK_OFF"):
            sector_direction = "SELECTIVE_RISK_ON"

        # Review flags — logic-conflict detection surfaced in all report outputs
        _review_flags: list = []
        if basket_move > 0 and sector_direction in ("RISK_OFF", "SELECTIVE_RISK_OFF"):
            _review_flags.append("POSITIVE_BASKET_RISK_OFF_CONFLICT")
        if basket_move < 0 and sector_direction in ("RISK_ON", "SELECTIVE_RISK_ON"):
            _review_flags.append("NEGATIVE_BASKET_RISK_ON_CONFLICT")

        # Global regime context — stored separately, never merged into sector_direction
        _global_regime_context = str(regime.get("regime_short", "UNKNOWN"))

        # Preserve `direction` field name for backward-compat with renderers/DB
        direction = sector_direction
        basket_tickers = [t.lower() for t in baskets.get(theme, [])]
        theme_kws      = [kw.lower() for kw in EVENT_THEMES.get(theme, [])]

        # BUG-ECE-001/002 FIX: ticker-validated why_signal selection
        # Problem: substring keyword matching produces false positives.
        #   "golden cross" (AVGO technical signal) matches "gold" keyword → GOLD/SAFE HAVEN
        #   "Bollinger Band / fallen below" (INTC signal) matches "be" keyword → CLEAN ENERGY
        # Fix: require that relevant_items come from signals whose text contains a
        # BASKET TICKER for this theme (exact word-boundary match).
        # Only fall back to keyword-matched items if no basket-ticker hit exists.
        # Final fallback: any item — but NEVER an item whose text starts with a
        # [TECHNICAL] or [FINANCIAL] tag for a ticker that is NOT in this basket.
        import re as _re
        _bt_pattern = _re.compile(
            r'(?<!\w)(' + '|'.join(_re.escape(t) for t in baskets.get(theme, [])) + r')(?!\w)',
            _re.IGNORECASE
        ) if baskets.get(theme) else None

        def _item_has_basket_ticker(s):
            return bool(_bt_pattern and _bt_pattern.search(s))

        def _item_is_wrong_ticker(s):
            """Return True if signal is a Moomoo tag for a ticker NOT in this basket."""
            m = _re.match(r'^\[(?:TECHNICAL|FINANCIAL|ANALYST RATINGS|WALL ST\. ANALYSTS|MORNINGSTAR)\]\s+([A-Z]{1,5}):', s)
            if not m:
                return False
            ticker_in_signal = m.group(1).upper()
            return ticker_in_signal not in {t.upper() for t in baskets.get(theme, [])}

        # P2-05 FIX (WO-RD-20260604-002):
        # CAUSAL PRIORITY GATE — analyst consensus is CONTEXT, not causal catalyst.
        # ChatGPT Research Department finding: 20/23 themes used analyst consensus
        # as why_signal, causing CAUSAL EXPLANATION INCOMPLETE every cycle.
        #
        # New priority order (highest to lowest):
        #   P1-CAUSAL:  basket-ticker items from causal sources (news/RSS/geo/earnings/CEO)
        #   P2-CAUSAL:  keyword-matched items from causal sources
        #   P3-CONTEXT: basket-ticker items from analyst/financial sources (last resort)
        #   P4-SAFE:    any non-wrong-ticker item
        #   P5-FALLBACK: first item (preserves old behaviour as last resort)
        #
        # Causal source = any signal NOT tagged as pure analyst consensus/valuation context.
        # Analyst consensus = [ANALYST CONSENSUS], [WALL ST. ANALYSTS], [ANALYST RATINGS],
        #                     [MORNINGSTAR], [FINANCIAL] tags.

        _CONTEXT_TAGS = (
            "[analyst consensus]",
            "[wall st. analysts]",
            "[analyst ratings]",
            "[morningstar]",
            "[financial]",
        )

        def _is_context_signal(s):
            """Return True if signal is analyst consensus / valuation context, not causal."""
            sl = s.lower().lstrip()
            return any(sl.startswith(tag) for tag in _CONTEXT_TAGS)

        def _is_causal_signal(s):
            """Return True if signal is a causal catalyst — news, earnings, geo, CEO, etc."""
            return not _is_context_signal(s)

        # All basket-ticker items
        basket_items = [s for s in rec["items"] if _item_has_basket_ticker(s)]

        # P1: basket-ticker items that are CAUSAL (not analyst consensus)
        basket_causal   = [s for s in basket_items if _is_causal_signal(s)]
        # P2: keyword-matched items that are CAUSAL and not wrong-ticker Moomoo tags
        keyword_causal  = [s for s in rec["items"]
                           if not _item_has_basket_ticker(s)
                           and any(kw in s.lower() for kw in theme_kws[:5])
                           and not _item_is_wrong_ticker(s)
                           and _is_causal_signal(s)]
        # P3: any causal item that is not a wrong-ticker tag (no basket-ticker required)
        safe_causal     = [s for s in rec["items"]
                           if not _item_is_wrong_ticker(s)
                           and _is_causal_signal(s)]
        # P4: basket-ticker analyst/context items (last resort — better than nothing)
        basket_context  = [s for s in basket_items if _is_context_signal(s)]
        # P5: any non-wrong-ticker item (full fallback)
        safe_items      = [s for s in rec["items"] if not _item_is_wrong_ticker(s)]

        # Select why_signal using causal priority
        # If any causal signal exists for this theme → use it.
        # Only fall back to analyst consensus if absolutely no causal signal found.
        relevant_items = (
            basket_causal   or   # P1: best case — causal + basket ticker
            keyword_causal  or   # P2: causal + keyword match
            safe_causal     or   # P3: any causal signal
            basket_context  or   # P4: analyst context for basket ticker (fallback)
            safe_items           # P5: last resort
        )

        why_signal = (relevant_items[0] if relevant_items else rec["items"][0] if rec["items"] else "")

        # If no causal signal found at all, flag it explicitly
        if _is_context_signal(why_signal) or not why_signal:
            # Mark in the signal itself that causal catalyst was not found
            # The tier classifier will correctly assign T4, capping confidence at 55%
            pass  # why_signal stays as analyst context — tier gate handles the rest

        # DEFECT-01 FIX: Analyst percentage assertion gate.
        # Moomoo_Intel analyst lines sometimes carry mathematically impossible
        # percentages (e.g. Buy 657%, Hold -557%) caused by recalculation inside
        # moomoo_intelligence.py rather than reading the raw buy/hold/sell counts.
        # Before writing any analyst percentage into the why text, we must validate.
        # Pattern: detect lines that look like analyst rating lines.
        _analyst_why_pattern = _re.compile(
            r'(?:buy|hold|sell)\s+(-?\d{1,4})%', _re.IGNORECASE
        )
        _analyst_tag_pattern = _re.compile(
            r'^\[(?:ANALYST CONSENSUS|ANALYST RATINGS|WALL ST\. ANALYSTS)\]',
            _re.IGNORECASE
        )
        analyst_rating_integrity = "OK"
        if _analyst_tag_pattern.search(why_signal) or _analyst_why_pattern.search(why_signal):
            pct_hits = _analyst_why_pattern.findall(why_signal)
            pct_vals = [int(p) for p in pct_hits]
            # Assertion: every percentage must be 0-100
            if pct_vals and any(p < 0 or p > 100 for p in pct_vals):
                analyst_rating_integrity = "FAILED"
                why_signal = "Analyst rating data invalid -- suppressed (percentage out of 0-100 range)"
                logger.warning(
                    "  [ECE] DEFECT-01: analyst pct assertion FAILED theme=%s "
                    "raw=%s -- why suppressed", theme, pct_vals
                )
            # Also assert sum is within 1% of 100 if we have 3 values
            elif len(pct_vals) >= 3:
                pct_sum = sum(pct_vals[:3])
                if abs(pct_sum - 100) > 1:
                    analyst_rating_integrity = "FAILED"
                    why_signal = "Analyst rating data invalid -- suppressed (percentages do not sum to 100)"
                    logger.warning(
                        "  [ECE] DEFECT-01: analyst %% sum assertion FAILED for theme %s -- "
                        "sum=%d (expected 100) -- why suppressed", theme, pct_sum
                    )

        # ── CROSS-THEME TICKER CONTAMINATION CHECK (WO-Final-PhD, Defect 1) ──────
        # After all selection logic runs, validate that why_signal does NOT use
        # evidence belonging exclusively to a FOREIGN theme's basket.
        # Example contaminations blocked:
        #   GOLD/SAFE HAVEN using MRVL (AI/SEMIS basket) news
        #   DEFENSE/AEROSPACE using BAC (BANKS/LIQUIDITY basket) options-flow
        #   GEOPOLITICAL using MRVL valuation evidence
        #
        # Algorithm:
        #   1. Find all known basket tickers mentioned in why_signal (word-boundary)
        #   2. Partition into this-theme tickers vs foreign-theme tickers
        #   3. If only foreign tickers found → evidence is contaminated → demote
        #
        # IMPORTANT: check fires on the SELECTED why_signal regardless of whether
        # basket_items is empty or not. basket_causal may be empty while basket_items
        # has analyst-only context signals — in that case safe_causal selects a foreign
        # ticker signal as why_signal, which must still be flagged as contaminated.
        if why_signal:
            _this_bkt_upper = {t.upper() for t in baskets.get(theme, [])}
            # Scan for ANY known basket ticker mentioned in why_signal
            _why_upper = why_signal.upper()
            _found_this = set()
            _found_foreign = set()
            for _tk_up, _tk_themes in _TICKER_TO_THEMES.items():
                # Word-boundary match to avoid "C" matching "CLOUD" etc.
                if len(_tk_up) < 2:
                    continue  # skip single-char tickers in text scan
                if _re.search(r'(?<!\w)' + _re.escape(_tk_up) + r'(?!\w)', _why_upper):
                    if theme in _tk_themes:
                        _found_this.add(_tk_up)
                    else:
                        _found_foreign.add(_tk_up)
            if _found_foreign and not _found_this:
                # why_signal is entirely about foreign-basket tickers — contaminated
                logger.info(
                    "  [ECE] CROSS_THEME_CONTAMINATION: theme=%s foreign_tickers=%s why=%s",
                    theme, sorted(_found_foreign), why_signal[:80]
                )
                if "SECTOR_EVIDENCE_MISMATCH" not in _review_flags:
                    _review_flags.append("SECTOR_EVIDENCE_MISMATCH")
                why_signal = (
                    "No direct theme-specific catalyst found; "
                    "direction based on basket price action only."
                )

        # Classify evidence tier using the now-computed why_signal
        # why_signal is guaranteed defined (initialised as "" above)
        evidence_tier       = _classify_tier(rec["items"], rec["layers"], why_signal)
        evidence_tier_cap   = _TIER_CAPS[evidence_tier]
        evidence_tier_label = _TIER_LABELS[evidence_tier]

        # Apply cap: confidence cannot exceed the tier cap
        if confidence > evidence_tier_cap:
            confidence = evidence_tier_cap

        # Evidence-sector mismatch: if no basket-ticker evidence found, flag it
        if not basket_items and why_signal and not _item_has_basket_ticker(why_signal):
            _review_flags.append("SECTOR_EVIDENCE_MISMATCH")
        elif not basket_causal and basket_context and why_signal:
            _review_flags.append("GENERIC_EVIDENCE_REVIEW")

        if "SECTOR_EVIDENCE_MISMATCH" in _review_flags:
            why_signal = (
                "No direct theme-specific catalyst found; "
                "direction based on basket price action only."
            )

        # Analyst-only causal gap: if the selected why_signal is analyst consensus, not causal
        if _is_context_signal(why_signal) and why_signal:
            _review_flags.append("ANALYST_ONLY_CAUSAL_GAP")

        # No direct catalyst: if no causal basket signal found at all
        if not basket_causal and not keyword_causal:
            _review_flags.append("NO_DIRECT_CATALYST")
            # Replace misleading why with explicit absence statement
            if not why_signal or _is_context_signal(why_signal):
                why_signal = "No direct theme-specific catalyst found; direction based on basket price action only."

        # ── Review-flag confidence caps (WO-ECE-20260613-001, Problem E fix) ────────
        # Applied AFTER tier cap. These are additional caps based on evidence quality.
        # SECTOR_EVIDENCE_MISMATCH : evidence is from the wrong sector — max 50%
        # GENERIC_EVIDENCE_REVIEW  : evidence is analyst context, not causal — max 65%
        # ANALYST_ONLY_CAUSAL_GAP  : why_signal is analyst consensus only — max 55%
        # NO_DIRECT_CATALYST       : no basket-validated catalyst — max 60%
        _FLAG_CAPS = {
            "SECTOR_EVIDENCE_MISMATCH": 0.50,
            "GENERIC_EVIDENCE_REVIEW":  0.65,
            "ANALYST_ONLY_CAUSAL_GAP":  0.55,
            "NO_DIRECT_CATALYST":       0.60,
        }
        _conf_before_flag_cap = confidence
        for _flag, _flag_cap in _FLAG_CAPS.items():
            if _flag in _review_flags and confidence > _flag_cap:
                confidence = _flag_cap
        if confidence < _conf_before_flag_cap and "CONFIDENCE_CAPPED_BY_EVIDENCE" not in _review_flags:
            _review_flags.append("CONFIDENCE_CAPPED_BY_EVIDENCE")

        # ── THEME CATALYST QUALITY — Defect 5 (WO-Final-PhD) ────────────────────
        # Assess whether large basket-ticker moves have causal explanation in signals.
        # Unexplained top-mover rallies must cap confidence — not treated as fully causal.
        # PRICE_ACTION_ONLY → confidence capped at 60%
        # PARTIAL_CAUSAL_SUPPORT → confidence capped at 70%
        # DIRECT_CAUSAL_SUPPORT / INSUFFICIENT_DATA → no additional cap
        _tcq = theme_catalyst_quality(theme, rec["items"])
        if _tcq == "PRICE_ACTION_ONLY":
            if confidence > 0.60:
                confidence = 0.60
                if "PRICE_ACTION_ONLY_CAP" not in _review_flags:
                    _review_flags.append("PRICE_ACTION_ONLY_CAP")
        elif _tcq == "PARTIAL_CAUSAL_SUPPORT":
            if confidence > 0.70:
                confidence = 0.70
                if "PARTIAL_CAUSAL_CAP" not in _review_flags:
                    _review_flags.append("PARTIAL_CAUSAL_CAP")

        # Scale sanity check: basket_move in percentage points, should be < ±50 for single day
        if abs(basket_move) > 50 and "PERCENT_SCALE_REVIEW" not in _review_flags:
            _review_flags.append("PERCENT_SCALE_REVIEW")
            logger.warning(
                "  [ECE] PERCENT_SCALE_REVIEW: theme=%s basket_move=%s — appears over-scaled",
                theme, basket_move
            )

        # Catalyst polarity — classify event type from theme + basket move + evidence text
        _why_lo = why_signal.lower()
        _th_up  = theme.upper()
        if any(kw in _why_lo for kw in ["close to deal","ceasefire","calls off strike",
                                          "deescalat","de-escalat","normalization","reopen",
                                          "markets rally","oil dip","oil fell","oil lower",
                                          "strait","peace deal"]):
            _catalyst_polarity = "GEOPOLITICAL_DEESCALATION"
        elif any(kw in _why_lo for kw in ["rate cut","dovish","fed cut","easing"]):
            _catalyst_polarity = "FED_DOVISH"
        elif any(kw in _why_lo for kw in ["rate hike","hawkish","fed hike","tightening"]):
            _catalyst_polarity = "FED_HAWKISH"
        elif any(kw in _why_lo for kw in ["cpi","inflation spike","oil surge"]) and basket_move < 0:
            _catalyst_polarity = "INFLATION_SHOCK"
        elif any(kw in _why_lo for kw in ["oil falls","oil lower","disinflation"]):
            _catalyst_polarity = "OIL_INFLATION_RELIEF"
        elif any(kw in _why_lo for kw in ["earnings","eps beat","revenue beat"]):
            _catalyst_polarity = "EARNINGS_STRENGTH" if basket_move > 0 else "EARNINGS_WEAKNESS"
        elif any(kw in _why_lo for kw in ["eps miss","revenue miss","guidance cut"]):
            _catalyst_polarity = "EARNINGS_WEAKNESS"
        elif any(x in _th_up for x in ("GOLD","SAFE HAVEN","DEFENSE","SPACE")) and basket_move > 0:
            _catalyst_polarity = "DEFENSIVE_BID"
        elif any(x in _th_up for x in ("IPO","MOMENTUM","CRYPTO","QUANTUM","FINTECH")) and basket_move > 0.10:
            _catalyst_polarity = "SPECULATIVE_BETA"
        elif basket_move >= 0.50:
            _catalyst_polarity = "RISK_ON_RALLY"
        elif basket_move <= -0.50:
            _catalyst_polarity = "RISK_OFF_SELLOFF"
        else:
            _catalyst_polarity = "MIXED_SIGNALS"

        correlations.append({
            "theme":                    theme,
            "layers":                   sorted(rec["layers"]),
            "source_count":             len(rec["items"]),
            "basket_move":              basket_move,
            "confidence":               round(confidence*100, 0),
            "evidence_tier":            evidence_tier,
            "evidence_tier_label":      evidence_tier_label,
            "direction":                direction,
            "sector_direction":         sector_direction,
            "global_regime_context":    _global_regime_context,
            "catalyst_polarity":        _catalyst_polarity,
            "review_flags":             _review_flags,
            "broad_rally_confirmed":    _broad_rally,
            "governing_logic_version":  "ECE_v2",
            "why":                      why_signal[:180],
            "analyst_rating_integrity": analyst_rating_integrity,
            "theme_catalyst_quality":   _tcq,
        })

    correlations.sort(key=lambda x: (-x["confidence"], -x["source_count"]))
    return correlations  # v2.6u: return ALL 23 themes — no cap. Top 10 was fatal intelligence gap.


def _write_event_correlation_to_db(correlations: list, result: IngestResult):
    """Write event correlation results to raw_signal_archive."""
    if not correlations:
        return
    raw_payload = {
        "source":       "Event_Correlation",
        "correlations": correlations,
        "count":        len(correlations),
        "cycle_ts":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    summary = " | ".join(
        f"{c['theme']} {c['confidence']:.0f}% {c['direction']}"
        for c in correlations[:4]
    )
    _write(result, "Event_Correlation", "event_correlation_engine",
           raw_payload,
           f"[EVENT CORRELATION] {summary}",
           signal_type="correlation", source_feed="event_correlation")


# ==========================================================================
# LAYER 7: PER-TICKER SENTIMENT (VADER)
# Runs VADER on Yahoo Finance RSS headlines for portfolio + watchlist tickers
# One DB row per ticker with score, label, headline sample
# ==========================================================================

def _fetch_ticker_sentiment(tickers: list, result: IngestResult) -> dict:
    """
    Per-ticker VADER sentiment from Yahoo Finance RSS headlines.
    Returns {ticker: {score, label, headlines}}.
    Writes to raw_signal_archive only when headlines found.
    """
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
    except ImportError:
        logger.warning("  [LAYER 7] vaderSentiment not installed -- pip install vaderSentiment")
        return {}

    sentiment = {}
    for ticker in tickers:
        headlines = []
        scores    = []
        try:
            rss_url = (f"https://feeds.finance.yahoo.com/rss/2.0/headline"
                       f"?s={ticker}&region=US&lang=en-US")
            r = _safe_fetch(rss_url, "Ticker_Sentiment", timeout=6)
            if r and r.status_code == 200:
                feed = feedparser.parse(r.content)
                for entry in feed.entries[:6]:
                    title = (entry.get("title") or "").strip()
                    if title:
                        headlines.append(title)
                        scores.append(sia.polarity_scores(title)["compound"])
        except Exception:
            pass

        avg_score = round(sum(scores)/len(scores), 4) if scores else 0.0
        if   avg_score >=  0.15: label = "BULLISH"
        elif avg_score <= -0.15: label = "BEARISH"
        else:                    label = "NEUTRAL"

        sentiment[ticker] = {"score": avg_score, "label": label,
                             "headlines": headlines[:3]}

        if headlines:
            _write(result, "Ticker_Sentiment", "vader_sentiment",
                   {"ticker": ticker, "score": avg_score, "label": label,
                    "headlines": headlines,
                    "cycle_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                   f"[SENTIMENT] {ticker}: {label} ({avg_score:+.3f}) -- "
                   f"{headlines[0][:80]}",
                   signal_type="sentiment",
                   source_feed="ticker_sentiment")
        time.sleep(0.1)

    return sentiment


# ==========================================================================
# ingest_all_v2() -- COMPLETE V2.5 CYCLE
# Entry point that runs ALL 8 layers in sequence.
# Call this instead of ingest_all() for full institutional intelligence.
# ==========================================================================

def ingest_all_v2() -> dict:
    """
    Full V2.5 ingest cycle -- 47 external sources + 7 cognition layers.
    Every layer writes to MySQL raw_signal_archive.
    All departments query from the same database.
    Returns result dict with full per-layer summary.
    """
    result = IngestResult()

    logger.info("-"*62)
    logger.info("MID INGEST START  [v2.6]  %s", result.cycle_timestamp)
    logger.info("  L0: %d sources | L1: Prices (%d tickers) | L2: Portfolio | L6: %d-theme ECE (all %d returned)", len(SOURCE_REGISTRY), len(WATCHLIST_83), len(EVENT_THEMES), len(EVENT_THEMES))
    logger.info("  L3: Moomoo Intel | L4: Analyst Targets")
    logger.info("  L5: Regime | L6: Event Correlation | L7: Sentiment")
    logger.info("-"*62)

    # -- PREFLIGHT --------------------------------------------------
    try:    run_preflight(SOURCE_REGISTRY)
    except Exception as e: logger.error("Preflight: %s", e)

    # -- OPEN CYCLE CONNECTION --------------------------------------
    try:
        get_cycle_conn()
        logger.info("  [OK]  Cycle DB connection open")
    except Exception as e:
        logger.error("  [FAIL]  Cycle connection failed: %s -- abort", e)
        return result.to_dict()

    # -- LAYER 0: 47 EXTERNAL SOURCES ------------------------------
    logger.info("  [LAYER 0] External: RSS + APIs + central banks...")
    try:    _fetch_rss_group(result)
    except Exception as e: logger.error("L0 RSS: %s", e)
    try:    _fetch_api_group(result)
    except Exception as e: logger.error("L0 API: %s", e)

    # -- LAYER 1: LIVE PRICES ---------------------------------------
    logger.info("  [LAYER 1] Live prices (%d tickers + VIX)...", len(set(list(PORTFOLIO_FALLBACK.keys()) + WATCHLIST_83)))
    all_prices = {}
    try:
        all_tickers = ["^VIX"] + list(set(list(PORTFOLIO_FALLBACK.keys()) + WATCHLIST_78))
        all_prices  = _fetch_moomoo_prices(all_tickers)
        _write_prices_to_db(all_prices, result)
    except Exception as e:
        logger.error("L1 prices: %s: %s", type(e).__name__, e)

    # -- LAYER 2: PORTFOLIO SNAPSHOT --------------------------------
    logger.info("  [LAYER 2] Portfolio snapshot...")
    snapshot = {"total_value":0,"total_pnl":0,"total_pnl_pct":0,
                "cash":0,"total_assets":0,"positions":{},
                "stale":False,"integrity_flag":False,"source":"unavailable"}
    try:
        snapshot = _build_portfolio_snapshot(all_prices)
        _write_snapshot_to_db(snapshot, result)
    except Exception as e:
        logger.error("L2 snapshot: %s: %s", type(e).__name__, e)

    # -- LAYER 3: MOOMOO INSTITUTIONAL INTELLIGENCE -----------------
    logger.info("  [LAYER 3] Moomoo institutional intelligence...")
    mm_intel = {"summary":[]}
    try:
        mm_tickers = list(PORTFOLIO_FALLBACK.keys()) + WATCHLIST_78[:12]
        mm_intel   = _fetch_and_write_moomoo_intel(mm_tickers, result)
    except Exception as e:
        logger.error("L3 Moomoo: %s: %s", type(e).__name__, e)

    # -- LAYER 4: ANALYST TARGETS -----------------------------------
    logger.info("  [LAYER 4] Analyst targets (from analyst_targets.json)...")
    try:
        _write_analyst_targets_to_db(result)
    except Exception as e:
        logger.error("L4 analyst targets: %s: %s", type(e).__name__, e)

    # -- LAYER 5: REGIME DETECTION ----------------------------------
    logger.info("  [LAYER 5] Regime detection engine...")
    regime = {"regime":"NEUTRAL","regime_short":"NEUTRAL","session_flag":"CLOSED","score":0,
              "action":"Hold positions.","drivers":[],"warnings":[],
              "vix_level":20.0,"fg_score":50,"inst_avg":0,"macro_avg":0}
    try:
        from core.db import get_connection
        # Fear/Greed from latest DB record
        fg = {"score": 50.0, "label": "NEUTRAL"}
        try:
            conn = get_connection()
            cur  = conn.cursor(dictionary=True)
            # DB column is received_at (confirmed by probe_feargreed.py v1)
            # source=CNN_FearGreed now stores EQUITY F/G (not crypto)
            cur.execute("""SELECT raw_payload FROM raw_signal_archive
                           WHERE source='CNN_FearGreed'
                           ORDER BY received_at DESC LIMIT 1""")
            row = cur.fetchone()
            if row:
                import json as _j
                raw = row["raw_payload"]
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8")
                p   = _j.loads(raw) if isinstance(raw, str) else raw
                fg_score = float(str(p.get("score", 50)).strip() or 50)
                fg_label = p.get("label", "NEUTRAL")
                fg = {"score": fg_score, "label": fg_label}
                logger.info("  [LAYER 5] CNN Equity F/G: %.1f -- %s",
                            fg_score, fg_label)
            else:
                logger.warning("  [LAYER 5] No CNN_FearGreed in DB yet -- "
                               "will populate after first fetch")
            cur.close(); conn.close()
        except Exception as e:
            logger.warning("  [LAYER 5] F/G DB error: %s: %s", type(e).__name__, e)

        # VADER averages from recent DB signals
        macro_texts = []
        inst_texts  = []
        try:
            conn = get_connection()
            cur  = conn.cursor(dictionary=True)
            cur.execute("""SELECT raw_text FROM raw_signal_archive
                           WHERE signal_type='macro'
                           AND received_at >= NOW() - INTERVAL 24 HOUR
                           AND raw_text IS NOT NULL
                           ORDER BY received_at DESC LIMIT 40""")
            macro_texts = [r["raw_text"] for r in cur.fetchall()]
            cur.execute("""SELECT raw_text FROM raw_signal_archive
                           WHERE signal_type IN ('news','institutional')
                           AND received_at >= NOW() - INTERVAL 12 HOUR
                           AND raw_text IS NOT NULL
                           ORDER BY received_at DESC LIMIT 40""")
            inst_texts = [r["raw_text"] for r in cur.fetchall()]
            cur.close(); conn.close()
        except Exception: pass

        macro_avg = _compute_vader_avg(macro_texts)
        inst_avg  = _compute_vader_avg(inst_texts)
        regime    = _compute_risk_regime(all_prices, fg, inst_avg, macro_avg)
        _write_regime_to_db(regime, result)
        drivers_str  = " / ".join(regime["drivers"][:2])  or "--"
        warnings_str = " / ".join(regime["warnings"][:2]) or "--"
        logger.info("  [LAYER 5] Regime: %s (score %+d) | VIX %.1f | F/G %.0f",
                    regime["regime_short"], regime["score"],
                    regime["vix_level"], regime["fg_score"])
        logger.info("  [LAYER 5]   Drivers:  %s", drivers_str)
        logger.info("  [LAYER 5]   Warnings: %s", warnings_str)
        logger.info("  [LAYER 5]   Action:   %s", regime["action"])
    except Exception as e:
        logger.error("L5 regime: %s: %s", type(e).__name__, e)

    # -- LAYER 6: EVENT CORRELATION ENGINE --------------------------
    logger.info("  [LAYER 6] Event correlation engine...")
    correlations = []
    try:
        recent_signals = []
        try:
            conn = get_connection()
            cur  = conn.cursor(dictionary=True)
            cur.execute("""SELECT source, signal_type, raw_text
                           FROM raw_signal_archive
                           WHERE received_at >= NOW() - INTERVAL 24 HOUR
                           AND raw_text IS NOT NULL
                           ORDER BY received_at DESC LIMIT 300""")
            recent_signals = cur.fetchall()
            cur.close(); conn.close()
        except Exception: pass

        # Also inject mm_intel summary lines directly as signals
        # These contain analyst/options/insider keywords not in RSS
        mm_signals = [
            {"source": "Moomoo_Intel", "signal_type": "institutional",
             "raw_text": line}
            for line in mm_intel.get("summary", []) if line
        ]
        all_signals_for_ece = recent_signals + mm_signals
        correlations = _build_event_correlation(all_prices, regime, all_signals_for_ece)
        _write_event_correlation_to_db(correlations, result)
        if correlations:
            top = correlations[0]
            logger.info("  [LAYER 6] Top: %s -- %.0f%% conf -- %s -- basket %+.2f%%",
                        top["theme"], top["confidence"],
                        top["direction"], top["basket_move"])
    except Exception as e:
        logger.error("L6 correlation: %s: %s", type(e).__name__, e)

    # -- LAYER 7: PER-TICKER SENTIMENT ------------------------------
    logger.info("  [LAYER 7] Per-ticker sentiment (VADER)...")
    sentiment = {}
    try:
        news_tickers = list(PORTFOLIO_FALLBACK.keys()) + WATCHLIST_78[:NEWS_TICKERS_COUNT]
        sentiment    = _fetch_ticker_sentiment(news_tickers, result)
        logger.info("  [LAYER 7] Sentiment: %d tickers scored", len(sentiment))
    except Exception as e:
        logger.error("L7 sentiment: %s: %s", type(e).__name__, e)

    # -- CLOSE CYCLE CONNECTION -------------------------------------
    try:
        close_cycle_conn()
        logger.info("  [OK]  Cycle DB connection closed")
    except Exception as e:
        logger.error("close_cycle_conn: %s", e)

    # -- OPEN CIRCUITS ----------------------------------------------
    open_cb = [s for s, cb in _cb_registry.items()
               if cb.state == CBState.OPEN or cb.permanent_skip]
    if open_cb:
        logger.warning("  [CB]  Open circuits: %s", open_cb)

    # -- BUILD RESULT DICT ------------------------------------------
    result.log_summary()
    summary = result.to_dict()
    summary["cognition"] = {
        "prices_fetched":    len(all_prices),
        "portfolio": {
            "total_value":   snapshot.get("total_value", 0),
            "total_pnl":     snapshot.get("total_pnl", 0),
            "total_pnl_pct": snapshot.get("total_pnl_pct", 0),
            "cash":          snapshot.get("cash", 0),
            "total_assets":  snapshot.get("total_assets", 0),
            "positions":     list(snapshot.get("positions",{}).keys()),
            "data_source":   snapshot.get("source","unknown"),
            "stale":         snapshot.get("stale", False),
            "integrity_flag":snapshot.get("integrity_flag", False),
        },
        "moomoo_signals":    len(mm_intel.get("summary",[])),
        "regime":            regime.get("regime_short","NEUTRAL"),
        "regime_score":      regime.get("score", 0),
        "vix":               regime.get("vix_level", 20),
        "fear_greed":        regime.get("fg_score", 50),
        "regime_drivers":    regime.get("drivers",[]),
        "regime_warnings":   regime.get("warnings",[]),
        "top_correlation":   correlations[0]["theme"] if correlations else "none",
        "correlations":      correlations,
        "sentiment_tickers": len(sentiment),
        "sentiment_summary": {t: v["label"] for t,v in sentiment.items()},
    }
    return summary



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    print()
    print("-"*62)
    print("  BLUELOTUS V2.0 -- mid/ingest_u.py v2.6u  [WO-RD-20260604-002 Phase 1.5]")
    print(f"  Layer 0: {len(SOURCE_REGISTRY)} sources (RSS + API + central banks)")
    print(f"  Layer 1: Live prices -- {len(WATCHLIST_83)} tickers (Moomoo OpenD + VIX)")
    print("  Layer 2: Portfolio snapshot (positions, P/L, cash)")
    print("  Layer 3: Moomoo institutional intelligence")
    print("  Layer 4: Analyst targets (consensus, buy/hold/sell)")
    print("  Layer 5: Regime detection (VIX + F/G + rotation)")
    print(f"  Layer 6: Event correlation engine ({len(EVENT_THEMES)} themes x baskets → all {len(EVENT_THEMES)})")
    print("  Layer 7: Per-ticker sentiment (VADER)")
    print("-"*62)
    print()

    from core.db import test_connection
    if not test_connection():
        print("  [FAIL]  Database failed."); exit(1)
    print("  [OK]  Database healthy.")
    print()

    result = ingest_all_v2()

    print()
    print("-"*62)
    print("  CYCLE RESULT -- ALL LAYERS")
    print("-"*62)
    print(f"  Duration      : {result['duration_seconds']}s")
    print(f"  Written       : {result['total_written']}  new signals ? DB")
    print(f"  Duplicates    : {result['total_duplicates']}  already archived")
    print(f"  Errors        : {result['total_errors']}")
    print(f"  Timeouts      : {result['total_timeouts']}")
    print(f"  CB Skipped    : {result['total_skipped']}")
    print(f"  Sources OK    : {result['sources_ok']}")
    print(f"  Sources Dup   : {result['sources_dup_only']}")
    print(f"  Sources Failed: {result['sources_failed']}")
    print()

    cog = result.get("cognition", {})
    port = cog.get("portfolio", {})
    print("  COGNITION LAYER RESULTS:")
    print(f"  -- Layer 1: Prices       {cog.get('prices_fetched',0)} tickers fetched")
    print(f"  -- Layer 2: Portfolio    ${port.get('total_value',0):>10,.2f} total value")
    print(f"                           ${port.get('total_pnl',0):>+10,.2f} P/L ({port.get('total_pnl_pct',0):+.2f}%)")
    print(f"                           Source: {port.get('data_source','unknown')} | Stale: {port.get('stale',False)}")
    print(f"  -- Layer 3: Moomoo Intel {cog.get('moomoo_signals',0)} institutional signals")
    print(f"  -- Layer 4: Analyst Tgts see raw_signal_archive source=Analyst_Targets")
    print(f"  -- Layer 5: Regime       {cog.get('regime','NEUTRAL')} (score {cog.get('regime_score',0):+d})")
    print(f"                           VIX {cog.get('vix',20):.1f} | Fear/Greed {cog.get('fear_greed',50):.0f}")
    print(f"  -- Layer 6: Top Theme    {cog.get('top_correlation','none')}")
    print(f"  -- Layer 7: Sentiment    {cog.get('sentiment_tickers',0)} tickers scored")
    print()

    print("  CIRCUIT BREAKER STATUS:")
    for sid, cb in sorted(_cb_registry.items()):
        if cb.permanent_skip:              icon, st = "[PERM]","PERMANENT SKIP"
        elif cb.state == CBState.OPEN:     icon, st = "[OPEN]",f"OPEN ({cb.failures} failures)"
        elif cb.state == CBState.HALF_OPEN:icon, st = "[HALF]","HALF_OPEN (testing)"
        else:                              icon, st = "[OK]","CLOSED (healthy)"
        print(f"    {icon}  {sid:<34} {st}")
    print()

    print("  PER-SOURCE BREAKDOWN:")
    for src_name, counts in sorted(result["by_source"].items()):
        if   counts["written"]    > 0: icon = "[OK]"
        elif counts["duplicates"] > 0: icon = "[DUP]"
        elif counts["timeouts"]   > 0: icon = "[TO]"
        elif counts["skipped"]    > 0: icon = "[CB]"
        else:                          icon = "[FAIL]"
        print(f"    {icon}  {src_name:<34} "
              f"w:{counts['written']:>3}  "
              f"d:{counts['duplicates']:>3}  "
              f"e:{counts['errors']:>2}  "
              f"t:{counts['timeouts']:>2}  "
              f"skip:{counts['skipped']:>2}")
    print()
    print("-"*62)
    print("  QUERY DB FOR FULL INTELLIGENCE:")
    print("  SELECT source, signal_type, COUNT(*) AS n")
    print("  FROM raw_signal_archive")
    print("  GROUP BY source, signal_type ORDER BY n DESC;")
    print("-"*62)


# ==========================================================================

