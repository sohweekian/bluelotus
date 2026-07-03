from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("Source Capacity", ["shannon_thorp_refinement", "signals"], ["source_capacity_status"])
    str_data = dataset.get("shannon_thorp_refinement") if isinstance(dataset.get("shannon_thorp_refinement"), dict) else {}
    rows = str_data.get("source_capacity") or str_data.get("source_capacity_rows") or []
    if rows:
        stage["source_capacity_status"] = "AVAILABLE"
        stage["source_capacity_rows"] = rows
    else:
        stage["source_capacity_status"] = "FALLBACK_SIGNAL_COVERAGE_ONLY"
        stage["warnings"].append("str_source_capacity_missing")
    return stage

