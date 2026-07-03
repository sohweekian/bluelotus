from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List


def brier_score(probability: float, outcome: int) -> float:
    p = max(0.0, min(1.0, float(probability)))
    o = 1 if int(outcome) else 0
    return round((p - o) ** 2, 6)


def log_score(probability: float, outcome: int) -> float:
    p = max(1e-6, min(1 - 1e-6, float(probability)))
    o = 1 if int(outcome) else 0
    score = math.log(p) if o else math.log(1 - p)
    return round(score, 6)


def crs_decomposition(forecasts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = [f for f in forecasts if f.get("final_outcome") in (0, 1, True, False)]
    n = len(resolved)
    if n == 0:
        return {
            "status": "COLLECTING",
            "resolved_count": 0,
            "resolved_forecasts": 0,
            "calibration": None,
            "resolution_component": None,
            "sharpness": None,
            "uncertainty": None,
            "thresholds": {"preliminary": 30, "pilot": 100, "credible": 300, "institutional": 1000},
        }
    probs = [float(f["probability"]) for f in resolved]
    outcomes = [1 if f["final_outcome"] else 0 for f in resolved]
    base = sum(outcomes) / n
    calibration = sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n
    sharpness = sum((p - base) ** 2 for p in probs) / n
    uncertainty = base * (1 - base)
    resolution_component = max(0.0, sharpness)
    return {
        "status": "PRELIMINARY" if n >= 30 else "COLLECTING",
        "resolved_count": n,
        "resolved_forecasts": n,
        "calibration": round(calibration, 6),
        "resolution_component": round(resolution_component, 6),
        "sharpness": round(sharpness, 6),
        "uncertainty": round(uncertainty, 6),
        "thresholds": {"preliminary": 30, "pilot": 100, "credible": 300, "institutional": 1000},
    }
