"""
BlueLotus Digital Institution — V2.0
mid/fetch_tech_publications.py

PURPOSE
-------
    Fetches articles from 8 free tech industry RSS feeds and writes them
    to the tech_publication_signals table.

    These publications surface hardware, semiconductor, AI, and quantum news
    2-6 hours before Reuters/CNBC/MarketWatch — closing the intelligence gap
    identified in gap_report_20260602_230000 (Gap 4).

    Implements Gap 4 of INTELLIGENCE_GAP_REPORT_20260602.txt.

ACTIVE FREE RSS SOURCES (8 feeds — no subscription required):
    NvidiaNewsroom   nvidianews.nvidia.com/releases.xml             tier=2 trust=0.90
    ServeTheHome     servethehome.com/feed/                         tier=2 trust=0.83
    TheQuantumInsider thequantuminsider.com/feed/                   tier=3 trust=0.80
    ArsTechnica      feeds.arstechnica.com/arstechnica/technology-lab  tier=2 trust=0.82
    TheRegister      theregister.com/headlines.atom                 tier=3 trust=0.80
    VentureBeat      venturebeat.com/category/ai/feed/              tier=3 trust=0.76
    IEEESpectrum     spectrum.ieee.org/feeds/topic/computing.rss    tier=3 trust=0.82
    TomsHardware     tomshardware.com/feeds/all                     tier=3 trust=0.75

BLOCKED/EXCLUDED SOURCES (documented for future reference):
    HPCwire          hpcwire.com/feed/ — Cloudflare domain-level block. Hard 403.
    AIwire           aiwire.net/feed/  — Paywall/bozo feed. Not accessible.

EXCLUDED PAID SOURCES (CIO decision 2026-06-03 — no paid RSS feeds):
    DigiTimes        digitimes.com/rss/          — paid subscription required
    SemiAnalysis     semianalysis.com            — newsletter, no free RSS
    The Information  theinformation.com          — paid subscription required
    Electronic Times etnews.com                  — Korean paywall
    NOTE: When subscriptions are obtained, add to FEED_REGISTRY below
    and uncomment the corresponding entry. No other changes needed.

PIPELINE
--------
    RSS Feed → feedparser → clean + extract → VADER sentiment →
    ticker tag → SHA256 dedup → INSERT ON DUPLICATE KEY UPDATE →
    tech_publication_signals table

DESIGN
------
    - feedparser handles all RSS/Atom parsing (pure Python, no browser)
    - VADER sentiment: compound score -1.0 to +1.0
        BULLISH  > +0.05
        BEARISH  < -0.05
        NEUTRAL  between
    - Ticker extraction: simple string match against WATCHLIST_83
      in headline + summary. Case-insensitive word boundary match.
    - content_hash = SHA256(source + article_url) — dedup key
      Re-runs on the same day produce 0 new rows (all ON DUPLICATE KEY)
    - summary truncated to 2000 chars to keep DB rows manageable
    - Batch pause: 2 seconds between feeds to be respectful to servers

DEPENDENCIES
------------
    pip install feedparser vaderSentiment

USAGE
-----
    cd C:\\bluelotus2
    python mid\\fetch_tech_publications.py

    Flags:
    --dry-run     Fetch and print, skip DB write
    --source      Run a single source only: --source HPCwire
    --limit       Max articles per feed (default: 20): --limit 5

RUN SCHEDULE
------------
    Every 4 hours during market hours (SGT 21:30 - 06:00 next day)
    or at minimum once daily before the analyst cycle runs.
    These feeds update continuously — more frequent runs = fresher signals.

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial — Gap 4 remediation, gap_report_20260602_230000

AUTHOR
------
    BlueLotus MID Engineering (Claude)
    CIO: Kian Soh
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from ticker_universe import COMPANY_TICKER_ALIASES, HIGH_AMBIGUITY_TICKERS as CENTRAL_HIGH_AMBIGUITY_TICKERS, get_universe


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

VERSION      = "v1.0"
FEED_PAUSE   = 2      # seconds between feeds — respectful to servers
DEFAULT_LIMIT = 20    # max articles per feed per run

# ── Feed registry ─────────────────────────────────────────────────────────────
# Each entry: source_id, url, tier, trust_score, signal_type_default
# To activate a paid source in future: uncomment and add subscription headers
# to _fetch_feed() if required.
FEED_REGISTRY = [
    {
        "source":       "NvidiaNewsroom",
        "url":          "https://nvidianews.nvidia.com/releases.xml",
        "tier":         2,
        "trust":        0.90,
        "default_type": "PRODUCT_ANNOUNCEMENT",
        "use_requests": False,
        # Official Nvidia press release feed — primary source for Jensen Huang keynote
        # announcements, product launches, partnership news. Free, no bot protection.
        # This is the SOURCE that publishes the announcements HPCwire/AIwire then report on.
        # Going direct to the source is better than any aggregator.
        # Gap report specifically flagged missing Nvidia conference intelligence — this fixes it.
        "notes":        "Official Nvidia press releases. Primary source for Jensen Huang "
                        "keynote announcements, Blackwell/Rubin product launches, "
                        "TSMC/Marvell partnerships. Free RSS. No intermediary needed.",
    },
    {
        "source":       "ServeTheHome",
        "url":          "https://www.servethehome.com/feed/",
        "tier":         2,
        "trust":        0.83,
        "default_type": "AI_INFRASTRUCTURE",
        "notes":        "AI server hardware, data center builds. "
                        "Early signal for NVDA/AMD GPU demand in enterprise.",
    },
    {
        "source":       "TheQuantumInsider",
        "url":          "https://thequantuminsider.com/feed/",
        "tier":         3,
        "trust":        0.80,
        "default_type": "QUANTUM_NEWS",
        "notes":        "Primary quantum sector publication. "
                        "Critical for QUBT, QBTS, IONQ, RGTI position monitoring.",
    },
    {
        "source":       "ArsTechnica",
        "url":          "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "tier":         2,
        "trust":        0.82,
        "default_type": "GENERAL",
        "notes":        "Broad tech, AI policy, chip architecture deep-dives.",
    },
    {
        "source":       "TheRegister",
        "url":          "https://www.theregister.com/headlines.atom",
        "tier":         3,
        "trust":        0.80,
        "default_type": "GENERAL",
        "notes":        "Enterprise tech, cloud, chip announcements. UK-based. "
                        "Good for MSFT, AMZN, GOOGL cloud competitive intelligence.",
    },
    {
        "source":       "VentureBeat",
        "url":          "https://venturebeat.com/category/ai/feed/",
        "tier":         3,
        "trust":        0.76,
        "default_type": "AI_INFRASTRUCTURE",
        "notes":        "AI enterprise applications and funding. "
                        "Relevant for PLTR, MSFT, GOOGL, META AI thesis.",
    },
    {
        "source":       "IEEESpectrum",
        "url":          "https://spectrum.ieee.org/feeds/topic/computing.rss",
        "tier":         3,
        "trust":        0.82,
        "default_type": "QUANTUM_NEWS",
        # Old URL spectrum.ieee.org/feeds/blog/quantum-computing.rss is DEAD as of 2025/2026.
        # IEEE Spectrum restructured RSS to topic-based format. Confirmed via research 2026-06-03.
        # New topic feeds: /feeds/topic/computing.rss (covers quantum computing articles)
        #                  /feeds/topic/semiconductors.rss (covers chip/hardware)
        # Both confirmed returning application/rss+xml. Using computing as primary (quantum subset).
        "notes":        "IEEE quantum computing section. Old /feeds/blog/quantum-computing.rss dead. "
                        "New URL: /feeds/topic/computing.rss confirmed live 2026-06-03.",
    },
    {
        "source":       "TomsHardware",
        "url":          "https://www.tomshardware.com/feeds/all",
        "tier":         3,
        "trust":        0.75,
        "default_type": "PRODUCT_ANNOUNCEMENT",
        "notes":        "GPU, processor, memory hardware launches. "
                        "Early signal for NVDA/AMD product cycles and MU demand.",
    },

    # ── PAID SOURCES — EXCLUDED per CIO decision 2026-06-03 ──────────────────
    # Uncomment when subscription is obtained. No other code changes needed.
    #
    # {
    #     "source":       "DigiTimes",
    #     "url":          "https://www.digitimes.com/rss/",
    #     "tier":         2,
    #     "trust":        0.86,
    #     "default_type": "SUPPLY_CHAIN",
    #     "notes":        "Taiwan supply chain, TSMC, Computex. PAID subscription required.",
    # },
    # {
    #     "source":       "SemiAnalysis",
    #     "url":          "https://www.semianalysis.com/feed",
    #     "tier":         2,
    #     "trust":        0.88,
    #     "default_type": "SUPPLY_CHAIN",
    #     "notes":        "Semiconductor deep-dives. Newsletter format. PAID.",
    # },
    # {
    #     "source":       "TheInformation",
    #     "url":          "https://www.theinformation.com/feed",
    #     "tier":         2,
    #     "trust":        0.87,
    #     "default_type": "AI_INFRASTRUCTURE",
    #     "notes":        "AI company strategy and funding. PAID subscription required.",
    # },
    # {
    #     "source":       "ElectronicTimes",
    #     "url":          "https://www.etnews.com/rss/",
    #     "tier":         3,
    #     "trust":        0.80,
    #     "default_type": "SUPPLY_CHAIN",
    #     "notes":        "Korean semiconductor — Samsung, SK Hynix. Korean paywall.",
    # },
]

# ── Watchlist for ticker extraction ───────────────────────────────────────────
# Mirrors WATCHLIST_83 from fetch_capital_flow.py exactly
WATCHLIST_83 = get_universe()

# ── Short ticker false-positive guard ─────────────────────────────────────────
# Tickers 1-2 chars that are extremely common English words — cannot be reliably
# extracted from prose without a $ prefix. Require $TICKER format only.
# BE = "be/will be/to be", C = "C language/see", MU = rare but ambiguous,
# AU = "au naturel", BA = "ba" (music), GE = "ge" (rare), MP = abbreviation.
# Research confirmed sentence-level gate still leaks for BE (9 false hits, 2026-06-03).
HIGH_AMBIGUITY_TICKERS = set(CENTRAL_HIGH_AMBIGUITY_TICKERS)

# Tickers 1-2 chars that are less ambiguous — allow sentence-level financial gate.
SHORT_TICKERS = {t for t in WATCHLIST_83 if len(t) <= 2} - HIGH_AMBIGUITY_TICKERS

FINANCIAL_CONTEXT_WORDS = [
    "stock", "share", "ticker", "nyse", "nasdaq", "price", "rally",
    "earnings", "revenue", "investor", "trading", "market cap", "etf",
    "semiconductor", "chip", "gpu", "quantum", "aerospace", "defense",
    "uranium", "mining", "energy", "solar", "fintech", "crypto",
    "portfolio", "position", "bull", "bear", "long", "short",
]

# ── P2-06: Company-name-to-ticker mapping (WO-RD-20260604-002) ────────────────
# Tier 4 of _extract_tickers(): applied AFTER Tier 1/2/3 word-boundary matching.
# Keys: lowercase company name variants (word-boundary matched, case-insensitive)
# Values: watchlist ticker symbol
# Only appends tickers that are in WATCHLIST_83 and not already found.
# Source: WO P2-06 specification + verified against WATCHLIST_83 above.
COMPANY_TICKER_MAP = COMPANY_TICKER_ALIASES

# Sources where every article is definitively about one ticker
# Applied as a source-level tag — zero false-positive risk
SOURCE_TICKER_MAP = {
    "NvidiaNewsroom": "NVDA",
}

# ── Theme keyword map ──────────────────────────────────────────────────────────
# Maps keywords found in headline/summary → theme tags
THEME_MAP = {
    "AI":              ["artificial intelligence", "machine learning", "deep learning",
                        "large language model", "llm", "generative ai", "ai model",
                        "neural network", "inference", "training"],
    "SEMICONDUCTOR":   ["semiconductor", "chip", "gpu", "cpu", "wafer", "fab",
                        "foundry", "tsmc", "samsung foundry", "node", "nm process",
                        "blackwell", "hopper", "mi300", "computex"],
    "QUANTUM":         ["quantum", "qubit", "quantum computing", "quantum error",
                        "superconducting", "ion trap", "photonic", "quantum advantage"],
    "AI_INFRASTRUCTURE":["data center", "server", "rack", "nvlink", "infiniband",
                         "networking", "cooling", "power", "gpu cluster", "h100",
                         "h200", "b200", "gb200"],
    "SUPPLY_CHAIN":    ["supply chain", "taiwan", "production", "yield", "capacity",
                        "shortage", "inventory", "lead time"],
    "CLOUD":           ["cloud", "aws", "azure", "google cloud", "gcp", "hyperscaler",
                        "data center capex"],
    "DEFENSE":         ["defense", "military", "pentagon", "dod", "missile",
                        "hypersonic", "autonomous", "drone"],
    "SPACE":           ["space", "rocket", "satellite", "launch", "orbit", "lunar",
                        "starship", "falcon"],
    "COMPUTEX":        ["computex", "taipei", "jensen huang", "huang keynote"],
}

# ── Signal type classifier keywords ───────────────────────────────────────────
SIGNAL_TYPE_MAP = {
    "PRODUCT_ANNOUNCEMENT": ["launch", "announce", "unveil", "reveal", "release",
                             "introduce", "new gpu", "new chip", "new processor"],
    "CONFERENCE_COVERAGE":  ["computex", "gtc", "ces", "wwdc", "re:invent", "keynote",
                             "conference", "summit", "forum"],
    "SUPPLY_CHAIN":         ["supply chain", "production", "yield", "tsmc", "samsung",
                             "inventory", "shortage", "capacity"],
    "EARNINGS_PREVIEW":     ["earnings", "revenue", "guidance", "forecast", "q1", "q2",
                             "q3", "q4", "quarter", "analyst estimate"],
    "PARTNERSHIP":          ["partnership", "collaboration", "deal", "agreement",
                             "joint venture", "alliance"],
    "REGULATORY":           ["regulation", "antitrust", "export control", "ban",
                             "sanction", "chips act", "investigation"],
    "QUANTUM_NEWS":         ["quantum", "qubit", "quantum computing"],
    "AI_INFRASTRUCTURE":    ["data center", "gpu cluster", "ai infrastructure",
                             "h100", "h200", "b200", "gb200", "nvlink"],
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_html(text: str) -> str:
    """Strip HTML tags and decode HTML entities from RSS text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)   # strip tags
    text = html.unescape(text)              # decode &amp; &lt; etc.
    text = re.sub(r"\s+", " ", text)       # collapse whitespace
    return text.strip()


