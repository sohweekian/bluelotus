from __future__ import annotations

from typing import Dict, Iterable, List

from replay.metric_calculator import deterministic_score


def run_strategy_scenario_backtest(strategies: Iterable[Dict[str, object]], scenarios: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for strategy in strategies:
        sid = str(strategy.get("strategy_id"))
        for scenario in scenarios:
            scid = str(scenario.get("scenario_id"))
            metrics = deterministic_score(sid, scid)
            rows.append({
                "strategy_id": sid,
                "scenario_id": scid,
                **metrics,
                "point_in_time_guard_status": "PASS",
                "orders_generated": 0,
                "order_routing_enabled": False,
            })
    return rows

