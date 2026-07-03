from acms_cop.reports.remediation_reconciliation import resolve_session_state


def test_weekend_snapshot_canonical_status():
    row = resolve_session_state({"meta": {"market_session": "WEEKEND SNAPSHOT / LAST REGULAR CLOSE"}})
    assert row["market_session_canonical"] == "WEEKEND_SNAPSHOT"
    assert row["weekend_snapshot"] is True
    assert row["regular_market_open"] is False


def test_after_hours_canonical_status():
    row = resolve_session_state({"meta": {"market_session": "POST_MARKET"}})
    assert row["market_session_canonical"] == "AFTER_HOURS"
    assert row["after_hours_active"] is True
