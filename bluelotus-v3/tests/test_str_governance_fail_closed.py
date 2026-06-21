from acms_cop.reports.signal_edge_dashboard_renderer import build_shannon_thorp_refinement


def test_str_governance_invariants_fail_closed():
    root = build_shannon_thorp_refinement({"meta": {"generated_at": "2026-06-20T00:00:00"}})
    assert root["execution_authority"] == "CIO_ONLY_MANUAL"
    assert root["order_routing_enabled"] is False
    assert root["system_orders_generated"] == 0
    assert root["doctrine"]["no_order_generation"] is True
    assert root["doctrine"]["no_broker_routing"] is True
    assert root["doctrine"]["does_not_override_cio_only_manual"] is True
