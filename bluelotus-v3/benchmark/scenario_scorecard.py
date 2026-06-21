from __future__ import annotations

from typing import Dict, Iterable, List


def build_scenario_scorecards(results: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    buckets: Dict[str, Dict[str, float]] = {}
    counts: Dict[str, int] = {}
    for row in results:
        scenario = str(row.get("scenario_id"))
        bucket = buckets.setdefault(scenario, {"return_proxy": 0.0, "drawdown_proxy": 0.0})
        counts[scenario] = counts.get(scenario, 0) + 1
        bucket["return_proxy"] += float(row.get("return_proxy") or 0.0)
        bucket["drawdown_proxy"] += float(row.get("max_drawdown_proxy") or 0.0)
    out = []
    for scenario, values in sorted(buckets.items()):
        count = max(1, counts.get(scenario, 1))
        avg_return = values["return_proxy"] / count
        avg_drawdown = values["drawdown_proxy"] / count
        out.append({
            "scenario_id": scenario,
            "avg_return_proxy": round(avg_return, 6),
            "avg_drawdown_proxy": round(avg_drawdown, 6),
            "scenario_status": "STRESS" if avg_drawdown < -0.08 else "WATCH",
        })
    return out

