from acms_cop.reports.remediation_reconciliation import build_remediation_reconciliation


def test_canonical_truth_source_marks_legacy_fields_deprecated():
    dataset = {
        "portfolio": {"cash": 1000, "buying_power": 1000, "buying_power_delta": 9999, "buying_power_delta_flag": True},
        "portfolio_readonly": {"buying_power": 1000, "cash": 1000},
        "orders": {"open_orders": []},
        "meta": {"market_session": "WEEKEND SNAPSHOT / LAST REGULAR CLOSE", "generated_at": "2026-06-20T02:00:00"},
        "regime": {"session_flag": "OPEN", "market_closed": False},
        "risk_model": {"return_observations": 0, "positions": [{"ticker": "ASTS"}]},
    }
    rem = build_remediation_reconciliation(dataset)
    canonical = rem["canonical_truth_source"]
    assert canonical["canonical_buying_power_delta"] == 0.0
    assert canonical["canonical_market_session"] == "WEEKEND_SNAPSHOT"
    assert canonical["legacy_fields"]["portfolio.buying_power_delta"]["do_not_render_as_primary"] is True
    assert rem["session_state"]["rendered_session_flag"] == "LEGACY_UNMAPPED"
    assert rem["session_state"]["rendered_market_closed"] is True
