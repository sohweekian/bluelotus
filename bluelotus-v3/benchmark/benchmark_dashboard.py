from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from .benchmark_schema import BENCHMARK_VERSION
from .layer_attribution import build_layer_attribution
from .portfolio_scorecard import build_portfolio_scorecard
from .scenario_scorecard import build_scenario_scorecards
from .strategy_scorecard import build_strategy_scorecards

LOCK_PATH = Path(r"C:\bluelotus3\data\frontend\v3_4_observation_lock.json")


def _now() -> datetime:
    return datetime.now()


def build_observation_lock(dataset: Dict[str, Any] | None = None) -> Dict[str, Any]:
    now = _now()
    start = None
    if LOCK_PATH.exists():
        try:
            existing = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            start_text = existing.get("observation_started_at")
            if start_text:
                start = datetime.fromisoformat(start_text)
        except Exception:
            start = None
    if start is None:
        start = now
    end = start + timedelta(days=7)
    active = now < end
    lock = {
        "version": "v3.4-one-week-observation-lock",
        "observation_started_at": start.isoformat(timespec="seconds"),
        "observation_ends_at": end.isoformat(timespec="seconds"),
        "days_elapsed": round(max(0.0, (now - start).total_seconds() / 86400.0), 4),
        "upgrade_allowed": not active,
        "lock_status": "OBSERVATION_ACTIVE" if active else "OBSERVATION_COMPLETE",
        "protected_layers": ["canonical", "deterministic_pipeline_v3_2", "risk_overlay", "deterministic_replay_v3_3", "benchmark_dashboard_v3_4"],
        "allowed_actions": ["OBSERVE", "BUG_FIX", "DATA_QUALITY_FIX"],
        "blocked_actions": ["ARCHITECTURE_REFACTOR", "AUTONOMY_EXPANSION", "BROKER_MUTATION"],
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
    }
    try:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    except Exception:
        lock["persistence_warning"] = "observation_lock_file_write_failed"
    return lock


def build_benchmark_dashboard(dataset: Dict[str, Any]) -> Dict[str, Any]:
    replay = dataset.get("deterministic_replay_v3_3") if isinstance(dataset.get("deterministic_replay_v3_3"), dict) else {}
    strategy_scorecards = build_strategy_scorecards(replay.get("summary") or [])
    scenario_scorecards = build_scenario_scorecards(replay.get("benchmark_results") or [])
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    rankings = sorted(strategy_scorecards, key=lambda row: float(row.get("avg_sharpe_proxy") or -999), reverse=True)
    return {
        "version": BENCHMARK_VERSION,
        "benchmark_id": f"BENCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_generated_at": meta.get("generated_at"),
        "report_id": meta.get("cycle_id") or meta.get("generated_at"),
        "point_in_time_status": replay.get("point_in_time_guard_status", "INSUFFICIENT_METADATA"),
        "strategies": replay.get("strategies") or [],
        "strategy_scorecards": strategy_scorecards,
        "scenario_scorecards": scenario_scorecards,
        "portfolio_scorecard": build_portfolio_scorecard(dataset),
        "layer_attribution": build_layer_attribution(dataset),
        "benchmark_rankings": rankings,
        "one_week_observation_lock": build_observation_lock(dataset),
        "governance": {
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "orders_generated": 0,
            "broker_mutation_allowed": False,
        },
        "benchmark_dashboard_status": "PASS",
    }
