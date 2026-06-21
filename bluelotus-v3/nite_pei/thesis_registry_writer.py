"""
BlueLotus V3 — NITE-PEI Sub-Engine E6: Thesis Registry Writer
==============================================================
Reads and writes NITE-PEI probability fields to config/thesis_registry.yaml.

Append-only contract:
  - probability_history[] is NEVER truncated or rewritten — only appended.
  - current_probability is the only field overwritten (it reflects the latest posterior).
  - kill_conditions[] states are updated in-place (P_kill and current_state only).

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "thesis_registry.yaml"


# ---------------------------------------------------------------------------
# SGT timestamp
# ---------------------------------------------------------------------------

def _sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_thesis_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load thesis_registry.yaml. Returns the full registry dict."""
    target = Path(path) if path else _DEFAULT_REGISTRY_PATH
    with open(target, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def save_thesis_registry(registry: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Write thesis_registry.yaml atomically (write to temp then rename)."""
    target = Path(path) if path else _DEFAULT_REGISTRY_PATH
    tmp = target.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(registry, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp.replace(target)


# ---------------------------------------------------------------------------
# Field accessors
# ---------------------------------------------------------------------------

def get_current_probability(thesis_id: str, registry: Dict[str, Any]) -> float:
    """
    Return the current_probability for a thesis.
    Defaults to 0.50 if field not present (uninformative prior).
    """
    thesis = registry.get("theses", {}).get(thesis_id, {})
    return float(thesis.get("current_probability", 0.50))


def get_thesis_type(thesis_id: str, registry: Dict[str, Any]) -> str:
    """Return the thesis_type for LR table lookup. Defaults to thesis_id."""
    thesis = registry.get("theses", {}).get(thesis_id, {})
    return str(thesis.get("thesis_type", thesis_id))


def get_kill_conditions(thesis_id: str, registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the kill_conditions list for a thesis. Empty list if not defined."""
    thesis = registry.get("theses", {}).get(thesis_id, {})
    kcs = thesis.get("kill_conditions", [])
    return list(kcs) if isinstance(kcs, list) else []


def get_active_thesis_ids(registry: Dict[str, Any]) -> List[str]:
    """Return thesis IDs with status 'active'."""
    theses = registry.get("theses", {})
    return [tid for tid, t in theses.items() if str(t.get("status", "")).lower() == "active"]


# ---------------------------------------------------------------------------
# Write probability update (append-only)
# ---------------------------------------------------------------------------

def write_probability_update(
    thesis_id: str,
    update_record: Dict[str, Any],
    registry_path: Optional[Path] = None,
) -> None:
    """
    Append a probability update to the thesis's probability_history and
    update current_probability + kill_condition states.

    update_record expected fields (from bayesian_updater.update_thesis +
    kill_condition_state_machine.update_kill_conditions output):
        p_posterior_final, delta_p_total, events_applied[], lr_lookups[],
        kill_conditions_updated[] (optional), brier_record_id (optional),
        event_ref (optional)
    """
    registry = load_thesis_registry(registry_path)
    theses = registry.setdefault("theses", {})

    if thesis_id not in theses:
        theses[thesis_id] = {
            "status": "active",
            "thesis_type": thesis_id,
            "mapped_assets": [],
            "review_policy": "cio_manual_review",
            "current_probability": 0.50,
            "probability_history": [],
            "kill_conditions": [],
        }

    thesis = theses[thesis_id]
    thesis.setdefault("current_probability", 0.50)
    thesis.setdefault("probability_history", [])
    thesis.setdefault("kill_conditions", [])

    # Build history record
    history_entry = {
        "event_ref": update_record.get("event_ref", ""),
        "prior": update_record.get("p_prior_initial", thesis["current_probability"]),
        "posterior": update_record.get("p_posterior_final"),
        "delta_p": update_record.get("delta_p_total"),
        "events_applied_count": len(update_record.get("events_applied", [])),
        "lr_sources": [lr.get("lr_source") for lr in update_record.get("lr_lookups", [])],
        "brier_record_id": update_record.get("brier_record_id", ""),
        "created_at_sgt": _sgt_now(),
    }
    thesis["probability_history"].append(history_entry)

    # Update current probability
    new_p = update_record.get("p_posterior_final")
    if new_p is not None:
        thesis["current_probability"] = round(float(new_p), 6)

    # Update kill conditions if provided
    updated_kcs = update_record.get("kill_conditions_updated")
    if updated_kcs is not None:
        thesis["kill_conditions"] = updated_kcs

    save_thesis_registry(registry, registry_path)
