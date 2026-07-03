from pei.forecast_registry import build_forecast_registry
from pei.forecast_resolver import resolve_forecast
from pei.event_registry import build_candidate_events
from pei.event_tree_builder import build_scenario_trees


def _dataset():
    return {"law_governance_binding": {"governance_pack_id": "GOVPACK_TEST", "report_memory_binding_id": "BIND_TEST"}}


def test_pei_forecast_registry_only_contains_resolvable_forecasts():
    forecasts = build_forecast_registry(build_scenario_trees(build_candidate_events(_dataset())))

    assert forecasts
    assert all(forecast["resolution_criteria"] for forecast in forecasts)
    assert all(forecast["cio_only_manual"] is True for forecast in forecasts)
    assert all(forecast["orders_generated"] == 0 for forecast in forecasts)
    assert all(forecast["routing_enabled"] is False for forecast in forecasts)


def test_pei_forecast_resolver_fails_closed_without_criteria():
    result = resolve_forecast({"forecast_id": "F1", "probability": 0.7}, 1)

    assert result["status"] == "UNRESOLVABLE_FORECAST"


def test_pei_forecast_resolver_scores_with_original_probability():
    result = resolve_forecast({"forecast_id": "F1", "probability": 0.7, "resolution_criteria": ["criterion"]}, 1)

    assert result["probability"] == 0.7
    assert round(result["brier_score"], 2) == 0.09
