"""
BlueLotus V3 — NITE-PEI Sub-Engine E7: CIO Advisory Renderer
=============================================================
Builds the canonical nite_pei{} JSON block and human-readable CIO advisory.

The nite_pei{} block is inserted into v3_agents_latest.json by the publisher.
The advisory text is surfaced in the Chief Strategist HTML section
"NITE-PEI Thesis Updates".

Also evaluates NITE-PEI contradiction rules:
  NITEPEI-001 (P3): Agent recommends add but P_posterior < 0.30
  NITEPEI-002 (P1): CKRI HIGH/CRITICAL but agent council shows no risk_flags

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# SGT timestamp
# ---------------------------------------------------------------------------

def _sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Posture determination (thesis §5 Step 17)
# ---------------------------------------------------------------------------

def determine_posture(
    delta_p: float,
    kill_states: Dict[str, Any],
) -> str:
    """
    Determine CIO advisory posture from probability change and kill states.

    Rules (from thesis §5 Step 17):
        KILL_CONDITION_CONFIRMED  — any kill state is CONFIRMED
        THESIS_RETIRED            — all kill states are RETIRED
        THESIS_STRENGTHENED       — delta_p ≥ +0.15 AND no active kill trigger
        THESIS_WEAKENED           — delta_p ≤ -0.15 AND kill state ≥ TRIGGERED
        THESIS_UNCHANGED          — |delta_p| < 0.15
    """
    states = [v.get("state") if isinstance(v, dict) else str(v) for v in kill_states.values()]

    if "CONFIRMED" in states:
        return "KILL_CONDITION_CONFIRMED — CIO_DECISION_REQUIRED"
    if states and all(s == "RETIRED" for s in states):
        return "THESIS_RETIRED — CLOSE_SLEEVE_PENDING_CIO"
    if delta_p >= 0.15 and "TRIGGERED" not in states and "CONFIRMED" not in states:
        return "THESIS_STRENGTHENED — CIO_REVIEW_FOR_ADD"
    if delta_p <= -0.15 and any(s in ("TRIGGERED", "CONFIRMED") for s in states):
        return "THESIS_WEAKENED — CIO_REVIEW_FOR_REDUCE"
    return "THESIS_UNCHANGED — MONITOR"


# ---------------------------------------------------------------------------
# Human-readable advisory text
# ---------------------------------------------------------------------------

def render_advisory_text(
    thesis_id: str,
    update_record: Dict[str, Any],
    kelly_result: Optional[Dict[str, Any]],
    posture: str,
) -> str:
    """
    Render a one-paragraph CIO advisory for a thesis probability update.
    """
    p_prior = update_record.get("p_prior_initial", 0.50)
    p_post = update_record.get("p_posterior_final", 0.50)
    delta = update_record.get("delta_p_total", 0.0)
    events = update_record.get("events_applied", [])
    event_desc = ", ".join(e.get("event_class", "UNKNOWN") for e in events) if events else "no events"

    lr_sources = update_record.get("lr_lookups", [])
    lr_desc = ""
    if lr_sources:
        lr_src = lr_sources[0]
        lr_desc = f" (LR {lr_src.get('lr_adjusted', 1.0):.3f} via {lr_src.get('lr_source', 'UNKNOWN')}, confidence: {lr_src.get('confidence', 'LOW')})"

    kelly_desc = ""
    if kelly_result:
        f_k = kelly_result.get("f_star_kelly", 0.0)
        delta_usd = kelly_result.get("delta_usd", 0.0)
        coh = kelly_result.get("coherence_score", 0.5)
        kelly_desc = (
            f" Kelly-NITE: f*={f_k:.3f} (coherence {coh:.2f}),"
            f" target delta ${delta_usd:,.0f}."
        )

    direction = "▲" if delta >= 0 else "▼"
    return (
        f"[NITE-PEI] {thesis_id}: {event_desc}{lr_desc}. "
        f"P: {p_prior:.3f} → {p_post:.3f} ({direction}{abs(delta):.3f}).{kelly_desc} "
        f"Posture: {posture}. MANUAL_EXECUTION_REQUIRED."
    )


# ---------------------------------------------------------------------------
# Contradiction rules evaluation
# ---------------------------------------------------------------------------

def evaluate_nite_pei_contradictions(
    thesis_snapshots: List[Dict[str, Any]],
    agent_reports: List[Dict[str, Any]],
    ckri_zone: str,
) -> List[Dict[str, Any]]:
    """
    Evaluate NITE-PEI contradiction rules against agent reports.

    NITEPEI-001 (P3): P_posterior < 0.30 but agent recommends add.
    NITEPEI-002 (P1): CKRI HIGH/CRITICAL but agent council shows no risk_flags.

    Returns list of contradiction dicts (same schema as contradiction_register entries).
    """
    contradictions = []

    # NITEPEI-001 — low thesis probability but add recommendation
    for snap in thesis_snapshots:
        p_post = float(snap.get("P_posterior", 0.50))
        thesis_id = str(snap.get("thesis_id", "UNKNOWN"))
        if p_post < 0.30:
            for report in agent_reports:
                rec = str(report.get("recommendation_to_chief_strategist", "")).upper()
                if "ADD" in rec or "BUY" in rec:
                    contradictions.append({
                        "contradiction_id": f"NITEPEI_001_{thesis_id}_{report.get('agent_id', 'UNKNOWN')}",
                        "severity": "P3",
                        "domain": "nite_pei_thesis_vs_agent_recommendation",
                        "source_a": f"nite_pei:{thesis_id}",
                        "source_b": f"agent:{report.get('agent_id', 'UNKNOWN')}",
                        "conflict_statement": (
                            f"NITE-PEI P_posterior={p_post:.3f} (below 0.30) for {thesis_id}, "
                            f"but agent {report.get('agent_id')} recommends "
                            f"{rec}. Thesis probability does not support add."
                        ),
                        "rule": "NITEPEI-001",
                        "cio_attention_required": False,
                        "recommended_resolution_path": (
                            "CIO should verify whether agent recommendation is based on "
                            "evidence NITE-PEI has not yet received, or if LR table needs calibration."
                        ),
                    })

    # NITEPEI-002 — high CKRI but no agent risk flags
    if ckri_zone in ("HIGH", "CRITICAL"):
        agents_with_no_risk_flags = [
            r for r in agent_reports
            if not r.get("risk_flags") or r.get("risk_flags") == []
        ]
        if agents_with_no_risk_flags:
            agent_ids = [r.get("agent_id", "UNKNOWN") for r in agents_with_no_risk_flags[:3]]
            contradictions.append({
                "contradiction_id": f"NITEPEI_002_CKRI_{ckri_zone}",
                "severity": "P1",
                "domain": "nite_pei_ckri_vs_agent_risk_assessment",
                "source_a": f"nite_pei:ckri_zone={ckri_zone}",
                "source_b": f"agents:{','.join(agent_ids)}",
                "conflict_statement": (
                    f"NITE-PEI CKRI zone is {ckri_zone} indicating elevated kill risk, "
                    f"but agents {agent_ids} report no risk_flags. "
                    "Agent council may be blind to thesis-level kill conditions."
                ),
                "rule": "NITEPEI-002",
                "cio_attention_required": True,
                "recommended_resolution_path": (
                    "CIO must review kill conditions manually. "
                    "Consider injecting CKRI context into next agent cycle."
                ),
            })

    return contradictions


# ---------------------------------------------------------------------------
# Canonical nite_pei{} block builder
# ---------------------------------------------------------------------------

def build_nite_pei_block(
    thesis_snapshots: List[Dict[str, Any]],
    ckri_result: Dict[str, Any],
    kelly_advisories: List[Dict[str, Any]],
    agent_reports: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build the canonical nite_pei{} block for v3_agents_latest.json.

    Args:
        thesis_snapshots:  List of per-thesis probability update dicts.
        ckri_result:       Output of ckri_calculator.compute_ckri().
        kelly_advisories:  List of kelly_nite_coupler.build_kelly_advisory() outputs.
        agent_reports:     Agent reports list (for contradiction evaluation). Optional.

    Returns:
        nite_pei{} block dict ready for JSON serialisation.
    """
    ckri_zone = str(ckri_result.get("ckri_zone", "CLEAR"))
    contradictions = evaluate_nite_pei_contradictions(
        thesis_snapshots,
        agent_reports or [],
        ckri_zone,
    )

    return {
        "schema_version": "bluelotus_v3_nite_pei_v1.0",
        "generated_at_sgt": _sgt_now(),
        "thesis_probability_snapshots": thesis_snapshots,
        "ckri": ckri_result.get("ckri", 0.0),
        "ckri_zone": ckri_zone,
        "ckri_detail": {
            "weighted_sum": ckri_result.get("weighted_sum", 0.0),
            "correlation_penalty_applied": ckri_result.get("correlation_penalty_applied", 0.0),
            "total_weight": ckri_result.get("total_weight", 0.0),
            "kill_breakdown": ckri_result.get("kill_breakdown", []),
        },
        "kelly_advisories": kelly_advisories,
        "nite_pei_contradictions": contradictions,
        "nite_pei_contradiction_count": len(contradictions),
        "nite_pei_p1_count": sum(1 for c in contradictions if c.get("severity") == "P1"),
        "manual_execution_required": True,
        "llm_order_generation": False,
        "order_routing_enabled": False,
    }
