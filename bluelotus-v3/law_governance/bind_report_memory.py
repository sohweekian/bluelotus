from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection
from law_governance.export_active_governance_pack import build_active_governance_pack, export_active_governance_pack
from law_governance.law_core import (
    ACTIVE_PACK_PATH,
    TYPE_TO_PACK_KEY,
    binding_hash,
    content_hash,
    load_json_path,
    make_id,
    utc_now,
)


PACK_TO_COLUMN = {
    "master_prompt": "master_prompt_memory_id",
    "cio_context_capsule": "cio_context_memory_id",
    "chief_strategist_governance": "chief_strategist_governance_memory_id",
    "strategy_doctrine": "strategy_doctrine_memory_id",
    "sleeve_rules": "sleeve_rules_memory_id",
    "kill_condition_set": "kill_condition_memory_id",
    "execution_doctrine": "execution_doctrine_memory_id",
    "source_priority_rules": "source_priority_memory_id",
}

REQUIRED_PACK_KEYS = {
    "master_prompt",
    "cio_context_capsule",
    "chief_strategist_governance",
    "strategy_doctrine",
    "sleeve_rules",
    "kill_condition_set",
    "execution_doctrine",
}


def _current_pack() -> Dict[str, Any]:
    if ACTIVE_PACK_PATH.exists():
        return load_json_path(ACTIVE_PACK_PATH)
    export_active_governance_pack()
    return load_json_path(ACTIVE_PACK_PATH)


def bind_report_memory(report_id: str, cycle_id: Optional[str] = None, notes: str = "") -> Dict[str, Any]:
    pack = _current_pack()
    active_memory = pack.get("active_memory") if isinstance(pack.get("active_memory"), dict) else {}
    columns: Dict[str, Optional[str]] = {column: None for column in PACK_TO_COLUMN.values()}
    missing: List[str] = []
    for pack_key, column in PACK_TO_COLUMN.items():
        entry = active_memory.get(pack_key)
        if isinstance(entry, dict) and entry.get("memory_id"):
            columns[column] = entry["memory_id"]
        elif pack_key in REQUIRED_PACK_KEYS:
            missing.append(pack_key)

    now = utc_now()
    status = "ACTIVE" if not missing else "INSTITUTIONAL_REVIEW_REQUIRED"
    stable_payload = {
        "report_id": report_id,
        "cycle_id": cycle_id or "",
        "active_pack_hash": pack.get("active_pack_hash") or content_hash(pack),
        "memory_ids": columns,
        "binding_status": status,
    }
    bhash = binding_hash(stable_payload)
    binding_id = make_id("BIND", "REPORT_MEMORY", bhash)

    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO report_memory_binding (
                binding_id, report_id, cycle_id, generated_at,
                master_prompt_memory_id, cio_context_memory_id,
                chief_strategist_governance_memory_id, strategy_doctrine_memory_id,
                sleeve_rules_memory_id, kill_condition_memory_id,
                execution_doctrine_memory_id, source_priority_memory_id,
                active_pack_hash, binding_hash, binding_status, binding_notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                binding_id,
                report_id,
                cycle_id,
                now,
                columns["master_prompt_memory_id"],
                columns["cio_context_memory_id"],
                columns["chief_strategist_governance_memory_id"],
                columns["strategy_doctrine_memory_id"],
                columns["sleeve_rules_memory_id"],
                columns["kill_condition_memory_id"],
                columns["execution_doctrine_memory_id"],
                columns["source_priority_memory_id"],
                stable_payload["active_pack_hash"],
                bhash,
                status,
                notes or ("Missing required memory: " + ", ".join(missing) if missing else "Report bound to active governance law pack."),
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    return {
        "status": status,
        "binding_id": binding_id,
        "report_id": report_id,
        "cycle_id": cycle_id,
        "active_pack_hash": stable_payload["active_pack_hash"],
        "binding_timestamp_utc": now,
        "binding_hash": bhash,
        "missing_required_memory": missing,
    }


def bind_current_report_memory(report_id: Optional[str] = None, cycle_id: Optional[str] = None) -> Dict[str, Any]:
    if not report_id:
        report_id = "Bluelotus_V3_Report"
    return bind_report_memory(report_id=report_id, cycle_id=cycle_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bind a report to the active governance law pack")
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--cycle-id")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    print(json.dumps(bind_report_memory(args.report_id, args.cycle_id, args.notes), indent=2))


if __name__ == "__main__":
    main()
