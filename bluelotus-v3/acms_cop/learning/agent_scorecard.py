from __future__ import annotations

from typing import Any, Dict, Iterable


def build_agent_scorecard(agent_rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    scorecards: Dict[str, Dict[str, float]] = {}
    grouped: Dict[str, list[Dict[str, Any]]] = {}
    for row in agent_rows:
        grouped.setdefault(str(row.get("agent_name") or "UNKNOWN"), []).append(row)
    for agent, rows in grouped.items():
        n = len(rows)
        accepted = sum(1 for r in rows if r.get("accepted_by_chief_strategist") is True)
        overridden = sum(1 for r in rows if r.get("overridden_by_chief_strategist") is True)
        correct = [r for r in rows if r.get("outcome_correct") is not None]
        briers = [float(r["agent_brier_score"]) for r in rows if r.get("agent_brier_score") is not None]
        scorecards[agent] = {
            "n": float(n),
            "accepted_ratio": accepted / n if n else 0.0,
            "overridden_ratio": overridden / n if n else 0.0,
            "hit_rate": sum(1 for r in correct if r.get("outcome_correct") is True) / len(correct) if correct else 0.0,
            "avg_brier": sum(briers) / len(briers) if briers else 0.0,
            "overclaiming_frequency": sum(1 for r in rows if r.get("overclaiming_flag") is True) / n if n else 0.0,
        }
    return scorecards

