from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection
from law_governance.export_active_governance_pack import export_active_governance_pack
from law_governance.law_core import (
    ACTIVE_PACK_PATH,
    OUTPUT_DIR,
    TYPE_TO_PACK_KEY,
    atomic_write_json,
    content_hash,
    load_json_path,
    utc_now,
)

VALIDATION_PATH = OUTPUT_DIR / "governance_law_validation_latest.json"
REQUIRED_TABLES = {
    "institutional_memory_registry",
    "institutional_memory_change_log",
    "institutional_governance_policy",
    "report_memory_binding",
    "memory_activation_event",
}


def _check(name: str, passed: bool, detail: str) -> Dict[str, Any]:
    return {"check": name, "result": "PASS" if passed else "FAIL", "detail": detail}


def validate_governance_law() -> Dict[str, Any]:
    export_active_governance_pack()
    checks: List[Dict[str, Any]] = []
    conn = get_v3_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SHOW TABLES")
        table_values = set()
        for row in cur.fetchall():
            table_values.update(str(v) for v in row.values())
        missing_tables = sorted(REQUIRED_TABLES - table_values)
        checks.append(_check("Required tables exist", not missing_tables, f"missing={missing_tables}"))

        cur.execute("SELECT * FROM institutional_memory_registry")
        rows = list(cur.fetchall())
        bad_hash = []
        missing_reason = []
        for row in rows:
            try:
                content = json.loads(row["content_json"])
                if content_hash(content) != row["content_hash"]:
                    bad_hash.append(row["memory_id"])
            except Exception:
                bad_hash.append(row["memory_id"])
            if not row.get("change_reason_code") or not row.get("change_reason_text"):
                missing_reason.append(row["memory_id"])
        checks.append(_check("Memory hashes match content", not bad_hash, f"bad_hash={bad_hash}"))
        checks.append(_check("Change reasons mandatory", not missing_reason, f"missing_reason={missing_reason}"))

        active_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            if row["status"] == "ACTIVE":
                active_by_type.setdefault(row["memory_type"], []).append(row)
        duplicate_active = {k: [r["memory_id"] for r in v] for k, v in active_by_type.items() if len(v) > 1}
        unapproved_active = [r["memory_id"] for v in active_by_type.values() for r in v if r["approval_status"] != "APPROVED"]
        no_effective_from = [r["memory_id"] for v in active_by_type.values() for r in v if not r.get("effective_from")]
        superseded_without_to = [r["memory_id"] for r in rows if r["status"] == "SUPERSEDED" and not r.get("effective_to")]
        checks.append(_check("Only one ACTIVE per memory type", not duplicate_active, f"duplicate_active={duplicate_active}"))
        checks.append(_check("ACTIVE memory approved", not unapproved_active, f"unapproved_active={unapproved_active}"))
        checks.append(_check("ACTIVE memory has effective_from", not no_effective_from, f"no_effective_from={no_effective_from}"))
        checks.append(_check("SUPERSEDED memory has effective_to", not superseded_without_to, f"missing_effective_to={superseded_without_to}"))

        active_content = {r["memory_type"]: json.loads(r["content_json"]) for v in active_by_type.values() for r in v}
        master_text = json.dumps(active_content.get("MASTER_PROMPT", {}), sort_keys=True)
        execution_text = json.dumps(active_content.get("EXECUTION_DOCTRINE", {}), sort_keys=True)
        checks.append(_check("MASTER_PROMPT preserves CIO_ONLY_MANUAL", "CIO_ONLY_MANUAL" in master_text, "CIO_ONLY_MANUAL present in active master prompt"))
        checks.append(_check("EXECUTION_DOCTRINE disables routing", "CIO_ONLY_MANUAL" in execution_text and '"order_routing_enabled": false' in execution_text.lower(), "execution doctrine requires manual-only / routing disabled"))

        pack = load_json_path(ACTIVE_PACK_PATH)
        active_memory = pack.get("active_memory") if isinstance(pack.get("active_memory"), dict) else {}
        missing_from_pack = []
        hash_mismatch = []
        for mtype, rows_for_type in active_by_type.items():
            pack_key = TYPE_TO_PACK_KEY.get(mtype)
            if not pack_key:
                continue
            entry = active_memory.get(pack_key)
            if not entry:
                missing_from_pack.append(mtype)
            elif entry.get("memory_id") != rows_for_type[0]["memory_id"] or entry.get("hash") != rows_for_type[0]["content_hash"]:
                hash_mismatch.append(mtype)
        checks.append(_check("Active pack mirrors DB active memory", not missing_from_pack and not hash_mismatch, f"missing={missing_from_pack}; mismatch={hash_mismatch}"))

        cur.execute("SELECT * FROM report_memory_binding ORDER BY generated_at DESC LIMIT 50")
        bindings = list(cur.fetchall())
        known_ids = {r["memory_id"] for r in rows}
        bad_bindings = []
        missing_binding_hash = []
        memory_columns = [
            "master_prompt_memory_id",
            "cio_context_memory_id",
            "chief_strategist_governance_memory_id",
            "strategy_doctrine_memory_id",
            "sleeve_rules_memory_id",
            "kill_condition_memory_id",
            "execution_doctrine_memory_id",
            "source_priority_memory_id",
        ]
        for binding in bindings:
            for column in memory_columns:
                value = binding.get(column)
                if value and value not in known_ids:
                    bad_bindings.append({"binding_id": binding["binding_id"], "column": column, "memory_id": value})
            if not binding.get("binding_hash"):
                missing_binding_hash.append(binding["binding_id"])
        checks.append(_check("Report bindings reference known memory", not bad_bindings, f"bad_bindings={bad_bindings}"))
        checks.append(_check("Report bindings have hashes", not missing_binding_hash, f"missing_hash={missing_binding_hash}"))
        cur.close()
    finally:
        conn.close()

    fail_count = sum(1 for item in checks if item["result"] == "FAIL")
    result = {
        "status": "PASS" if fail_count == 0 else "FAIL",
        "generated_at": utc_now(),
        "pass_count": len(checks) - fail_count,
        "fail_count": fail_count,
        "checks": checks,
        "active_pack_path": str(ACTIVE_PACK_PATH),
    }
    atomic_write_json(VALIDATION_PATH, result)
    return result


def main() -> None:
    print(json.dumps(validate_governance_law(), indent=2))


if __name__ == "__main__":
    main()
