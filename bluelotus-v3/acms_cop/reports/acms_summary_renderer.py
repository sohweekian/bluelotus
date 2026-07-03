from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable


def build_acms_summary(
    cycle_row: Dict[str, Any],
    ticker_rows: Iterable[Dict[str, Any]],
    theme_rows: Iterable[Dict[str, Any]],
    forecast_rows: Iterable[Dict[str, Any]],
    agent_rows: Iterable[Dict[str, Any]],
    dq_rows: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    ticker_list = list(ticker_rows)
    theme_list = list(theme_rows)
    dq_list = list(dq_rows)
    states = Counter(str(r.get("acms_state") or "UNCLASSIFIED") for r in ticker_list)
    return {
        "regime_label": cycle_row.get("regime_label"),
        "cio_posture": cycle_row.get("cio_posture"),
        "dominant_acms_state": states.most_common(1)[0][0] if states else "UNCLASSIFIED",
        "ticker_count": len(ticker_list),
        "theme_count": len(theme_list),
        "forecast_count": len(list(forecast_rows)),
        "agent_count": len(list(agent_rows)),
        "data_quality_event_count": len(dq_list),
        "critical_data_quality_event_count": sum(1 for r in dq_list if str(r.get("severity")).upper() == "CRITICAL"),
        "execution_authority": cycle_row.get("execution_authority"),
        "order_routing_enabled": cycle_row.get("order_routing_enabled"),
        "llm_order_generation_enabled": cycle_row.get("llm_order_generation_enabled"),
        "system_generated_orders": cycle_row.get("system_generated_orders"),
        "second_tranche_status": cycle_row.get("second_tranche_status"),
        "scale_in_status": cycle_row.get("scale_in_status"),
        "state_counts": dict(states),
    }

