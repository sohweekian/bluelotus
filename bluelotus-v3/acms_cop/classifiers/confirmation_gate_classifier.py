from __future__ import annotations

from typing import Any, Dict


REQUIRED_GATES = [
    "regime_confirmed",
    "flow_confirmed",
    "high_beta_confirmed",
    "banks_confirmed",
    "hedge_demand_cooled",
    "credit_calm",
    "usd_jpy_stable",
    "event_window_cleared",
    "pnl_integrity_pass",
    "causal_confirmed",
]


def enforce_execution_safety(cycle: Dict[str, Any]) -> None:
    if str(cycle.get("execution_authority", "")).upper() != "CIO_ONLY_MANUAL":
        raise ValueError("ACMS execution safety violation: execution_authority is not CIO_ONLY_MANUAL")
    if bool(cycle.get("order_routing_enabled")):
        raise ValueError("ACMS execution safety violation: order routing enabled")
    if bool(cycle.get("llm_order_generation_enabled")):
        raise ValueError("ACMS execution safety violation: LLM order generation enabled")
    if int(cycle.get("system_generated_orders") or 0) > 0:
        raise ValueError("ACMS execution safety violation: system generated orders > 0")


def classify_confirmation_gate(cycle: Dict[str, Any], signals: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signals = signals or {}
    gates = {gate: bool(signals.get(gate, False)) for gate in REQUIRED_GATES}
    gates["pnl_integrity_pass"] = str(cycle.get("pnl_integrity_status", "OK")).upper() in {"OK", "PASS", "INFO"}
    hard_blocks = []

    try:
        enforce_execution_safety(cycle)
    except ValueError as exc:
        hard_blocks.append(str(exc))

    regime = str(cycle.get("regime_label") or "").upper()
    if regime == "RISK_OFF":
        hard_blocks.append("Regime RISK_OFF")
    if str(signals.get("credit_stress", "")).upper() == "SEVERE":
        hard_blocks.append("Credit stress severe")
    if str(signals.get("boj_yen_carry", "")).upper() == "SEVERE":
        hard_blocks.append("BOJ/Yen carry severe")
    if not gates["pnl_integrity_pass"]:
        hard_blocks.append("P/L integrity fail")

    unresolved = [name for name, passed in gates.items() if not passed]
    if hard_blocks:
        status = "BLOCKED"
    elif unresolved:
        status = "REVIEW"
    else:
        status = "CLEAR"
    if unresolved and any(name in unresolved for name in ["regime_confirmed", "credit_calm", "usd_jpy_stable", "event_window_cleared", "pnl_integrity_pass"]):
        status = "BLOCKED"

    return {
        "second_tranche_status": status,
        "scale_in_status": status,
        "gates": gates,
        "unresolved_gates": unresolved,
        "blocked_actions": hard_blocks + [f"UNRESOLVED_GATE:{name}" for name in unresolved],
    }

