from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection
from law_governance.activate_memory_version import activate_memory_version
from law_governance.approve_memory_change import approve_memory_change
from law_governance.db_schema import run_migrations
from law_governance.export_active_governance_pack import export_active_governance_pack
from law_governance.law_core import PROJECT_ROOT, load_json_path
from law_governance.propose_memory_change import propose_memory_change


def _safe_load(path: Path) -> Dict[str, Any]:
    if path.exists():
        return load_json_path(path)
    return {}


def _dataset() -> Dict[str, Any]:
    return _safe_load(PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json")


def _active_memory_id(memory_type: str) -> Optional[str]:
    conn = get_v3_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT memory_id FROM institutional_memory_registry WHERE memory_type=%s AND status='ACTIVE' ORDER BY effective_from DESC LIMIT 1",
            (memory_type,),
        )
        row = cur.fetchone()
        cur.close()
        return row["memory_id"] if row else None
    finally:
        conn.close()


def build_seed_memories() -> Dict[str, Dict[str, Any]]:
    dataset = _dataset()
    master = _safe_load(PROJECT_ROOT / "data" / "cio_context" / "chief_strategist_master_prompt_latest.json")
    capsule = _safe_load(PROJECT_ROOT / "data" / "cio_context" / "cio_context_capsule_latest.json")
    csg = _safe_load(PROJECT_ROOT / "data" / "chief_strategist" / "chief_strategist_context_latest.json")
    if not csg:
        csg = dataset.get("chief_strategist_governance") if isinstance(dataset.get("chief_strategist_governance"), dict) else {}

    source_priority = {
        "schema_version": "source_priority_rules.v1",
        "source_priority": master.get("source_priority") or capsule.get("source_hierarchy") or [],
        "doctrine": "Higher-priority institutional law overrides tactical and LLM commentary.",
        "pipeline_may_consume": True,
        "pipeline_may_mutate": False,
    }
    strategy_doctrine = {
        "schema_version": "strategy_doctrine.v1",
        "active_strategy_defaults": master.get("active_strategy_defaults") or {},
        "latest_cio_layer_decision": capsule.get("latest_cio_layer_decision") or {},
        "cio_three_step_record": capsule.get("cio_three_step_record") or {},
        "doctrine": "CIO strategy must be read before tactical market interpretation.",
    }
    sleeve_rules = {
        "schema_version": "sleeve_rules.v1",
        "active_sleeve_rules": capsule.get("active_sleeve_rules") or master.get("sleeve_rules") or {},
        "doctrine": "Sleeves define capital role, ticker role, and forbidden interpretations.",
    }
    kill_conditions = {
        "schema_version": "kill_condition_set.v1",
        "kill_conditions": capsule.get("kill_conditions") or master.get("kill_conditions") or {},
        "doctrine": "Structural thesis invalidation requires explicit kill-condition evidence.",
    }
    execution_doctrine = {
        "schema_version": "execution_doctrine.v1",
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_generated_orders": 0,
        "broker_api_role": "READ_ONLY",
        "pipeline_role": "Record, analyze, validate, archive, bind reports to law.",
        "pipeline_may_mutate_law": False,
        "doctrine": capsule.get("core_doctrine") or {},
    }

    return {
        "MASTER_PROMPT": master,
        "CIO_CONTEXT_CAPSULE": capsule,
        "CHIEF_STRATEGIST_GOVERNANCE": csg,
        "STRATEGY_DOCTRINE": strategy_doctrine,
        "SLEEVE_RULES": sleeve_rules,
        "KILL_CONDITION_SET": kill_conditions,
        "EXECUTION_DOCTRINE": execution_doctrine,
        "SOURCE_PRIORITY_RULES": source_priority,
    }


def seed_current_governance_law() -> Dict[str, Any]:
    run_migrations()
    seeded: List[Dict[str, Any]] = []
    for memory_type, content in build_seed_memories().items():
        if not content:
            seeded.append({"memory_type": memory_type, "status": "SKIPPED_EMPTY"})
            continue
        active_id = _active_memory_id(memory_type)
        result = propose_memory_change(
            memory_type=memory_type,
            content=content,
            version=str(content.get("version") or content.get("schema_version") or "v1.0-foundation"),
            summary=f"Founding baseline for {memory_type}",
            reason_code="FOUNDING_BASELINE",
            reason_text="Initial immutable law registry seed from current BlueLotus V3 institutional doctrine.",
            requested_by="Dr. Codex",
            supersedes_memory_id=active_id,
            artifact_path="current_v3_artifacts",
        )
        if result["status"] == "PROPOSED":
            approve_memory_change(result["memory_id"], approved_by="CIO_BASELINE")
            activation = activate_memory_version(result["memory_id"], performed_by="Dr. Codex")
            seeded.append({"memory_type": memory_type, **result, "activation": activation})
        else:
            seeded.append({"memory_type": memory_type, **result})
    export_result = export_active_governance_pack()
    return {"status": "PASS", "seeded": seeded, "export": export_result}


def main() -> None:
    print(json.dumps(seed_current_governance_law(), indent=2))


if __name__ == "__main__":
    main()
