from acms_cop.learning.kelly_edge_calculator import build_kelly_sizing_advisory


def test_kelly_rows_use_sleeve_fields_not_full_dictionary_blob():
    dataset = {
        "portfolio": {"total_assets": 100000, "positions": {}},
        "research_forecasting": {
            "forecasts_by_ticker": {
                "PL": {"ANALYST_CONSENSUS": {"analyst_upside_pct": 20, "probability_90d": 0.7}}
            }
        },
        "cio_context_capsule": {
            "active_sleeve_rules": {
                "foundational_tactical_cash_engine": {
                    "role": "TACTICAL_CASH_GENERATION_ENGINE",
                    "tickers": ["PL", "ASTS"],
                    "current_policy": "MAY_SCALE_STAGED_TO_4000_MAX",
                    "max_capital_per_ticker_usd": 4000,
                    "kill_conditions": ["support_break_without_reclaim"],
                }
            }
        },
    }
    row = build_kelly_sizing_advisory(dataset)[0]
    assert row["active_sleeve_rule"] == "foundational_tactical_cash_engine"
    assert row["sleeve_id"] == "foundational_tactical_cash_engine"
    assert "gold_miners" not in row["active_sleeve_rule"]
    assert isinstance(row["kill_condition_refs"], list)
