"""
BlueLotus V3 — NITE-PEI: Composite Kill Risk Index (CKRI)
==========================================================
Replaces the binary cash_fortress_mode flag with a continuous risk index
that aggregates kill-condition probabilities across all active theses,
with a correlation penalty for kill conditions that share trigger events.

Formula:
    weighted_sum        = Σᵢ (kill_weight_i × P_kill_i)
    correlation_penalty = max(0, n_correlated_kills - 1)
    ckri_raw            = weighted_sum + ρ × correlation_penalty
    ckri                = ckri_raw / Σᵢ kill_weight_i   (normalized)

CKRI Zones:
    CLEAR     [0.00, 0.20) — normal operations
    WATCH     [0.20, 0.40) — reduce new adds; monitor
    ELEVATED  [0.40, 0.60) — freeze new adds; CIO review required
    HIGH      [0.60, 0.80) — RISK_REVIEW_REQUIRED
    CRITICAL  [0.80, ∞)    — RAISE_CASH_REVIEW or HEDGE_REVIEW

BLV3-DOCTRINE-007: De-risk actions route to equity_action_gate ONLY.
VXX/VIXY are governed exclusively by hedge_action_gate.

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# CKRI zone thresholds (lower bound, label)
# ---------------------------------------------------------------------------

CKRI_ZONES: List[Tuple[float, str]] = [
    (0.00, "CLEAR"),
    (0.20, "WATCH"),
    (0.40, "ELEVATED"),
    (0.60, "HIGH"),
    (0.80, "CRITICAL"),
]

_DEFAULT_CORRELATION_PENALTY_COEFF = 0.15


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_RISK_STATE_PATH = Path(__file__).parent / "portfolio_risk_state.json"


def _sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------

def get_ckri_zone(ckri: float) -> str:
    """Return the CKRI zone label for a given CKRI value."""
    zone = "CLEAR"
    for threshold, label in CKRI_ZONES:
        if ckri >= threshold:
            zone = label
        else:
            break
    return zone


# ---------------------------------------------------------------------------
# Core CKRI computation
# ---------------------------------------------------------------------------

def compute_ckri(
    theses: List[Dict[str, Any]],
    correlation_penalty_coeff: float = _DEFAULT_CORRELATION_PENALTY_COEFF,
) -> Dict[str, Any]:
    """
    Compute the Composite Kill Risk Index across all provided theses.

    Args:
        theses: List of thesis dicts. Each must contain a `kill_conditions` list.
                Each kill condition must have: kill_weight, P_kill,
                event_classes_that_trigger (list).
        correlation_penalty_coeff: ρ coefficient (default 0.15).

    Returns dict:
        ckri, ckri_zone, weighted_sum, correlation_penalty_applied,
        total_weight, kill_breakdown[], manual_execution_required, llm_order_generation
    """
    weighted_sum = 0.0
    total_weight = 0.0
    kill_breakdown = []
    trigger_class_counter: Counter = Counter()

    for thesis in theses:
        thesis_id = str(thesis.get("thesis_id", thesis.get("id", "UNKNOWN")))
        kill_conditions = thesis.get("kill_conditions", [])

        for kc in kill_conditions:
            w = float(kc.get("kill_weight", 0.0))
            p = float(kc.get("P_kill", 0.0))
            triggers = kc.get("event_classes_that_trigger", [])

            weighted_sum += w * p
            total_weight += w
            kill_breakdown.append({
                "thesis_id": thesis_id,
                "kill_id": kc.get("kill_id", "UNKNOWN"),
                "kill_weight": round(w, 4),
                "P_kill": round(p, 6),
                "current_state": kc.get("current_state", "INACTIVE"),
                "contribution": round(w * p, 6),
            })

            for ec in triggers:
                trigger_class_counter[str(ec)] += 1

    # Correlation penalty: for each trigger event_class shared by >1 kill condition
    n_correlated = sum(max(0, count - 1) for count in trigger_class_counter.values())
    correlation_penalty = correlation_penalty_coeff * n_correlated

    ckri_raw = weighted_sum + correlation_penalty
    ckri = ckri_raw / total_weight if total_weight > 0 else 0.0
    ckri = round(ckri, 6)
    ckri_zone = get_ckri_zone(ckri)

    return {
        "ckri": ckri,
        "ckri_zone": ckri_zone,
        "weighted_sum": round(weighted_sum, 6),
        "correlation_penalty_applied": round(correlation_penalty, 6),
        "total_weight": round(total_weight, 6),
        "kill_breakdown": kill_breakdown,
        "manual_execution_required": True,
        "llm_order_generation": False,
        "order_routing_enabled": False,
    }


# ---------------------------------------------------------------------------
# Compute CKRI from thesis registry dict
# ---------------------------------------------------------------------------

def compute_ckri_from_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute CKRI directly from a loaded thesis_registry dict.
    Only includes theses with status 'active'.
    """
    theses_raw = registry.get("theses", {})
    theses = []
    for thesis_id, thesis_data in theses_raw.items():
        if str(thesis_data.get("status", "")).lower() in ("active", "watch"):
            theses.append({
                "thesis_id": thesis_id,
                "kill_conditions": thesis_data.get("kill_conditions", []),
            })
    return compute_ckri(theses)


# ---------------------------------------------------------------------------
# Append-only risk state writer
# ---------------------------------------------------------------------------

def write_risk_state(
    ckri_result: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> None:
    """
    Append a CKRI result to portfolio_risk_state.json (append-only).
    """
    target = Path(output_path) if output_path else _RISK_STATE_PATH
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []
    else:
        existing = []

    record = dict(ckri_result)
    record["recorded_at_sgt"] = _sgt_now()
    existing.append(record)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
