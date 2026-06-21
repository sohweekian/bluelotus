from acms_cop.learning.hedge_ratio_reviewer import build_hedge_ratio_review, review_hedge_ratio


def test_hedge_review_never_routes_orders():
    row = review_hedge_ratio(1.0, 10000, 500, 500, hedge_effectiveness=4.0)
    assert row["advisory_only"] is True
    assert row["orders_generated"] == 0
    assert row["order_routing_enabled"] is False
    assert "does not create a hedge order" in row["disclaimer"]
    assert row["hedge_status"] in {"UNDER_HEDGED", "ROUGHLY_HEDGED", "OVER_HEDGED", "HEDGE_DATA_INSUFFICIENT"}


def test_hedge_review_reports_under_hedged_when_gap_large():
    row = review_hedge_ratio(2.0, 10000, 100, 100, hedge_effectiveness=4.0, event_failure_probability=0.5)
    assert row["hedge_status"] == "UNDER_HEDGED"
    assert row["hedge_gap_usd"] > 0


def test_hedge_review_reads_live_position_market_value_aliases():
    dataset = {
        "portfolio": {
            "market_val": 10000,
            "positions": {
                "VXX": {"qty": 50, "price": 22.8, "mkt_val": 1140.0},
                "VIXY": {"qty": 50, "price": 21.9, "market_value": 1095.0},
                "QUBT": {"qty": 100, "price": 10.0, "mkt_val": 1000.0},
            },
        },
        "risk_model": {
            "positions": [
                {"ticker": "QUBT", "market_value": 1000.0, "beta_to_spy": 2.0},
                {"ticker": "VXX", "market_value": 1140.0, "beta_to_spy": -4.0},
                {"ticker": "VIXY", "market_value": 1095.0, "beta_to_spy": -3.2},
            ]
        },
    }
    row = build_hedge_ratio_review(dataset)
    assert row["current_vxx_value"] == 1140.0
    assert row["current_vixy_value"] == 1095.0
    assert row["current_hedge_value"] == 2235.0
    assert row["data_quality_status"] == "RECONCILED"
    assert row["hedge_tickers_matched"] == ["VIXY", "VXX"]
    assert row["hedge_value_source"] == "dataset.portfolio.positions[*].mkt_val"


def test_hedge_review_reads_portfolio_readonly_list_shape():
    dataset = {
        "portfolio": {"market_val": 10000, "positions": []},
        "portfolio_readonly": {
            "positions": [
                {"ticker": "VXX", "market_value": 500.0},
                {"symbol": "VIXY", "qty": 10, "price": 20.0},
            ],
        },
    }
    row = build_hedge_ratio_review(dataset)
    assert row["current_hedge_value"] == 700.0
    assert row["hedge_tickers_matched"] == ["VIXY", "VXX"]
