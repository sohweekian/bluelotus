from __future__ import annotations

from typing import Any, Dict, List

from pei import PEI_VERSION
from pei.brier_crs_engine import crs_decomposition
from pei.common import PEI_LATEST_PATH, atomic_write_json, sgt_now
from pei.db_schema import run_migrations
from pei.event_cascade_model import cascade_model_status
from pei.event_registry import build_candidate_events, persist_events
from pei.event_to_sleeve_mapper import build_sleeve_map, persist_sleeve_map
from pei.event_tree_builder import build_scenario_trees, persist_branches
from pei.forecast_registry import build_forecast_registry, persist_forecasts
from pei.forecast_scorecards import forecast_registry_snapshot
from pei.oscillation_engine_calibrator import calibrate_oscillation_engine, persist_oscillation_calibration
from pei.portfolio_playbook_renderer import build_portfolio_playbook, persist_playbook
from pei.reflexive_suppression_detector import detect_reflexive_suppression, persist_reflexive_suppression


def _law_binding(dataset: Dict[str, Any]) -> Dict[str, Any]:
    value = dataset.get("law_governance_binding")
    return value if isinstance(value, dict) else {}


def _kill_condition_summary(playbook: List[Dict[str, Any]]) -> Dict[str, Any]:
    conditions = []
    for row in playbook:
        conditions.extend(row.get("kill_conditions") or [])
    unique = sorted({str(c) for c in conditions if c})
    return {
        "status": "WATCH",
        "active_watch_count": len(unique),
        "kill_conditions": unique[:20],
    }


def build_prospective_event_intelligence(dataset: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    law = _law_binding(dataset)
    if not law or not law.get("governance_pack_id"):
        return {
            "status": "GOVERNANCE_BINDING_MISSING",
            "version": PEI_VERSION,
            "generated_at_sgt": sgt_now(),
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "orders_generated": 0,
            "cio_action_cap": "ADD_BLOCKED",
            "warning": "PEI cannot operate without active governance law binding.",
        }

    if persist:
        run_migrations()

    events = build_candidate_events(dataset)
    scenario_trees = build_scenario_trees(events)
    sleeve_map = build_sleeve_map(scenario_trees)
    playbook = build_portfolio_playbook(scenario_trees, sleeve_map)
    forecasts = build_forecast_registry(scenario_trees)
    suppression = detect_reflexive_suppression(dataset, "ASTS")
    oscillation = {
        ticker: calibrate_oscillation_engine(ticker)
        for ticker in ["ASTS", "PL", "RKLB", "LUNR", "QBTS", "QUBT"]
    }
    brier_status = forecast_registry_snapshot(forecasts)
    crs = crs_decomposition([])
    cascade_status = cascade_model_status(len(events), 0)

    if persist:
        persist_events(events)
        persist_branches(scenario_trees)
        persist_sleeve_map(sleeve_map)
        persist_playbook(playbook)
        persist_forecasts(forecasts)
        persist_reflexive_suppression(suppression)
        for calibration in oscillation.values():
            persist_oscillation_calibration(calibration)

    payload = {
        "status": "OPERATIONAL",
        "version": PEI_VERSION,
        "generated_at_sgt": sgt_now(),
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
        "broker_api_role": "READ_ONLY_EXTRACTION",
        "pei_authority": "RESEARCH / FORECASTING / PREPARATION ONLY",
        "governance_pack_id": law.get("governance_pack_id", ""),
        "governance_pack_hash": law.get("governance_pack_hash", ""),
        "report_memory_binding_id": law.get("report_memory_binding_id", ""),
        "active_events": [event.to_dict() for event in events],
        "scenario_trees": scenario_trees,
        "event_to_sleeve_map": sleeve_map,
        "portfolio_playbook": playbook,
        "forecast_registry_snapshot": brier_status,
        "forecast_registry": forecasts,
        "brier_status": brier_status,
        "crs_decomposition": crs,
        "reflexive_suppression": suppression,
        "oscillation_engine": oscillation,
        "hawkes_branching_estimator": cascade_status,
        "kill_condition_summary": _kill_condition_summary(playbook),
        "failure_mode": None,
        "cio_action_cap": "UNCHANGED_UNLESS_TREE_INVALID",
    }
    atomic_write_json(PEI_LATEST_PATH, payload)
    return payload
