from __future__ import annotations

from typing import Any, Dict

from db_efficiency.object_store import build_object_reference

from .artifact_manifest import build_artifact_manifest
from .canonical_schema import CANONICAL_VERSION
from .canonical_validator import validate_canonical_contract
from .target_usd_vector import build_target_usd_vector
from .truth_source_resolver import (
    build_truth_source_audit,
    now_iso,
    resolve_governance,
    resolve_order_state,
    resolve_portfolio_state,
    resolve_session,
)


def build_canonical_contract(
    dataset: Dict[str, Any],
    risk_overlay: Dict[str, Any] | None = None,
    artifact_paths: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    governance = resolve_governance(dataset)
    session = resolve_session(dataset)
    portfolio = resolve_portfolio_state(dataset)
    orders = resolve_order_state(dataset)
    risk_state = risk_overlay or dataset.get("risk_overlay") or {}
    target = build_target_usd_vector(dataset, risk_state if isinstance(risk_state, dict) else {})
    manifest = build_artifact_manifest(dataset, artifact_paths)
    truth = build_truth_source_audit(dataset, session, portfolio)
    pei_payload = dataset.get("prospective_event_intelligence") or {}
    str_payload = dataset.get("shannon_thorp_refinement") or {}
    risk_payload = risk_state if isinstance(risk_state, dict) else {}
    contract = {
        "version": CANONICAL_VERSION,
        "generated_at": now_iso(),
        "governance": governance,
        "market_state": {
            "regime": (dataset.get("regime") or {}).get("regime") if isinstance(dataset.get("regime"), dict) else None,
            "regime_score": (dataset.get("regime") or {}).get("score") if isinstance(dataset.get("regime"), dict) else None,
        },
        "session_state": session,
        "portfolio_state": portfolio,
        "order_state": orders,
        "risk_state": {
            "status": risk_payload.get("risk_overlay_status") if isinstance(risk_payload, dict) else "UNKNOWN",
            "object_ref": build_object_reference("RISK_OVERLAY", risk_payload, source_key="risk_overlay", schema_version=str(risk_payload.get("version", "")) if isinstance(risk_payload, dict) else ""),
        },
        "pei_state": {
            "status": pei_payload.get("status") if isinstance(pei_payload, dict) else "UNKNOWN",
            "active_event_count": len(pei_payload.get("active_events") or []) if isinstance(pei_payload, dict) else 0,
            "forecast_count": len(pei_payload.get("forecast_registry") or []) if isinstance(pei_payload, dict) else 0,
            "object_ref": build_object_reference("PEI", pei_payload, source_key="prospective_event_intelligence", schema_version=str(pei_payload.get("version", "")) if isinstance(pei_payload, dict) else ""),
        },
        "str_state": {
            "status": str_payload.get("status") if isinstance(str_payload, dict) else "UNKNOWN",
            "kelly_row_count": len(str_payload.get("kelly_sizing_advisory") or []) if isinstance(str_payload, dict) else 0,
            "signal_entropy_count": len(str_payload.get("signal_entropy") or []) if isinstance(str_payload, dict) else 0,
            "object_ref": build_object_reference("STR", str_payload, source_key="shannon_thorp_refinement", schema_version=str(str_payload.get("version", "")) if isinstance(str_payload, dict) else ""),
        },
        "target_usd_vector": target,
        "artifact_manifest": manifest,
        "truth_source_audit": truth,
    }
    contract["validation"] = validate_canonical_contract(contract)
    return contract


def build_v3_1_to_v3_4_payload(dataset: Dict[str, Any]) -> Dict[str, Any]:
    from deterministic_pipeline.pipeline_runner import run_deterministic_pipeline
    from replay.replay_engine import build_deterministic_replay
    from benchmark.benchmark_dashboard import build_benchmark_dashboard, build_observation_lock

    pipeline = run_deterministic_pipeline(dataset)
    risk_overlay = pipeline.get("risk_overlay") or dataset.get("risk_overlay") or {}
    canonical = build_canonical_contract(dataset, risk_overlay=risk_overlay)
    dataset["canonical"] = canonical
    dataset["risk_overlay"] = risk_overlay
    dataset["deterministic_pipeline_v3_2"] = pipeline
    dataset["deterministic_replay_v3_3"] = build_deterministic_replay(dataset)
    dataset["benchmark_dashboard_v3_4"] = build_benchmark_dashboard(dataset)
    dataset["v3_4_observation_lock"] = build_observation_lock(dataset)
    dataset["canonical"]["target_usd_vector"] = dataset["canonical"]["target_usd_vector"]
    return dataset
