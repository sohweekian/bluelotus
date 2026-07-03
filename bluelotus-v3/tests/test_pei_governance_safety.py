from pei.builder import build_prospective_event_intelligence


def _dataset():
    return {
        "law_governance_binding": {
            "status": "BOUND",
            "governance_pack_id": "GOVPACK_TEST",
            "governance_pack_hash": "hash",
            "report_memory_binding_id": "BIND_TEST",
        },
        "live_prices": {
            "ASTS": {"change_pct": -4.5},
            "RKLB": {"change_pct": 0.8},
            "LUNR": {"change_pct": 0.2},
            "PL": {"change_pct": -0.3},
        },
    }


def test_pei_fails_closed_without_law_binding():
    pei = build_prospective_event_intelligence({}, persist=False)

    assert pei["status"] == "GOVERNANCE_BINDING_MISSING"
    assert pei["execution_authority"] == "CIO_ONLY_MANUAL"
    assert pei["order_routing_enabled"] is False
    assert pei["orders_generated"] == 0
    assert pei["cio_action_cap"] == "ADD_BLOCKED"


def test_pei_never_generates_orders_or_enables_routing():
    pei = build_prospective_event_intelligence(_dataset(), persist=False)

    assert pei["status"] == "OPERATIONAL"
    assert pei["execution_authority"] == "CIO_ONLY_MANUAL"
    assert pei["order_routing_enabled"] is False
    assert pei["orders_generated"] == 0
    assert all(forecast["routing_enabled"] is False for forecast in pei["forecast_registry"])
    assert all(forecast["orders_generated"] == 0 for forecast in pei["forecast_registry"])
