from __future__ import annotations

from typing import Any, Dict, List

from .pipeline_manifest import STAGE_NAMES


def validate_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    stages = payload.get("stages") if isinstance(payload.get("stages"), list) else []
    names = [stage.get("stage_name") for stage in stages if isinstance(stage, dict)]
    for name in STAGE_NAMES:
        if name not in names:
            errors.append(f"missing_stage:{name}")
    if payload.get("execution_authority") != "CIO_ONLY_MANUAL":
        errors.append("execution_authority_not_cio_only_manual")
    if payload.get("order_routing_enabled") is not False:
        errors.append("order_routing_enabled_not_false")
    if int(payload.get("orders_generated") or 0) != 0:
        errors.append("orders_generated_not_zero")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "error_count": len(errors)}

