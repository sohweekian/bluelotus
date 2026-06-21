from __future__ import annotations

from typing import Any, Dict, List


def resolve_disagreements(cycle_id: str, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    risk_reports = [r for r in reports if r.get("risk_flags")]
    cio_reports = [r for r in reports if r.get("requires_cio_attention") is True]
    disagreements = []
    recommendations = {str(r.get("agent_id")): str(r.get("recommendation_to_chief_strategist")) for r in reports}
    unique_recommendations = sorted(set(recommendations.values()))
    if len(unique_recommendations) > 1:
        disagreements.append({
            "topic": "agent recommendation dispersion",
            "agent_a": next(iter(recommendations.keys()), ""),
            "agent_b": ",".join(recommendations.keys()),
            "severity": "medium" if len(cio_reports) else "low",
            "chief_strategist_resolution": "Use most conservative CIO manual review posture when agents disagree.",
            "requires_cio_attention": bool(cio_reports),
        })
    if len(risk_reports) >= max(2, len(reports) // 3):
        disagreements.append({
            "topic": "risk emphasis versus ordinary review",
            "agent_a": ",".join(str(r.get("agent_id")) for r in risk_reports[:2]),
            "agent_b": "agent council",
            "severity": "high" if len(cio_reports) else "medium",
            "chief_strategist_resolution": "Preserve deterministic operator blocks and escalate risk items to CIO review.",
            "requires_cio_attention": True,
        })
    return {"cycle_id": cycle_id, "disagreements": disagreements}
