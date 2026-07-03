from __future__ import annotations

from pei.hawkes_branching_estimator import hawkes_status


def cascade_model_status(event_count: int = 0, resolved_forecast_count: int = 0) -> dict:
    status = hawkes_status(event_count, resolved_forecast_count)
    status["cascade_risk_level"] = "NOT_ACTIVE_FOR_DECISIONING"
    return status
