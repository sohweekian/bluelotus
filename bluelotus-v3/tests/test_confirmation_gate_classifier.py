from acms_cop.classifiers.confirmation_gate_classifier import classify_confirmation_gate


def test_confirmation_gate_blocks_when_macro_gate_unresolved():
    result = classify_confirmation_gate({
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "llm_order_generation_enabled": False,
        "system_generated_orders": 0,
        "pnl_integrity_status": "OK",
        "regime_label": "MILD RISK OFF",
    }, {"flow_confirmed": True})
    assert result["second_tranche_status"] == "BLOCKED"
    assert "regime_confirmed" in result["unresolved_gates"]

