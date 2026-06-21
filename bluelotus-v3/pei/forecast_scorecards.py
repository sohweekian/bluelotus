from __future__ import annotations

from typing import Any, Dict, List


def forecast_registry_snapshot(forecasts: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "status": "COLLECTING",
        "active_forecasts": len(forecasts),
        "resolved_forecasts": 0,
        "minimum_reporting_threshold": 30,
        "pilot_accountability_threshold": 100,
        "institutional_grade_threshold": 1000,
        "warning": "PEI must not claim forecasting superiority before sufficient resolved forecasts exist.",
    }
