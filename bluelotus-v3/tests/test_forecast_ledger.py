import pytest

from acms_cop.extractors.forecast_extractor import extract_forecasts
from acms_cop.learning.forecast_resolver import validate_forecast


def test_forecasts_have_required_fields():
    rows = extract_forecasts({"meta": {"generated_at": "2026-06-18T05:00:00"}, "regime": {"regime": "MILD RISK OFF"}})
    assert len(rows) == 5
    for row in rows:
        validate_forecast(row)
        assert row["status"] == "OPEN"


def test_forecast_rejects_missing_probability_horizon_definition():
    with pytest.raises(ValueError):
        validate_forecast({"horizon_sessions": 3, "outcome_definition": "x"})
    with pytest.raises(ValueError):
        validate_forecast({"forecast_probability": 1.2, "horizon_sessions": 3, "outcome_definition": "x"})
    with pytest.raises(ValueError):
        validate_forecast({"forecast_probability": 0.5, "outcome_definition": "x"})
    with pytest.raises(ValueError):
        validate_forecast({"forecast_probability": 0.5, "horizon_sessions": 3})

