import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chief_strategist.synthesis_engine import synthesize
from llm_clients.json_response_validator import validate_json_response


def main() -> None:
    ctx = {"cycle_id": "test_cycle", "operator_verdict_pack": {"blocked_actions": ["ADD_HIGH_BETA_RISK"]}}
    reports = [{
        "agent_name": "Risk Challenger Agent",
        "recommendation_to_chief_strategist": "RISK_REVIEW_REQUIRED",
        "risk_flags": ["stress"],
        "requires_cio_attention": True,
    }]
    briefing = synthesize(ctx, reports)
    assert briefing["recommended_posture"] == "REDUCE_RISK_REVIEW"
    validate_json_response(json.dumps(briefing), "CHIEF_STRATEGIST_BRIEFING_SCHEMA_PATH", save_failed=False)
    print("PASS chief strategist synthesis")


if __name__ == "__main__":
    main()
