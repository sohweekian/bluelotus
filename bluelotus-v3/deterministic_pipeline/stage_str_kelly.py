from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("STR Kelly", ["shannon_thorp_refinement"], ["kelly_status"])
    str_data = dataset.get("shannon_thorp_refinement") if isinstance(dataset.get("shannon_thorp_refinement"), dict) else {}
    rows = str_data.get("kelly_sizing_advisory") or []
    stage["kelly_row_count"] = len(rows) if isinstance(rows, list) else 0
    stage["kelly_status"] = "AVAILABLE" if stage["kelly_row_count"] else "INSUFFICIENT_DATA"
    if not stage["kelly_row_count"]:
        stage["warnings"].append("kelly_advisory_missing")
    return stage

