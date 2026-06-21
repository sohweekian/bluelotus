from acms_cop.learning.kelly_edge_calculator import build_kelly_sizing_advisory


def _dataset():
    positions = {
        "ASTS": {"qty": 10, "price": 100, "mkt_val": 1000, "cost_basis": 900},
        "PL": {"qty": 20, "price": 50, "mkt_val": 1000, "cost_basis": 800},
        "QUBT": {"qty": 30, "price": 10, "mkt_val": 300, "cost_basis": 250},
        "LUNR": {"qty": 40, "price": 20, "mkt_val": 800, "cost_basis": 700},
        "QBTS": {"qty": 50, "price": 30, "mkt_val": 1500, "cost_basis": 1200},
        "VXX": {"qty": 5, "price": 22, "mkt_val": 110, "cost_basis": 100},
        "VIXY": {"qty": 6, "price": 21, "mkt_val": 126, "cost_basis": 120},
    }
    forecasts = {
        t: {"ANALYST_CONSENSUS": {"analyst_upside_pct": 50, "probability_90d": 0.7}}
        for t in positions
    }
    return {"portfolio": {"total_assets": 10000, "positions": positions}, "research_forecasting": {"forecasts_by_ticker": forecasts}}


def test_held_tickers_join_to_live_market_value():
    rows = {r["ticker"]: r for r in build_kelly_sizing_advisory(_dataset())}
    for ticker, expected in {"ASTS": 1000, "PL": 1000, "QUBT": 300, "LUNR": 800, "QBTS": 1500}.items():
        assert rows[ticker]["current_position_usd"] == expected
        assert rows[ticker]["current_qty"] > 0
        assert rows[ticker]["current_price"] > 0
        assert rows[ticker]["holding_status"] == "HELD"


def test_volatility_hedges_are_not_ordinary_equity_kelly_opportunities():
    rows = {r["ticker"]: r for r in build_kelly_sizing_advisory(_dataset())}
    assert rows["VXX"]["kelly_status"] == "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
    assert rows["VIXY"]["kelly_status"] == "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
    assert rows["VXX"]["holding_status"] == "HELD_HEDGE_INSTRUMENT"
