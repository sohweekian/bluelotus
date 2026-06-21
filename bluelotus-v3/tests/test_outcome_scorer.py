from acms_cop.learning.brier_scorer import brier_score
from acms_cop.learning.outcome_scorer import score_outcome


def test_brier_score_and_forward_return_fields():
    assert brier_score(0.7, True) == 0.09
    scored = score_outcome({"forecast_probability": 0.7}, True, {"forward_return_1s": 1.2, "forward_return_20s": 4.5})
    assert scored["brier_score"] == 0.09
    assert scored["forward_return_1s"] == 1.2
    assert "forward_return_20s" in scored

