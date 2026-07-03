from acms_cop.reports.remediation_reconciliation import reconcile_open_orders


def test_waiting_submit_is_pending_not_live_on_exchange():
    rows = reconcile_open_orders({
        "orders": {"open_orders": [
            {"ticker": "AU", "trd_side": "BUY", "qty": 13, "price": 76.90, "order_status": "WAITING_SUBMIT"}
        ]}
    })
    assert rows[0]["canonical_order_state"] == "WAITING_SUBMIT_PENDING"
    assert rows[0]["is_live_on_exchange"] is False


def test_submitted_is_live_on_exchange():
    rows = reconcile_open_orders({
        "orders": {"open_orders": [
            {"ticker": "XYZ", "trd_side": "BUY", "qty": 1, "price": 10, "order_status": "SUBMITTED"}
        ]}
    })
    assert rows[0]["canonical_order_state"] == "SUBMITTED_LIVE"
    assert rows[0]["is_live_on_exchange"] is True
