from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from acms_cop.common import first_dict, parse_dt
from acms_cop.learning.forecast_resolver import validate_forecast


SCENARIO_FORECASTS = [
    (0.45, 3, "MARKET", "SPY", "Choppy digestion over next 3 U.S. sessions", "SPY 3-session absolute return remains within +/-2.0%."),
    (0.30, 5, "MACRO", "WARSH_FED", "Hawkish Warsh follow-through risk-off fade", "SPY is negative over 5 sessions while VIX or VXX rises."),
    (0.15, 5, "MARKET", "RELIEF_RALLY", "Relief rally resumption", "SPY and QQQ both close higher over 5 sessions."),
    (0.07, 5, "MACRO", "BOJ_YEN_CARRY", "BOJ/yen carry flare-up", "USDJPY stress or yen-carry warning is active within 5 sessions."),
    (0.03, 10, "CREDIT", "LIQUIDITY_ACCIDENT", "Credit/liquidity accident", "Credit/liquidity stress escalates to severe within 10 sessions."),
]


def extract_forecasts(dataset: Dict[str, Any], text_report_path: str | None = None) -> List[Dict[str, Any]]:
    meta = first_dict(dataset.get("meta"))
    regime = first_dict(dataset.get("regime"))
    forecast_time = parse_dt(meta.get("generated_at") or datetime.now())
    dt = datetime.fromisoformat(forecast_time)
    rows: List[Dict[str, Any]] = []
    for probability, horizon, scope_type, scope_id, question, definition in SCENARIO_FORECASTS:
        row = {
            "forecast_time": forecast_time,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "forecast_question": question,
            "forecast_probability": probability,
            "confidence": 0.55,
            "horizon_sessions": horizon,
            "horizon_end_time": (dt + timedelta(days=horizon)).strftime("%Y-%m-%d %H:%M:%S"),
            "outcome_definition": definition,
            "regime_label": str(regime.get("regime_short") or regime.get("regime") or ""),
            "acms_state": "REGIME_TRANSITION",
            "cio_posture": str(regime.get("action") or "REVIEW"),
            "benchmark_type": "SPY_QQQ_VIX_CONTEXT",
            "status": "OPEN",
            "notes": "Scenario forecast opened by ACMS-COP v1.0 from Chief Strategist context.",
        }
        validate_forecast(row)
        rows.append(row)
    return rows

