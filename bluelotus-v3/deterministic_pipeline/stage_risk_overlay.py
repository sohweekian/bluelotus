from __future__ import annotations

from typing import Any, Dict

from risk.risk_overlay import build_risk_overlay

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any], target_vector: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stage = stage_shell("Risk Overlay", ["portfolio", "orders", "target_usd_vector"], ["risk_overlay"])
    risk_overlay = build_risk_overlay(dataset, target_vector)
    stage["risk_overlay"] = risk_overlay
    stage["risk_overlay_status"] = risk_overlay.get("risk_overlay_status")
    return stage

