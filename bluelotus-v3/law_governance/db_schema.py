from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection


TABLES: Dict[str, str] = {
    "institutional_memory_registry": """
        CREATE TABLE IF NOT EXISTS institutional_memory_registry (
            memory_id VARCHAR(128) PRIMARY KEY,
            memory_type VARCHAR(64) NOT NULL,
            version VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            content_json LONGTEXT NOT NULL,
            content_hash CHAR(64) NOT NULL,
            summary TEXT NULL,
            artifact_path TEXT NULL,
            change_reason_code VARCHAR(64) NOT NULL,
            change_reason_text TEXT NOT NULL,
            supersedes_memory_id VARCHAR(128) NULL,
            approval_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
            approved_by VARCHAR(128) NULL,
            approved_at DATETIME NULL,
            requested_by VARCHAR(128) NULL,
            created_at DATETIME NOT NULL,
            effective_from DATETIME NULL,
            effective_to DATETIME NULL,
            UNIQUE KEY uq_memory_hash (memory_type, content_hash),
            KEY idx_memory_type_status (memory_type, status),
            KEY idx_memory_approval (approval_status),
            KEY idx_memory_effective (effective_from, effective_to)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "institutional_memory_change_log": """
        CREATE TABLE IF NOT EXISTS institutional_memory_change_log (
            change_id VARCHAR(128) PRIMARY KEY,
            memory_id VARCHAR(128) NOT NULL,
            memory_type VARCHAR(64) NOT NULL,
            change_type VARCHAR(64) NOT NULL,
            reason_code VARCHAR(64) NOT NULL,
            reason_text TEXT NOT NULL,
            diff_summary LONGTEXT NULL,
            evidence_refs LONGTEXT NULL,
            requested_by VARCHAR(128) NULL,
            approved_by VARCHAR(128) NULL,
            approved_at DATETIME NULL,
            created_at DATETIME NOT NULL,
            KEY idx_change_memory (memory_id),
            KEY idx_change_type (memory_type, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "institutional_governance_policy": """
        CREATE TABLE IF NOT EXISTS institutional_governance_policy (
            policy_id VARCHAR(128) PRIMARY KEY,
            policy_name VARCHAR(128) NOT NULL,
            policy_version VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            policy_json LONGTEXT NOT NULL,
            policy_hash CHAR(64) NOT NULL,
            created_at DATETIME NOT NULL,
            effective_from DATETIME NULL,
            effective_to DATETIME NULL,
            UNIQUE KEY uq_policy_hash (policy_name, policy_hash),
            KEY idx_policy_status (policy_name, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "report_memory_binding": """
        CREATE TABLE IF NOT EXISTS report_memory_binding (
            binding_id VARCHAR(128) PRIMARY KEY,
            report_id VARCHAR(128) NOT NULL,
            cycle_id VARCHAR(128) NULL,
            generated_at DATETIME NOT NULL,
            master_prompt_memory_id VARCHAR(128) NULL,
            cio_context_memory_id VARCHAR(128) NULL,
            chief_strategist_governance_memory_id VARCHAR(128) NULL,
            strategy_doctrine_memory_id VARCHAR(128) NULL,
            sleeve_rules_memory_id VARCHAR(128) NULL,
            kill_condition_memory_id VARCHAR(128) NULL,
            execution_doctrine_memory_id VARCHAR(128) NULL,
            source_priority_memory_id VARCHAR(128) NULL,
            active_pack_hash CHAR(64) NOT NULL,
            binding_hash CHAR(64) NOT NULL,
            binding_status VARCHAR(64) NOT NULL,
            binding_notes TEXT NULL,
            KEY idx_binding_report (report_id),
            KEY idx_binding_cycle (cycle_id),
            KEY idx_binding_status (binding_status),
            KEY idx_binding_generated (generated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "memory_activation_event": """
        CREATE TABLE IF NOT EXISTS memory_activation_event (
            event_id VARCHAR(128) PRIMARY KEY,
            memory_type VARCHAR(64) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            previous_active_memory_id VARCHAR(128) NULL,
            new_active_memory_id VARCHAR(128) NULL,
            performed_by VARCHAR(128) NULL,
            event_reason TEXT NULL,
            event_at DATETIME NOT NULL,
            active_pack_hash CHAR(64) NULL,
            KEY idx_activation_type (memory_type, event_at),
            KEY idx_activation_new (new_active_memory_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
}


def run_migrations() -> Dict[str, Any]:
    conn = get_v3_connection()
    applied: List[str] = []
    try:
        cur = conn.cursor()
        for table_name, sql in TABLES.items():
            cur.execute(sql)
            applied.append(table_name)
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return {"status": "PASS", "tables": applied}


def main() -> None:
    print(json.dumps(run_migrations(), indent=2))


if __name__ == "__main__":
    main()
