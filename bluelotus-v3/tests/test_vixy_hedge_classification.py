from acms_cop.reports.cio_order_policy import apply_policy_security_overrides


def test_vixy_is_volatility_hedge_not_unknown_equity():
    dataset = {"security_master": {"VIXY": {"sector": "UNKNOWN", "industry": "UNKNOWN"}}}
    apply_policy_security_overrides(dataset)
    row = dataset["security_master"]["VIXY"]
    assert row["sector"] == "VOLATILITY"
    assert row["industry"] == "VOLATILITY_ETP"
    assert row["instrument_role"] == "HEDGE_INSTRUMENT"
    assert row["equity_kelly_eligible"] is False
