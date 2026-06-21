from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from law_governance.law_core import (
    ACTIVE_PACK_PATH,
    TYPE_TO_PACK_KEY,
    active_memory_rows,
    atomic_write_json,
    content_hash,
    memory_row_to_pack_entry,
    utc_now,
)


def build_active_governance_pack() -> Dict[str, Any]:
    active_rows = active_memory_rows()
    active_memory: Dict[str, Any] = {}
    for row in active_rows:
        pack_key = TYPE_TO_PACK_KEY.get(row.get("memory_type"))
        if pack_key:
            active_memory[pack_key] = memory_row_to_pack_entry(row)

    stable_payload = {
        "schema_version": "governance_law_pack.v1",
        "version": "v1.0-governance-law-pack",
        "status": "ACTIVE",
        "active_memory": active_memory,
        "binding_rules": {
            "v3_pipeline_consumes_only_active_pack": True,
            "pipeline_must_not_mutate_law": True,
            "reports_must_bind_memory_hashes": True,
            "inactive_or_draft_memory_must_not_govern_reports": True,
        },
        "safety": {
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "system_orders_generated": 0,
        },
    }
    pack_hash = content_hash(stable_payload)
    pack = {"generated_at": utc_now(), **stable_payload}
    pack["governance_pack_id"] = f"GOVPACK_{pack_hash[:16]}"
    pack["active_pack_hash"] = pack_hash
    return pack


def export_active_governance_pack() -> Dict[str, Any]:
    pack = build_active_governance_pack()
    atomic_write_json(ACTIVE_PACK_PATH, pack)
    return {
        "status": "PASS",
        "path": str(ACTIVE_PACK_PATH),
        "active_pack_hash": pack.get("active_pack_hash"),
        "active_memory_count": len(pack.get("active_memory", {})),
    }


def main() -> None:
    print(json.dumps(export_active_governance_pack(), indent=2))


if __name__ == "__main__":
    main()
