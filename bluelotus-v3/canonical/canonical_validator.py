from __future__ import annotations

from typing import Any, Dict, List

from .canonical_schema import ALLOWED_CANONICAL_SESSIONS, REQUIRED_CANONICAL_ROOT_KEYS


def validate_canonical_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(contract, dict):
        return {"status": "FAIL", "errors": ["canonical_contract_not_dict"]}
    missing = sorted(REQUIRED_CANONICAL_ROOT_KEYS - set(contract.keys()))
    errors.extend(f"missing:{m}" for m in missing)
    session = contract.get("session_state") if isinstance(contract.get("session_state"), dict) else {}
    if session.get("canonical_market_session") not in ALLOWED_CANONICAL_SESSIONS:
        errors.append("invalid_canonical_market_session")
    gov = contract.get("governance") if isinstance(contract.get("governance"), dict) else {}
    if gov.get("execution_authority") != "CIO_ONLY_MANUAL":
        errors.append("execution_authority_not_cio_only_manual")
    if gov.get("order_routing_enabled") is not False:
        errors.append("order_routing_enabled_not_false")
    if int(gov.get("system_orders_generated") or 0) != 0:
        errors.append("system_orders_generated_not_zero")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "error_count": len(errors),
    }

