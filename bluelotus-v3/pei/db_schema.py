from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection


TABLES: Dict[str, str] = {
    "pei_event_registry": """
        CREATE TABLE IF NOT EXISTS pei_event_registry (
            event_id VARCHAR(128) PRIMARY KEY,
            event_type VARCHAR(64),
            event_title TEXT,
            event_timestamp_sgt VARCHAR(64),
            source_layer VARCHAR(128),
            source_confidence DOUBLE,
            event_status VARCHAR(64),
            affected_sleeves LONGTEXT,
            governing_thesis TEXT,
            resolution_date VARCHAR(64),
            resolution_status VARCHAR(64),
            governance_pack_id VARCHAR(128),
            report_memory_binding_id VARCHAR(128),
            created_at VARCHAR(64),
            updated_at VARCHAR(64)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "pei_event_branches": """
        CREATE TABLE IF NOT EXISTS pei_event_branches (
            branch_id VARCHAR(128) PRIMARY KEY,
            event_id VARCHAR(128),
            branch_name TEXT,
            branch_description TEXT,
            branch_probability DOUBLE,
            branch_time_horizon VARCHAR(64),
            evidence_for LONGTEXT,
            evidence_against LONGTEXT,
            confirmation_signals LONGTEXT,
            contradiction_signals LONGTEXT,
            kill_conditions LONGTEXT,
            affected_sleeves LONGTEXT,
            allowed_action TEXT,
            blocked_action TEXT,
            resolution_criteria LONGTEXT,
            resolution_status VARCHAR(64),
            KEY idx_pei_branch_event (event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "pei_event_branch_probabilities": "CREATE TABLE IF NOT EXISTS pei_event_branch_probabilities (id BIGINT AUTO_INCREMENT PRIMARY KEY, branch_id VARCHAR(128), event_id VARCHAR(128), probability DOUBLE, updated_at VARCHAR(64), evidence LONGTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_event_evidence": "CREATE TABLE IF NOT EXISTS pei_event_evidence (id BIGINT AUTO_INCREMENT PRIMARY KEY, event_id VARCHAR(128), branch_id VARCHAR(128), evidence_type VARCHAR(64), evidence_text TEXT, source_layer VARCHAR(128), created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_event_to_sleeve_map": "CREATE TABLE IF NOT EXISTS pei_event_to_sleeve_map (id BIGINT AUTO_INCREMENT PRIMARY KEY, event_id VARCHAR(128), branch_id VARCHAR(128), sleeve VARCHAR(128), expected_direction VARCHAR(64), confidence DOUBLE, transmission_channel VARCHAR(128), allowed_action TEXT, blocked_action TEXT, required_confirmation TEXT, kill_condition TEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_portfolio_playbooks": "CREATE TABLE IF NOT EXISTS pei_portfolio_playbooks (playbook_id VARCHAR(128) PRIMARY KEY, event_id VARCHAR(128), playbook_json LONGTEXT, created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_kill_condition_checks": "CREATE TABLE IF NOT EXISTS pei_kill_condition_checks (id BIGINT AUTO_INCREMENT PRIMARY KEY, event_id VARCHAR(128), branch_id VARCHAR(128), kill_condition TEXT, status VARCHAR(64), checked_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_forecast_registry": """
        CREATE TABLE IF NOT EXISTS pei_forecast_registry (
            forecast_id VARCHAR(128) PRIMARY KEY,
            event_id VARCHAR(128),
            branch_id VARCHAR(128),
            probability DOUBLE,
            forecast_timestamp_sgt VARCHAR(64),
            forecast_horizon VARCHAR(64),
            resolution_date VARCHAR(64),
            resolution_criteria LONGTEXT,
            model_version VARCHAR(64),
            governance_pack_id VARCHAR(128),
            report_memory_binding_id VARCHAR(128),
            cio_only_manual BOOLEAN,
            orders_generated INTEGER,
            routing_enabled BOOLEAN
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "pei_forecast_resolutions": "CREATE TABLE IF NOT EXISTS pei_forecast_resolutions (resolution_id VARCHAR(128) PRIMARY KEY, forecast_id VARCHAR(128), final_outcome INTEGER, resolved_at VARCHAR(64), resolution_source TEXT, notes TEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_brier_scores": "CREATE TABLE IF NOT EXISTS pei_brier_scores (id BIGINT AUTO_INCREMENT PRIMARY KEY, forecast_id VARCHAR(128), probability DOUBLE, outcome INTEGER, brier_score DOUBLE, log_score DOUBLE, scored_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_crs_decomposition": "CREATE TABLE IF NOT EXISTS pei_crs_decomposition (id BIGINT AUTO_INCREMENT PRIMARY KEY, sample_name VARCHAR(128), calibration DOUBLE, resolution_component DOUBLE, sharpness DOUBLE, uncertainty DOUBLE, created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_postmortems": "CREATE TABLE IF NOT EXISTS pei_postmortems (postmortem_id VARCHAR(128) PRIMARY KEY, forecast_id VARCHAR(128), label VARCHAR(128), notes TEXT, created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_reflexive_suppression_checks": "CREATE TABLE IF NOT EXISTS pei_reflexive_suppression_checks (check_id VARCHAR(128) PRIMARY KEY, ticker VARCHAR(24), classification VARCHAR(128), criteria_json LONGTEXT, action_mapping TEXT, created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_oscillation_engine_calibrations": "CREATE TABLE IF NOT EXISTS pei_oscillation_engine_calibrations (calibration_id VARCHAR(128) PRIMARY KEY, ticker VARCHAR(24), behavioral_mean DOUBLE, support_band_low DOUBLE, support_band_high DOUBLE, reload_zone TEXT, trim_zone TEXT, mean_reversion_confidence DOUBLE, regime_broken BOOLEAN, created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    "pei_backtest_runs": "CREATE TABLE IF NOT EXISTS pei_backtest_runs (backtest_id VARCHAR(128) PRIMARY KEY, strategy_name VARCHAR(128), run_json LONGTEXT, created_at VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
}


def run_migrations() -> Dict[str, Any]:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        for sql in TABLES.values():
            cur.execute(sql)
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return {"status": "PASS", "tables": sorted(TABLES)}


def main() -> None:
    print(json.dumps(run_migrations(), indent=2))


if __name__ == "__main__":
    main()
