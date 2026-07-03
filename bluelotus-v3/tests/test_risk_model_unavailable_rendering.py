from acms_cop.reports.remediation_reconciliation import build_risk_model_canonical_status
from research.research_report_generator import build_risk_summary_rows


def test_zero_observations_render_var_beta_unavailable():
    dataset = {"risk_model": {"return_observations": 0, "positions": [{"ticker": "ASTS"}], "beta_to_spy": 0}}
    status = build_risk_model_canonical_status(dataset)
    rows = dict(build_risk_summary_rows(dataset))
    assert status["portfolio_var_status"] == "PORTFOLIO_VAR_UNAVAILABLE"
    assert status["VaR95_display"] == "UNAVAILABLE - HISTORY_INSUFFICIENT"
    assert rows["VaR 95 Daily $"] == "UNAVAILABLE - HISTORY_INSUFFICIENT"
    assert rows["Beta To SPY"] == "UNAVAILABLE - HISTORY_INSUFFICIENT"
