from acms_cop.reports.remediation_reconciliation import resolve_snapshot_age


def test_formal_report_newer_than_dashboard_is_explicit_not_current():
    result = resolve_snapshot_age({
        "meta": {"generated_at": "2026-06-20T03:00:00+00:00"},
        "portfolio_readonly": {"cycle_ts": "2026-06-20T02:30:00+00:00"},
    })
    assert result["snapshot_alignment_status"] == "FORMAL_REPORT_NEWER_THAN_LIVE_DASHBOARD"
    assert result["formal_minus_dashboard_minutes"] == 30
