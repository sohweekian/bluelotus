from acms_cop.extractors.data_quality_extractor import extract_data_quality_events


def test_data_quality_sparse_empty_when_clean():
    rows = extract_data_quality_events({
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "llm_order_generation_enabled": False,
        "system_generated_orders": 0,
    }, [{"ticker": "A", "flow_bias": "INFLOW"}], [{"theme": "T"}], {"portfolio": {"positions": {}}, "source_health": []})
    assert rows == []


def test_data_quality_detects_safety_and_pnl_and_duplicate_theme():
    rows = extract_data_quality_events({
        "execution_authority": "AUTO",
        "order_routing_enabled": True,
        "llm_order_generation_enabled": False,
        "system_generated_orders": 1,
    }, [{"ticker": "A", "flow_bias": ""}], [{"theme": "T"}, {"theme": "T"}], {
        "portfolio": {"positions": {"QBTS": {"pnl_integrity_status": "BROKER_PNL_SOURCE_CONFLICT"}}},
        "source_health": [{"source": "X", "active": False}],
    })
    types = {r["issue_type"] for r in rows}
    assert {"EXECUTION_SAFETY_CONFLICT", "PNL_CONFLICT", "DUPLICATE_THEME", "MISSING_FIELD", "STALE_SOURCE"} <= types

