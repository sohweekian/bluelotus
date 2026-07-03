"""
BlueLotus V3 — NITE-PEI Sub-Engine E4: Kill-Condition State Machine
=====================================================================
Tracks kill-condition states for each active thesis.

State machine:
    INACTIVE   — P(kill) < 0.10  — not on radar
    WATCH      — P(kill) ≥ 0.10  — monitoring; no action required
    TRIGGERED  — P(kill) ≥ 0.35  — live; CIO must review thesis
    CONFIRMED  — P(kill) ≥ 0.65  — invalidated; thesis review mandatory
    RETIRED    — thesis resolved  — archived

Transitions are monotonic by default but reversible on new evidence.
CIO must manually confirm RETIRED state — NITE-PEI proposes, CIO decides.

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# State thresholds (lower bound of each state)
# ---------------------------------------------------------------------------

_THRESHOLD_WATCH     = 0.10
_THRESHOLD_TRIGGERED = 0.35
_THRESHOLD_CONFIRMED = 0.65


# ---------------------------------------------------------------------------
# Core state classification
# ---------------------------------------------------------------------------

def classify_kill_state(p_kill: float) -> str:
    """
    Map a kill-condition probability to its state label.

    Args:
        p_kill: Current probability that the kill condition is triggered [0, 1].

    Returns:
        "INACTIVE" | "WATCH" | "TRIGGERED" | "CONFIRMED"
    """
    p = float(p_kill)
    if p >= _THRESHOLD_CONFIRMED:
        return "CONFIRMED"
    if p >= _THRESHOLD_TRIGGERED:
        return "TRIGGERED"
    if p >= _THRESHOLD_WATCH:
        return "WATCH"
    return "INACTIVE"


# ---------------------------------------------------------------------------
# Kill-condition update
# ---------------------------------------------------------------------------

def update_kill_conditions(
    kill_conditions: List[Dict[str, Any]],
    event_class: str,
    p_posterior: float,
) -> List[Dict[str, Any]]:
    """
    Update kill conditions in light of a new event.

    For each kill condition: if the event class appears in the kill condition's
    `event_classes_that_trigger` list, update P_kill = p_posterior and
    recompute current_state.  Conditions not triggered by this event are
    returned unchanged.

    Args:
        kill_conditions: List of kill condition dicts from thesis_registry.yaml.
        event_class:     The classified event class from event_classifier.
        p_posterior:     Updated thesis probability from bayesian_updater.

    Returns:
        Updated copy of kill_conditions (input is not mutated).
    """
    updated = []
    for kc in kill_conditions:
        kc_copy = dict(kc)
        triggers = kc_copy.get("event_classes_that_trigger", [])

        if event_class in triggers:
            kc_copy["P_kill"] = round(float(p_posterior), 6)
            kc_copy["current_state"] = classify_kill_state(p_posterior)
            kc_copy["last_updated_by_event_class"] = event_class
        else:
            # Ensure existing P_kill has a state label even if not triggered
            existing_p = float(kc_copy.get("P_kill", 0.0))
            kc_copy["P_kill"] = round(existing_p, 6)
            if "current_state" not in kc_copy:
                kc_copy["current_state"] = classify_kill_state(existing_p)

        updated.append(kc_copy)
    return updated


# ---------------------------------------------------------------------------
# Kill-condition state snapshot (for canonical JSON output)
# ---------------------------------------------------------------------------

def build_kill_state_snapshot(kill_conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a compact kill-condition state snapshot for the canonical JSON block.

    Returns:
        Dict mapping kill_id → {state, P_kill}
    """
    snapshot: Dict[str, Any] = {}
    for kc in kill_conditions:
        kid = str(kc.get("kill_id", "UNKNOWN"))
        snapshot[kid] = {
            "state": kc.get("current_state", classify_kill_state(float(kc.get("P_kill", 0.0)))),
            "P_kill": round(float(kc.get("P_kill", 0.0)), 6),
        }
    return snapshot


# ---------------------------------------------------------------------------
# Worst kill state across all conditions
# ---------------------------------------------------------------------------

_STATE_RANK = {"INACTIVE": 0, "WATCH": 1, "TRIGGERED": 2, "CONFIRMED": 3, "RETIRED": 4}


def worst_kill_state(kill_conditions: List[Dict[str, Any]]) -> str:
    """Return the worst (most severe) kill state across all conditions."""
    if not kill_conditions:
        return "INACTIVE"
    states = [kc.get("current_state", "INACTIVE") for kc in kill_conditions]
    return max(states, key=lambda s: _STATE_RANK.get(s, 0))
