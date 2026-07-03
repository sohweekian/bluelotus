#!/usr/bin/env python3
"""
BlueLotus MID -- dataset snapshot archiver.

Stores the current dataset_raw.json in institutional_dataset_snapshots so the
platform has point-in-time reconstruction even when later quant/report stages
fail. This is archival only; it does not touch broker execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "audit" / "dataset_snapshot_archive_latest.json"


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "").replace("+00:00", "")[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load_dataset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("dataset_raw.json must be a JSON object")
    return data


def archive_snapshot(dataset_path: Path, write_signal: bool = True) -> Dict[str, Any]:
    sys.path.insert(0, str(PROJECT_ROOT))

    from dotenv import load_dotenv
    from core.db import close_cycle_conn, get_connection, write_raw_signal
    from mid.institutional_quant_tables import create_tables

    load_dotenv(PROJECT_ROOT / ".env")
    create_tables()

    dataset = load_dataset(dataset_path)
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    payload = json_dumps(dataset)
    dataset_sha = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
    snapshot_id = f"dataset_{dataset_sha[:20]}"
    captured_at = datetime.now()
    dataset_generated_at = parse_dt(meta.get("generated_at"))

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO institutional_dataset_snapshots (
                snapshot_id, captured_at, dataset_generated_at, export_version,
                ingest_version, dataset_sha256, dataset_path, dataset_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
            ON DUPLICATE KEY UPDATE
                dataset_path = VALUES(dataset_path),
                dataset_json = VALUES(dataset_json)
            """,
            (
                snapshot_id,
                captured_at,
                dataset_generated_at,
                meta.get("export_version"),
                meta.get("ingest_version"),
                dataset_sha,
                str(dataset_path),
                payload,
            ),
        )
        conn.commit()
        cur.execute(
            """
            SELECT snapshot_id, captured_at, dataset_generated_at, export_version,
                   ingest_version, dataset_sha256, dataset_path, created_at
            FROM institutional_dataset_snapshots
            WHERE snapshot_id = %s
            LIMIT 1
            """,
            (snapshot_id,),
        )
        verified = cur.fetchone() or {}
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary = {
        "status": "archived",
        "snapshot_id": snapshot_id,
        "captured_at": captured_at.isoformat(sep=" "),
        "dataset_generated_at": meta.get("generated_at"),
        "dataset_export_version": meta.get("export_version"),
        "dataset_ingest_version": meta.get("ingest_version"),
        "dataset_sha256": dataset_sha,
        "dataset_path": str(dataset_path),
        "verified_from_database": bool(verified),
        "database_row": json_safe(verified),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    if write_signal:
        try:
            write_raw_signal(
                source="Dataset_Snapshot_Archive",
                ingestion_method="dataset_snapshot_archive",
                raw_payload=summary,
                raw_text=(
                    f"Dataset snapshot archived: {snapshot_id} | "
                    f"sha {dataset_sha[:12]} | export {meta.get('export_version')}"
                ),
                signal_type="governance",
                suspected_category="POINT_IN_TIME_DATASET_ARCHIVE",
                suspected_entities=["dataset_raw"],
                suspected_impact="medium",
                quality_score=1.0 if summary["verified_from_database"] else 0.6,
                quality_flags={"point_in_time_archive": True},
            )
        finally:
            close_cycle_conn()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive dataset_raw.json into institutional_dataset_snapshots")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--no-signal", action="store_true")
    args = parser.parse_args()

    summary = archive_snapshot(args.dataset, write_signal=not args.no_signal)
    print("Dataset snapshot archive complete.")
    print(f"Snapshot: {summary['snapshot_id']}")
    print(f"SHA256  : {summary['dataset_sha256']}")
    print(f"Verified: {summary['verified_from_database']}")


if __name__ == "__main__":
    main()

