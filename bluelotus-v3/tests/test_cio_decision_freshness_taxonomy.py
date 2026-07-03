from datetime import datetime, timezone

from acms_cop.reports.remediation_reconciliation import classify_cio_decisions


def test_cio_decision_staleness_is_governance_context_not_market_data():
    result = classify_cio_decisions(
        {"cio_decisions": {"generated_at": "2026-06-19T00:00:00+00:00", "pending_review_count": 1}},
        now=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
    )
    assert result["governance_context_stale"] is True
    assert result["cio_context_stale_review_required"] is True
    assert result["market_data_freshness_failure"] is False
