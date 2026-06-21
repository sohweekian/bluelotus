from __future__ import annotations

import sys
from pathlib import Path


V3_ROOT = Path(__file__).resolve().parents[1]
if str(V3_ROOT) not in sys.path:
    sys.path.insert(0, str(V3_ROOT))


def test_weekday_weekend_snapshot_normalizes_to_last_regular_close():
    from research.research_report_generator import normalize_market_session

    assert (
        normalize_market_session("WEEKEND SNAPSHOT / LAST REGULAR CLOSE", "2026-06-18T00:22:33")
        == "MARKET_CLOSED_LAST_REGULAR_CLOSE"
    )


def test_source_coverage_label_distinguishes_baseline():
    from research.research_report_generator import source_coverage_label

    assert source_coverage_label(70, 52) == "Sources active: 70 / baseline 52"


def test_ece_price_action_label_discloses_causal_gap():
    from research.research_report_generator import causal_price_action_label

    assert (
        causal_price_action_label("RISK_ON", ["PARTIAL_CAUSAL_CAP"])
        == "PRICE_ACTION_RISK_ON / CAUSAL_NOT_CONFIRMED"
    )


def test_gold_thesis_zero_miner_cluster_not_excessive():
    from research.research_report_generator import build_gold_thesis_tracker

    dataset = {
        "portfolio": {"total_assets": 100000, "positions": {"VXX": {"mkt_val": 1000}}},
        "live_prices": {
            "prices": {
                "GLD": {"price": 300, "chg_pct": 1.0},
                "SLV": {"price": 30, "chg_pct": 1.0},
                "GDX": {"price": 40, "chg_pct": 1.5},
                "GDXJ": {"price": 50, "chg_pct": 1.7},
                "AU": {"price": 35, "chg_pct": 1.4},
                "NEM": {"price": 60, "chg_pct": 1.4},
                "UUP": {"price": 28, "chg_pct": -0.5},
                "TLT": {"price": 90, "chg_pct": 0.5},
                "IEF": {"price": 95, "chg_pct": 0.4},
                "SHY": {"price": 82, "chg_pct": 0.1},
                "SPY": {"price": 600, "chg_pct": -0.2},
                "QQQ": {"price": 500, "chg_pct": -0.2},
                "VXX": {"price": 22, "chg_pct": 0.5},
                "UVXY": {"price": 10, "chg_pct": 0.5},
                "XLE": {"price": 90, "chg_pct": 0.2},
            }
        },
        "treasury_yields": {"yield_10y": 4.0},
        "signals": {"Reuters_Commodities": ["Iran crude oil risk premium elevated"]},
    }
    result = build_gold_thesis_tracker(dataset)

    assert "gold-miner exposure is institutionally excessive" not in result["summary"]
    assert "Current live gold-miner cluster is 0%" in result["summary"]


def test_open_order_rows_include_order_intent():
    from research.research_report_generator import build_open_order_rows

    dataset = {
        "orders": {
            "open_orders": [
                {"ticker": "US.AU", "trd_side": "SELL", "order_type": "LIMIT", "order_status": "SUBMITTED", "qty": 1, "price": 40}
            ]
        }
    }
    row = build_open_order_rows(dataset)[0]

    assert row[0] == "AU"
    assert row[4] == "DECONCENTRATION_REVIEW"


def test_risk_process_zero_observations_is_qualified():
    from research.research_report_generator import build_process_rows

    dataset = {
        "risk_model": {"return_observations": 0},
        "institutional_quant": {
            "processes": {
                "risk_model": {"status": "PASS", "readiness_score": 100, "readiness_label": "INSTITUTIONAL_READY"}
            }
        },
    }
    row = build_process_rows(dataset)[0]

    assert row[1] == "TELEMETRY_PRESENT"
    assert row[3] == "HISTORY_INSUFFICIENT"
