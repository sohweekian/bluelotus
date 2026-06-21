from __future__ import annotations

from typing import Any, Dict

from acms_cop.learning.outcome_scorer import score_outcome


def validate_forecast(row: Dict[str, Any]) -> None:
    if row.get("forecast_probability") is None:
        raise ValueError("Forecast cannot be stored without probability")
    probability = float(row["forecast_probability"])
    if probability < 0 or probability > 1:
        raise ValueError("Forecast probability must be between 0 and 1")
    if not row.get("horizon_sessions"):
        raise ValueError("Forecast cannot be stored without horizon")
    if not row.get("outcome_definition"):
        raise ValueError("Forecast cannot be stored without outcome definition")


def resolve_forecast(row: Dict[str, Any], outcome_binary: bool | int, forward_returns: Dict[str, Any] | None = None) -> Dict[str, Any]:
    validate_forecast(row)
    scored = score_outcome(row, outcome_binary, forward_returns)
    return {**scored, "status": "RESOLVED"}

