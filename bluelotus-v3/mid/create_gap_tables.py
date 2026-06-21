"""
BlueLotus Digital Institution — V2.0
mid/create_gap_tables.py

PURPOSE
-------
    One-time (idempotent) DDL runner that creates all 5 new tables required
    for dataset_raw.json v1.8, as specified in:

        INTELLIGENCE_GAP_REPORT_20260602.txt
        Gap Report ID: gap_report_20260602_230000

    Implements:
        Gap 1 — conference_calendar          (tech conference forward calendar)
        Gap 2 — ceo_appearance_tracker       (executive public appearance feed)
        Gap 3 — portfolio_catalyst_calendar  (per-ticker earnings/events feed)
        Gap 4 — tech_publication_signals     (tech industry RSS publication feed)
        Gap 5 — ece_named_events             (ECE seasonal named events registry)

DOCTRINE
--------
    - All tables follow existing BlueLotus DB conventions:
        snapshot_date DATE     — the trading day the data represents
        cycle_ts DATETIME      — SGT wall-clock time the fetcher ran (naive, no tzinfo)
                                 (matches BUG-MID-004 fix in export_dataset_raw.py)
        source VARCHAR         — identifies which fetcher/feed wrote the row
    - All tables use ON DUPLICATE KEY UPDATE semantics (idempotent re-runs)
    - This script is DDL-ONLY: no INSERT, no SELECT, no data modification
    - Safe to re-run at any time (IF NOT EXISTS on all tables)
    - Run BEFORE any fetcher scripts

USAGE
-----
    cd C:\\bluelotus2
    python mid\\create_gap_tables.py

    Optional flags:
    --verify        After creation, run DESCRIBE on each table and print schema
    --drop-recreate !! DESTRUCTIVE !! Drop and recreate all 5 tables (dev only)

ENVIRONMENT (.env)
------------------
    MYSQL_HOST / DB_HOST         (default: 127.0.0.1)
    MYSQL_PORT / DB_PORT         (default: 3306)
    MYSQL_USER / DB_USER         (required)
    MYSQL_PASSWORD / DB_PASSWORD (default: "")
    MYSQL_DATABASE / DB_NAME     (required, default: bluelotus2)

NEXT STEPS AFTER THIS SCRIPT
-----------------------------
    1. Run this script → tables created
    2. Run seed_ece_events.py → populates ece_named_events with Gap 5 data
    3. Build & run fetch_conference_calendar.py → populates conference_calendar
    4. Build & run fetch_ceo_appearances.py → populates ceo_appearance_tracker
    5. Build & run fetch_catalyst_calendar.py → populates portfolio_catalyst_calendar
    6. Build & run fetch_tech_publications.py → populates tech_publication_signals
    7. Update export_dataset_raw.py to v1.8 using the query blocks at the
       bottom of this file (see EXPORT QUERY BLOCKS section)

VERSION HISTORY
---------------
    v1.0  2026-06-03  Initial — Gap Report gap_report_20260602_230000 remediation

AUTHOR
------
    BlueLotus MID Engineering (Claude)
    CIO: Kian Soh
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


# ── Output helpers (match existing fetcher style) ─────────────────────────────
def _ok(msg):      print(f"  [OK]   {msg}")
def _fail(msg):    print(f"  [FAIL] {msg}")
def _warn(msg):    print(f"  [WARN] {msg}")
def _info(msg):    print(f"         {msg}")
def _section(t):
    print(f"\n{'─'*66}")
    print(f"  {t}")
    print(f"{'─'*66}")


# ── DB connection (mirrors fetch_capital_flow.py exactly) ─────────────────────
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
# DDL DEFINITIONS
# Each table is defined as (name, sql) so we can loop, verify, and report cleanly.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Gap 1: conference_calendar ────────────────────────────────────────────────
#
# Stores forward-looking tech conference and keynote events.
# Populated by: fetch_conference_calendar.py
#
# Design notes:
#   - conference_slug is a stable machine key (e.g. "COMPUTEX_2026") used by
#     ceo_appearance_tracker as a foreign reference (soft FK — no hard constraint
#     to keep scripts independent)
#   - keynote_speakers, affected_tickers, affected_themes stored as JSON arrays
#     so export_dataset_raw.py can surface them without additional joins
#   - hist_impact_* fields hold the ECE calibration data from the gap report
#     (Computex 2024/2025/2026 outcomes). These are populated at seed time and
#     updated by the Research Team after each event resolves.
#   - days_until_event is computed at fetch time so the analyst report can
#     immediately show "COMPUTEX starts in 3 days" without date arithmetic
#
# FREE RSS SOURCES (no paid feeds — see fetch_conference_calendar.py):
#   HPCwire (hpcwire.com/feed/) — had the Marvell/Huang announcement 7 days early
#   NASA News (already in system as NASA_News source)
#   Manual seed file: conference_seeds.json (Research Team maintained)
#
# NOTE: DigiTimes requires paid subscription. Excluded per CIO decision 2026-06-03.
#   When subscription is obtained, add source="DigiTimes" rows here.
#   fetch_conference_calendar.py contains commented-out DigiTimes RSS block.
#
DDL_CONFERENCE_CALENDAR = """
CREATE TABLE IF NOT EXISTS conference_calendar (
    id                   INT           NOT NULL AUTO_INCREMENT,

    -- Event identity
    conference_name      VARCHAR(200)  NOT NULL
                         COMMENT 'Human-readable name, e.g. Computex Taipei 2026',
    conference_slug      VARCHAR(100)  NOT NULL
                         COMMENT 'Stable machine key, e.g. COMPUTEX_2026',
    edition_year         SMALLINT      NOT NULL
                         COMMENT 'Calendar year of this edition',

    -- Timing
    event_date_start     DATE          NOT NULL
                         COMMENT 'First day of conference (inclusive)',
    event_date_end       DATE          NOT NULL
                         COMMENT 'Last day of conference (inclusive)',
    keynote_date         DATE          NULL
                         COMMENT 'Specific keynote day if known; NULL = TBC',
    keynote_time_local   VARCHAR(10)   NULL
                         COMMENT 'Keynote start time in local tz, e.g. 14:00',
    keynote_timezone     VARCHAR(50)   NULL
                         COMMENT 'IANA timezone, e.g. Asia/Taipei',

    -- Participants
    keynote_speakers     JSON          NULL
                         COMMENT 'Array of speaker names, e.g. ["Jensen Huang"]',
    hosting_company      VARCHAR(100)  NULL
                         COMMENT 'Company hosting or co-presenting the keynote',
    location_city        VARCHAR(100)  NULL,
    location_country     VARCHAR(10)   NULL
                         COMMENT 'ISO 3166-1 alpha-2, e.g. TW US',

    -- Market impact model
    impact_tier          TINYINT       NOT NULL DEFAULT 2
                         COMMENT '1=CRITICAL 2=HIGH 3=MEDIUM — market move potential',
    affected_tickers     JSON          NULL
                         COMMENT 'Watchlist tickers expected to move, e.g. ["NVDA","MRVL"]',
    affected_themes      JSON          NULL
                         COMMENT 'Theme tags, e.g. ["AI","SEMICONDUCTOR","QUANTUM"]',

    -- Historical impact for ECE calibration (% price move, positive = up)
    hist_impact_bull     DECIMAL(6,2)  NULL
                         COMMENT 'Bull case: best historical % move (e.g. +10.4 for NVDA 2024)',
    hist_impact_base     DECIMAL(6,2)  NULL
                         COMMENT 'Base case: typical expected % move',
    hist_impact_bear     DECIMAL(6,2)  NULL
                         COMMENT 'Bear case: fade/underperform % move (e.g. -1.2)',
    hist_years_tracked   TINYINT       NULL
                         COMMENT 'Number of historical years backing the impact model',

    -- Forward signal status (computed at fetch time)
    days_until_event     SMALLINT      NULL
                         COMMENT 'Calendar days from snapshot_date to event_date_start',
    catalyst_flag        VARCHAR(30)   NULL
                         COMMENT 'IMMINENT (<3d) | UPCOMING (<14d) | ACTIVE | PAST',
    announcement_url     VARCHAR(500)  NULL
                         COMMENT 'URL of the official schedule or announcement',

    -- Provenance
    source               VARCHAR(100)  NOT NULL
                         COMMENT 'Feed that provided this record, e.g. HPCwire | Manual_Calendar',
    fetched_at           DATETIME      NOT NULL
                         COMMENT 'SGT wall-clock time this row was written (naive, no tzinfo)',
    snapshot_date        DATE          NOT NULL
                         COMMENT 'Trading date this record was ingested',
    cycle_ts             DATETIME      NOT NULL
                         COMMENT 'SGT cycle timestamp — matches BUG-MID-004 convention',
    notes                TEXT          NULL
                         COMMENT 'Research Team annotations, e.g. surprise appearance context',

    PRIMARY KEY (id),
    UNIQUE KEY uq_conf_slug_year (conference_slug, edition_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Gap 1: Forward-looking tech conference and keynote calendar.
           Populated by fetch_conference_calendar.py.
           Gap Report: gap_report_20260602_230000';
"""

# ── Gap 2: ceo_appearance_tracker ─────────────────────────────────────────────
#
# Tracks Tier 1 and Tier 2 executive scheduled and confirmed public appearances.
# Populated by: fetch_ceo_appearances.py
#
# Design notes:
#   - executive_slug is a stable key (e.g. "JENSEN_HUANG") used for dedup
#   - conference_slug is a soft reference to conference_calendar.conference_slug
#     so the appearance can be linked to its parent conference event
#   - is_scheduled vs is_confirmed: scheduled = on calendar but unconfirmed;
#     confirmed = officially announced. Surprise appearances are is_scheduled=FALSE.
#   - alert_72h_flag / alert_24h_flag are set by the fetcher based on days delta
#     from snapshot_date to appearance_date. These drive the CATALYST ALERT logic
#     described in the gap report.
#   - X_Signals (trust 0.40) is used only for post-hoc confirmation of surprise
#     appearances, not as a primary forward-looking source.
#
# FREE RSS SOURCES:
#   HPCwire (hpcwire.com/feed/) — named executive conference appearances
#   SEC EDGAR 8-K (already in system as SEC_EDGAR_8K source) —
#     Item 8.01 (other events) announces investor days, conference presentations
#   Manual seed: executive_seeds.json — Tier 1/2 roster with ticker mapping
#
# NOTE: X_Signals is in the system at trust=0.40 (reactive, not forward-looking).
#   Tier 1 executives are cross-referenced against conference_calendar keynote_speakers
#   so a confirmed speaker → auto-creates a ceo_appearance_tracker row.
#
DDL_CEO_APPEARANCE_TRACKER = """
CREATE TABLE IF NOT EXISTS ceo_appearance_tracker (
    id                   INT           NOT NULL AUTO_INCREMENT,

    -- Person identity
    executive_name       VARCHAR(100)  NOT NULL
                         COMMENT 'Full name, e.g. Jensen Huang',
    executive_slug       VARCHAR(50)   NOT NULL
                         COMMENT 'Stable key, e.g. JENSEN_HUANG',
    company              VARCHAR(100)  NOT NULL
                         COMMENT 'Employer, e.g. Nvidia',
    ticker               VARCHAR(20)   NULL
                         COMMENT 'Primary ticker, e.g. NVDA. NULL for non-public (Sam Altman)',
    tier                 TINYINT       NOT NULL
                         COMMENT '1=Market-moving any statement; 2=Sector-specific mover',

    -- Appearance details
    appearance_type      VARCHAR(50)   NOT NULL
                         COMMENT 'KEYNOTE | INTERVIEW | PANEL | EARNINGS_CALL | CONGRESSIONAL | INVESTOR_DAY',
    event_name           VARCHAR(200)  NULL
                         COMMENT 'e.g. Marvell Technology Keynote at Computex 2026',
    conference_slug      VARCHAR(100)  NULL
                         COMMENT 'Soft ref to conference_calendar.conference_slug',
    appearance_date      DATE          NOT NULL,
    appearance_time_utc  VARCHAR(10)   NULL
                         COMMENT 'UTC time of appearance, e.g. 06:00',
    is_scheduled         BOOLEAN       NOT NULL DEFAULT TRUE
                         COMMENT 'TRUE = on published schedule; FALSE = surprise/unannounced',
    is_confirmed         BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE = officially announced by company or organiser',

    -- Market signal context
    topics_expected      JSON          NULL
                         COMMENT 'Expected discussion topics, e.g. ["Blackwell","quantum","AI infra"]',
    sentiment_bias       VARCHAR(20)   NULL
                         COMMENT 'BULLISH | BEARISH | NEUTRAL | UNKNOWN',
    affected_tickers     JSON          NULL
                         COMMENT 'Tickers expected to move on this appearance',

    -- Alert window flags (computed at fetch time)
    alert_72h_flag       BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE if appearance_date within 72h of snapshot_date',
    alert_24h_flag       BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE if appearance_date within 24h of snapshot_date',

    -- Provenance
    source_url           VARCHAR(500)  NULL,
    source               VARCHAR(100)  NOT NULL
                         COMMENT 'HPCwire | SEC_EDGAR_8K | Manual | X_Signals | Nvidia_Newsroom',
    fetched_at           DATETIME      NOT NULL,
    snapshot_date        DATE          NOT NULL,
    cycle_ts             DATETIME      NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_exec_event_date (executive_slug, event_name(100), appearance_date),
    INDEX idx_ceo_date (appearance_date),
    INDEX idx_ceo_slug (executive_slug),
    INDEX idx_ceo_alert72 (alert_72h_flag),
    INDEX idx_ceo_ticker (ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Gap 2: Executive public appearance forward tracker.
           Tier 1 (any statement moves market) and Tier 2 (sector movers).
           Populated by fetch_ceo_appearances.py.
           Gap Report: gap_report_20260602_230000';
"""

# ── Gap 3: portfolio_catalyst_calendar ────────────────────────────────────────
#
# Per-ticker forward catalyst calendar: earnings, investor days, ex-div, etc.
# Populated by: fetch_catalyst_calendar.py
#
# Design notes:
#   - Covers ALL 83 watchlist tickers, not just current portfolio positions.
#     in_portfolio and has_working_order flags are set from Portfolio_Snapshot
#     data in raw_signal_archive at fetch time — so the export can filter to
#     "live exposure" rows for the analyst report.
#   - catalyst_type drives which optional fields are populated:
#       EARNINGS         → eps_estimate, eps_prior, revenue_estimate
#       DIVIDEND_EX      → dividend_amount, dividend_frequency
#       SECONDARY_OFFER  → offering_size_usd, dilution_pct
#       INVESTOR_DAY     → event_name, event_venue, event_url
#       LOCKUP_EXPIRY    → (date only — critical for quantum names QUBT/QBTS)
#   - is_estimate=TRUE means date was inferred from historical pattern
#     (e.g. "usually reports 3rd week of month") — not confirmed by company
#   - Nasdaq Earnings Calendar is the primary public source (free, no auth).
#     Moomoo get_earnings_date() used as secondary to cross-check.
#
# FREE DATA SOURCES:
#   Moomoo OpenD get_earnings_date() — confirmed dates for watchlist tickers
#   Nasdaq Earnings Calendar (nasdaq.com/earnings-calendar) — free, scrapeable
#   SEC EDGAR 8-K (already ingested) — Item 8.01 for investor days / conferences
#   Manual input — lock-up expiry dates for recent IPOs (RKLB, ASTS, LUNR etc.)
#
# NOTE: Paid services like Bloomberg Earnings Calendar excluded per CIO 2026-06-03.
#   fetch_catalyst_calendar.py contains commented block for paid sources.
#
DDL_PORTFOLIO_CATALYST_CALENDAR = """
CREATE TABLE IF NOT EXISTS portfolio_catalyst_calendar (
    id                   INT           NOT NULL AUTO_INCREMENT,

    -- Ticker identity
    ticker               VARCHAR(20)   NOT NULL,
    company_name         VARCHAR(200)  NULL,

    -- Catalyst event core
    catalyst_type        VARCHAR(50)   NOT NULL
                         COMMENT 'EARNINGS | INVESTOR_DAY | ANALYST_DAY | CONFERENCE_APPEARANCE
                                  | DIVIDEND_EX | DIVIDEND_PAY | SECONDARY_OFFERING
                                  | LOCKUP_EXPIRY | FDA_DECISION | PRODUCT_LAUNCH | OTHER',
    catalyst_date        DATE          NOT NULL,
    catalyst_time_et     VARCHAR(10)   NULL
                         COMMENT 'ET time, e.g. 07:00 for pre-market earnings',
    is_confirmed         BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE = confirmed by company or exchange filing',
    is_estimate          BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE = date inferred from pattern, not confirmed',

    -- Event detail fields (populated by catalyst_type)
    event_name           VARCHAR(300)  NULL
                         COMMENT 'e.g. D-Wave Investor Day at NYSE',
    event_venue          VARCHAR(200)  NULL,
    event_url            VARCHAR(500)  NULL,

    -- Earnings context (populated when catalyst_type = EARNINGS)
    eps_estimate         DECIMAL(10,4) NULL
                         COMMENT 'Analyst consensus EPS estimate (USD)',
    eps_prior            DECIMAL(10,4) NULL
                         COMMENT 'Prior quarter actual EPS for YoY comparison',
    revenue_estimate     DECIMAL(20,2) NULL
                         COMMENT 'Analyst consensus revenue estimate (USD)',

    -- Dividend context (populated when catalyst_type = DIVIDEND_EX or DIVIDEND_PAY)
    dividend_amount      DECIMAL(10,4) NULL
                         COMMENT 'Declared dividend per share (USD)',
    dividend_frequency   VARCHAR(20)   NULL
                         COMMENT 'QUARTERLY | ANNUAL | MONTHLY | SPECIAL',

    -- Dilution risk (populated when catalyst_type = SECONDARY_OFFERING)
    offering_size_usd    DECIMAL(20,2) NULL
                         COMMENT 'Offering size in USD',
    dilution_pct         DECIMAL(8,4)  NULL
                         COMMENT 'Estimated dilution as % of shares outstanding',

    -- Portfolio exposure flags (set from Portfolio_Snapshot at fetch time)
    in_portfolio         BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE if ticker is an active position in Portfolio_Snapshot',
    has_working_order    BOOLEAN       NOT NULL DEFAULT FALSE
                         COMMENT 'TRUE if ticker has an active working order',

    -- Signal status (computed at fetch time)
    days_until_catalyst  SMALLINT      NULL
                         COMMENT 'Calendar days from snapshot_date to catalyst_date',
    alert_flag           VARCHAR(30)   NULL
                         COMMENT 'IMMINENT (<3d) | UPCOMING (<14d) | ACTIVE | PAST',

    -- Provenance
    source               VARCHAR(100)  NOT NULL
                         COMMENT 'Moomoo_EarningsCalendar | Nasdaq_Calendar | SEC_EDGAR_8K | Manual',
    source_url           VARCHAR(500)  NULL,
    fetched_at           DATETIME      NOT NULL,
    snapshot_date        DATE          NOT NULL,
    cycle_ts             DATETIME      NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_catalyst_ticker_type_date (ticker, catalyst_type, catalyst_date),
    INDEX idx_cat_ticker (ticker),
    INDEX idx_cat_date (catalyst_date),
    INDEX idx_cat_type (catalyst_type),
    INDEX idx_cat_portfolio (in_portfolio),
    INDEX idx_cat_alert (alert_flag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Gap 3: Per-ticker forward catalyst calendar.
           Earnings, investor days, dividends, lock-up expiries, secondary offerings.
           Populated by fetch_catalyst_calendar.py.
           Gap Report: gap_report_20260602_230000';
"""

# ── Gap 4: tech_publication_signals ───────────────────────────────────────────
#
# Stores signals from tech industry RSS publications — hardware, semiconductor,
# AI, quantum — which surface news 2-6 hours before Reuters/CNBC/MarketWatch.
# Populated by: fetch_tech_publications.py
#
# Design notes:
#   - content_hash = SHA256(source + article_url) is the dedup key. This means
#     re-running the fetcher on the same day will not create duplicates.
#   - tickers_mentioned is populated by NLP ticker extraction against WATCHLIST_83.
#     Simple string matching is used first (v1.0); VADER sentiment is applied per
#     article. Advanced NER can be added in a later version.
#   - signal_type classifies the article category for downstream filtering:
#     PRODUCT_ANNOUNCEMENT, CONFERENCE_COVERAGE, SUPPLY_CHAIN, etc.
#   - tier and trust_score mirror the SOURCE_REGISTRY convention in
#     export_dataset_raw.py — these values are hardcoded per source in the fetcher.
#   - published_at is the RSS <pubDate> field — can be NULL if absent from feed.
#     fetched_at is always populated (our server time).
#
# FREE RSS SOURCES (all confirmed free, no subscription required):
#   HPCwire            hpcwire.com/feed/                    tier=2, trust=0.85
#   ServeTheHome       servethehome.com/feed/               tier=2, trust=0.83
#   The Quantum Insider thequantuminsider.com/feed/          tier=3, trust=0.80
#   Ars Technica       feeds.arstechnica.com/arstechnica/technology-lab  tier=2, trust=0.82
#   The Register       theregister.com/headlines.atom       tier=3, trust=0.80
#   VentureBeat AI     venturebeat.com/category/ai/feed/   tier=3, trust=0.76
#   IEEE Spectrum      spectrum.ieee.org/feeds/blog/quantum-computing.rss  tier=3, trust=0.82
#   Tom's Hardware     tomshardware.com/feeds/all            tier=3, trust=0.75
#
# NOTE: DigiTimes (paid), SemiAnalysis (newsletter/paid), The Information (paid)
#   are EXCLUDED per CIO decision 2026-06-03.
#   fetch_tech_publications.py contains commented-out blocks for each paid source
#   with the correct RSS URL and trust score for future activation.
#   Electronic Times (Korean, paywall) also excluded.
#
DDL_TECH_PUBLICATION_SIGNALS = """
CREATE TABLE IF NOT EXISTS tech_publication_signals (
    id                   INT           NOT NULL AUTO_INCREMENT,

    -- Source identity
    source               VARCHAR(100)  NOT NULL
                         COMMENT 'HPCwire | ServeTheHome | TheQuantumInsider | ArsTechnica
                                  | TheRegister | VentureBeat | IEEESpectrum | TomsHardware',
    tier                 TINYINT       NOT NULL
                         COMMENT '2=High-value specialist; 3=Specialist niche',
    trust_score          DECIMAL(4,2)  NOT NULL
                         COMMENT 'Trust score 0.0-1.0, mirrors SOURCE_REGISTRY convention',

    -- Article content
    headline             VARCHAR(500)  NOT NULL,
    summary              TEXT          NULL
                         COMMENT 'RSS <description> or <summary> field, truncated to 2000 chars',
    article_url          VARCHAR(500)  NOT NULL,
    published_at         DATETIME      NULL
                         COMMENT 'RSS pubDate parsed to DATETIME; NULL if absent from feed',
    author               VARCHAR(200)  NULL,

    -- Ticker and theme tagging (NLP extraction against WATCHLIST_83)
    tickers_mentioned    JSON          NULL
                         COMMENT 'Watchlist tickers found in headline+summary, e.g. ["NVDA","MRVL"]',
    themes_detected      JSON          NULL
                         COMMENT 'Theme tags matched, e.g. ["AI","SEMICONDUCTOR","COMPUTEX"]',

    -- Sentiment (VADER applied to headline + summary)
    vader_score          DECIMAL(6,4)  NULL
                         COMMENT 'Compound VADER score: -1.0 (very negative) to +1.0 (very positive)',
    sentiment_label      VARCHAR(20)   NULL
                         COMMENT 'BULLISH (>0.05) | BEARISH (<-0.05) | NEUTRAL',

    -- Signal classification
    signal_type          VARCHAR(50)   NULL
                         COMMENT 'PRODUCT_ANNOUNCEMENT | CONFERENCE_COVERAGE | SUPPLY_CHAIN
                                  | EARNINGS_PREVIEW | PARTNERSHIP | REGULATORY | QUANTUM_NEWS
                                  | AI_INFRASTRUCTURE | GENERAL',

    -- Deduplication
    content_hash         VARCHAR(64)   NULL
                         COMMENT 'SHA256(source + article_url) — dedup key for re-runs',

    -- Provenance
    fetched_at           DATETIME      NOT NULL
                         COMMENT 'SGT wall-clock time row was written',
    snapshot_date        DATE          NOT NULL,
    cycle_ts             DATETIME      NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_tech_pub_hash (content_hash),
    INDEX idx_tech_pub_source (source),
    INDEX idx_tech_pub_date (snapshot_date),
    INDEX idx_tech_pub_published (published_at),
    INDEX idx_tech_pub_sentiment (sentiment_label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Gap 4: Tech industry publication RSS signals.
           Hardware, semiconductor, AI, quantum publications that lead
           Reuters/CNBC by 2-6 hours on product and conference news.
           Populated by fetch_tech_publications.py.
           Gap Report: gap_report_20260602_230000';
"""

# ── Gap 5: ece_named_events ───────────────────────────────────────────────────
#
# ECE (Event Correlation Engine) seasonal named events registry.
# Populated by: seed_ece_events.py (one-time Research Team seed)
#               Updated manually by Research Team after each event resolves.
#
# Design notes:
#   - event_slug is the stable machine key used by the ECE when generating
#     event_correlation signals in ingest.py. The ECE looks up this table to
#     determine if a named seasonal event is IMMINENT, ACTIVE, or PAST and
#     adjusts confidence weighting on correlated signals accordingly.
#   - trigger_type drives how next_occurrence is computed:
#       ANNUAL_DATE    → same calendar date each year (e.g. Jan 6 CES)
#       ANNUAL_WEEKDAY → Nth weekday of month (e.g. first Monday of June = Computex)
#   - historical_years is a JSON array of past event outcomes used to calibrate
#     the impact model. Updated by Research Team after each event resolves.
#   - sector_impact_map is a JSON object mapping ticker → impact role:
#       DIRECT_PRIMARY, DIRECT_SECONDARY, INDIRECT_SENTIMENT, QUANTUM_SPILLOVER
#   - This table is RESEARCHER-MAINTAINED. The fetcher does not scrape it.
#     Initial population = seed_ece_events.py reading from ece_seeds.json.
#     The gap report contains all data needed to populate the first record:
#     COMPUTEX_HUANG_KEYNOTE (2024, 2025, 2026 outcomes).
#
# NOTE: This table has no RSS source. It encodes institutional knowledge.
#   CIO/Research Team updates it after each event. There is no automated
#   population beyond the initial seed.
#
DDL_ECE_NAMED_EVENTS = """
CREATE TABLE IF NOT EXISTS ece_named_events (
    id                      INT           NOT NULL AUTO_INCREMENT,

    -- Event identity
    event_slug               VARCHAR(100)  NOT NULL
                             COMMENT 'Stable machine key, e.g. COMPUTEX_HUANG_KEYNOTE',
    event_name               VARCHAR(200)  NOT NULL
                             COMMENT 'Human label, e.g. Computex Jensen Huang Keynote',
    event_category           VARCHAR(50)   NOT NULL
                             COMMENT 'SEASONAL_TECH | FED_DECISION | EARNINGS_SEASON
                                      | GEOPOLITICAL | REGULATORY | SECTOR_ROTATION',
    description              TEXT          NULL
                             COMMENT 'Research Team narrative of why this event matters',

    -- Annual trigger logic
    trigger_type             VARCHAR(30)   NOT NULL
                             COMMENT 'ANNUAL_DATE (fixed date) | ANNUAL_WEEKDAY (Nth weekday)',
    trigger_month            TINYINT       NULL
                             COMMENT 'Month number 1-12',
    trigger_week_of_month    TINYINT       NULL
                             COMMENT 'For ANNUAL_WEEKDAY: 1=first, 2=second, etc.',
    trigger_day_of_week      TINYINT       NULL
                             COMMENT 'For ANNUAL_WEEKDAY: 0=Mon 1=Tue ... 6=Sun (ISO)',
    trigger_day_of_month     TINYINT       NULL
                             COMMENT 'For ANNUAL_DATE: day number 1-31',
    trigger_description      VARCHAR(200)  NULL
                             COMMENT 'Human description, e.g. First Monday of June (Taipei time)',

    -- Impact model — probability-weighted scenarios
    base_case_sectors        JSON          NULL
                             COMMENT 'Primary affected sectors, e.g. ["SEMICONDUCTOR","AI","QUANTUM"]',
    base_case_impact_pct     DECIMAL(6,2)  NULL
                             COMMENT 'Expected % market move, base case (S&P proxy)',
    base_case_duration_days  TINYINT       NULL
                             COMMENT 'Expected carry duration in trading days',

    bull_trigger             TEXT          NULL
                             COMMENT 'Condition that produces the bull case outcome',
    bull_case_impact_pct     DECIMAL(6,2)  NULL
                             COMMENT '% move, bull case. e.g. +6.26 (NVDA Day1, 2026)',
    bull_case_tickers        JSON          NULL
                             COMMENT 'Primary movers in bull case, e.g. ["NVDA","MRVL"]',
    bull_duration_days       TINYINT       NULL
                             COMMENT 'Carry days in bull case',

    bear_trigger             TEXT          NULL
                             COMMENT 'Condition that produces the bear case outcome',
    bear_case_impact_pct     DECIMAL(6,2)  NULL
                             COMMENT '% move, bear case. e.g. -1.20 (fade)',
    bear_duration_days       TINYINT       NULL
                             COMMENT 'Carry days in bear case',

    -- Sector / ticker impact map
    sector_impact_map        JSON          NULL
                             COMMENT 'JSON object: ticker -> role string.
                                      Roles: DIRECT_PRIMARY | DIRECT_SECONDARY
                                             | INDIRECT_SENTIMENT | QUANTUM_SPILLOVER
                                      e.g. {"NVDA":"DIRECT_PRIMARY","BAC":"INDIRECT_SENTIMENT"}',

    -- Historical calibration data
    historical_years         JSON          NULL
                             COMMENT 'Array of past event outcomes.
                                      Each entry: {year, outcome, nvda_pct, sp500_pct, notes}
                                      Updated by Research Team after each event resolves.',
    years_tracked            TINYINT       NULL
                             COMMENT 'Count of entries in historical_years array',

    -- Status and scheduling
    is_active                BOOLEAN       NOT NULL DEFAULT TRUE
                             COMMENT 'FALSE = deprecated or one-off event',
    last_occurrence          DATE          NULL
                             COMMENT 'Date of most recent occurrence (updated post-event)',
    next_occurrence          DATE          NULL
                             COMMENT 'Computed next trigger date (updated by seed_ece_events.py)',

    -- Provenance
    source                   VARCHAR(100)  NOT NULL DEFAULT 'Manual_ECE'
                             COMMENT 'Manual_ECE | Research_Team | Auto_ECE',
    authored_by              VARCHAR(100)  NULL
                             COMMENT 'Author of this event record',
    created_at               DATETIME      NOT NULL,
    updated_at               DATETIME      NOT NULL,
    notes                    TEXT          NULL
                             COMMENT 'Research Team annotations and calibration history',

    PRIMARY KEY (id),
    UNIQUE KEY uq_ece_event_slug (event_slug),
    INDEX idx_ece_category (event_category),
    INDEX idx_ece_next_occurrence (next_occurrence),
    INDEX idx_ece_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Gap 5: ECE seasonal named events registry.
           Encodes institutional knowledge of recurring market-moving events.
           Initial seed: COMPUTEX_HUANG_KEYNOTE (2024/2025/2026 calibrated).
           Populated by seed_ece_events.py (Research Team maintained).
           Gap Report: gap_report_20260602_230000';
"""


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE REGISTRY — ordered: create in this order, drop in reverse
# ═══════════════════════════════════════════════════════════════════════════════
TABLES = [
    ("conference_calendar",         DDL_CONFERENCE_CALENDAR),
    ("ceo_appearance_tracker",      DDL_CEO_APPEARANCE_TRACKER),
    ("portfolio_catalyst_calendar", DDL_PORTFOLIO_CATALYST_CALENDAR),
    ("tech_publication_signals",    DDL_TECH_PUBLICATION_SIGNALS),
    ("ece_named_events",            DDL_ECE_NAMED_EVENTS),
]

DROP_ORDER = [name for name, _ in reversed(TABLES)]


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT QUERY BLOCKS FOR export_dataset_raw.py v1.8
#
# Copy these 5 blocks verbatim into export_dataset_raw.py.
# Insert after the existing treasury_yields block (line ~664).
# Update EXPORT_VERSION to "v1.8" and add the 5 new keys to the dataset dict
# and the freshness dict.
#
# The blocks are also printed at the end of this script when --verify is used.
# ═══════════════════════════════════════════════════════════════════════════════

EXPORT_QUERY_BLOCKS = '''
# ---------------------------------------------------------------------------
# GAP 1: CONFERENCE CALENDAR — from conference_calendar table
# ---------------------------------------------------------------------------
conference_calendar_data: list = []
try:
    rows = _q(cur, """
        SELECT
            id, conference_name, conference_slug, edition_year,
            event_date_start, event_date_end, keynote_date,
            keynote_time_local, keynote_timezone,
            keynote_speakers, hosting_company,
            location_city, location_country,
            impact_tier, affected_tickers, affected_themes,
            hist_impact_bull, hist_impact_base, hist_impact_bear,
            hist_years_tracked, days_until_event, catalyst_flag,
            announcement_url, source, snapshot_date, cycle_ts, notes
        FROM conference_calendar
        WHERE catalyst_flag != 'PAST' OR event_date_start >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        ORDER BY event_date_start ASC
    """)
    conference_calendar_data = [_json_safe(r) for r in rows]
except Exception as e:
    conference_calendar_data = [{"_error": str(e)}]

# ---------------------------------------------------------------------------
# GAP 2: CEO APPEARANCE TRACKER — from ceo_appearance_tracker table
# ---------------------------------------------------------------------------
ceo_appearances: list = []
try:
    rows = _q(cur, """
        SELECT
            id, executive_name, executive_slug, company, ticker, tier,
            appearance_type, event_name, conference_slug,
            appearance_date, appearance_time_utc,
            is_scheduled, is_confirmed,
            topics_expected, sentiment_bias, affected_tickers,
            alert_72h_flag, alert_24h_flag,
            source_url, source, snapshot_date, cycle_ts
        FROM ceo_appearance_tracker
        WHERE appearance_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
        ORDER BY alert_72h_flag DESC, appearance_date ASC
    """)
    ceo_appearances = [_json_safe(r) for r in rows]
except Exception as e:
    ceo_appearances = [{"_error": str(e)}]

# ---------------------------------------------------------------------------
# GAP 3: PORTFOLIO CATALYST CALENDAR — from portfolio_catalyst_calendar table
# ---------------------------------------------------------------------------
catalyst_calendar: dict = {"all": [], "portfolio_only": [], "working_orders": []}
try:
    rows = _q(cur, """
        SELECT
            id, ticker, company_name, catalyst_type,
            catalyst_date, catalyst_time_et,
            is_confirmed, is_estimate,
            event_name, event_venue, event_url,
            eps_estimate, eps_prior, revenue_estimate,
            dividend_amount, dividend_frequency,
            offering_size_usd, dilution_pct,
            in_portfolio, has_working_order,
            days_until_catalyst, alert_flag,
            source, source_url, snapshot_date, cycle_ts
        FROM portfolio_catalyst_calendar
        WHERE catalyst_date >= DATE_SUB(CURDATE(), INTERVAL 3 DAY)
        ORDER BY catalyst_date ASC, ticker ASC
    """)
    all_cats = [_json_safe(r) for r in rows]
    catalyst_calendar["all"]            = all_cats
    catalyst_calendar["portfolio_only"] = [r for r in all_cats if r.get("in_portfolio")]
    catalyst_calendar["working_orders"] = [r for r in all_cats if r.get("has_working_order")]
except Exception as e:
    catalyst_calendar = {"_error": str(e)}

# ---------------------------------------------------------------------------
# GAP 4: TECH PUBLICATION SIGNALS — from tech_publication_signals table
# ---------------------------------------------------------------------------
tech_pub_signals: dict = {}
try:
    rows = _q(cur, """
        SELECT
            id, source, tier, trust_score,
            headline, summary, article_url, published_at, author,
            tickers_mentioned, themes_detected,
            vader_score, sentiment_label, signal_type,
            fetched_at, snapshot_date, cycle_ts
        FROM tech_publication_signals
        WHERE snapshot_date >= DATE_SUB(CURDATE(), INTERVAL 2 DAY)
        ORDER BY published_at DESC
        LIMIT 200
    """)
    # Group by source for easy consumption
    for r in rows:
        src = r.get("source", "UNKNOWN")
        if src not in tech_pub_signals:
            tech_pub_signals[src] = []
        tech_pub_signals[src].append(_json_safe(r))
except Exception as e:
    tech_pub_signals = {"_error": str(e)}

# ---------------------------------------------------------------------------
# GAP 5: ECE NAMED EVENTS — from ece_named_events table
# ---------------------------------------------------------------------------
ece_named_events: list = []
try:
    rows = _q(cur, """
        SELECT
            id, event_slug, event_name, event_category, description,
            trigger_type, trigger_month, trigger_week_of_month,
            trigger_day_of_week, trigger_day_of_month, trigger_description,
            base_case_sectors, base_case_impact_pct, base_case_duration_days,
            bull_trigger, bull_case_impact_pct, bull_case_tickers, bull_duration_days,
            bear_trigger, bear_case_impact_pct, bear_duration_days,
            sector_impact_map, historical_years, years_tracked,
            is_active, last_occurrence, next_occurrence,
            source, authored_by, created_at, updated_at, notes
        FROM ece_named_events
        WHERE is_active = TRUE
        ORDER BY next_occurrence ASC
    """)
    ece_named_events = [_json_safe(r) for r in rows]
except Exception as e:
    ece_named_events = [{"_error": str(e)}]
'''


# ═══════════════════════════════════════════════════════════════════════════════
# DATASET ASSEMBLY ADDITIONS FOR export_dataset_raw.py v1.8
#
# Add these keys to the dataset dict in export_dataset_raw.py:
#
#     "conference_calendar":   conference_calendar_data,
#     "ceo_appearances":       ceo_appearances,
#     "catalyst_calendar":     catalyst_calendar,
#     "tech_pub_signals":      tech_pub_signals,
#     "ece_named_events":      ece_named_events,
#
# Add these to the dataset_for_freshness dict:
#
#     "conference_calendar":  _ts(next(iter(conference_calendar_data), {})) if conference_calendar_data else "",
#     "ceo_appearances":      _ts(next(iter(ceo_appearances), {})) if ceo_appearances else "",
#     "catalyst_calendar":    _ts(next(iter(catalyst_calendar.get("all", [])), {})) if isinstance(catalyst_calendar, dict) else "",
#     "tech_pub_signals":     _ts(next(iter(next(iter(tech_pub_signals.values()), [])), {})) if tech_pub_signals and not tech_pub_signals.get("_error") else "",
#     "ece_named_events":     "",   -- static table, no cycle_ts freshness needed
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def create_tables(cur, conn, drop_first: bool = False) -> list[tuple[str, str]]:
    """
    Create all 5 gap tables. Returns list of (table_name, status) tuples.
    If drop_first=True, drops tables in reverse order before recreating.
    """
    results = []

    if drop_first:
        _warn("--drop-recreate flag set. Dropping tables in reverse order...")
        for name in DROP_ORDER:
            try:
                cur.execute(f"DROP TABLE IF EXISTS `{name}`")
                conn.commit()
                _warn(f"Dropped: {name}")
            except Exception as e:
                _fail(f"Drop failed for {name}: {e}")

    for name, ddl in TABLES:
        try:
            cur.execute(ddl)
            conn.commit()
            _ok(f"Created (or already exists): {name}")
            results.append((name, "OK"))
        except Exception as e:
            _fail(f"Failed to create {name}: {e}")
            results.append((name, f"FAIL: {e}"))

    return results


def verify_tables(cur) -> None:
    """Run DESCRIBE on each table and print column summary."""
    for name, _ in TABLES:
        try:
            cur.execute(f"DESCRIBE `{name}`")
            rows = cur.fetchall()
            print(f"\n  ── {name} ({len(rows)} columns) ──")
            for r in rows:
                if isinstance(r, dict):
                    field = r.get("Field", r.get("field", "?"))
                    typ   = r.get("Type",  r.get("type",  "?"))
                    null  = r.get("Null",  "")
                    key   = r.get("Key",   "")
                    key_str = f" [{key}]" if key else ""
                    null_str = " NULL" if null == "YES" else " NOT NULL"
                    print(f"    {field:<35} {typ:<25}{null_str}{key_str}")
        except Exception as e:
            _fail(f"DESCRIBE {name} failed: {e}")


def print_export_blocks() -> None:
    """Print the export query blocks for copy-paste into export_dataset_raw.py."""
    print("\n" + "═"*66)
    print("  EXPORT QUERY BLOCKS FOR export_dataset_raw.py v1.8")
    print("  Copy the block below into export_dataset_raw.py after the")
    print("  existing treasury_yields block. Update EXPORT_VERSION to v1.8.")
    print("═"*66)
    print(EXPORT_QUERY_BLOCKS)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus MID — Gap Table DDL Runner v1.0\n"
                    "Creates 5 new tables for dataset_raw.json v1.8"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After creation, DESCRIBE each table and print column summary",
    )
    parser.add_argument(
        "--drop-recreate",
        action="store_true",
        help="[DESTRUCTIVE] Drop and recreate all 5 tables. Dev/reset only.",
    )
    parser.add_argument(
        "--print-export-blocks",
        action="store_true",
        help="Print the export query blocks to copy into export_dataset_raw.py",
    )
    args = parser.parse_args()

    now = datetime.now()

    print()
    print("=" * 66)
    print("  BLUELOTUS MID — Gap Table DDL Runner v1.0")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print(f"  Implements: gap_report_20260602_230000")
    print(f"  Tables to create: {len(TABLES)}")
    if args.drop_recreate:
        print("  ⚠️  MODE: DROP + RECREATE (destructive)")
    else:
        print("  MODE: CREATE IF NOT EXISTS (safe, idempotent)")
    print("=" * 66)

    # ── Load .env ─────────────────────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        _info(f".env loaded from {env_path}")
    else:
        _warn(f".env not found at {env_path} — using environment variables")

    # ── Connect ───────────────────────────────────────────────────────────────
    _section("STEP 1: Connecting to MySQL")
    try:
        conn = _get_conn()
        cur  = conn.cursor(dictionary=True)
        db   = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "bluelotus2")
        host = os.getenv("MYSQL_HOST")     or os.getenv("DB_HOST", "127.0.0.1")
        _ok(f"Connected to {host} / {db}")
    except Exception as e:
        _fail(f"DB connection failed: {e}")
        _info("Check MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE in .env")
        sys.exit(1)

    # ── Create tables ─────────────────────────────────────────────────────────
    _section("STEP 2: Creating gap tables")
    results = create_tables(cur, conn, drop_first=args.drop_recreate)

    ok_count   = sum(1 for _, s in results if s == "OK")
    fail_count = sum(1 for _, s in results if s != "OK")

    # ── Verify ────────────────────────────────────────────────────────────────
    if args.verify:
        _section("STEP 3: Verifying table schemas (DESCRIBE)")
        verify_tables(cur)

    # ── Print export blocks ───────────────────────────────────────────────────
    if args.print_export_blocks:
        print_export_blocks()

    # ── Close ─────────────────────────────────────────────────────────────────
    cur.close()
    conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 66)
    print(f"  COMPLETE — Gap Table DDL Runner v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
    print()
    for name, status in results:
        icon = "✅" if status == "OK" else "❌"
        print(f"  {icon}  {name:<38} {status}")
    print()
    print(f"  Tables OK     : {ok_count}/{len(TABLES)}")
    print(f"  Tables FAILED : {fail_count}/{len(TABLES)}")
    print()
    if fail_count == 0:
        print("  NEXT STEPS:")
        print("  1. python mid\\seed_ece_events.py")
        print("     → Seeds ece_named_events with COMPUTEX_HUANG_KEYNOTE")
        print("  2. python mid\\fetch_conference_calendar.py")
        print("     → Populates conference_calendar from HPCwire + seed file")
        print("  3. python mid\\fetch_ceo_appearances.py")
        print("     → Populates ceo_appearance_tracker")
        print("  4. python mid\\fetch_catalyst_calendar.py")
        print("     → Populates portfolio_catalyst_calendar")
        print("  5. python mid\\fetch_tech_publications.py")
        print("     → Populates tech_publication_signals")
        print("  6. Update export_dataset_raw.py to v1.8")
        print("     → Run with --print-export-blocks to get query block code")
        print()
        print("  Run with --verify to inspect column schemas.")
        print("  Run with --print-export-blocks to get export_dataset_raw.py v1.8 additions.")
    else:
        print("  ⚠️  Some tables failed. Check error messages above.")
        print("     Verify DB credentials and permissions before running fetchers.")
    print("=" * 66)
    print()

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
