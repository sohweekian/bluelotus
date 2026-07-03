from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection
from db_efficiency.object_store import build_cycle_manifest, canonical_json, store_object

DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "audit" / "db_efficiency_persist_latest.json"


OBJECT_KEYS = {
    "CANONICAL": "canonical",
    "STR": "shannon_thorp_refinement",
    "PEI": "prospective_event_intelligence",
    "RISK_OVERLAY": "risk_overlay",
    "DETERMINISTIC_PIPELINE": "deterministic_pipeline_v3_2",
    "DETERMINISTIC_REPLAY": "deterministic_replay_v3_3",
    "BENCHMARK_DASHBOARD": "benchmark_dashboard_v3_4",
}


def persist_dataset_objects(dataset: Dict[str, Any]) -> Dict[str, Any]:
    manifest = build_cycle_manifest(dataset)
    cycle_id = str(manifest["cycle_id"])
    stored = []
    conn = get_v3_connection()
    try:
        cursor = conn.cursor()
        for object_type, key in OBJECT_KEYS.items():
            payload = dataset.get(key)
            if payload in (None, {}, []):
                continue
            stored.append(store_object(cursor, object_type, cycle_id, payload, schema_version=str((payload or {}).get("version", "")) if isinstance(payload, dict) else ""))
        cursor.execute(
            """
            INSERT IGNORE INTO v3_cycle_manifests (
                cycle_id, dataset_hash, dataset_payload_size_bytes, manifest_json,
                execution_authority, order_routing_enabled, system_orders_generated
            ) VALUES (%s,%s,%s,CAST(%s AS JSON),%s,%s,%s)
            """,
            (
                cycle_id,
                manifest["dataset_hash"],
                manifest["dataset_payload_size_bytes"],
                canonical_json(manifest),
                manifest["execution_authority"],
                manifest["order_routing_enabled"],
                manifest["system_orders_generated"],
            ),
        )
        manifest_inserted = cursor.rowcount == 1
        conn.commit()
        cursor.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "status": "persisted",
        "cycle_id": cycle_id,
        "stored_object_count": len(stored),
        "stored_objects": stored,
        "manifest_inserted": manifest_inserted,
        "manifest": manifest,
    }


def persist_current_dataset(path: Path = DEFAULT_DATASET) -> Dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    summary = persist_dataset_objects(dataset)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main() -> None:
    summary = persist_current_dataset()
    print(json.dumps({
        "status": summary["status"],
        "cycle_id": summary["cycle_id"],
        "stored_object_count": summary["stored_object_count"],
        "manifest_inserted": summary["manifest_inserted"],
        "objects": [
            {
                "object_type": item["object_type"],
                "payload_size_bytes": item["payload_size_bytes"],
                "deduplicated": item["deduplicated"],
            }
            for item in summary["stored_objects"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
