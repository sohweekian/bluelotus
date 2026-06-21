import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.json_response_validator import validate_json_response


def main() -> None:
    report = {
        "schema_version": "bluelotus_v3_agent_report_v1.0",
        "cycle_id": "test_cycle",
        "agent_id": "data_integrity",
        "agent_name": "Data Integrity Agent",
        "agent_role": "Test",
        "model_used": "configured",
        "input_refs": {},
        "summary": "OK",
        "key_findings": [],
        "risk_flags": [],
        "blocked_actions_observed": [],
        "allowed_actions_observed": ["WAIT"],
        "affected_theses": [],
        "affected_assets": [],
        "causal_completeness": "partial",
        "blind_spots": [],
        "confidence": 0.5,
        "recommendation_to_chief_strategist": "WAIT",
        "requires_cio_attention": False,
        "manual_execution_required": True,
        "llm_order_generation": False,
        "created_at_sgt": "2026-06-15T00:00:00+08:00",
    }
    assert validate_json_response(json.dumps(report), "AGENT_REPORT_SCHEMA_PATH", save_failed=False)
    print("PASS agent report schema")


if __name__ == "__main__":
    main()
