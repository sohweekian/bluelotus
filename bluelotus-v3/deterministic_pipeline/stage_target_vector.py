from __future__ import annotations

from typing import Any, Dict

from canonical.target_usd_vector import build_target_usd_vector

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any], risk_overlay: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stage = stage_shell("Target Vector", ["portfolio", "shannon_thorp_refinement", "risk_overlay"], ["target_usd_vector"])
    vector = build_target_usd_vector(dataset, risk_overlay or {})
    stage["target_usd_vector"] = vector
    stage["target_row_count"] = vector.get("row_count", 0)
    return stage

