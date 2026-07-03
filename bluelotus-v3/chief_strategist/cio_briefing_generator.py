from __future__ import annotations

from typing import Any, Dict


def build_cio_action_menu(briefing: Dict[str, Any]) -> Dict[str, Any]:
    posture = str(briefing["recommended_posture"])
    return {
        "schema_version": "bluelotus_v3_cio_action_menu_v1.0",
        "cycle_id": str(briefing["cycle_id"]),
        "recommended_posture": posture,
        "allowed_manual_actions": allowed_manual_actions(posture),
        "operator_blocks": briefing.get("operator_blocks", []),
        "manual_execution_required": True,
        "llm_order_generation": False,
    }


def render_cio_action_menu(menu: Dict[str, Any], briefing: Dict[str, Any]) -> str:
    lines = [
        "CIO Action Menu",
        "",
        f"Recommended posture: {menu.get('recommended_posture')}",
        "",
        f"Reason: {briefing.get('summary')}",
        "",
        "Operator blocks:",
    ]
    blocks = menu.get("operator_blocks", [])
    lines.extend(f"- {item}" for item in blocks) if blocks else lines.append("- None reported")
    lines.extend([
        "",
        "Agent consensus:",
    ])
    consensus = briefing.get("agent_consensus", [])
    lines.extend(f"- {item}" for item in consensus) if consensus else lines.append("- No validated reports")
    lines.extend([
        "",
        "Agent disagreements:",
    ])
    disagreements = briefing.get("disagreements", [])
    lines.extend(f"- {item.get('topic')}: {item.get('severity')}" for item in disagreements) if disagreements else lines.append("- None recorded")
    lines.extend([
        "",
        "Allowed manual review actions:",
    ])
    lines.extend(f"- {item}" for item in menu.get("allowed_manual_actions", []))
    lines.extend([
        "",
        "Manual execution required: YES",
        "No automatic orders generated.",
    ])
    return "\n".join(lines)


def allowed_manual_actions(posture: str) -> list[str]:
    base = ["WAIT", "HOLD", "REVIEW"]
    if posture in {"REDUCE_RISK_REVIEW", "RAISE_CASH_REVIEW", "HEDGE_REVIEW"}:
        return base + [posture]
    if posture in {"MANUAL_BUY_REVIEW", "MANUAL_SELL_REVIEW"}:
        return base + [posture]
    return base
