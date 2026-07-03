#!/usr/bin/env python3
"""
BlueLotus MID -- Institutional Quant process tables.

Creates the small database layer used by institutional_quant_pipeline.py:
- immutable input dataset snapshots
- one row per institutional quant run
- one row per process result inside the run
- lightweight audit events

The tables are intentionally append-friendly and JSON-native. They do not
replace raw_signal_archive or the existing specialist tables; they add an
auditable process-result layer that export_dataset_raw.py can publish.
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
    CREATE TABLE IF NOT EXISTS institutional_dataset_snapshots (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        snapshot_id VARCHAR(64) NOT NULL UNIQUE,
        captured_at DATETIME NOT NULL,
        dataset_generated_at DATETIME NULL,
        export_version VARCHAR(32) NULL,
        ingest_version VARCHAR(32) NULL,
        dataset_sha256 CHAR(64) NOT NULL,
        dataset_path VARCHAR(500) NULL,
        dataset_json JSON NOT NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_iq_dataset_generated_at (dataset_generated_at),
        KEY idx_iq_dataset_sha256 (dataset_sha256)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS institutional_quant_runs (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL UNIQUE,
        run_version VARCHAR(32) NOT NULL,
        run_status VARCHAR(32) NOT NULL,
        started_at DATETIME NOT NULL,
        completed_at DATETIME NULL,
        snapshot_id VARCHAR(64) NOT NULL,
        dataset_generated_at DATETIME NULL,
        dataset_export_version VARCHAR(32) NULL,
        dataset_ingest_version VARCHAR(32) NULL,
        dataset_sha256 CHAR(64) NOT NULL,
        dataset_snapshot_path VARCHAR(500) NULL,
        total_processes INT NOT NULL DEFAULT 0,
        passed_processes INT NOT NULL DEFAULT 0,
        warning_processes INT NOT NULL DEFAULT 0,
        failed_processes INT NOT NULL DEFAULT 0,
        readiness_score DECIMAL(6,3) NULL,
        readiness_label VARCHAR(32) NULL,
        summary_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_iq_runs_completed (completed_at),
        KEY idx_iq_runs_status (run_status),
        KEY idx_iq_runs_snapshot (snapshot_id),
        CONSTRAINT fk_iq_runs_snapshot
            FOREIGN KEY (snapshot_id)
            REFERENCES institutional_dataset_snapshots(snapshot_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS institutional_quant_process_results (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL,
        process_name VARCHAR(96) NOT NULL,
        process_version VARCHAR(32) NOT NULL,
        process_status VARCHAR(32) NOT NULL,
        readiness_score DECIMAL(6,3) NULL,
        readiness_label VARCHAR(32) NULL,
        result_json JSON NOT NULL,
        metrics_json JSON NULL,
        warnings_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_iq_process_run_name (run_id, process_name),
        KEY idx_iq_process_name (process_name),
        KEY idx_iq_process_status (process_status),
        CONSTRAINT fk_iq_process_run
            FOREIGN KEY (run_id)
            REFERENCES institutional_quant_runs(run_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS institutional_quant_audit_events (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id VARCHAR(64) NULL,
        event_type VARCHAR(64) NOT NULL,
        severity VARCHAR(24) NOT NULL,
        message TEXT NOT NULL,
        payload_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_iq_audit_run (run_id),
        KEY idx_iq_audit_type (event_type),
        KEY idx_iq_audit_severity (severity)
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
    print("Institutional quant process tables are ready.")


if __name__ == "__main__":
    main()

