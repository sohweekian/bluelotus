from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(r"C:\bluelotus3")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from canonical.canonical_data_contract import build_v3_1_to_v3_4_payload
from db_efficiency.object_store import build_cycle_manifest, build_object_reference, object_hash, payload_size_bytes
from db_efficiency.public_dataset import build_public_dataset


def sample_dataset() -> dict:
    return {
        "meta": {"generated_at": "2026-06-20T04:00:00", "market_session": "WEEKEND_SNAPSHOT", "sources_active": 3, "sources_expected": 3, "total_signals": 8},
        "regime": {"regime": "MILD_RISK_OFF", "score": -2, "session_flag": "CLOSED"},
        "portfolio": {
            "cash": 56000,
            "total_assets": 60000,
            "positions": [
                {"ticker": "BKSY", "qty": 10, "price": 5.0, "market_value": 50.0, "thesis": "SPACE HIGH BETA"},
                {"ticker": "VXX", "qty": 5, "price": 20.0, "market_value": 100.0, "thesis": "HEDGE"},
            ],
        },
        "orders": {"open_orders": []},
        "live_prices": {"BKSY": {"price": 5.0}, "VXX": {"price": 20.0}},
        "prospective_event_intelligence": {
            "version": "pei_test",
            "status": "OPERATIONAL",
            "active_events": [{"event_id": "WARSH"}],
            "forecast_registry": [{"forecast_id": "F1"}],
            "large_blob": ["x" * 1000 for _ in range(20)],
        },
        "shannon_thorp_refinement": {
            "version": "str_test",
            "status": "OPERATIONAL",
            "kelly_sizing_advisory": [{"ticker": "BKSY", "capped_advisory_usd": 1500} for _ in range(25)],
            "signal_entropy": [{"ticker": "BKSY", "entropy": 0.5} for _ in range(25)],
        },
    }


def test_object_hash_is_stable_for_key_order() -> None:
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert object_hash(a) == object_hash(b)


def test_object_reference_is_compact() -> None:
    payload = {"status": "PASS", "rows": [{"x": i} for i in range(50)]}
    ref = build_object_reference("TEST", payload, source_key="unit")
    assert ref["object_type"] == "TEST"
    assert len(ref["object_hash"]) == 64
    assert ref["payload_size_bytes"] == payload_size_bytes(payload)
    assert ref["row_count"] == 50
    assert "rows" not in ref


def test_canonical_uses_refs_not_full_duplicate_str_pei_risk() -> None:
    dataset = build_v3_1_to_v3_4_payload(sample_dataset())
    canonical = dataset["canonical"]
    assert "object_ref" in canonical["str_state"]
    assert "object_ref" in canonical["pei_state"]
    assert "object_ref" in canonical["risk_state"]
    assert "kelly_sizing_advisory" not in canonical["str_state"]
    assert "forecast_registry" not in canonical["pei_state"]
    assert "ticker_outputs" not in canonical["risk_state"]


def test_pipeline_uses_compact_stage_refs() -> None:
    dataset = build_v3_1_to_v3_4_payload(sample_dataset())
    pipeline = dataset["deterministic_pipeline_v3_2"]
    risk_stage = next(stage for stage in pipeline["stages"] if stage["stage_name"] == "Risk Overlay")
    target_stage = next(stage for stage in pipeline["stages"] if stage["stage_name"] == "Target Vector")
    assert "output_ref" in risk_stage
    assert "output_ref" in target_stage
    assert "risk_overlay" not in risk_stage
    assert "target_usd_vector" not in target_stage
    assert "risk_overlay" in pipeline
    assert "target_usd_vector" in pipeline


def test_public_dataset_is_smaller_and_preserves_safety() -> None:
    dataset = build_v3_1_to_v3_4_payload(sample_dataset())
    public = build_public_dataset(dataset)
    assert payload_size_bytes(public) < payload_size_bytes(dataset)
    assert public["execution_authority"] == "CIO_ONLY_MANUAL"
    assert public["order_routing_enabled"] is False
    assert public["system_orders_generated"] == 0
    assert public["canonical_summary"]["validation"]["status"] == "PASS"


def test_cycle_manifest_references_major_objects() -> None:
    dataset = build_v3_1_to_v3_4_payload(sample_dataset())
    manifest = build_cycle_manifest(dataset)
    refs = manifest["object_references"]
    for key in ["canonical", "shannon_thorp_refinement", "prospective_event_intelligence", "risk_overlay", "deterministic_pipeline_v3_2", "deterministic_replay_v3_3", "benchmark_dashboard_v3_4"]:
        assert key in refs
        assert len(refs[key]["object_hash"]) == 64
    assert manifest["order_routing_enabled"] is False
    assert manifest["system_orders_generated"] == 0
