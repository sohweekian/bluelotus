from datetime import datetime, timezone

from acms_cop.reports.remediation_reconciliation import classify_cio_decisions


def test_weekend_stale_cio_decisions_are_non_blocking_without_pending_review():
    row = classify_cio_decisions(
        {
            "meta": {"market_session": "WEEKEND SNAPSHOT"},
            "cio_decisions": {"generated_at": "2026-06-20T00:00:00", "pending_review_count": 0},
        },
        now=datetime(2026, 6, 20, 8, 30, tzinfo=timezone.utc),
    )
    assert row["status"] == "CIO_DECISIONS_STALE_BUT_NON_BLOCKING"
    assert row["market_data_freshness_failure"] is False


def test_stale_cio_decisions_with_pending_review_require_review():
    row = classify_cio_decisions(
        {
            "meta": {"market_session": "REGULAR_OPEN"},
            "cio_decisions": {"generated_at": "2026-06-20T00:00:00", "pending_review_count": 2},
        },
        now=datetime(2026, 6, 20, 8, 30, tzinfo=timezone.utc),
    )
    assert row["status"] == "CIO_DECISIONS_STALE_REVIEW_REQUIRED"
