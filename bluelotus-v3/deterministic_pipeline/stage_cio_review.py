from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any], risk_overlay: Dict[str, Any], target_vector: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("CIO Review", ["risk_overlay", "target_usd_vector", "governance"], ["cio_review_packet"])
    risk_status = risk_overlay.get("risk_overlay_status")
    possible_adds = [
        row for row in (target_vector.get("rows") or [])
        if isinstance(row, dict) and float(row.get("manual_delta_usd") or 0) > 0
    ]
    posture = "REVIEW" if possible_adds or risk_status != "PASS" else "WAIT"
    stage["cio_review_packet"] = {
        "recommended_posture": posture,
        "manual_add_candidates": len(possible_adds),
        "permitted_action_class": "CIO_MANUAL_REVIEW_ONLY",
        "blocked_action_class": ["AUTOMATIC_DCA", "AUTOMATIC_SECOND_TRANCHE", "BROKER_MUTATION"],
        "orders_generated": 0,
        "order_routing_enabled": False,
    }
    return stage

