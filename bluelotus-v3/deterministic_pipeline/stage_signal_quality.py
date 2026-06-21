from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("Signal Quality", ["signals", "signals_latest"], ["quality_status"])
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    total = int(meta.get("total_signals") or 0)
    active = int(meta.get("sources_active") or 0)
    expected = int(meta.get("sources_expected") or active or 0)
    coverage = active / expected if expected else 0.0
    stage["total_signals"] = total
    stage["source_coverage"] = round(coverage, 6)
    stage["quality_status"] = "PASS" if coverage >= 0.70 or total > 0 else "DEGRADED"
    if stage["quality_status"] != "PASS":
        stage["warnings"].append("low_signal_or_source_coverage")
    return stage

