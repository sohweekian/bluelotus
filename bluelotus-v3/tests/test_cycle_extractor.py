import json

from acms_cop.extractors.cycle_extractor import extract_cycle


def test_cycle_extractor_preserves_execution_doctrine(tmp_path):
    p = tmp_path / "dataset_raw.json"
    ds = {
        "meta": {"generated_at": "2026-06-18T05:47:36", "export_version": "V3"},
        "regime": {"regime": "MILD RISK OFF", "score": -1, "vix_level": 18.4},
        "portfolio": {"total_assets": 100000, "cash": 94000, "market_val": 6000, "positions": {}},
        "deterministic_operators": {
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "orders_generated": 0,
            "summary": {"blocked_actions": ["SECOND_TRANCHE_ADD"]},
        },
        "execution": {"order_generation_enabled": False},
    }
    p.write_text(json.dumps(ds), encoding="utf-8")
    row = extract_cycle(ds, p)
    assert row["execution_authority"] == "CIO_ONLY_MANUAL"
    assert row["order_routing_enabled"] is False
    assert row["llm_order_generation_enabled"] is False
    assert row["system_generated_orders"] == 0
    assert row["cash_fortress_mode"] is True
    assert row["dataset_hash"]

