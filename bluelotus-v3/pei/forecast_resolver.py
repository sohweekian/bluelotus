from __future__ import annotations

from typing import Any, Dict

from db.v3_db_connection import get_v3_connection
from pei.brier_crs_engine import brier_score, log_score
from pei.common import sgt_now, stable_id


def resolve_forecast(forecast: Dict[str, Any], outcome: int, source: str = "manual_resolution") -> Dict[str, Any]:
    if not forecast.get("resolution_criteria"):
        return {"status": "UNRESOLVABLE_FORECAST", "reason": "missing resolution criteria"}
    probability = float(forecast.get("probability") or 0)
    result = {
        "resolution_id": stable_id("PEI_RESOLUTION", forecast.get("forecast_id"), outcome),
        "forecast_id": forecast.get("forecast_id"),
        "probability": probability,
        "final_outcome": 1 if outcome else 0,
        "brier_score": brier_score(probability, outcome),
        "log_score": log_score(probability, outcome),
        "resolved_at": sgt_now(),
        "resolution_source": source,
    }
    return result


def persist_resolution(resolution: Dict[str, Any]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pei_forecast_resolutions (resolution_id, forecast_id, final_outcome, resolved_at, resolution_source, notes) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                resolution["resolution_id"], resolution["forecast_id"], resolution["final_outcome"],
                resolution["resolved_at"], resolution["resolution_source"], "",
            ),
        )
        cur.execute(
            "INSERT INTO pei_brier_scores (forecast_id, probability, outcome, brier_score, log_score, scored_at) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                resolution["forecast_id"], float(resolution.get("probability") or 0.0), resolution["final_outcome"],
                resolution["brier_score"], resolution["log_score"], resolution["resolved_at"],
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
