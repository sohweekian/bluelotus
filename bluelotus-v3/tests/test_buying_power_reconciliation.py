from acms_cop.reports.remediation_reconciliation import reconcile_buying_power


def test_open_orders_reduce_available_buying_power():
    row = reconcile_buying_power({
        "portfolio": {"cash": 10000, "buying_power": 9000},
        "portfolio_readonly": {"cash": 10000, "buying_power": 9000},
        "orders": {"open_orders": [{"trd_side": "BUY", "qty": 10, "price": 100, "order_status": "SUBMITTED"}]},
    })
    assert row["open_order_reserved_cash"] == 1000
    assert row["computed_buying_power"] == 9000
    assert row["buying_power_delta_flag"] is False


def test_cash_only_not_compared_directly_against_margin_buying_power():
    row = reconcile_buying_power({"portfolio": {"cash": 10000}, "portfolio_readonly": {"cash": 10000, "buying_power": 20000}})
    assert row["status"] == "RECONCILED"
    assert row["margin_adjustment"] == 10000


def test_delta_always_has_explanation():
    row = reconcile_buying_power({"portfolio": {"cash": 10000, "buying_power": 10000}, "portfolio_readonly": {"cash": 10000, "buying_power": 10000}})
    assert row["delta_explanation"]


def test_unexplained_delta_triggers_review_when_threshold_exceeded():
    row = reconcile_buying_power({"portfolio": {"cash": 10000, "buying_power": 10000}, "portfolio_readonly": {"cash": 10000, "buying_power": 10000, "settlement_adjustment": -1200}})
    assert row["status"] == "REVIEW"
    assert row["buying_power_delta_flag"] is True
