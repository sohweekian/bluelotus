from __future__ import annotations


def brier_score(probability: float, outcome_binary: bool | int) -> float:
    p = float(probability)
    if p < 0 or p > 1:
        raise ValueError("forecast probability must be between 0 and 1")
    outcome = 1.0 if bool(outcome_binary) else 0.0
    return round((p - outcome) ** 2, 6)

