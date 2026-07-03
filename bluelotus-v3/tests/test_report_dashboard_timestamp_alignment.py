from acms_cop.reports.remediation_reconciliation import resolve_snapshot_age


def test_snapshot_age_banner_marks_live_dashboard_newer():
    row = resolve_snapshot_age({
        "meta": {"generated_at": "2026-06-20T01:00:00"},
        "portfolio_readonly": {"cycle_ts": "2026-06-20T01:20:00"},
    })
    assert row["AGE_DELTA_MINUTES"] == 20
    assert row["REPORT_STALENESS_STATUS"] == "LIVE_DASHBOARD_NEWER"


def test_snapshot_age_banner_current_when_aligned():
    row = resolve_snapshot_age({
        "meta": {"generated_at": "2026-06-20T01:00:00"},
        "portfolio_readonly": {"cycle_ts": "2026-06-20T01:02:00"},
    })
    assert row["REPORT_STALENESS_STATUS"] == "CURRENT"
