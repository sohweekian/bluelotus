from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"C:\bluelotus3")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from canonical.canonical_data_contract import build_v3_1_to_v3_4_payload
from canonical.target_usd_vector import build_target_usd_vector
from deterministic_pipeline.pipeline_runner import run_deterministic_pipeline
from replay.replay_engine import build_deterministic_replay
from risk.risk_overlay import build_risk_overlay
from benchmark.benchmark_dashboard import build_benchmark_dashboard, build_observation_lock


def sample_dataset() -> dict:
    return {
        "meta": {
            "generated_at": "2026-06-20T03:00:00",
            "market_session": "MARKET_CLOSED_LAST_REGULAR_CLOSE",
            "sources_active": 50,
            "sources_expected": 54,
            "total_signals": 120,
        },
        "regime": {"regime": "MILD_RISK_OFF", "score": -2, "session_flag": "CLOSED"},
        "portfolio": {
            "cash": 56000,
            "total_assets": 60000,
            "positions": [
                {"ticker": "BKSY", "qty": 10, "price": 5.0, "market_value": 50.0, "thesis": "SPACE HIGH BETA"},
                {"ticker": "VXX", "qty": 5, "price": 20.0, "market_value": 100.0, "thesis": "HEDGE"},
            ],
        },
        "orders": {
            "open_order_count": 1,
            "open_orders": [{"ticker": "BKSY", "status": "WAITING_SUBMIT", "estimated_value": 500}],
        },
        "live_prices": {"BKSY": {"price": 5.0}, "VXX": {"price": 20.0}},
        "prospective_event_intelligence": {"active_events": [{"event": "WARSH_HAWKISH"}]},
        "shannon_thorp_refinement": {
            "kelly_sizing_advisory": [
                {"ticker": "BKSY", "capped_advisory_usd": 1500},
                {"ticker": "VXX", "capped_advisory_usd": 3000},
            ]
        },
    }


def test_target_vector_is_advisory_only_and_excludes_hedges() -> None:
    vector = build_target_usd_vector(sample_dataset())
    assert vector["execution_authority"] == "CIO_ONLY_MANUAL"
    assert vector["order_routing_enabled"] is False
    assert vector["system_orders_generated"] == 0
    rows = {row["ticker"]: row for row in vector["rows"]}
    assert rows["VXX"]["action_classification"] == "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
    assert rows["BKSY"]["cash_fortress_constraint"] == "CASH_FORTRESS_ACTIVE"


def test_risk_overlay_preserves_safety_invariants() -> None:
    overlay = build_risk_overlay(sample_dataset())
    assert overlay["execution_authority"] == "CIO_ONLY_MANUAL"
    assert overlay["order_routing_enabled"] is False
    assert overlay["system_orders_generated"] == 0
    assert overlay["portfolio"]["cash_overlay_status"] == "CASH_FORTRESS_ACTIVE"
    assert "portfolio_beta_estimate" in overlay["portfolio"]
    assert "VaR95_display" in overlay["portfolio"]


def test_pipeline_has_required_nine_stages() -> None:
    pipeline = run_deterministic_pipeline(sample_dataset())
    assert pipeline["validation"]["status"] == "PASS"
    assert pipeline["stage_count"] == 9
    assert pipeline["orders_generated"] == 0
    assert pipeline["order_routing_enabled"] is False
    names = [stage["stage_name"] for stage in pipeline["stages"]]
    assert names == [
        "Universe Selection",
        "Signal Quality",
        "Source Capacity",
        "Sleeve Rule",
        "PEI Event Gate",
        "STR Kelly",
        "Risk Overlay",
        "Target Vector",
        "CIO Review",
    ]


def test_replay_has_twelve_strategies_and_nine_scenarios() -> None:
    replay = build_deterministic_replay(sample_dataset())
    assert replay["strategy_count"] >= 12
    assert replay["scenario_count"] >= 9
    assert len(replay["benchmark_results"]) >= 108
    assert replay["point_in_time_guard_status"] == "PASS"
    assert replay["orders_generated"] == 0


def test_benchmark_dashboard_and_observation_lock_are_governed() -> None:
    ds = sample_dataset()
    ds = build_v3_1_to_v3_4_payload(ds)
    dashboard = build_benchmark_dashboard(ds)
    lock = build_observation_lock(ds)
    assert dashboard["governance"]["execution_authority"] == "CIO_ONLY_MANUAL"
    assert dashboard["governance"]["order_routing_enabled"] is False
    assert dashboard["governance"]["orders_generated"] == 0
    assert dashboard["strategy_scorecards"]
    assert dashboard["scenario_scorecards"]
    assert lock["lock_status"] in {"OBSERVATION_ACTIVE", "OBSERVATION_COMPLETE"}
    assert "upgrade_allowed" in lock


def test_full_payload_contains_v3_1_to_v3_4_keys() -> None:
    payload = build_v3_1_to_v3_4_payload(sample_dataset())
    for key in [
        "canonical",
        "risk_overlay",
        "deterministic_pipeline_v3_2",
        "deterministic_replay_v3_3",
        "benchmark_dashboard_v3_4",
        "v3_4_observation_lock",
    ]:
        assert key in payload
    assert payload["canonical"]["validation"]["status"] == "PASS"
    assert payload["canonical"]["governance"]["broker_mode"] == "READ_ONLY"


def test_schema_files_and_db_migration_exist() -> None:
    schema_names = [
        "canonical_data_contract.schema.json",
        "artifact_manifest.schema.json",
        "target_usd_vector.schema.json",
        "deterministic_pipeline.schema.json",
        "risk_overlay.schema.json",
        "replay_engine.schema.json",
        "backtest_result.schema.json",
        "benchmark_result.schema.json",
        "benchmark_dashboard.schema.json",
        "benchmark_scorecard.schema.json",
    ]
    for name in schema_names:
        path = PROJECT_ROOT / "schemas" / name
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["type"] == "object"
    migration = PROJECT_ROOT / "db" / "v3_4_architecture_tables.sql"
    assert migration.exists()
    assert "CREATE TABLE IF NOT EXISTS benchmark_dashboards" in migration.read_text(encoding="utf-8")
