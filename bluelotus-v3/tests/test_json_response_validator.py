from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import load_dotenv
from llm_clients.json_response_validator import ResponseValidationError, validate_json_response
from llm_clients.model_router import get_default_model_role


def main() -> int:
    load_dotenv()
    valid = {
        "schema_version": "bluelotus_llm_response_v1.0",
        "model_role": get_default_model_role(),
        "summary": "Operator result requires review.",
        "key_findings": ["Risk-off watch remains active."],
        "risk_flags": [],
        "recommended_cio_action": "WAIT",
        "manual_execution_required": True,
        "llm_order_generation": False,
    }
    parsed = validate_json_response(json.dumps(valid), "LLM_RESPONSE_SCHEMA_PATH")
    assert parsed["manual_execution_required"] is True
    for bad in ["{bad json", json.dumps({**valid, "llm_order_generation": True})]:
        try:
            validate_json_response(bad, "LLM_RESPONSE_SCHEMA_PATH")
        except ResponseValidationError:
            continue
        raise AssertionError("JSON validator accepted malformed or unsafe output.")
    print("PASS JSON response validator")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
