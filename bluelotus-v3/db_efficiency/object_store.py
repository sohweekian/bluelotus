from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class StoredObjectRef:
    object_type: str
    object_hash: str
    payload_size_bytes: int
    schema_version: str
    source_key: str
    status: str
    row_count: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        data = {
            "object_type": self.object_type,
            "object_hash": self.object_hash,
            "payload_size_bytes": self.payload_size_bytes,
            "schema_version": self.schema_version,
            "source_key": self.source_key,
            "status": self.status,
        }
        if self.row_count is not None:
            data["row_count"] = self.row_count
        return data


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8", errors="replace")).hexdigest()


def payload_size_bytes(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8", errors="replace"))


def infer_row_count(value: Any) -> Optional[int]:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("rows", "kelly_sizing_advisory", "signal_entropy", "benchmark_results", "ticker_outputs", "strategies", "scenarios"):
            rows = value.get(key)
            if isinstance(rows, list):
                return len(rows)
    return None


def summarize_status(value: Any) -> str:
    if isinstance(value, dict):
        for key in (
            "status",
            "validation_status",
            "risk_overlay_status",
            "benchmark_dashboard_status",
            "point_in_time_guard_status",
            "final_status",
        ):
            if value.get(key):
                return str(value.get(key))
        validation = value.get("validation")
        if isinstance(validation, dict) and validation.get("status"):
            return str(validation.get("status"))
    return "PRESENT" if value not in ({}, [], None, "") else "MISSING"


def build_object_reference(
    object_type: str,
    payload: Any,
    *,
    source_key: str = "",
    schema_version: str = "",
) -> Dict[str, Any]:
    ref = StoredObjectRef(
        object_type=object_type,
        object_hash=object_hash(payload),
        payload_size_bytes=payload_size_bytes(payload),
        schema_version=schema_version,
        source_key=source_key,
        status=summarize_status(payload),
        row_count=infer_row_count(payload),
    )
    return ref.as_dict()


def store_object(cursor, object_type: str, cycle_id: str, payload: Any, *, schema_version: str = "", source_system: str = "BlueLotusV3") -> Dict[str, Any]:
    payload_json = canonical_json(payload)
    sha = hashlib.sha256(payload_json.encode("utf-8", errors="replace")).hexdigest()
    size = len(payload_json.encode("utf-8", errors="replace"))
    cursor.execute(
        """
        INSERT IGNORE INTO institutional_object_store (
            object_type, object_hash, object_version, payload_json,
            payload_size_bytes, source_system, schema_version
        ) VALUES (%s,%s,%s,CAST(%s AS JSON),%s,%s,%s)
        """,
        (object_type, sha, schema_version, payload_json, size, source_system, schema_version),
    )
    inserted = cursor.rowcount == 1
    cursor.execute(
        """
        INSERT INTO institutional_object_references (
            cycle_id, object_type, object_hash, payload_size_bytes,
            source_system, schema_version
        ) VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (cycle_id, object_type, sha, size, source_system, schema_version),
    )
    return {
        "object_type": object_type,
        "object_hash": sha,
        "payload_size_bytes": size,
        "schema_version": schema_version,
        "deduplicated": not inserted,
    }


def build_cycle_manifest(dataset: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    cycle_id = str(meta.get("cycle_id") or meta.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
    object_map = {
        "canonical": dataset.get("canonical"),
        "shannon_thorp_refinement": dataset.get("shannon_thorp_refinement"),
        "prospective_event_intelligence": dataset.get("prospective_event_intelligence"),
        "risk_overlay": dataset.get("risk_overlay"),
        "deterministic_pipeline_v3_2": dataset.get("deterministic_pipeline_v3_2"),
        "deterministic_replay_v3_3": dataset.get("deterministic_replay_v3_3"),
        "benchmark_dashboard_v3_4": dataset.get("benchmark_dashboard_v3_4"),
    }
    refs = {
        key: build_object_reference(key.upper(), value, source_key=key)
        for key, value in object_map.items()
        if value not in (None, {}, [])
    }
    return {
        "version": "v3-db-efficiency-cycle-manifest",
        "cycle_id": cycle_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_generated_at": meta.get("generated_at"),
        "dataset_hash": object_hash(dataset),
        "dataset_payload_size_bytes": payload_size_bytes(dataset),
        "object_references": refs,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
    }