def _content_hash(source: str, url: str) -> str:
    """SHA256 of source + url — dedup key."""
    raw = f"{source}::{url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_pubdate(entry) -> datetime | None:
    """
    Parse RSS pubDate into a datetime.
    feedparser normalises to time.struct_time in entry.published_parsed.
    Returns None if absent or unparseable.
    """
    import calendar
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts = calendar.timegm(entry.published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    except Exception:
        pass
    return None


def _extract_tickers(text: str) -> list[str]:
    """
    Find WATCHLIST_83 tickers mentioned in text. Three-tier strategy:

    Tier 1 — Long tickers (3+ chars, e.g. NVDA, AMD, MRVL):
        Word-boundary match on uppercased text. Sufficient.

    Tier 2 — Short tickers, lower ambiguity (e.g. MU):
        Word-boundary match PLUS sentence-level financial context gate.
        The ticker and a financial keyword must appear in the same sentence.

    Tier 3 — High-ambiguity tickers (BE, C, AU, BA, GE, MP):
        These are too common as English words for any prose-level gate to work.
        Require explicit $ prefix only: "$BE", "$C", "$AU".
        Sentence-level gate still leaked 9 BE false positives (2026-06-03).
        Dollar-prefix is the only reliable signal for these tickers in RSS text.
    """
    found      = []
    text_upper = text.upper()

    for ticker in WATCHLIST_83:
        pattern = r"\b" + re.escape(ticker) + r"\b"
        if not re.search(pattern, text_upper):
            continue

        if ticker in HIGH_AMBIGUITY_TICKERS:
            # Tier 3: $ prefix ONLY
            if re.search(r"\$" + re.escape(ticker) + r"\b", text, re.IGNORECASE):
                found.append(ticker)

        elif ticker in SHORT_TICKERS:
            # Tier 2: $ prefix OR same-sentence financial context
            if re.search(r"\$" + re.escape(ticker) + r"\b", text, re.IGNORECASE):
                found.append(ticker)
                continue
            for sentence in re.split(r'[.!?\n]', text):
                if re.search(pattern, sentence.upper()) and \
                   any(fw in sentence.lower() for fw in FINANCIAL_CONTEXT_WORDS):
                    found.append(ticker)
                    break

        else:
            # Tier 1: long ticker, word boundary sufficient
            found.append(ticker)

    # Tier 4 — P2-06: Company-name-to-ticker mapping
    # Applied after Tier 1/2/3. Case-insensitive word-boundary match
    # against company name variants. Only adds tickers in WATCHLIST_83
    # not already found in Tiers 1-3.
    text_lower  = text.lower()
    found_set   = set(found)
    watchlist_set = set(WATCHLIST_83)
    for name_variants, ticker in COMPANY_TICKER_MAP:
        if ticker not in watchlist_set:
            continue
        if ticker in found_set:
            continue
        for name in name_variants:
            pattern_t4 = r'(?<![a-z])' + re.escape(name) + r'(?![a-z])'
            if re.search(pattern_t4, text_lower):
                found.append(ticker)
                found_set.add(ticker)
                break

    return found


def _detect_themes(text: str) -> list[str]:
    """Match theme keywords against lowercased text."""
    text_lower = text.lower()
    themes = []
    for theme, keywords in THEME_MAP.items():
        if any(kw in text_lower for kw in keywords):
            themes.append(theme)
    return themes


def _classify_signal_type(text: str, default: str) -> str:
    """Return signal type based on keyword match, falling back to default."""
    text_lower = text.lower()
    for sig_type, keywords in SIGNAL_TYPE_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return sig_type
    return default


def _vader_sentiment(text: str) -> tuple[float, str]:
    """
    Run VADER on text. Returns (compound_score, label).
    BULLISH > +0.05, BEARISH < -0.05, NEUTRAL otherwise.
    """
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        scores   = analyzer.polarity_scores(text)
        compound = round(scores["compound"], 4)
        if compound > 0.05:
            label = "BULLISH"
        elif compound < -0.05:
            label = "BEARISH"
        else:
            label = "NEUTRAL"
        return compound, label
    except ImportError:
        # vaderSentiment not installed — return neutral, log once
        return 0.0, "NEUTRAL"
    except Exception:
        return 0.0, "NEUTRAL"


# ═══════════════════════════════════════════════════════════════════════════════
# FEED FETCHER
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_feed(feed_cfg: dict, limit: int) -> list[dict]:
    """
    Fetch and parse one RSS feed. Returns list of article dicts.
    Each dict has all fields needed for DB insert.
    Returns [] on any failure — caller logs the error.

    Two fetch modes:
      use_requests=False (default): feedparser.parse(url) directly.
      use_requests=True:  fetch raw XML via requests with a browser User-Agent,
                          then pass raw content string to feedparser.parse().
                          Used for sites that block feedparser's default UA
                          (e.g. HPCwire / Cloudflare bot detection).
    """
    import feedparser

    source       = feed_cfg["source"]
    url          = feed_cfg["url"]
    tier         = feed_cfg["tier"]
    trust        = feed_cfg["trust"]
    default_type = feed_cfg["default_type"]
    use_requests = feed_cfg.get("use_requests", False)

    try:
        if use_requests:
            # Browser User-Agent to bypass bot detection (HPCwire, Cloudflare)
            import requests as _requests
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
            resp = _requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        else:
            feed = feedparser.parse(url)
    except Exception as e:
        _fail(f"{source}: fetch error — {e}")
        return []

    if feed.bozo and not feed.entries:
        _warn(f"{source}: feed returned 0 entries (bozo={feed.bozo})")
        return []

    entries  = feed.entries[:limit]
    articles = []
    now      = datetime.now()
    today    = now.date()

    for entry in entries:
        # ── Extract fields ────────────────────────────────────────────────────
        headline    = _clean_html(getattr(entry, "title",   "") or "")
        article_url = getattr(entry, "link",    "") or ""
        author      = _clean_html(getattr(entry, "author",  "") or "")
        published   = _parse_pubdate(entry)

        # Summary: prefer summary, fall back to content
        raw_summary = (
            getattr(entry, "summary", "")
            or (entry.content[0].value if hasattr(entry, "content") and entry.content else "")
            or ""
        )
        summary = _clean_html(raw_summary)[:2000]  # truncate to 2000 chars

        # Skip entries with no headline or URL
        if not headline or not article_url:
            continue

        # ── Dedup hash ────────────────────────────────────────────────────────
        c_hash = _content_hash(source, article_url)

        # ── NLP processing ────────────────────────────────────────────────────
        full_text       = f"{headline} {summary}"
        tickers         = _extract_tickers(full_text)
        # P2-06: source-level tag — some sources are definitively about one company
        src_ticker = SOURCE_TICKER_MAP.get(source)
        if src_ticker and src_ticker not in tickers and src_ticker in WATCHLIST_83:
            tickers.append(src_ticker)
        themes          = _detect_themes(full_text)
        signal_type     = _classify_signal_type(full_text, default_type)
        vader_score, sentiment_label = _vader_sentiment(full_text)

        articles.append({
            "source":           source,
            "tier":             tier,
            "trust_score":      trust,
            "headline":         headline[:500],
            "summary":          summary,
            "article_url":      article_url[:500],
            "published_at":     published,
            "author":           author[:200] if author else None,
            "tickers_mentioned": tickers,
            "themes_detected":  themes,
            "vader_score":      vader_score,
            "sentiment_label":  sentiment_label,
            "signal_type":      signal_type,
            "content_hash":     c_hash,
            "fetched_at":       now,
            "snapshot_date":    today,
            "cycle_ts":         now,
        })

    return articles


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


def write_to_db(articles: list[dict]) -> tuple[int, int, int]:
    """
    Upsert articles into tech_publication_signals.
    UNIQUE KEY is content_hash — re-runs are safe.
    Returns (inserted, updated, failed).
    """
    if not articles:
        return 0, 0, 0

    conn = _get_conn()
    cur  = conn.cursor()
    inserted = updated = failed = 0

    sql = """
        INSERT INTO tech_publication_signals (
            source, tier, trust_score,
            headline, summary, article_url, published_at, author,
            tickers_mentioned, themes_detected,
            vader_score, sentiment_label, signal_type,
            content_hash,
            fetched_at, snapshot_date, cycle_ts
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s,
            %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            headline         = VALUES(headline),
            summary          = VALUES(summary),
            vader_score      = VALUES(vader_score),
            sentiment_label  = VALUES(sentiment_label),
            tickers_mentioned = VALUES(tickers_mentioned),
            themes_detected  = VALUES(themes_detected),
            fetched_at       = VALUES(fetched_at)
    """

    for a in articles:
        try:
            cur.execute(sql, (
                a["source"],
                a["tier"],
                a["trust_score"],
                a["headline"],
                a["summary"],
                a["article_url"],
                a["published_at"],
                a["author"],
                json.dumps(a["tickers_mentioned"]),
                json.dumps(a["themes_detected"]),
                a["vader_score"],
                a["sentiment_label"],
                a["signal_type"],
                a["content_hash"],
                a["fetched_at"],
                a["snapshot_date"],
                a["cycle_ts"],
            ))
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            _fail(f"DB write failed [{a.get('source')}] {a.get('headline','')[:60]}: {e}")
            failed += 1

    conn.commit()
    cur.close()
    conn.close()
    return inserted, updated, failed


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Tech Publications RSS Fetcher v1.0"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print, skip DB write")
    parser.add_argument("--source",  type=str, default=None,
                        help="Run single source only: --source HPCwire")
    parser.add_argument("--limit",   type=int, default=DEFAULT_LIMIT,
                        help=f"Max articles per feed (default: {DEFAULT_LIMIT})")
    args = parser.parse_args()

    now = datetime.now()

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    # ── Filter feeds ──────────────────────────────────────────────────────────
    feeds = FEED_REGISTRY
    if args.source:
        feeds = [f for f in FEED_REGISTRY if f["source"].lower() == args.source.lower()]
        if not feeds:
            print(f"  [FAIL] Unknown source: {args.source}")
            print(f"         Available: {', '.join(f['source'] for f in FEED_REGISTRY)}")
            sys.exit(1)

    print()
    print("=" * 66)
    print(f"  BLUELOTUS MID — Tech Publications RSS Fetcher {VERSION}")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Feeds   : {len(feeds)}")
    print(f"  Limit   : {args.limit} articles per feed")
    print(f"  Mode    : {'DRY RUN (no DB write)' if args.dry_run else 'LIVE (writes to DB)'}")
    print("=" * 66)

    # ── Check dependencies ────────────────────────────────────────────────────
    _section("STEP 1: Checking dependencies")
    try:
        import feedparser
        _ok(f"feedparser {feedparser.__version__}")
    except ImportError:
        _fail("feedparser not installed. Run: pip install feedparser")
        sys.exit(1)

    try:
        import requests
        _ok(f"requests {requests.__version__}")
    except ImportError:
        _fail("requests not installed. Run: pip install requests")
        sys.exit(1)

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _ok("vaderSentiment installed")
    except ImportError:
        _warn("vaderSentiment not installed — sentiment will be NEUTRAL for all articles")
        _warn("Install with: pip install vaderSentiment")

    # ── Fetch all feeds ───────────────────────────────────────────────────────
    _section("STEP 2: Fetching RSS feeds")

    all_articles = []
    feed_summary = []

    for i, feed_cfg in enumerate(feeds):
        source = feed_cfg["source"]
        url    = feed_cfg["url"]
        print(f"\n  [{i+1}/{len(feeds)}] {source}")
        print(f"         {url}")

        articles = _fetch_feed(feed_cfg, args.limit)

        if not articles:
            _warn(f"{source}: 0 articles returned")
            feed_summary.append((source, 0, 0, 0))
            continue

        # Count tickers found
        ticker_hits = sum(1 for a in articles if a["tickers_mentioned"])
        bullish     = sum(1 for a in articles if a["sentiment_label"] == "BULLISH")
        bearish     = sum(1 for a in articles if a["sentiment_label"] == "BEARISH")

        _ok(f"{source}: {len(articles)} articles | "
            f"{ticker_hits} with tickers | "
            f"BULLISH={bullish} BEARISH={bearish}")

        # Print top 3 articles with ticker hits (or just top 3)
        preview = [a for a in articles if a["tickers_mentioned"]][:3] or articles[:3]
        for a in preview:
            tickers_str = ", ".join(a["tickers_mentioned"]) if a["tickers_mentioned"] else "—"
            _info(f"  [{a['sentiment_label']:<7}] {a['headline'][:70]}")
            _info(f"           Tickers: {tickers_str} | Type: {a['signal_type']}")

        all_articles.extend(articles)
        feed_summary.append((source, len(articles), ticker_hits, bullish))

        if i < len(feeds) - 1:
            time.sleep(FEED_PAUSE)

    # ── Summary before write ──────────────────────────────────────────────────
    _section("STEP 3: Fetch summary")
    total_articles = len(all_articles)
    total_tickers  = sum(1 for a in all_articles if a["tickers_mentioned"])
    total_bullish  = sum(1 for a in all_articles if a["sentiment_label"] == "BULLISH")
    total_bearish  = sum(1 for a in all_articles if a["sentiment_label"] == "BEARISH")
    total_neutral  = sum(1 for a in all_articles if a["sentiment_label"] == "NEUTRAL")

    print(f"\n  {'Source':<25} {'Articles':>8} {'w/Tickers':>10} {'Bullish':>8}")
    print(f"  {'─'*25} {'─'*8} {'─'*10} {'─'*8}")
    for src, n, t, b in feed_summary:
        print(f"  {src:<25} {n:>8} {t:>10} {b:>8}")
    print(f"  {'─'*25} {'─'*8} {'─'*10} {'─'*8}")
    print(f"  {'TOTAL':<25} {total_articles:>8} {total_tickers:>10} {total_bullish:>8}")
    print()
    _info(f"Sentiment: BULLISH={total_bullish} | BEARISH={total_bearish} | NEUTRAL={total_neutral}")

    # ── Ticker mention leaderboard ────────────────────────────────────────────
    ticker_counts: dict[str, int] = {}
    for a in all_articles:
        for t in a["tickers_mentioned"]:
            ticker_counts[t] = ticker_counts.get(t, 0) + 1

    if ticker_counts:
        print()
        _info("Top tickers mentioned across all feeds:")
        top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for ticker, count in top_tickers:
            bar = "█" * count
            _info(f"  {ticker:<6} {bar} ({count})")

    # ── DB write ──────────────────────────────────────────────────────────────
    if args.dry_run:
        _section("DRY RUN — Skipping DB write")
        _info("Run without --dry-run to write to tech_publication_signals table")
    else:
        _section("STEP 4: Writing to tech_publication_signals")
        inserted, updated, failed = write_to_db(all_articles)
        _ok(f"Inserted : {inserted} new rows")
        _ok(f"Updated  : {updated} existing rows (already seen)")
        if failed:
            _fail(f"Failed   : {failed} rows")

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — Tech Publications RSS Fetcher {VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Feeds processed : {len(feeds)}")
    print(f"  Articles fetched: {total_articles}")
    if not args.dry_run:
        print(f"  DB inserted     : {inserted}")
        print(f"  DB updated      : {updated}")
    print()
    print("  NEXT STEPS:")
    print("  1. python mid\\fetch_conference_calendar.py")
    print("  2. python mid\\fetch_ceo_appearances.py")
    print("  3. python mid\\fetch_catalyst_calendar.py")
    print("  4. Update export_dataset_raw.py to v1.8")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
