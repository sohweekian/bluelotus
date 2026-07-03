from __future__ import annotations


def hawkes_status(event_count: int, resolved_forecast_count: int) -> dict:
    ready = event_count >= 300 and resolved_forecast_count >= 100
    return {
        "status": "DEFERRED_UNTIL_EVENT_DATA_SUFFICIENT" if not ready else "READY_FOR_RESEARCH_ESTIMATION",
        "priority": "P2",
        "minimum_events_required": 300,
        "minimum_resolved_forecasts_required": 100,
        "current_event_count": event_count,
        "current_resolved_forecast_count": resolved_forecast_count,
    }
