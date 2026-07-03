from __future__ import annotations

import math
from typing import Any, Dict

from acms_cop.learning.brier_scorer import brier_score


def log_loss(probability: float, outcome_binary: bool | int) -> float:
    p = min(max(float(probability), 1e-12), 1 - 1e-12)
    outcome = 1.0 if bool(outcome_binary) else 0.0
    return round(-(outcome * math.log(p) + (1.0 - outcome) * math.log(1.0 - p)), 6)


def score_outcome(forecast: Dict[str, Any], outcome_binary: bool | int, forward_returns: Dict[str, Any] | None = None) -> Dict[str, Any]:
    probability = forecast.get("forecast_probability")
    if probability is None:
        raise ValueError("forecast_probability is required")
    result = {
        "outcome_binary": bool(outcome_binary),
        "brier_score": brier_score(float(probability), outcome_binary),
        "log_loss": log_loss(float(probability), outcome_binary),
    }
    for key in ["forward_return_1s", "forward_return_3s", "forward_return_5s", "forward_return_10s", "forward_return_20s"]:
        result[key] = (forward_returns or {}).get(key)
    return result

