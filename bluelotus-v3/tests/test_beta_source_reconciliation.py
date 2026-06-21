from acms_cop.reports.remediation_reconciliation import reconcile_beta_sources


def test_insufficient_history_labels_str_proxy_without_conflict():
    row = reconcile_beta_sources(
        {"risk_model": {"return_observations": 0, "beta_to_spy": 0}},
        {"hedge_ratio_review": {"portfolio_beta_to_spy": 2.5}},
    )
    assert row["risk_model_beta"] is None
    assert row["risk_model_beta_status"] == "RISK_MODEL_BETA_UNAVAILABLE"
    assert row["str_proxy_beta_status"] == "STR_PROXY_BETA_ESTIMATE"
    assert row["beta_conflict"] is False
    assert row["beta_source_mismatch"] == "expected_due_to_history_insufficient"


def test_validated_beta_sources_can_conflict():
    row = reconcile_beta_sources(
        {"risk_model": {"return_observations": 90, "beta_to_spy": 0.2}},
        {"hedge_ratio_review": {"portfolio_beta_to_spy": 2.5}},
    )
    assert row["risk_model_beta_status"] == "HISTORICAL_BETA_VALIDATED"
    assert row["beta_conflict"] is True
