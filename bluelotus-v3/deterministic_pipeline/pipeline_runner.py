from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from db_efficiency.object_store import build_object_reference

from .pipeline_manifest import PIPELINE_VERSION
from .pipeline_validator import validate_pipeline
from . import (
    stage_cio_review,
    stage_pei_event_gate,
    stage_risk_overlay,
    stage_signal_quality,
    stage_sleeve_rule,
    stage_source_capacity,
    stage_str_kelly,
    stage_target_vector,
    stage_universe_selection,
)


def _compact_stage(stage: Dict[str, Any]) -> Dict[str, Any]:
    compact = {
        "stage_name": stage.get("stage_name"),
        "stage_version": stage.get("stage_version"),
        "input_keys": stage.get("input_keys") or [],
        "output_keys": stage.get("output_keys") or [],
        "status": stage.get("status"),
        "warnings": stage.get("warnings") or [],
        "errors": stage.get("errors") or [],
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
    }
    if "risk_overlay" in stage:
        compact["output_ref"] = build_object_reference("RISK_OVERLAY", stage.get("risk_overlay"), source_key="risk_overlay")
        compact["risk_overlay_status"] = stage.get("risk_overlay_status")
    if "target_usd_vector" in stage:
        compact["output_ref"] = build_object_reference("TARGET_USD_VECTOR", stage.get("target_usd_vector"), source_key="target_usd_vector")
        compact["target_row_count"] = stage.get("target_row_count")
    for key in ("universe_tickers", "ticker_count", "quality_status", "source_coverage", "source_capacity_status", "sleeve_rule_count", "sleeve_rule_status", "pei_gate_status", "macro_gate_active", "kelly_row_count", "kelly_status", "cio_review_packet"):
        if key in stage:
            compact[key] = stage[key]
    if isinstance(compact.get("universe_tickers"), list) and len(compact["universe_tickers"]) > 50:
        compact["universe_tickers"] = compact["universe_tickers"][:50]
        compact["universe_truncated"] = True
    return compact


def run_deterministic_pipeline(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stages = []
    outputs: Dict[str, Any] = {}

    for mod in (
        stage_universe_selection,
        stage_signal_quality,
        stage_source_capacity,
        stage_sleeve_rule,
        stage_pei_event_gate,
        stage_str_kelly,
    ):
        stage = mod.run_stage(dataset)
        compact = _compact_stage(stage)
        stages.append(compact)
        outputs[stage["stage_name"]] = compact

    target_stage_initial = stage_target_vector.run_stage(dataset, {})
    risk_stage = stage_risk_overlay.run_stage(dataset, target_stage_initial.get("target_usd_vector"))
    risk_overlay = risk_stage.get("risk_overlay") or {}
    target_stage = stage_target_vector.run_stage(dataset, risk_overlay)
    target_vector = target_stage.get("target_usd_vector") or {}
    cio_stage = stage_cio_review.run_stage(dataset, risk_overlay, target_vector)

    for stage in (risk_stage, target_stage, cio_stage):
        compact = _compact_stage(stage)
        stages.append(compact)
        outputs[stage["stage_name"]] = compact

    payload = {
        "version": PIPELINE_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stage_count": len(stages),
        "stages": stages,
        "stage_outputs": outputs,
        "risk_overlay": risk_overlay,
        "target_usd_vector": target_vector,
        "final_status": "PASS" if all(stage.get("status") == "PASS" for stage in stages) else "WARN",
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
        "blocked_actions": ["AUTOMATIC_DCA", "AUTOMATIC_SECOND_TRANCHE", "BROKER_MUTATION"],
        "advisory_only": True,
    }
    payload["validation"] = validate_pipeline(payload)
    return payload
