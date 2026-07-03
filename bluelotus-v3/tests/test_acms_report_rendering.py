from acms_cop.reports.strategic_thinking_report import render_acms_cop_report


def test_acms_report_contains_required_sections_and_doctrine():
    report = render_acms_cop_report(
        {"regime_label": "MILD RISK OFF", "cio_posture": "REVIEW", "execution_authority": "CIO_ONLY_MANUAL", "order_routing_enabled": False, "llm_order_generation_enabled": False, "system_generated_orders": 0},
        [{"ticker": "QUBT", "flow_bias": "INFLOW", "acms_state": "CLEAN_ACCUMULATION", "price_direction": "UP"}],
        [{"theme": "QUANTUM", "acms_state": "REGIME_TRANSITION", "theme_direction": "RISK_ON", "confidence": 80}],
        [{"forecast_probability": 0.45, "horizon_sessions": 3, "forecast_question": "x", "outcome_definition": "y"}],
        [],
        [],
    )
    assert "ACMS-COP Strategic Thinking" in report
    assert "CIO Planning Dossier" in report
    assert "10 Strategic Questions" in report
    assert "CIO_ONLY_MANUAL" in report
