#!/usr/bin/env python3
"""
BlueLotus MID -- Superforecast/Brier database tables.

Creates the append-friendly research forecast layer:
- ticker_forecasts: one forecast row per ticker/method/snapshot
- forecast_resolutions: one resolved horizon row per forecast/horizon

This is research-only infrastructure. It does not read, create, modify, cancel,
or route orders.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable


def project_root() -> Path:
    p = Path.cwd()
    if (p / "core").exists() or (p / "mid").exists():
        return p
    if p.name.lower() in {"mid", "research"}:
        return p.parent
    return Path(r"C:\bluelotus3")


DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ticker_forecasts (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        forecast_id VARCHAR(96) NOT NULL UNIQUE,
        snapshot_id VARCHAR(96) NOT NULL,
        forecast_date DATETIME NOT NULL,
        dataset_generated_at DATETIME NULL,
        dataset_sha256 CHAR(64) NULL,
        ticker VARCHAR(16) NOT NULL,
        current_price DECIMAL(18, 6) NOT NULL,
        prediction_method VARCHAR(64) NOT NULL,
        forecast_direction VARCHAR(16) NOT NULL,
        target_price_7d DECIMAL(18, 6) NULL,
        target_price_14d DECIMAL(18, 6) NULL,
        target_price_30d DECIMAL(18, 6) NULL,
        target_price_60d DECIMAL(18, 6) NULL,
        target_price_90d DECIMAL(18, 6) NULL,
        probability_7d DECIMAL(8, 4) NULL,
        probability_14d DECIMAL(8, 4) NULL,
        probability_30d DECIMAL(8, 4) NULL,
        probability_60d DECIMAL(8, 4) NULL,
        probability_90d DECIMAL(8, 4) NULL,
        expected_return_7d DECIMAL(10, 4) NULL,
        expected_return_14d DECIMAL(10, 4) NULL,
        expected_return_30d DECIMAL(10, 4) NULL,
        expected_return_60d DECIMAL(10, 4) NULL,
        expected_return_90d DECIMAL(10, 4) NULL,
        confidence DECIMAL(8, 4) NULL,
        bluelotus_score DECIMAL(10, 4) NULL,
        analyst_target DECIMAL(18, 6) NULL,
        analyst_upside_pct DECIMAL(10, 4) NULL,
        regime VARCHAR(64) NULL,
        sector_theme VARCHAR(128) NULL,
        method_basis TEXT NULL,
        risk_notes TEXT NULL,
        source_dataset_path VARCHAR(500) NULL,
        created_by VARCHAR(96) NOT NULL DEFAULT 'BlueLotus_Superforecast_Engine',
        forecast_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_tf_snapshot (snapshot_id),
        KEY idx_tf_ticker_date (ticker, forecast_date),
        KEY idx_tf_method_date (prediction_method, forecast_date),
        KEY idx_tf_direction (forecast_direction)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS forecast_resolutions (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        forecast_id VARCHAR(96) NOT NULL,
        snapshot_id VARCHAR(96) NOT NULL,
        ticker VARCHAR(16) NOT NULL,
        prediction_method VARCHAR(64) NOT NULL,
        horizon_days INT NOT NULL,
        forecast_date DATETIME NOT NULL,
        resolution_date DATETIME NOT NULL,
        current_price DECIMAL(18, 6) NOT NULL,
        predicted_price DECIMAL(18, 6) NULL,
        actual_price DECIMAL(18, 6) NULL,
        forecast_direction VARCHAR(16) NOT NULL,
        forecast_probability DECIMAL(8, 4) NULL,
        actual_outcome TINYINT NULL,
        brier_score DECIMAL(12, 8) NULL,
        absolute_error DECIMAL(18, 6) NULL,
        percentage_error DECIMAL(12, 8) NULL,
        expected_return_pct DECIMAL(10, 4) NULL,
        actual_return_pct DECIMAL(10, 4) NULL,
        directional_correct TINYINT NULL,
        resolution_json JSON NULL,
        created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_fr_forecast_horizon (forecast_id, horizon_days),
        KEY idx_fr_ticker (ticker),
        KEY idx_fr_method_horizon (prediction_method, horizon_days),
        KEY idx_fr_resolution_date (resolution_date),
        CONSTRAINT fk_fr_forecast
            FOREIGN KEY (forecast_id)
            REFERENCES ticker_forecasts(forecast_id)
            ON UPDATE CASCADE
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


COLUMN_PATCHES: dict[str, tuple[tuple[str, str], ...]] = {
    "ticker_forecasts": (
        ("forecast_id", "ADD COLUMN forecast_id VARCHAR(96) NULL"),
        ("snapshot_id", "ADD COLUMN snapshot_id VARCHAR(96) NULL"),
        ("forecast_date", "ADD COLUMN forecast_date DATETIME NULL"),
        ("dataset_generated_at", "ADD COLUMN dataset_generated_at DATETIME NULL"),
        ("dataset_sha256", "ADD COLUMN dataset_sha256 CHAR(64) NULL"),
        ("ticker", "ADD COLUMN ticker VARCHAR(16) NULL"),
        ("current_price", "ADD COLUMN current_price DECIMAL(18, 6) NULL"),
        ("prediction_method", "ADD COLUMN prediction_method VARCHAR(64) NULL"),
        ("forecast_direction", "ADD COLUMN forecast_direction VARCHAR(16) NULL"),
        ("target_price_7d", "ADD COLUMN target_price_7d DECIMAL(18, 6) NULL"),
        ("target_price_14d", "ADD COLUMN target_price_14d DECIMAL(18, 6) NULL"),
        ("target_price_30d", "ADD COLUMN target_price_30d DECIMAL(18, 6) NULL"),
        ("target_price_60d", "ADD COLUMN target_price_60d DECIMAL(18, 6) NULL"),
        ("target_price_90d", "ADD COLUMN target_price_90d DECIMAL(18, 6) NULL"),
        ("probability_7d", "ADD COLUMN probability_7d DECIMAL(8, 4) NULL"),
        ("probability_14d", "ADD COLUMN probability_14d DECIMAL(8, 4) NULL"),
        ("probability_30d", "ADD COLUMN probability_30d DECIMAL(8, 4) NULL"),
        ("probability_60d", "ADD COLUMN probability_60d DECIMAL(8, 4) NULL"),
        ("probability_90d", "ADD COLUMN probability_90d DECIMAL(8, 4) NULL"),
        ("expected_return_7d", "ADD COLUMN expected_return_7d DECIMAL(10, 4) NULL"),
        ("expected_return_14d", "ADD COLUMN expected_return_14d DECIMAL(10, 4) NULL"),
        ("expected_return_30d", "ADD COLUMN expected_return_30d DECIMAL(10, 4) NULL"),
        ("expected_return_60d", "ADD COLUMN expected_return_60d DECIMAL(10, 4) NULL"),
        ("expected_return_90d", "ADD COLUMN expected_return_90d DECIMAL(10, 4) NULL"),
        ("confidence", "ADD COLUMN confidence DECIMAL(8, 4) NULL"),
        ("bluelotus_score", "ADD COLUMN bluelotus_score DECIMAL(10, 4) NULL"),
        ("analyst_target", "ADD COLUMN analyst_target DECIMAL(18, 6) NULL"),
        ("analyst_upside_pct", "ADD COLUMN analyst_upside_pct DECIMAL(10, 4) NULL"),
        ("regime", "ADD COLUMN regime VARCHAR(64) NULL"),
        ("sector_theme", "ADD COLUMN sector_theme VARCHAR(128) NULL"),
        ("method_basis", "ADD COLUMN method_basis TEXT NULL"),
        ("risk_notes", "ADD COLUMN risk_notes TEXT NULL"),
        ("source_dataset_path", "ADD COLUMN source_dataset_path VARCHAR(500) NULL"),
        ("created_by", "ADD COLUMN created_by VARCHAR(96) NULL"),
        ("forecast_json", "ADD COLUMN forecast_json JSON NULL"),
        ("created_at", "ADD COLUMN created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP"),
    ),
    "forecast_resolutions": (
        ("forecast_id", "ADD COLUMN forecast_id VARCHAR(96) NULL"),
        ("snapshot_id", "ADD COLUMN snapshot_id VARCHAR(96) NULL"),
        ("ticker", "ADD COLUMN ticker VARCHAR(16) NULL"),
        ("prediction_method", "ADD COLUMN prediction_method VARCHAR(64) NULL"),
        ("horizon_days", "ADD COLUMN horizon_days INT NULL"),
        ("forecast_date", "ADD COLUMN forecast_date DATETIME NULL"),
        ("resolution_date", "ADD COLUMN resolution_date DATETIME NULL"),
        ("current_price", "ADD COLUMN current_price DECIMAL(18, 6) NULL"),
        ("predicted_price", "ADD COLUMN predicted_price DECIMAL(18, 6) NULL"),
        ("actual_price", "ADD COLUMN actual_price DECIMAL(18, 6) NULL"),
        ("forecast_direction", "ADD COLUMN forecast_direction VARCHAR(16) NULL"),
        ("forecast_probability", "ADD COLUMN forecast_probability DECIMAL(8, 4) NULL"),
        ("actual_outcome", "ADD COLUMN actual_outcome TINYINT NULL"),
        ("brier_score", "ADD COLUMN brier_score DECIMAL(12, 8) NULL"),
        ("absolute_error", "ADD COLUMN absolute_error DECIMAL(18, 6) NULL"),
        ("percentage_error", "ADD COLUMN percentage_error DECIMAL(12, 8) NULL"),
        ("expected_return_pct", "ADD COLUMN expected_return_pct DECIMAL(10, 4) NULL"),
        ("actual_return_pct", "ADD COLUMN actual_return_pct DECIMAL(10, 4) NULL"),
        ("directional_correct", "ADD COLUMN directional_correct TINYINT NULL"),
        ("resolution_json", "ADD COLUMN resolution_json JSON NULL"),
        ("created_at", "ADD COLUMN created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP"),
    ),
}


def ensure_columns(cur) -> None:
    for table, patches in COLUMN_PATCHES.items():
        cur.execute(f"SHOW COLUMNS FROM {table}")
        existing = {str(row[0]).lower() for row in cur.fetchall()}
        for column, alter in patches:
            if column.lower() not in existing:
                cur.execute(f"ALTER TABLE {table} {alter}")
    for stmt in (
        "ALTER TABLE ticker_forecasts MODIFY COLUMN forecast_date DATETIME NULL",
        "ALTER TABLE ticker_forecasts MODIFY COLUMN forecast_id VARCHAR(96) NULL",
        "ALTER TABLE ticker_forecasts MODIFY COLUMN snapshot_id VARCHAR(96) NULL",
        "ALTER TABLE ticker_forecasts MODIFY COLUMN prediction_method VARCHAR(64) NULL",
        "ALTER TABLE forecast_resolutions MODIFY COLUMN forecast_id VARCHAR(96) NULL",
        "ALTER TABLE forecast_resolutions MODIFY COLUMN snapshot_id VARCHAR(96) NULL",
        "ALTER TABLE forecast_resolutions MODIFY COLUMN prediction_method VARCHAR(64) NULL",
    ):
        try:
            cur.execute(stmt)
        except Exception:
            # Legacy forecast tables may already have foreign keys or narrower
            # columns. The engine uses compact IDs for compatibility, so this
            # optional widening should never block table readiness.
            pass
    cur.execute("SHOW INDEX FROM ticker_forecasts")
    indexes = {str(row[2]) for row in cur.fetchall()}
    if "idx_forecast_ticker_date" in indexes:
        cur.execute("ALTER TABLE ticker_forecasts DROP INDEX idx_forecast_ticker_date")
    if "uq_tf_snapshot_ticker_method" not in indexes:
        cur.execute("ALTER TABLE ticker_forecasts ADD UNIQUE KEY uq_tf_snapshot_ticker_method (snapshot_id, ticker, prediction_method)")


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
        ensure_columns(cur)
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    create_tables()
    print("BlueLotus Superforecast/Brier tables are ready.")


if __name__ == "__main__":
    main()

