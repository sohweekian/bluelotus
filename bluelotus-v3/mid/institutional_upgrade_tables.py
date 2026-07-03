#!/usr/bin/env python3
"""
BlueLotus MID -- institutional upgrade tables.

This module creates append-friendly tables for the V2 institutional upgrade:
- read-only broker portfolio snapshots
- Moomoo historical price bars
- history-based risk model runs
- research-only portfolio target runs
- thesis lifecycle state
- CIO strategic thinking / planning / execution journal
- monitoring alerts and lineage events

All tables are data/audit tables only. They do not contain order-routing
contracts and they do not authorize execution.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable


def project_root() -> Path:
    p = Path.cwd()
    if (p / "core").exists() or (p / "mid").exists():
        return p
    if p.name.lower() == "mid":
        return p.parent
    return Path(r"C:\bluelotus3")


DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS portfolio_readonly_snapshots (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL UNIQUE,
        cycle_ts DATETIME NOT NULL,
        broker VARCHAR(32) NOT NULL DEFAULT 'moomoo',
        data_source VARCHAR(64) NOT NULL DEFAULT 'OpenSecTradeContext',
        account_currency VARCHAR(16) NOT NULL DEFAULT 'USD',
        position_count INT NOT NULL DEFAULT 0,
        total_assets DECIMAL(20,4) NULL,
        cash DECIMAL(20,4) NULL,
        buying_power DECIMAL(20,4) NULL,
        market_value DECIMAL(20,4) NULL,
        total_cost DECIMAL(20,4) NULL,
        total_pnl DECIMAL(20,4) NULL,
        total_pnl_pct DECIMAL(12,6) NULL,
        integrity_flag BOOLEAN NOT NULL DEFAULT FALSE,
        integrity_reason TEXT NULL,
        read_only_protocol_json JSON NOT NULL,
        account_raw_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_prs_cycle_ts (cycle_ts),
        KEY idx_prs_integrity (integrity_flag)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_readonly_positions (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL,
        ticker VARCHAR(24) NOT NULL,
        code VARCHAR(32) NULL,
        qty DECIMAL(20,6) NOT NULL DEFAULT 0,
        average_cost DECIMAL(20,6) NULL,
        cost_price DECIMAL(20,6) NULL,
        diluted_cost DECIMAL(20,6) NULL,
        price DECIMAL(20,6) NULL,
        market_value DECIMAL(20,4) NULL,
        cost_basis DECIMAL(20,4) NULL,
        unrealized_pnl DECIMAL(20,4) NULL,
        unrealized_pnl_pct DECIMAL(12,6) NULL,
        day_change_pct DECIMAL(12,6) NULL,
        raw_position_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_prp_snapshot_ticker (snapshot_id, ticker),
        KEY idx_prp_ticker (ticker),
        CONSTRAINT fk_prp_snapshot
            FOREIGN KEY (snapshot_id)
            REFERENCES portfolio_readonly_snapshots(snapshot_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS historical_prices (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(24) NOT NULL,
        code VARCHAR(32) NULL,
        bar_date DATE NOT NULL,
        time_key VARCHAR(32) NOT NULL,
        ktype VARCHAR(16) NOT NULL DEFAULT 'K_DAY',
        autype VARCHAR(16) NOT NULL DEFAULT 'QFQ',
        open_price DECIMAL(20,6) NULL,
        high_price DECIMAL(20,6) NULL,
        low_price DECIMAL(20,6) NULL,
        close_price DECIMAL(20,6) NULL,
        volume BIGINT NULL,
        turnover DECIMAL(24,6) NULL,
        change_rate DECIMAL(12,6) NULL,
        raw_bar_json JSON NULL,
        fetched_at DATETIME NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_hp_ticker_date_type (ticker, bar_date, ktype, autype),
        KEY idx_hp_ticker_date (ticker, bar_date),
        KEY idx_hp_fetched_at (fetched_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_model_runs (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL UNIQUE,
        generated_at DATETIME NOT NULL,
        source_snapshot_id VARCHAR(64) NULL,
        price_start DATE NULL,
        price_end DATE NULL,
        lookback_days INT NULL,
        position_count INT NOT NULL DEFAULT 0,
        portfolio_value DECIMAL(20,4) NULL,
        historical_var_95 DECIMAL(20,6) NULL,
        historical_var_99 DECIMAL(20,6) NULL,
        expected_shortfall_95 DECIMAL(20,6) NULL,
        volatility_annualized DECIMAL(12,6) NULL,
        max_drawdown DECIMAL(12,6) NULL,
        beta_to_spy DECIMAL(12,6) NULL,
        metrics_json JSON NOT NULL,
        positions_json JSON NULL,
        factor_exposures_json JSON NULL,
        correlation_json JSON NULL,
        breaches_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_rmr_generated_at (generated_at),
        KEY idx_rmr_snapshot (source_snapshot_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_optimizer_runs (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL UNIQUE,
        generated_at DATETIME NOT NULL,
        source_snapshot_id VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL,
        objective VARCHAR(255) NOT NULL,
        current_weights_json JSON NOT NULL,
        target_weights_json JSON NOT NULL,
        constraints_json JSON NOT NULL,
        actions_json JSON NULL,
        notes TEXT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_por_generated_at (generated_at),
        KEY idx_por_snapshot (source_snapshot_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS thesis_lifecycle (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        thesis_id VARCHAR(64) NOT NULL UNIQUE,
        thesis_name VARCHAR(255) NOT NULL,
        version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
        status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
        priority VARCHAR(16) NOT NULL DEFAULT 'P2',
        base_probability DECIMAL(8,6) NULL,
        current_probability DECIMAL(8,6) NULL,
        confidence DECIMAL(8,6) NULL,
        direction VARCHAR(64) NULL,
        horizon_days INT NULL,
        thesis_json JSON NOT NULL,
        evidence_json JSON NULL,
        contradiction_json JSON NULL,
        kill_condition TEXT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_tl_status_priority (status, priority)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS thesis_ticker_links (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        thesis_id VARCHAR(64) NOT NULL,
        ticker VARCHAR(24) NOT NULL,
        role VARCHAR(64) NOT NULL DEFAULT 'linked',
        weight DECIMAL(8,6) NULL,
        rationale TEXT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ttl_thesis_ticker (thesis_id, ticker),
        KEY idx_ttl_ticker (ticker),
        CONSTRAINT fk_ttl_thesis
            FOREIGN KEY (thesis_id)
            REFERENCES thesis_lifecycle(thesis_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS cio_cognition_journal (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        journal_id VARCHAR(96) NOT NULL UNIQUE,
        journal_ts DATETIME NOT NULL,
        source_cycle_ts DATETIME NULL,
        source_report_archive_id BIGINT NULL,
        source_dataset_sha256 CHAR(64) NULL,
        entry_type VARCHAR(48) NOT NULL DEFAULT 'CIO_DAILY_REVIEW',
        status VARCHAR(48) NOT NULL DEFAULT 'RECORDED',
        priority VARCHAR(16) NOT NULL DEFAULT 'P2',
        regime VARCHAR(64) NULL,
        cio_action VARCHAR(64) NULL,
        confidence DECIMAL(8,6) NULL,
        strategic_thinking TEXT NULL,
        planning TEXT NULL,
        execution_intent TEXT NULL,
        non_execution_rationale TEXT NULL,
        key_risks_json JSON NULL,
        evidence_refs_json JSON NULL,
        linked_theses_json JSON NULL,
        linked_decisions_json JSON NULL,
        follow_up_json JSON NULL,
        author VARCHAR(128) NOT NULL DEFAULT 'CIO',
        execution_authority VARCHAR(64) NOT NULL DEFAULT 'CIO_ONLY_MANUAL',
        order_generated BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_ccj_journal_ts (journal_ts),
        KEY idx_ccj_status_priority (status, priority),
        KEY idx_ccj_report_archive (source_report_archive_id),
        KEY idx_ccj_dataset_sha (source_dataset_sha256)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS cio_thesis_reviews (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        review_id VARCHAR(128) NOT NULL UNIQUE,
        journal_id VARCHAR(96) NOT NULL,
        thesis_id VARCHAR(64) NOT NULL,
        review_ts DATETIME NOT NULL,
        status_at_review VARCHAR(32) NULL,
        probability_at_review DECIMAL(8,6) NULL,
        confidence_at_review DECIMAL(8,6) NULL,
        cio_assessment VARCHAR(64) NOT NULL DEFAULT 'WATCH',
        strategic_note TEXT NULL,
        planning_note TEXT NULL,
        execution_note TEXT NULL,
        kill_condition_review TEXT NULL,
        repeatability_hypothesis TEXT NULL,
        mistake_risk TEXT NULL,
        evidence_json JSON NULL,
        contradiction_json JSON NULL,
        follow_up_json JSON NULL,
        author VARCHAR(128) NOT NULL DEFAULT 'CIO',
        execution_authority VARCHAR(64) NOT NULL DEFAULT 'CIO_ONLY_MANUAL',
        order_generated BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_ctr_journal (journal_id),
        KEY idx_ctr_thesis (thesis_id),
        KEY idx_ctr_review_ts (review_ts),
        CONSTRAINT fk_ctr_journal
            FOREIGN KEY (journal_id)
            REFERENCES cio_cognition_journal(journal_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS monitoring_alerts (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        alert_id VARCHAR(64) NOT NULL UNIQUE,
        cycle_ts DATETIME NOT NULL,
        severity VARCHAR(24) NOT NULL,
        layer_name VARCHAR(64) NOT NULL,
        alert_type VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        message TEXT NOT NULL,
        related_ticker VARCHAR(24) NULL,
        payload_json JSON NULL,
        resolved BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_ma_cycle_ts (cycle_ts),
        KEY idx_ma_severity (severity),
        KEY idx_ma_layer (layer_name),
        KEY idx_ma_related_ticker (related_ticker)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS data_lineage_events (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        event_id VARCHAR(64) NOT NULL UNIQUE,
        cycle_ts DATETIME NOT NULL,
        stage VARCHAR(64) NOT NULL,
        input_refs_json JSON NULL,
        output_refs_json JSON NULL,
        dataset_sha256 CHAR(64) NULL,
        notes TEXT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_dle_cycle_ts (cycle_ts),
        KEY idx_dle_stage (stage),
        KEY idx_dle_dataset_sha (dataset_sha256)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS security_listing_status (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(24) NOT NULL,
        code VARCHAR(32) NOT NULL,
        snapshot_date DATE NOT NULL,
        name VARCHAR(255) NULL,
        security_type VARCHAR(64) NULL,
        exchange_type VARCHAR(64) NULL,
        owner_market VARCHAR(64) NULL,
        listing_date VARCHAR(64) NULL,
        delisting_flag BOOLEAN NOT NULL DEFAULT FALSE,
        listing_status VARCHAR(64) NULL,
        raw_json JSON NOT NULL,
        fetched_at DATETIME NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_sls_ticker_snapshot (ticker, snapshot_date),
        KEY idx_sls_ticker (ticker),
        KEY idx_sls_delisting (delisting_flag)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS corporate_actions (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        action_id VARCHAR(96) NOT NULL UNIQUE,
        ticker VARCHAR(24) NOT NULL,
        code VARCHAR(32) NOT NULL,
        action_type VARCHAR(32) NOT NULL,
        event_date DATE NULL,
        ex_date DATE NULL,
        record_date DATE NULL,
        pay_date DATE NULL,
        statement TEXT NULL,
        ratio_text VARCHAR(128) NULL,
        amount DECIMAL(20,8) NULL,
        currency VARCHAR(16) NULL,
        raw_json JSON NOT NULL,
        fetched_at DATETIME NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_ca_ticker_date (ticker, event_date),
        KEY idx_ca_type (action_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS freshness_recovery_runs (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL UNIQUE,
        cycle_ts DATETIME NOT NULL,
        dataset_generated_at DATETIME NULL,
        market_session VARCHAR(32) NULL,
        stale_sections_json JSON NULL,
        market_closed_deferred_json JSON NULL,
        attempted_modules_json JSON NULL,
        command_results_json JSON NULL,
        unresolved_sections_json JSON NULL,
        status VARCHAR(32) NOT NULL,
        summary_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_frr_cycle_ts (cycle_ts),
        KEY idx_frr_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS historical_backfill_queue (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(24) NOT NULL UNIQUE,
        universe_source VARCHAR(64) NOT NULL DEFAULT 'grand_universe_200',
        priority INT NOT NULL DEFAULT 5,
        desired_days INT NOT NULL DEFAULT 180,
        min_rows INT NOT NULL DEFAULT 90,
        row_count INT NOT NULL DEFAULT 0,
        first_bar_date DATE NULL,
        latest_bar_date DATE NULL,
        latest_fetch_at DATETIME NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
        attempt_count INT NOT NULL DEFAULT 0,
        last_attempt_at DATETIME NULL,
        last_success_at DATETIME NULL,
        last_error TEXT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_hbq_status_priority (status, priority, last_attempt_at),
        KEY idx_hbq_latest_bar (latest_bar_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS historical_backfill_runs (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL UNIQUE,
        cycle_ts DATETIME NOT NULL,
        status VARCHAR(32) NOT NULL,
        batch_size INT NOT NULL DEFAULT 0,
        selected_tickers_json JSON NULL,
        command_json JSON NULL,
        command_exit_code INT NULL,
        coverage_json JSON NULL,
        summary_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_hbr_cycle_ts (cycle_ts),
        KEY idx_hbr_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS cio_decision_journal (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        decision_id VARCHAR(96) NOT NULL UNIQUE,
        decision_ts DATETIME NOT NULL,
        source_run_id VARCHAR(64) NULL,
        decision_type VARCHAR(64) NOT NULL,
        status VARCHAR(48) NOT NULL DEFAULT 'RESEARCH_PENDING_CIO_REVIEW',
        priority VARCHAR(16) NOT NULL DEFAULT 'P2',
        ticker VARCHAR(24) NULL,
        thesis_id VARCHAR(64) NULL,
        current_weight DECIMAL(12,6) NULL,
        target_weight DECIMAL(12,6) NULL,
        delta_weight DECIMAL(12,6) NULL,
        research_recommendation_json JSON NOT NULL,
        cio_decision VARCHAR(64) NULL,
        cio_notes TEXT NULL,
        execution_authority VARCHAR(64) NOT NULL DEFAULT 'CIO_ONLY_MANUAL',
        order_generated BOOLEAN NOT NULL DEFAULT FALSE,
        order_reference VARCHAR(128) NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_cdj_decision_ts (decision_ts),
        KEY idx_cdj_status_priority (status, priority),
        KEY idx_cdj_ticker (ticker),
        KEY idx_cdj_thesis (thesis_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_readonly_snapshots (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL UNIQUE,
        cycle_ts DATETIME NOT NULL,
        broker VARCHAR(32) NOT NULL DEFAULT 'moomoo',
        data_source VARCHAR(96) NOT NULL,
        trd_env VARCHAR(24) NOT NULL DEFAULT 'REAL',
        market VARCHAR(24) NOT NULL DEFAULT 'US',
        start_date DATE NULL,
        end_date DATE NULL,
        open_order_count INT NOT NULL DEFAULT 0,
        historical_order_count INT NOT NULL DEFAULT 0,
        open_deal_count INT NOT NULL DEFAULT 0,
        historical_deal_count INT NOT NULL DEFAULT 0,
        fee_record_count INT NOT NULL DEFAULT 0,
        query_errors_json JSON NULL,
        read_only_protocol_json JSON NOT NULL,
        summary_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_ers_cycle_ts (cycle_ts),
        KEY idx_ers_counts (historical_order_count, historical_deal_count)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_readonly_orders (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL,
        order_scope VARCHAR(24) NOT NULL,
        order_id VARCHAR(128) NOT NULL,
        code VARCHAR(32) NULL,
        ticker VARCHAR(24) NULL,
        trd_side VARCHAR(32) NULL,
        order_type VARCHAR(64) NULL,
        order_status VARCHAR(64) NULL,
        qty DECIMAL(20,6) NULL,
        price DECIMAL(20,6) NULL,
        dealt_qty DECIMAL(20,6) NULL,
        dealt_avg_price DECIMAL(20,6) NULL,
        create_time DATETIME NULL,
        updated_time DATETIME NULL,
        raw_order_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ero_snapshot_scope_order (snapshot_id, order_scope, order_id),
        KEY idx_ero_ticker (ticker),
        KEY idx_ero_order_status (order_status),
        KEY idx_ero_create_time (create_time),
        CONSTRAINT fk_ero_snapshot
            FOREIGN KEY (snapshot_id)
            REFERENCES execution_readonly_snapshots(snapshot_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_readonly_deals (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL,
        deal_scope VARCHAR(24) NOT NULL,
        deal_id VARCHAR(128) NOT NULL,
        order_id VARCHAR(128) NULL,
        code VARCHAR(32) NULL,
        ticker VARCHAR(24) NULL,
        trd_side VARCHAR(32) NULL,
        qty DECIMAL(20,6) NULL,
        price DECIMAL(20,6) NULL,
        deal_time DATETIME NULL,
        raw_deal_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_erd_snapshot_scope_deal (snapshot_id, deal_scope, deal_id),
        KEY idx_erd_ticker (ticker),
        KEY idx_erd_order (order_id),
        KEY idx_erd_deal_time (deal_time),
        CONSTRAINT fk_erd_snapshot
            FOREIGN KEY (snapshot_id)
            REFERENCES execution_readonly_snapshots(snapshot_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_readonly_fees (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL,
        order_id VARCHAR(128) NOT NULL,
        fee_record_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_erf_snapshot_order (snapshot_id, order_id),
        CONSTRAINT fk_erf_snapshot
            FOREIGN KEY (snapshot_id)
            REFERENCES execution_readonly_snapshots(snapshot_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


def create_tables(statements: Iterable[str] = DDL) -> None:
    root = project_root()
    sys.path.insert(0, str(root))

    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(root / ".env")
    conn = get_connection()
    try:
        cur = conn.cursor()
        for sql in statements:
            cur.execute(sql)
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    create_tables()
    print("Institutional upgrade tables are ready.")


if __name__ == "__main__":
    main()

