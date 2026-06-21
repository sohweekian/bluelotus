from datetime import datetime, timezone

from acms_cop.reports.remediation_reconciliation import build_remediation_reconciliation, reconcile_open_orders


def test_cio_trading_strategy_order_is_not_generic_blocked_add():
    rows = reconcile_open_orders(
        {"orders": {"open_orders": [{"ticker": "BKSY", "trd_side": "BUY", "qty": 50, "price": 28.75, "order_status": "WAITING_SUBMIT", "create_time": "2026-06-20T00:00:00"}]}},
        now=datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
    )
    row = rows[0]
    assert row["classification"] == "CIO_TRADING_STRATEGY_ORDER_PENDING"
    assert row["order_intent"] == "CIO_TRADING_STRATEGY_ORDER"
    assert row["still_live"] is True
    assert row["blocked_by_operator"] is False
    assert row["requires_cio_review"] is True
    assert row["cancelled"] is False
    assert row["filled"] is False


def test_gold_support_bid_order_is_cio_policy_pending_not_blocked():
    rows = reconcile_open_orders(
        {"orders": {"open_orders": [{"ticker": "AEM", "trd_side": "BUY", "qty": 7, "price": 151.50, "order_status": "WAITING_SUBMIT"}]}}
    )
    row = rows[0]
    assert row["classification"] == "CIO_APPROVED_GOLD_SUPPORT_BID_PENDING"
    assert row["order_intent"] == "GOLD_MINER_5D_SUPPORT_BID"
    assert row["policy_bucket"] == "gold_miners"
    assert row["policy_target_usd"] == 4000.0
    assert row["order_notional"] == 1060.5
    assert row["blocked_by_operator"] is False
    assert row["requires_cio_review"] is True


def test_unclassified_live_order_still_blocked_pending_cio_review_without_action():
    rows = reconcile_open_orders(
        {"orders": {"open_orders": [{"ticker": "XYZ", "trd_side": "BUY", "qty": 50, "price": 28.75, "order_status": "WAITING_SUBMIT", "create_time": "2026-06-20T00:00:00"}]}},
        now=datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
    )
    row = rows[0]
    assert row["classification"] == "LIVE_BLOCKED_PENDING_CIO_REVIEW"
    assert row["still_live"] is True
    assert row["blocked_by_operator"] is True
    assert row["requires_cio_review"] is True
    assert row["cancelled"] is False
    assert row["filled"] is False


def test_filled_order_classification():
    row = reconcile_open_orders({"orders": {"open_orders": [{"ticker": "PL", "qty": 10, "dealt_qty": 10, "order_status": "FILLED"}]}})[0]
    assert row["classification"] == "FILLED"
    assert row["filled"] is True


def test_gold_support_policy_aggregates_pending_orders_against_16000_target():
    rem = build_remediation_reconciliation({
        "orders": {
            "open_orders": [
                {"ticker": "AU", "trd_side": "BUY", "qty": 13, "price": 76.90, "order_status": "WAITING_SUBMIT"},
                {"ticker": "NEM", "trd_side": "BUY", "qty": 11, "price": 92.40, "order_status": "WAITING_SUBMIT"},
                {"ticker": "AEM", "trd_side": "BUY", "qty": 7, "price": 151.50, "order_status": "WAITING_SUBMIT"},
                {"ticker": "B", "trd_side": "BUY", "qty": 28, "price": 37.00, "order_status": "WAITING_SUBMIT"},
            ]
        },
        "portfolio": {"positions": {}},
    })
    policy = rem["gold_support_bid_policy"]
    assert policy["total_target_usd"] == 16000.0
    assert policy["per_ticker_target_usd"] == 4000.0
    assert policy["pending_order_notional"] == 4112.6
    assert policy["remaining_to_target"] == 11887.4
