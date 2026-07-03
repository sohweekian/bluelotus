-- BlueLotus V2 schema installer
-- Generated from live BlueLotus database without data rows.
-- Source MySQL: 8.4.9 | MySQL Community Server - GPL | Win64
-- Source schema: bluelotus2
-- Tables: 44 | Triggers: 2

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

-- Table: ceo_appearance_tracker
CREATE TABLE IF NOT EXISTS `ceo_appearance_tracker` (
  `id` int NOT NULL AUTO_INCREMENT,
  `executive_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Full name, e.g. Jensen Huang',
  `executive_slug` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Stable key, e.g. JENSEN_HUANG',
  `company` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Employer, e.g. Nvidia',
  `ticker` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Primary ticker, e.g. NVDA. NULL for non-public (Sam Altman)',
  `tier` tinyint NOT NULL COMMENT '1=Market-moving any statement; 2=Sector-specific mover',
  `appearance_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'KEYNOTE | INTERVIEW | PANEL | EARNINGS_CALL | CONGRESSIONAL | INVESTOR_DAY',
  `event_name` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'e.g. Marvell Technology Keynote at Computex 2026',
  `conference_slug` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Soft ref to conference_calendar.conference_slug',
  `appearance_date` date NOT NULL,
  `appearance_time_utc` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'UTC time of appearance, e.g. 06:00',
  `is_scheduled` tinyint(1) NOT NULL DEFAULT '1' COMMENT 'TRUE = on published schedule; FALSE = surprise/unannounced',
  `is_confirmed` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE = officially announced by company or organiser',
  `topics_expected` json DEFAULT NULL COMMENT 'Expected discussion topics, e.g. ["Blackwell","quantum","AI infra"]',
  `sentiment_bias` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'BULLISH | BEARISH | NEUTRAL | UNKNOWN',
  `affected_tickers` json DEFAULT NULL COMMENT 'Tickers expected to move on this appearance',
  `alert_72h_flag` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE if appearance_date within 72h of snapshot_date',
  `alert_24h_flag` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE if appearance_date within 24h of snapshot_date',
  `source_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'HPCwire | SEC_EDGAR_8K | Manual | X_Signals | Nvidia_Newsroom',
  `fetched_at` datetime NOT NULL,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_exec_event_date` (`executive_slug`,`event_name`(100),`appearance_date`),
  KEY `idx_ceo_date` (`appearance_date`),
  KEY `idx_ceo_slug` (`executive_slug`),
  KEY `idx_ceo_alert72` (`alert_72h_flag`),
  KEY `idx_ceo_ticker` (`ticker`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Gap 2: Executive public appearance forward tracker.\n           Tier 1 (any statement moves market) and Tier 2 (sector movers).\n           Populated by fetch_ceo_appearances.py.\n           Gap Report: gap_report_20260602_230000';

-- Table: cio_decision_journal
CREATE TABLE IF NOT EXISTS `cio_decision_journal` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `decision_id` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_ts` datetime NOT NULL,
  `source_run_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `decision_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(48) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'RESEARCH_PENDING_CIO_REVIEW',
  `priority` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'P2',
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `thesis_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `current_weight` decimal(12,6) DEFAULT NULL,
  `target_weight` decimal(12,6) DEFAULT NULL,
  `delta_weight` decimal(12,6) DEFAULT NULL,
  `research_recommendation_json` json NOT NULL,
  `cio_decision` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cio_notes` text COLLATE utf8mb4_unicode_ci,
  `execution_authority` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'CIO_ONLY_MANUAL',
  `order_generated` tinyint(1) NOT NULL DEFAULT '0',
  `order_reference` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `decision_id` (`decision_id`),
  KEY `idx_cdj_decision_ts` (`decision_ts`),
  KEY `idx_cdj_status_priority` (`status`,`priority`),
  KEY `idx_cdj_ticker` (`ticker`),
  KEY `idx_cdj_thesis` (`thesis_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: cio_decisions
CREATE TABLE IF NOT EXISTS `cio_decisions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `decision_id` varchar(60) COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_date` date NOT NULL,
  `decision_time` time NOT NULL,
  `recorded_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `action` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ticker` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `quantity` int DEFAULT NULL,
  `price_at_decision` decimal(12,4) DEFAULT NULL,
  `size_usd` decimal(14,2) DEFAULT NULL,
  `confidence` decimal(4,3) NOT NULL DEFAULT '0.000',
  `rationale` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `thesis_reference` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `risk_reference` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `regime_at_decision` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `portfolio_pct_before` decimal(6,3) DEFAULT NULL,
  `portfolio_pct_after` decimal(6,3) DEFAULT NULL,
  `entry_type` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `working_order_placed` tinyint(1) NOT NULL DEFAULT '0',
  `order_price` decimal(12,4) DEFAULT NULL,
  `strategic_note` text COLLATE utf8mb4_unicode_ci,
  `outcome_review_date` date DEFAULT NULL,
  `outcome_recorded` tinyint(1) NOT NULL DEFAULT '0',
  `outcome_notes` text COLLATE utf8mb4_unicode_ci,
  `schema_version` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '1.0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cio_decision_id` (`decision_id`),
  KEY `idx_cio_date` (`decision_date` DESC),
  KEY `idx_cio_ticker` (`ticker`),
  KEY `idx_cio_action` (`action`),
  KEY `idx_cio_outcome` (`outcome_recorded`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: conference_calendar
CREATE TABLE IF NOT EXISTS `conference_calendar` (
  `id` int NOT NULL AUTO_INCREMENT,
  `conference_name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Human-readable name, e.g. Computex Taipei 2026',
  `conference_slug` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Stable machine key, e.g. COMPUTEX_2026',
  `edition_year` smallint NOT NULL COMMENT 'Calendar year of this edition',
  `event_date_start` date NOT NULL COMMENT 'First day of conference (inclusive)',
  `event_date_end` date NOT NULL COMMENT 'Last day of conference (inclusive)',
  `keynote_date` date DEFAULT NULL COMMENT 'Specific keynote day if known; NULL = TBC',
  `keynote_time_local` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Keynote start time in local tz, e.g. 14:00',
  `keynote_timezone` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'IANA timezone, e.g. Asia/Taipei',
  `keynote_speakers` json DEFAULT NULL COMMENT 'Array of speaker names, e.g. ["Jensen Huang"]',
  `hosting_company` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Company hosting or co-presenting the keynote',
  `location_city` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `location_country` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'ISO 3166-1 alpha-2, e.g. TW US',
  `impact_tier` tinyint NOT NULL DEFAULT '2' COMMENT '1=CRITICAL 2=HIGH 3=MEDIUM â€” market move potential',
  `affected_tickers` json DEFAULT NULL COMMENT 'Watchlist tickers expected to move, e.g. ["NVDA","MRVL"]',
  `affected_themes` json DEFAULT NULL COMMENT 'Theme tags, e.g. ["AI","SEMICONDUCTOR","QUANTUM"]',
  `hist_impact_bull` decimal(6,2) DEFAULT NULL COMMENT 'Bull case: best historical % move (e.g. +10.4 for NVDA 2024)',
  `hist_impact_base` decimal(6,2) DEFAULT NULL COMMENT 'Base case: typical expected % move',
  `hist_impact_bear` decimal(6,2) DEFAULT NULL COMMENT 'Bear case: fade/underperform % move (e.g. -1.2)',
  `hist_years_tracked` tinyint DEFAULT NULL COMMENT 'Number of historical years backing the impact model',
  `days_until_event` smallint DEFAULT NULL COMMENT 'Calendar days from snapshot_date to event_date_start',
  `catalyst_flag` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'IMMINENT (<3d) | UPCOMING (<14d) | ACTIVE | PAST',
  `announcement_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'URL of the official schedule or announcement',
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Feed that provided this record, e.g. HPCwire | Manual_Calendar',
  `fetched_at` datetime NOT NULL COMMENT 'SGT wall-clock time this row was written (naive, no tzinfo)',
  `snapshot_date` date NOT NULL COMMENT 'Trading date this record was ingested',
  `cycle_ts` datetime NOT NULL COMMENT 'SGT cycle timestamp â€” matches BUG-MID-004 convention',
  `notes` text COLLATE utf8mb4_unicode_ci COMMENT 'Research Team annotations, e.g. surprise appearance context',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_conf_slug_year` (`conference_slug`,`edition_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Gap 1: Forward-looking tech conference and keynote calendar.\n           Populated by fetch_conference_calendar.py.\n           Gap Report: gap_report_20260602_230000';

-- Table: corporate_actions
CREATE TABLE IF NOT EXISTS `corporate_actions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `action_id` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_date` date DEFAULT NULL,
  `ex_date` date DEFAULT NULL,
  `record_date` date DEFAULT NULL,
  `pay_date` date DEFAULT NULL,
  `statement` text COLLATE utf8mb4_unicode_ci,
  `ratio_text` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount` decimal(20,8) DEFAULT NULL,
  `currency` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `raw_json` json NOT NULL,
  `fetched_at` datetime NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `action_id` (`action_id`),
  KEY `idx_ca_ticker_date` (`ticker`,`event_date`),
  KEY `idx_ca_type` (`action_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: daily_regime_snapshots
CREATE TABLE IF NOT EXISTS `daily_regime_snapshots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `snapshot_date` date NOT NULL,
  `regime_label` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `regime_score` decimal(4,2) DEFAULT NULL,
  `vix` decimal(6,2) DEFAULT NULL,
  `fear_greed_index` int DEFAULT NULL,
  `dxy` decimal(8,4) DEFAULT NULL,
  `spy_close` decimal(10,4) DEFAULT NULL,
  `qqq_close` decimal(10,4) DEFAULT NULL,
  `tnx` decimal(6,4) DEFAULT NULL,
  `oil_price` decimal(8,4) DEFAULT NULL,
  `gold_price` decimal(10,4) DEFAULT NULL,
  `sector_leadership` json DEFAULT NULL,
  `volatility_state` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `macro_bias` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cio_annotation` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `snapshot_date` (`snapshot_date`),
  KEY `idx_regime_date` (`snapshot_date` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: dashboard_snapshots
CREATE TABLE IF NOT EXISTS `dashboard_snapshots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `snapshot_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `snapshot_timestamp` datetime NOT NULL,
  `regime_label` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `total_tickers` int DEFAULT NULL,
  `high_conviction_ct` int DEFAULT NULL,
  `medium_ct` int DEFAULT NULL,
  `avoid_ct` int DEFAULT NULL,
  `top_gainers` json DEFAULT NULL,
  `top_losers` json DEFAULT NULL,
  `payload_json` json DEFAULT NULL,
  `html_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `snapshot_id` (`snapshot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: data_lineage_events
CREATE TABLE IF NOT EXISTS `data_lineage_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `stage` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `input_refs_json` json DEFAULT NULL,
  `output_refs_json` json DEFAULT NULL,
  `dataset_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `event_id` (`event_id`),
  KEY `idx_dle_cycle_ts` (`cycle_ts`),
  KEY `idx_dle_stage` (`stage`),
  KEY `idx_dle_dataset_sha` (`dataset_sha256`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: decision_audit_log
CREATE TABLE IF NOT EXISTS `decision_audit_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `log_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `log_timestamp` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `entity_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previous_value` json DEFAULT NULL,
  `new_value` json DEFAULT NULL,
  `reason` text COLLATE utf8mb4_unicode_ci,
  `confidence_shift` decimal(4,2) DEFAULT NULL,
  `model_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `session_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `log_id` (`log_id`),
  KEY `idx_audit_timestamp` (`log_timestamp` DESC),
  KEY `idx_audit_actor` (`actor`),
  KEY `idx_audit_action` (`action_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: ece_named_events
CREATE TABLE IF NOT EXISTS `ece_named_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `event_slug` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Stable machine key, e.g. COMPUTEX_HUANG_KEYNOTE',
  `event_name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Human label, e.g. Computex Jensen Huang Keynote',
  `event_category` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'SEASONAL_TECH | FED_DECISION | EARNINGS_SEASON\n                                      | GEOPOLITICAL | REGULATORY | SECTOR_ROTATION',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT 'Research Team narrative of why this event matters',
  `trigger_type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ANNUAL_DATE (fixed date) | ANNUAL_WEEKDAY (Nth weekday)',
  `trigger_month` tinyint DEFAULT NULL COMMENT 'Month number 1-12',
  `trigger_week_of_month` tinyint DEFAULT NULL COMMENT 'For ANNUAL_WEEKDAY: 1=first, 2=second, etc.',
  `trigger_day_of_week` tinyint DEFAULT NULL COMMENT 'For ANNUAL_WEEKDAY: 0=Mon 1=Tue ... 6=Sun (ISO)',
  `trigger_day_of_month` tinyint DEFAULT NULL COMMENT 'For ANNUAL_DATE: day number 1-31',
  `trigger_description` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Human description, e.g. First Monday of June (Taipei time)',
  `base_case_sectors` json DEFAULT NULL COMMENT 'Primary affected sectors, e.g. ["SEMICONDUCTOR","AI","QUANTUM"]',
  `base_case_impact_pct` decimal(6,2) DEFAULT NULL COMMENT 'Expected % market move, base case (S&P proxy)',
  `base_case_duration_days` tinyint DEFAULT NULL COMMENT 'Expected carry duration in trading days',
  `bull_trigger` text COLLATE utf8mb4_unicode_ci COMMENT 'Condition that produces the bull case outcome',
  `bull_case_impact_pct` decimal(6,2) DEFAULT NULL COMMENT '% move, bull case. e.g. +6.26 (NVDA Day1, 2026)',
  `bull_case_tickers` json DEFAULT NULL COMMENT 'Primary movers in bull case, e.g. ["NVDA","MRVL"]',
  `bull_duration_days` tinyint DEFAULT NULL COMMENT 'Carry days in bull case',
  `bear_trigger` text COLLATE utf8mb4_unicode_ci COMMENT 'Condition that produces the bear case outcome',
  `bear_case_impact_pct` decimal(6,2) DEFAULT NULL COMMENT '% move, bear case. e.g. -1.20 (fade)',
  `bear_duration_days` tinyint DEFAULT NULL COMMENT 'Carry days in bear case',
  `sector_impact_map` json DEFAULT NULL COMMENT 'JSON object: ticker -> role string.\n                                      Roles: DIRECT_PRIMARY | DIRECT_SECONDARY\n                                             | INDIRECT_SENTIMENT | QUANTUM_SPILLOVER\n                                      e.g. {"NVDA":"DIRECT_PRIMARY","BAC":"INDIRECT_SENTIMENT"}',
  `historical_years` json DEFAULT NULL COMMENT 'Array of past event outcomes.\n                                      Each entry: {year, outcome, nvda_pct, sp500_pct, notes}\n                                      Updated by Research Team after each event resolves.',
  `years_tracked` tinyint DEFAULT NULL COMMENT 'Count of entries in historical_years array',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT 'FALSE = deprecated or one-off event',
  `last_occurrence` date DEFAULT NULL COMMENT 'Date of most recent occurrence (updated post-event)',
  `next_occurrence` date DEFAULT NULL COMMENT 'Computed next trigger date (updated by seed_ece_events.py)',
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Manual_ECE' COMMENT 'Manual_ECE | Research_Team | Auto_ECE',
  `authored_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Author of this event record',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci COMMENT 'Research Team annotations and calibration history',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ece_event_slug` (`event_slug`),
  KEY `idx_ece_category` (`event_category`),
  KEY `idx_ece_next_occurrence` (`next_occurrence`),
  KEY `idx_ece_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Gap 5: ECE seasonal named events registry.\n           Encodes institutional knowledge of recurring market-moving events.\n           Initial seed: COMPUTEX_HUANG_KEYNOTE (2024/2025/2026 calibrated).\n           Populated by seed_ece_events.py (Research Team maintained).\n           Gap Report: gap_report_20260602_230000';

-- Table: freshness_recovery_runs
CREATE TABLE IF NOT EXISTS `freshness_recovery_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `dataset_generated_at` datetime DEFAULT NULL,
  `market_session` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `stale_sections_json` json DEFAULT NULL,
  `market_closed_deferred_json` json DEFAULT NULL,
  `attempted_modules_json` json DEFAULT NULL,
  `command_results_json` json DEFAULT NULL,
  `unresolved_sections_json` json DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary_json` json NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `run_id` (`run_id`),
  KEY `idx_frr_cycle_ts` (`cycle_ts`),
  KEY `idx_frr_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: historical_backfill_queue
CREATE TABLE IF NOT EXISTS `historical_backfill_queue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `universe_source` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'grand_universe_200',
  `priority` int NOT NULL DEFAULT '5',
  `desired_days` int NOT NULL DEFAULT '180',
  `min_rows` int NOT NULL DEFAULT '90',
  `row_count` int NOT NULL DEFAULT '0',
  `first_bar_date` date DEFAULT NULL,
  `latest_bar_date` date DEFAULT NULL,
  `latest_fetch_at` datetime DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'PENDING',
  `attempt_count` int NOT NULL DEFAULT '0',
  `last_attempt_at` datetime DEFAULT NULL,
  `last_success_at` datetime DEFAULT NULL,
  `last_error` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ticker` (`ticker`),
  KEY `idx_hbq_status_priority` (`status`,`priority`,`last_attempt_at`),
  KEY `idx_hbq_latest_bar` (`latest_bar_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: historical_backfill_runs
CREATE TABLE IF NOT EXISTS `historical_backfill_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_size` int NOT NULL DEFAULT '0',
  `selected_tickers_json` json DEFAULT NULL,
  `command_json` json DEFAULT NULL,
  `command_exit_code` int DEFAULT NULL,
  `coverage_json` json DEFAULT NULL,
  `summary_json` json NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `run_id` (`run_id`),
  KEY `idx_hbr_cycle_ts` (`cycle_ts`),
  KEY `idx_hbr_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: historical_prices
CREATE TABLE IF NOT EXISTS `historical_prices` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bar_date` date NOT NULL,
  `time_key` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ktype` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'K_DAY',
  `autype` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'QFQ',
  `open_price` decimal(20,6) DEFAULT NULL,
  `high_price` decimal(20,6) DEFAULT NULL,
  `low_price` decimal(20,6) DEFAULT NULL,
  `close_price` decimal(20,6) DEFAULT NULL,
  `volume` bigint DEFAULT NULL,
  `turnover` decimal(24,6) DEFAULT NULL,
  `change_rate` decimal(12,6) DEFAULT NULL,
  `raw_bar_json` json DEFAULT NULL,
  `fetched_at` datetime NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hp_ticker_date_type` (`ticker`,`bar_date`,`ktype`,`autype`),
  KEY `idx_hp_ticker_date` (`ticker`,`bar_date`),
  KEY `idx_hp_fetched_at` (`fetched_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: institutional_dataset_snapshots
CREATE TABLE IF NOT EXISTS `institutional_dataset_snapshots` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `snapshot_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `captured_at` datetime NOT NULL,
  `dataset_generated_at` datetime DEFAULT NULL,
  `export_version` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ingest_version` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dataset_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dataset_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dataset_json` json NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `snapshot_id` (`snapshot_id`),
  KEY `idx_iq_dataset_generated_at` (`dataset_generated_at`),
  KEY `idx_iq_dataset_sha256` (`dataset_sha256`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: institutional_doctrine
CREATE TABLE IF NOT EXISTS `institutional_doctrine` (
  `id` int NOT NULL AUTO_INCREMENT,
  `doctrine_id` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `rationale` text COLLATE utf8mb4_unicode_ci,
  `effective_date` date NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `superseded_by` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `authored_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `model_version` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `doctrine_id` (`doctrine_id`),
  KEY `idx_doctrine_status` (`status`),
  KEY `idx_doctrine_effective` (`effective_date` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: institutional_quant_audit_events
CREATE TABLE IF NOT EXISTS `institutional_quant_audit_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `severity` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_iq_audit_run` (`run_id`),
  KEY `idx_iq_audit_type` (`event_type`),
  KEY `idx_iq_audit_severity` (`severity`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: institutional_quant_runs
CREATE TABLE IF NOT EXISTS `institutional_quant_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `run_version` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `run_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `started_at` datetime NOT NULL,
  `completed_at` datetime DEFAULT NULL,
  `snapshot_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dataset_generated_at` datetime DEFAULT NULL,
  `dataset_export_version` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dataset_ingest_version` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dataset_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dataset_snapshot_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `total_processes` int NOT NULL DEFAULT '0',
  `passed_processes` int NOT NULL DEFAULT '0',
  `warning_processes` int NOT NULL DEFAULT '0',
  `failed_processes` int NOT NULL DEFAULT '0',
  `readiness_score` decimal(6,3) DEFAULT NULL,
  `readiness_label` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `summary_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `run_id` (`run_id`),
  KEY `idx_iq_runs_completed` (`completed_at`),
  KEY `idx_iq_runs_status` (`run_status`),
  KEY `idx_iq_runs_snapshot` (`snapshot_id`),
  CONSTRAINT `fk_iq_runs_snapshot` FOREIGN KEY (`snapshot_id`) REFERENCES `institutional_dataset_snapshots` (`snapshot_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: macro_yields
CREATE TABLE IF NOT EXISTS `macro_yields` (
  `id` int NOT NULL AUTO_INCREMENT,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `source` varchar(50) NOT NULL DEFAULT 'Treasury_Yields',
  `yield_10y` decimal(8,4) DEFAULT NULL COMMENT 'US 10-Year Treasury Yield %',
  `yield_2y` decimal(8,4) DEFAULT NULL COMMENT 'US 2-Year Treasury Yield %',
  `yield_30y` decimal(8,4) DEFAULT NULL COMMENT 'US 30-Year Treasury Yield %',
  `yield_3m` decimal(8,4) DEFAULT NULL COMMENT 'US 3-Month T-Bill Yield %',
  `yield_spread_10_2` decimal(8,4) DEFAULT NULL COMMENT '10Y - 2Y spread (bps x 100)',
  `yield_spread_10_3m` decimal(8,4) DEFAULT NULL COMMENT '10Y - 3M spread',
  `curve_status` varchar(20) DEFAULT NULL COMMENT 'NORMAL / FLAT / INVERTED',
  `ffr_target` decimal(8,4) DEFAULT NULL COMMENT 'Fed Funds Rate target %',
  `ffr_upper` decimal(8,4) DEFAULT NULL COMMENT 'Fed Funds Rate upper bound %',
  `ffr_lower` decimal(8,4) DEFAULT NULL COMMENT 'Fed Funds Rate lower bound %',
  `cpi_latest` decimal(8,4) DEFAULT NULL COMMENT 'Latest CPI reading % YoY',
  `real_yield_10y` decimal(8,4) DEFAULT NULL COMMENT '10Y yield - CPI = real yield',
  `nim_proxy` decimal(8,4) DEFAULT NULL COMMENT '10Y - FFR = bank NIM proxy',
  PRIMARY KEY (`id`),
  UNIQUE KEY `snapshot_date` (`snapshot_date`),
  KEY `idx_yields_date` (`snapshot_date` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Daily treasury yield curve and Fed rate data â€” macro overlay';

-- Table: monitoring_alerts
CREATE TABLE IF NOT EXISTS `monitoring_alerts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `alert_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `severity` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `layer_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `related_ticker` varchar(24) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payload_json` json DEFAULT NULL,
  `resolved` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `alert_id` (`alert_id`),
  KEY `idx_ma_cycle_ts` (`cycle_ts`),
  KEY `idx_ma_severity` (`severity`),
  KEY `idx_ma_layer` (`layer_name`),
  KEY `idx_ma_related_ticker` (`related_ticker`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: portfolio_catalyst_calendar
CREATE TABLE IF NOT EXISTS `portfolio_catalyst_calendar` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticker` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `company_name` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `catalyst_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'EARNINGS | INVESTOR_DAY | ANALYST_DAY | CONFERENCE_APPEARANCE\n                                  | DIVIDEND_EX | DIVIDEND_PAY | SECONDARY_OFFERING\n                                  | LOCKUP_EXPIRY | FDA_DECISION | PRODUCT_LAUNCH | OTHER',
  `catalyst_date` date NOT NULL,
  `catalyst_time_et` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'ET time, e.g. 07:00 for pre-market earnings',
  `is_confirmed` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE = confirmed by company or exchange filing',
  `is_estimate` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE = date inferred from pattern, not confirmed',
  `event_name` varchar(300) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'e.g. D-Wave Investor Day at NYSE',
  `event_venue` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `eps_estimate` decimal(10,4) DEFAULT NULL COMMENT 'Analyst consensus EPS estimate (USD)',
  `eps_prior` decimal(10,4) DEFAULT NULL COMMENT 'Prior quarter actual EPS for YoY comparison',
  `revenue_estimate` decimal(20,2) DEFAULT NULL COMMENT 'Analyst consensus revenue estimate (USD)',
  `dividend_amount` decimal(10,4) DEFAULT NULL COMMENT 'Declared dividend per share (USD)',
  `dividend_frequency` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'QUARTERLY | ANNUAL | MONTHLY | SPECIAL',
  `offering_size_usd` decimal(20,2) DEFAULT NULL COMMENT 'Offering size in USD',
  `dilution_pct` decimal(8,4) DEFAULT NULL COMMENT 'Estimated dilution as % of shares outstanding',
  `in_portfolio` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE if ticker is an active position in Portfolio_Snapshot',
  `has_working_order` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'TRUE if ticker has an active working order',
  `days_until_catalyst` smallint DEFAULT NULL COMMENT 'Calendar days from snapshot_date to catalyst_date',
  `alert_flag` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'IMMINENT (<3d) | UPCOMING (<14d) | ACTIVE | PAST',
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Moomoo_EarningsCalendar | Nasdaq_Calendar | SEC_EDGAR_8K | Manual',
  `source_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fetched_at` datetime NOT NULL,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_catalyst_ticker_type_date` (`ticker`,`catalyst_type`,`catalyst_date`),
  KEY `idx_cat_ticker` (`ticker`),
  KEY `idx_cat_date` (`catalyst_date`),
  KEY `idx_cat_type` (`catalyst_type`),
  KEY `idx_cat_portfolio` (`in_portfolio`),
  KEY `idx_cat_alert` (`alert_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Gap 3: Per-ticker forward catalyst calendar.\n           Earnings, investor days, dividends, lock-up expiries, secondary offerings.\n           Populated by fetch_catalyst_calendar.py.\n           Gap Report: gap_report_20260602_230000';

-- Table: portfolio_optimizer_runs
CREATE TABLE IF NOT EXISTS `portfolio_optimizer_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generated_at` datetime NOT NULL,
  `source_snapshot_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `objective` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_weights_json` json NOT NULL,
  `target_weights_json` json NOT NULL,
  `constraints_json` json NOT NULL,
  `actions_json` json DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `run_id` (`run_id`),
  KEY `idx_por_generated_at` (`generated_at`),
  KEY `idx_por_snapshot` (`source_snapshot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: portfolio_readonly_snapshots
CREATE TABLE IF NOT EXISTS `portfolio_readonly_snapshots` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `snapshot_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `broker` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'moomoo',
  `data_source` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'OpenSecTradeContext',
  `account_currency` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'USD',
  `position_count` int NOT NULL DEFAULT '0',
  `total_assets` decimal(20,4) DEFAULT NULL,
  `cash` decimal(20,4) DEFAULT NULL,
  `buying_power` decimal(20,4) DEFAULT NULL,
  `market_value` decimal(20,4) DEFAULT NULL,
  `total_cost` decimal(20,4) DEFAULT NULL,
  `total_pnl` decimal(20,4) DEFAULT NULL,
  `total_pnl_pct` decimal(12,6) DEFAULT NULL,
  `integrity_flag` tinyint(1) NOT NULL DEFAULT '0',
  `integrity_reason` text COLLATE utf8mb4_unicode_ci,
  `read_only_protocol_json` json NOT NULL,
  `account_raw_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `snapshot_id` (`snapshot_id`),
  KEY `idx_prs_cycle_ts` (`cycle_ts`),
  KEY `idx_prs_integrity` (`integrity_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: raw_signal_archive
CREATE TABLE IF NOT EXISTS `raw_signal_archive` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ingestion_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `received_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_url` text COLLATE utf8mb4_unicode_ci,
  `source_feed` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ingestion_method` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ingestion_agent` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `raw_payload` json NOT NULL,
  `raw_text` text COLLATE utf8mb4_unicode_ci,
  `raw_format` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'json',
  `payload_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_size_bytes` int DEFAULT NULL,
  `signal_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `suspected_category` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `suspected_entities` json DEFAULT NULL,
  `suspected_impact` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extraction_status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `extraction_errors` json DEFAULT NULL,
  `quality_score` decimal(3,2) DEFAULT NULL,
  `quality_flags` json DEFAULT NULL,
  `manually_reviewed` tinyint(1) DEFAULT '0',
  `review_notes` text COLLATE utf8mb4_unicode_ci,
  `processed_event_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `superseded_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_immutable` tinyint(1) DEFAULT '1',
  `archived_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ingestion_id` (`ingestion_id`),
  UNIQUE KEY `idx_raw_payload_hash` (`payload_hash`),
  KEY `idx_raw_received_at` (`received_at` DESC),
  KEY `idx_raw_source` (`source`),
  KEY `idx_raw_signal_type` (`signal_type`),
  KEY `idx_raw_extraction_status` (`extraction_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: research_report_archive
CREATE TABLE IF NOT EXISTS `research_report_archive` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `report_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'RESEARCH_DEPARTMENT_REPORT',
  `report_version` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `generated_at` datetime NOT NULL,
  `dataset_generated_at` datetime DEFAULT NULL,
  `market_session` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `export_version` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ingest_version` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `regime` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `regime_score` int DEFAULT NULL,
  `regime_action` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cio_action` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `confidence` decimal(5,3) DEFAULT NULL,
  `confidence_label` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `blind_spot_status` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `causal_explanation_status` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `doctrine_warning` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `portfolio_assets` decimal(18,2) DEFAULT NULL,
  `portfolio_cash` decimal(18,2) DEFAULT NULL,
  `portfolio_equity` decimal(18,2) DEFAULT NULL,
  `portfolio_pnl` decimal(18,2) DEFAULT NULL,
  `portfolio_pnl_pct` decimal(8,3) DEFAULT NULL,
  `total_signals` int DEFAULT NULL,
  `latest_signal_at` datetime DEFAULT NULL,
  `sources_active` int DEFAULT NULL,
  `sources_expected` int DEFAULT NULL,
  `report_title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `report_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `report_text` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_file_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_report_sha256` (`report_sha256`),
  KEY `idx_generated_at` (`generated_at`),
  KEY `idx_regime` (`regime`),
  KEY `idx_cio_action` (`cio_action`),
  KEY `idx_blind_spot_status` (`blind_spot_status`),
  KEY `idx_causal_status` (`causal_explanation_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: research_reports
CREATE TABLE IF NOT EXISTS `research_reports` (
  `id` int NOT NULL AUTO_INCREMENT,
  `report_date` date NOT NULL,
  `report_id` varchar(60) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `model_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `model_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `prompt_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dataset_snapshot_id` varchar(60) COLLATE utf8mb4_unicode_ci NOT NULL,
  `regime_at_generation` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `market_outlook` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `sector_outlook` json NOT NULL,
  `ticker_recommendations` json NOT NULL,
  `top_conviction_tickers` json NOT NULL,
  `probability_assessments` json NOT NULL,
  `forecasts` json NOT NULL,
  `key_catalysts` text COLLATE utf8mb4_unicode_ci,
  `risk_flags` text COLLATE utf8mb4_unicode_ci,
  `confidence_overall` decimal(4,3) NOT NULL DEFAULT '0.000',
  `delivered_to_publishing` tinyint(1) NOT NULL DEFAULT '0',
  `schema_version` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '1.0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_research_report_id` (`report_id`),
  UNIQUE KEY `uq_research_report_date` (`report_date`),
  KEY `idx_research_regime` (`regime_at_generation`),
  KEY `idx_research_model` (`model_name`),
  KEY `idx_research_pending` (`delivered_to_publishing`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: risk_model_runs
CREATE TABLE IF NOT EXISTS `risk_model_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generated_at` datetime NOT NULL,
  `source_snapshot_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `price_start` date DEFAULT NULL,
  `price_end` date DEFAULT NULL,
  `lookback_days` int DEFAULT NULL,
  `position_count` int NOT NULL DEFAULT '0',
  `portfolio_value` decimal(20,4) DEFAULT NULL,
  `historical_var_95` decimal(20,6) DEFAULT NULL,
  `historical_var_99` decimal(20,6) DEFAULT NULL,
  `expected_shortfall_95` decimal(20,6) DEFAULT NULL,
  `volatility_annualized` decimal(12,6) DEFAULT NULL,
  `max_drawdown` decimal(12,6) DEFAULT NULL,
  `beta_to_spy` decimal(12,6) DEFAULT NULL,
  `metrics_json` json NOT NULL,
  `positions_json` json DEFAULT NULL,
  `factor_exposures_json` json DEFAULT NULL,
  `correlation_json` json DEFAULT NULL,
  `breaches_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `run_id` (`run_id`),
  KEY `idx_rmr_generated_at` (`generated_at`),
  KEY `idx_rmr_snapshot` (`source_snapshot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: risk_reports
CREATE TABLE IF NOT EXISTS `risk_reports` (
  `id` int NOT NULL AUTO_INCREMENT,
  `report_date` date NOT NULL,
  `report_id` varchar(60) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `model_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `model_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `prompt_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dataset_snapshot_id` varchar(60) COLLATE utf8mb4_unicode_ci NOT NULL,
  `regime_at_generation` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `portfolio_risk_summary` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `regime_risk_score` int NOT NULL DEFAULT '0',
  `risk_assessments` json NOT NULL,
  `counterarguments` json NOT NULL,
  `scenario_risks` json NOT NULL,
  `macro_risks` json NOT NULL,
  `geopolitical_risks` json DEFAULT NULL,
  `sector_exposure_risk` json NOT NULL,
  `recommended_actions` json DEFAULT NULL,
  `overall_risk_rating` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'MEDIUM',
  `delivered_to_publishing` tinyint(1) NOT NULL DEFAULT '0',
  `schema_version` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '1.0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_risk_report_id` (`report_id`),
  UNIQUE KEY `uq_risk_report_date` (`report_date`),
  KEY `idx_risk_rating` (`overall_risk_rating`),
  KEY `idx_risk_regime` (`regime_risk_score`),
  KEY `idx_risk_pending` (`delivered_to_publishing`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: security_listing_status
CREATE TABLE IF NOT EXISTS `security_listing_status` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `snapshot_date` date NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `security_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exchange_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_market` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `listing_date` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `delisting_flag` tinyint(1) NOT NULL DEFAULT '0',
  `listing_status` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `raw_json` json NOT NULL,
  `fetched_at` datetime NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sls_ticker_snapshot` (`ticker`,`snapshot_date`),
  KEY `idx_sls_ticker` (`ticker`),
  KEY `idx_sls_delisting` (`delisting_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: strategist_reports
CREATE TABLE IF NOT EXISTS `strategist_reports` (
  `id` int NOT NULL AUTO_INCREMENT,
  `report_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `report_date` date NOT NULL,
  `report_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `regime_label` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `regime_score` decimal(4,2) DEFAULT NULL,
  `bullish_score` int DEFAULT NULL,
  `bearish_score` int DEFAULT NULL,
  `overall_confidence` decimal(3,2) DEFAULT NULL,
  `top_risks` json DEFAULT NULL,
  `top_opportunities` json DEFAULT NULL,
  `key_entities` json DEFAULT NULL,
  `forecast_horizon` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `executive_summary` text COLLATE utf8mb4_unicode_ci,
  `full_report_json` json DEFAULT NULL,
  `html_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `delivered_via` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `model_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `model_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `prompt_hash` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `authored_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cio_approved` tinyint(1) DEFAULT '0',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `report_id` (`report_id`),
  KEY `idx_report_date` (`report_date` DESC),
  KEY `idx_report_type` (`report_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: tech_publication_signals
CREATE TABLE IF NOT EXISTS `tech_publication_signals` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'HPCwire | ServeTheHome | TheQuantumInsider | ArsTechnica\n                                  | TheRegister | VentureBeat | IEEESpectrum | TomsHardware',
  `tier` tinyint NOT NULL COMMENT '2=High-value specialist; 3=Specialist niche',
  `trust_score` decimal(4,2) NOT NULL COMMENT 'Trust score 0.0-1.0, mirrors SOURCE_REGISTRY convention',
  `headline` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary` text COLLATE utf8mb4_unicode_ci COMMENT 'RSS <description> or <summary> field, truncated to 2000 chars',
  `article_url` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `published_at` datetime DEFAULT NULL COMMENT 'RSS pubDate parsed to DATETIME; NULL if absent from feed',
  `author` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tickers_mentioned` json DEFAULT NULL COMMENT 'Watchlist tickers found in headline+summary, e.g. ["NVDA","MRVL"]',
  `themes_detected` json DEFAULT NULL COMMENT 'Theme tags matched, e.g. ["AI","SEMICONDUCTOR","COMPUTEX"]',
  `vader_score` decimal(6,4) DEFAULT NULL COMMENT 'Compound VADER score: -1.0 (very negative) to +1.0 (very positive)',
  `sentiment_label` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'BULLISH (>0.05) | BEARISH (<-0.05) | NEUTRAL',
  `signal_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'PRODUCT_ANNOUNCEMENT | CONFERENCE_COVERAGE | SUPPLY_CHAIN\n                                  | EARNINGS_PREVIEW | PARTNERSHIP | REGULATORY | QUANTUM_NEWS\n                                  | AI_INFRASTRUCTURE | GENERAL',
  `content_hash` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'SHA256(source + article_url) â€” dedup key for re-runs',
  `fetched_at` datetime NOT NULL COMMENT 'SGT wall-clock time row was written',
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tech_pub_hash` (`content_hash`),
  KEY `idx_tech_pub_source` (`source`),
  KEY `idx_tech_pub_date` (`snapshot_date`),
  KEY `idx_tech_pub_published` (`published_at`),
  KEY `idx_tech_pub_sentiment` (`sentiment_label`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Gap 4: Tech industry publication RSS signals.\n           Hardware, semiconductor, AI, quantum publications that lead\n           Reuters/CNBC by 2-6 hours on product and conference news.\n           Populated by fetch_tech_publications.py.\n           Gap Report: gap_report_20260602_230000';

-- Table: telegram_delivery_archive
CREATE TABLE IF NOT EXISTS `telegram_delivery_archive` (
  `id` int NOT NULL AUTO_INCREMENT,
  `delivery_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `report_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `delivered_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `chat_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `message_text` text COLLATE utf8mb4_unicode_ci,
  `char_count` int DEFAULT NULL,
  `chunk_count` int DEFAULT NULL,
  `delivery_status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'sent',
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `delivery_id` (`delivery_id`),
  KEY `idx_telegram_delivered_at` (`delivered_at` DESC),
  KEY `idx_telegram_report_id` (`report_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: thesis_lifecycle
CREATE TABLE IF NOT EXISTS `thesis_lifecycle` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `thesis_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `thesis_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'v1.0',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ACTIVE',
  `priority` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'P2',
  `base_probability` decimal(8,6) DEFAULT NULL,
  `current_probability` decimal(8,6) DEFAULT NULL,
  `confidence` decimal(8,6) DEFAULT NULL,
  `direction` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `horizon_days` int DEFAULT NULL,
  `thesis_json` json NOT NULL,
  `evidence_json` json DEFAULT NULL,
  `contradiction_json` json DEFAULT NULL,
  `kill_condition` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `thesis_id` (`thesis_id`),
  KEY `idx_tl_status_priority` (`status`,`priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: thesis_ticker_links
CREATE TABLE IF NOT EXISTS `thesis_ticker_links` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `thesis_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'linked',
  `weight` decimal(8,6) DEFAULT NULL,
  `rationale` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ttl_thesis_ticker` (`thesis_id`,`ticker`),
  KEY `idx_ttl_ticker` (`ticker`),
  CONSTRAINT `fk_ttl_thesis` FOREIGN KEY (`thesis_id`) REFERENCES `thesis_lifecycle` (`thesis_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: ticker_capital_flow
CREATE TABLE IF NOT EXISTS `ticker_capital_flow` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticker` varchar(10) NOT NULL,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `source` varchar(50) NOT NULL DEFAULT 'Moomoo_CapitalFlow',
  `main_in` decimal(20,2) DEFAULT NULL COMMENT 'Main force inflow USD',
  `main_out` decimal(20,2) DEFAULT NULL COMMENT 'Main force outflow USD',
  `main_net` decimal(20,2) DEFAULT NULL COMMENT 'Main force net flow USD',
  `main_net_ratio` decimal(10,4) DEFAULT NULL COMMENT 'Net flow as % of total flow',
  `super_large_in` decimal(20,2) DEFAULT NULL COMMENT 'Super-large lot inflow USD',
  `super_large_out` decimal(20,2) DEFAULT NULL COMMENT 'Super-large lot outflow USD',
  `super_large_net` decimal(20,2) DEFAULT NULL COMMENT 'Super-large lot net flow USD',
  `large_in` decimal(20,2) DEFAULT NULL COMMENT 'Large lot inflow USD',
  `large_out` decimal(20,2) DEFAULT NULL COMMENT 'Large lot outflow USD',
  `large_net` decimal(20,2) DEFAULT NULL COMMENT 'Large lot net flow USD',
  `medium_in` decimal(20,2) DEFAULT NULL COMMENT 'Medium lot inflow USD',
  `medium_out` decimal(20,2) DEFAULT NULL COMMENT 'Medium lot outflow USD',
  `medium_net` decimal(20,2) DEFAULT NULL COMMENT 'Medium lot net flow USD',
  `small_in` decimal(20,2) DEFAULT NULL COMMENT 'Small lot (retail) inflow USD',
  `small_out` decimal(20,2) DEFAULT NULL COMMENT 'Small lot outflow USD',
  `small_net` decimal(20,2) DEFAULT NULL COMMENT 'Small lot net flow USD',
  `institutional_bias` varchar(10) DEFAULT NULL COMMENT 'ACCUMULATE / DISTRIBUTE / NEUTRAL',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cf_ticker_date` (`ticker`,`snapshot_date`),
  KEY `idx_cf_ticker` (`ticker`),
  KEY `idx_cf_date` (`snapshot_date` DESC),
  KEY `idx_cf_net` (`main_net`),
  KEY `idx_cf_bias` (`institutional_bias`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Daily capital flow by lot size per ticker â€” institutional vs retail';

-- Table: ticker_earnings
CREATE TABLE IF NOT EXISTS `ticker_earnings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticker` varchar(10) NOT NULL,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `source` varchar(50) NOT NULL DEFAULT 'Moomoo_Earnings',
  `next_earnings_date` date DEFAULT NULL COMMENT 'Next scheduled earnings date',
  `days_to_earnings` int DEFAULT NULL COMMENT 'Days until next earnings (computed)',
  `earnings_quarter` varchar(10) DEFAULT NULL COMMENT 'e.g. Q2 2026',
  `earnings_time` varchar(10) DEFAULT NULL COMMENT 'BMO / AMC / During',
  `eps_estimate` decimal(10,4) DEFAULT NULL COMMENT 'Consensus EPS estimate',
  `eps_estimate_high` decimal(10,4) DEFAULT NULL COMMENT 'High EPS estimate',
  `eps_estimate_low` decimal(10,4) DEFAULT NULL COMMENT 'Low EPS estimate',
  `revenue_estimate` decimal(20,2) DEFAULT NULL COMMENT 'Consensus revenue estimate USD',
  `eps_actual_last` decimal(10,4) DEFAULT NULL COMMENT 'Last quarter actual EPS',
  `eps_surprise_pct` decimal(10,4) DEFAULT NULL COMMENT 'Last quarter EPS surprise %',
  `revenue_actual_last` decimal(20,2) DEFAULT NULL COMMENT 'Last quarter actual revenue USD',
  `earnings_catalyst` tinyint(1) NOT NULL DEFAULT '0' COMMENT '1 = earnings within 30 days',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_earn_ticker_date` (`ticker`,`snapshot_date`),
  KEY `idx_earn_ticker` (`ticker`),
  KEY `idx_earn_date` (`snapshot_date` DESC),
  KEY `idx_earn_next` (`next_earnings_date`),
  KEY `idx_earn_catalyst` (`earnings_catalyst`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Earnings estimates and calendar per ticker';

-- Table: ticker_forecasts
CREATE TABLE IF NOT EXISTS `ticker_forecasts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `forecast_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `forecast_date` datetime DEFAULT NULL,
  `ticker` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `company_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sector` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `live_price` decimal(12,4) DEFAULT NULL,
  `bl_target` decimal(12,4) DEFAULT NULL,
  `analyst_consensus` decimal(12,4) DEFAULT NULL,
  `analyst_count` int DEFAULT NULL,
  `bl_upside_pct` decimal(7,2) DEFAULT NULL,
  `analyst_upside_pct` decimal(7,2) DEFAULT NULL,
  `bl_vs_analyst_pct` decimal(7,2) DEFAULT NULL,
  `conviction_fi` decimal(3,2) DEFAULT NULL,
  `rating` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `valuation_stretch` tinyint(1) DEFAULT '0',
  `eps_estimate` decimal(10,4) DEFAULT NULL,
  `pe_applied` decimal(6,2) DEFAULT NULL,
  `macro_adjustment` decimal(5,2) DEFAULT NULL,
  `safety_margin` decimal(4,2) DEFAULT NULL,
  `rationale` text COLLATE utf8mb4_unicode_ci,
  `brier_baseline_price` decimal(12,4) DEFAULT NULL,
  `brier_resolution_date` date DEFAULT NULL,
  `brier_resolved` tinyint(1) DEFAULT '0',
  `brier_hit` tinyint(1) DEFAULT NULL,
  `brier_score` decimal(6,4) DEFAULT NULL,
  `resolution_method` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `model_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `snapshot_id` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dataset_generated_at` datetime DEFAULT NULL,
  `dataset_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `current_price` decimal(18,6) DEFAULT NULL,
  `prediction_method` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `forecast_direction` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_price_7d` decimal(18,6) DEFAULT NULL,
  `target_price_14d` decimal(18,6) DEFAULT NULL,
  `target_price_30d` decimal(18,6) DEFAULT NULL,
  `target_price_60d` decimal(18,6) DEFAULT NULL,
  `target_price_90d` decimal(18,6) DEFAULT NULL,
  `probability_7d` decimal(8,4) DEFAULT NULL,
  `probability_14d` decimal(8,4) DEFAULT NULL,
  `probability_30d` decimal(8,4) DEFAULT NULL,
  `probability_60d` decimal(8,4) DEFAULT NULL,
  `probability_90d` decimal(8,4) DEFAULT NULL,
  `expected_return_7d` decimal(10,4) DEFAULT NULL,
  `expected_return_14d` decimal(10,4) DEFAULT NULL,
  `expected_return_30d` decimal(10,4) DEFAULT NULL,
  `expected_return_60d` decimal(10,4) DEFAULT NULL,
  `expected_return_90d` decimal(10,4) DEFAULT NULL,
  `confidence` decimal(8,4) DEFAULT NULL,
  `bluelotus_score` decimal(10,4) DEFAULT NULL,
  `analyst_target` decimal(18,6) DEFAULT NULL,
  `regime` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sector_theme` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `method_basis` text COLLATE utf8mb4_unicode_ci,
  `risk_notes` text COLLATE utf8mb4_unicode_ci,
  `source_dataset_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_by` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `forecast_json` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forecast_id` (`forecast_id`),
  UNIQUE KEY `uq_tf_snapshot_ticker_method` (`snapshot_id`,`ticker`,`prediction_method`),
  KEY `idx_forecast_date` (`forecast_date` DESC),
  KEY `idx_forecast_ticker` (`ticker`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: ticker_fundamentals
CREATE TABLE IF NOT EXISTS `ticker_fundamentals` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticker` varchar(10) NOT NULL,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `source` varchar(50) NOT NULL DEFAULT 'Moomoo_Fundamentals',
  `pe_ttm` decimal(10,4) DEFAULT NULL COMMENT 'Price/Earnings trailing 12M',
  `pe_forward` decimal(10,4) DEFAULT NULL COMMENT 'Forward P/E estimate',
  `pb_ratio` decimal(10,4) DEFAULT NULL COMMENT 'Price to Book ratio',
  `ps_ratio` decimal(10,4) DEFAULT NULL COMMENT 'Price to Sales trailing 12M',
  `ev_ebitda` decimal(10,4) DEFAULT NULL COMMENT 'EV / EBITDA',
  `roe` decimal(10,4) DEFAULT NULL COMMENT 'Return on Equity (%)',
  `roa` decimal(10,4) DEFAULT NULL COMMENT 'Return on Assets (%)',
  `rotce` decimal(10,4) DEFAULT NULL COMMENT 'Return on Tangible Common Equity (banks)',
  `net_profit_margin` decimal(10,4) DEFAULT NULL COMMENT 'Net profit margin (%)',
  `revenue_ttm` decimal(20,2) DEFAULT NULL COMMENT 'Revenue trailing 12M',
  `net_income_ttm` decimal(20,2) DEFAULT NULL COMMENT 'Net income trailing 12M',
  `eps_ttm` decimal(10,4) DEFAULT NULL COMMENT 'EPS trailing 12M',
  `eps_forward` decimal(10,4) DEFAULT NULL COMMENT 'Forward EPS estimate',
  `eps_surprise_last` decimal(10,4) DEFAULT NULL COMMENT 'Last quarter EPS surprise %',
  `market_cap` decimal(20,2) DEFAULT NULL COMMENT 'Market cap USD',
  `shares_outstanding` decimal(20,2) DEFAULT NULL COMMENT 'Total shares outstanding',
  `debt_to_equity` decimal(10,4) DEFAULT NULL COMMENT 'Debt/Equity ratio',
  `current_ratio` decimal(10,4) DEFAULT NULL COMMENT 'Current ratio',
  `dividend_yield` decimal(10,4) DEFAULT NULL COMMENT 'Dividend yield (%)',
  `beta` decimal(10,4) DEFAULT NULL COMMENT 'Beta vs S&P 500',
  `high_52w` decimal(12,4) DEFAULT NULL COMMENT '52-week high price',
  `low_52w` decimal(12,4) DEFAULT NULL COMMENT '52-week low price',
  `avg_volume_30d` decimal(20,2) DEFAULT NULL COMMENT '30-day average daily volume',
  `pct_from_52w_high` decimal(10,4) DEFAULT NULL COMMENT '% below 52-week high (computed)',
  `pct_from_52w_low` decimal(10,4) DEFAULT NULL COMMENT '% above 52-week low (computed)',
  `earnings_yield` decimal(10,4) DEFAULT NULL COMMENT '1/PE â€” forward earnings yield (%)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ticker_date` (`ticker`,`snapshot_date`),
  KEY `idx_fund_ticker` (`ticker`),
  KEY `idx_fund_date` (`snapshot_date` DESC),
  KEY `idx_fund_pb` (`pb_ratio`),
  KEY `idx_fund_pe` (`pe_ttm`),
  KEY `idx_fund_roe` (`roe`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Daily fundamental valuation data per ticker â€” all 83 watchlist';

-- Table: ticker_short_interest
CREATE TABLE IF NOT EXISTS `ticker_short_interest` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticker` varchar(10) NOT NULL,
  `snapshot_date` date NOT NULL,
  `cycle_ts` datetime NOT NULL,
  `source` varchar(50) NOT NULL DEFAULT 'Moomoo_ShortInterest',
  `short_volume` decimal(20,2) DEFAULT NULL COMMENT 'Short sale volume shares',
  `short_volume_ratio` decimal(10,4) DEFAULT NULL COMMENT 'Short volume as % of total volume',
  `short_interest` decimal(20,2) DEFAULT NULL COMMENT 'Total short interest shares',
  `days_to_cover` decimal(10,4) DEFAULT NULL COMMENT 'Short interest / avg 30d volume',
  `short_signal` varchar(20) DEFAULT NULL COMMENT 'HIGH / MEDIUM / LOW short pressure',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_si_ticker_date` (`ticker`,`snapshot_date`),
  KEY `idx_si_ticker` (`ticker`),
  KEY `idx_si_date` (`snapshot_date` DESC),
  KEY `idx_si_ratio` (`short_volume_ratio`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Daily short interest data per ticker';

-- Table: extraction_audit_log
CREATE TABLE IF NOT EXISTS `extraction_audit_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `audit_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `raw_ingestion_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `extracted_event_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extracted_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `extraction_model` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extraction_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extraction_duration_ms` int DEFAULT NULL,
  `extracted_category` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extracted_entities` json DEFAULT NULL,
  `extracted_trust_score` decimal(3,2) DEFAULT NULL,
  `extracted_impact_score` decimal(3,2) DEFAULT NULL,
  `extracted_regime` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extraction_confidence` decimal(3,2) DEFAULT NULL,
  `validation_passed` tinyint(1) DEFAULT NULL,
  `validation_errors` json DEFAULT NULL,
  `human_corrected` tinyint(1) DEFAULT '0',
  `correction_actor` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `corrected_category` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `corrected_entities` json DEFAULT NULL,
  `correction_notes` text COLLATE utf8mb4_unicode_ci,
  `corrected_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `audit_id` (`audit_id`),
  KEY `idx_extract_audit_raw` (`raw_ingestion_id`),
  KEY `idx_extract_audit_model` (`extraction_model`),
  KEY `idx_extract_audit_corrected` (`human_corrected`),
  CONSTRAINT `fk_extraction_raw` FOREIGN KEY (`raw_ingestion_id`) REFERENCES `raw_signal_archive` (`ingestion_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: forecast_resolutions
CREATE TABLE IF NOT EXISTS `forecast_resolutions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `forecast_id` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `snapshot_id` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ticker` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prediction_method` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `horizon_days` int NOT NULL,
  `forecast_date` datetime NOT NULL,
  `resolution_date` datetime NOT NULL,
  `current_price` decimal(18,6) NOT NULL,
  `predicted_price` decimal(18,6) DEFAULT NULL,
  `actual_price` decimal(18,6) DEFAULT NULL,
  `forecast_direction` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `forecast_probability` decimal(8,4) DEFAULT NULL,
  `actual_outcome` tinyint DEFAULT NULL,
  `brier_score` decimal(12,8) DEFAULT NULL,
  `absolute_error` decimal(18,6) DEFAULT NULL,
  `percentage_error` decimal(12,8) DEFAULT NULL,
  `expected_return_pct` decimal(10,4) DEFAULT NULL,
  `actual_return_pct` decimal(10,4) DEFAULT NULL,
  `directional_correct` tinyint DEFAULT NULL,
  `resolution_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fr_forecast_horizon` (`forecast_id`,`horizon_days`),
  KEY `idx_fr_ticker` (`ticker`),
  KEY `idx_fr_method_horizon` (`prediction_method`,`horizon_days`),
  KEY `idx_fr_resolution_date` (`resolution_date`),
  CONSTRAINT `fk_fr_forecast` FOREIGN KEY (`forecast_id`) REFERENCES `ticker_forecasts` (`forecast_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: institutional_quant_process_results
CREATE TABLE IF NOT EXISTS `institutional_quant_process_results` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `process_name` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL,
  `process_version` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `process_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `readiness_score` decimal(6,3) DEFAULT NULL,
  `readiness_label` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_json` json NOT NULL,
  `metrics_json` json DEFAULT NULL,
  `warnings_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_iq_process_run_name` (`run_id`,`process_name`),
  KEY `idx_iq_process_name` (`process_name`),
  KEY `idx_iq_process_status` (`process_status`),
  CONSTRAINT `fk_iq_process_run` FOREIGN KEY (`run_id`) REFERENCES `institutional_quant_runs` (`run_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: market_events
CREATE TABLE IF NOT EXISTS `market_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ingestion_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `raw_ingestion_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_timestamp` datetime NOT NULL,
  `category` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `trust_score` decimal(3,2) DEFAULT NULL,
  `impact_score` decimal(3,2) DEFAULT NULL,
  `entities` json DEFAULT NULL,
  `regime_context` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headline` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `raw_text` text COLLATE utf8mb4_unicode_ci,
  `tags` json DEFAULT NULL,
  `extraction_confidence` decimal(3,2) DEFAULT NULL,
  `processed` tinyint(1) DEFAULT '0',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ingestion_id` (`ingestion_id`),
  KEY `idx_market_events_raw_id` (`raw_ingestion_id`),
  KEY `idx_market_events_timestamp` (`event_timestamp` DESC),
  KEY `idx_market_events_category` (`category`),
  CONSTRAINT `fk_raw_signal` FOREIGN KEY (`raw_ingestion_id`) REFERENCES `raw_signal_archive` (`ingestion_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: portfolio_readonly_positions
CREATE TABLE IF NOT EXISTS `portfolio_readonly_positions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `snapshot_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ticker` varchar(24) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `qty` decimal(20,6) NOT NULL DEFAULT '0.000000',
  `average_cost` decimal(20,6) DEFAULT NULL,
  `cost_price` decimal(20,6) DEFAULT NULL,
  `diluted_cost` decimal(20,6) DEFAULT NULL,
  `price` decimal(20,6) DEFAULT NULL,
  `market_value` decimal(20,4) DEFAULT NULL,
  `cost_basis` decimal(20,4) DEFAULT NULL,
  `unrealized_pnl` decimal(20,4) DEFAULT NULL,
  `unrealized_pnl_pct` decimal(12,6) DEFAULT NULL,
  `day_change_pct` decimal(12,6) DEFAULT NULL,
  `raw_position_json` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_prp_snapshot_ticker` (`snapshot_id`,`ticker`),
  KEY `idx_prp_ticker` (`ticker`),
  CONSTRAINT `fk_prp_snapshot` FOREIGN KEY (`snapshot_id`) REFERENCES `portfolio_readonly_snapshots` (`snapshot_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER //
-- Trigger: enforce_raw_immutability
CREATE TRIGGER IF NOT EXISTS `enforce_raw_immutability` BEFORE UPDATE ON `raw_signal_archive`
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
  SET MESSAGE_TEXT = 'raw_signal_archive is immutable. Records cannot be modified.';
END//

-- Trigger: enforce_raw_no_delete
CREATE TRIGGER IF NOT EXISTS `enforce_raw_no_delete` BEFORE DELETE ON `raw_signal_archive`
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000'
  SET MESSAGE_TEXT = 'raw_signal_archive is immutable. Records cannot be deleted.';
END//

DELIMITER ;

SET FOREIGN_KEY_CHECKS=1;

