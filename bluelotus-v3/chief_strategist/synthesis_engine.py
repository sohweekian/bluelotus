from __future__ import annotations

from typing import Any, Dict, List

from agents.base_agent import sgt_now
from chief_strategist.disagreement_resolver import resolve_disagreements


def synthesize(cycle_context: Dict[str, Any], reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    disagreements = resolve_disagreements(str(cycle_context["cycle_id"]), reports)
    operator_pack = cycle_context["operator_verdict_pack"]
    cio_items = []
    consensus = []
    for report in reports:
        consensus.append(f"{report.get('agent_name')}: {report.get('recommendation_to_chief_strategist')}")
        if report.get("requires_cio_attention") is True:
            cio_items.append(str(report.get("agent_name")))
    posture = choose_posture(reports, disagreements)

    # Extract cash-fortress mode flags from deterministic operator pack
    _cfm_op = (operator_pack.get("operators") or {}).get("cash_fortress_mode", {})
    _cfm_metrics = _cfm_op.get("metrics", {})
    _cash_fortress_mode     = bool(_cfm_metrics.get("cash_fortress_mode", False))
    _scout_mode             = bool(_cfm_metrics.get("scout_mode", False))
    _second_tranche_blocked = bool(_cfm_metrics.get("second_tranche_blocked", False))

    return {
        "schema_version": "bluelotus_v3_chief_strategist_briefing_v1.0",
        "cycle_id": str(cycle_context["cycle_id"]),
        "summary": build_summary(reports, posture, _cash_fortress_mode, _scout_mode, _second_tranche_blocked),
        "recommended_posture": posture,
        "cash_fortress_mode": _cash_fortress_mode,
        "scout_mode": _scout_mode,
        "second_tranche_blocked": _second_tranche_blocked,
        "operator_blocks": operator_pack.get("blocked_actions", []),
        "agent_consensus": consensus,
        "disagreements": disagreements["disagreements"],
        "cio_attention_items": cio_items,
        "manual_execution_required": True,
        "llm_order_generation": False,
        "created_at_sgt": sgt_now(),
    }


def choose_posture(reports: List[Dict[str, Any]], disagreements: Dict[str, Any]) -> str:
    recommendations = [str(r.get("recommendation_to_chief_strategist", "WAIT")) for r in reports]
    if any(item.get("severity") == "high" for item in disagreements.get("disagreements", [])):
        return "REVIEW"
    if any(value in {"RISK_REVIEW_REQUIRED", "REDUCE_RISK_REVIEW", "RAISE_CASH_REVIEW", "HEDGE_REVIEW"} for value in recommendations):
        return "REDUCE_RISK_REVIEW"
    if any(value in {"REVIEW", "MANUAL_REVIEW_REQUIRED", "CIO_VERIFICATION_REQUIRED", "THESIS_REVIEW_REQUIRED"} for value in recommendations):
        return "REVIEW"
    if "HOLD" in recommendations:
        return "HOLD"
    return "WAIT"


def build_summary(reports: List[Dict[str, Any]], posture: str,
                  cash_fortress_mode: bool = False, scout_mode: bool = False,
                  second_tranche_blocked: bool = False) -> str:
    base = f"Chief Strategist synthesized {len(reports)} validated agent reports. Recommended posture: {posture}."
    if cash_fortress_mode or scout_mode:
        posture_note = (
            " CASH_FORTRESS_ACTIVE - the council recognizes the current portfolio as cash-fortress / scout-book mode. "
            "High cash is intentional defensive posture, not automatic defect or fund-level concentration breach."
        )
        if second_tranche_blocked:
            posture_note += (
                " Second tranche is blocked pending macro confirmation: "
                "FOMC/Warsh event resolved | BOJ/yield/yen stable | regime confirmed risk-on."
            )
        return base + posture_note
    return base
