"""
BlueLotus V3 — NITE-PEI Sub-Engine E3: Bayesian Updater
=========================================================
Computes posterior thesis probability from prior odds × likelihood ratio.

Formula:
    Prior odds     = P_prior / (1 - P_prior)
    Posterior odds = Prior odds × LR_adjusted
    P_posterior    = Posterior odds / (1 + Posterior odds)
    P_posterior    = clamp(P_posterior, 0.05, 0.95)

Sequential updating: posterior of event N becomes prior of event N+1.
LR_adjusted = LR × (1 - noise_discount_factor)

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# LR Table loading
# ---------------------------------------------------------------------------

_LR_TABLE_PATH = Path(__file__).parent / "likelihood_ratio_table.yaml"
_lr_table_cache: Optional[Dict[str, Any]] = None


def _load_lr_table(path: Optional[Path] = None) -> Dict[str, Any]:
    global _lr_table_cache
    target = Path(path) if path else _LR_TABLE_PATH
    if _lr_table_cache is None or path:
        with open(target, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        table = data.get("lr_table", {})
        if not path:
            _lr_table_cache = table
        return table
    return _lr_table_cache


def reload_lr_table() -> None:
    """Force reload of the LR table (call after Brier calibration updates it)."""
    global _lr_table_cache
    _lr_table_cache = None
    _load_lr_table()


# ---------------------------------------------------------------------------
# LR lookup
# ---------------------------------------------------------------------------

def get_lr(
    event_class: str,
    thesis_type: str,
    noise_discount_factor: float = 0.0,
    lr_table: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Look up the likelihood ratio for (event_class, thesis_type).

    Lookup order:
        1. lr_table[event_class][thesis_type]
        2. lr_table[event_class]["ANY"]
        3. Default: LR = 1.0 (no information)

    Returns dict with:
        lr_raw            — LR from table (before noise discount)
        lr_adjusted       — LR after noise discount applied
        lr_source         — which lookup key was used
        confidence        — LOW / MEDIUM / HIGH
        calibration_n     — number of calibration events seen
        noise_discount_factor
    """
    table = lr_table if lr_table is not None else _load_lr_table()
    event_entries = table.get(event_class, {})

    entry = None
    source = None

    if thesis_type in event_entries:
        entry = event_entries[thesis_type]
        source = f"{event_class}/{thesis_type}"
    elif "ANY" in event_entries:
        entry = event_entries["ANY"]
        source = f"{event_class}/ANY"
    else:
        entry = {"lr": 1.0, "confidence": "LOW", "calibration_n": 0}
        source = "DEFAULT_NO_ENTRY"

    lr_raw = float(entry.get("lr", 1.0))
    ndf = max(0.0, min(1.0, float(noise_discount_factor)))
    lr_adjusted = adjust_lr_toward_neutral(lr_raw, ndf)

    return {
        "lr_raw": round(lr_raw, 6),
        "lr_adjusted": round(lr_adjusted, 6),
        "lr_source": source,
        "confidence": entry.get("confidence", "LOW"),
        "calibration_n": int(entry.get("calibration_n", 0)),
        "noise_discount_factor": round(ndf, 4),
    }


# ---------------------------------------------------------------------------
# Core Bayesian computation
# ---------------------------------------------------------------------------

_P_MIN = 0.05
_P_MAX = 0.95


def compute_posterior(
    p_prior: float,
    lr_adjusted: float,
) -> Dict[str, float]:
    """
    Compute Bayesian posterior from prior probability and adjusted LR.

    Args:
        p_prior:      Prior probability [0.05, 0.95].
        lr_adjusted:  Likelihood ratio after noise discount applied.

    Returns dict:
        p_prior, lr_adjusted, p_posterior, delta_p
    """
    p_prior = max(_P_MIN, min(_P_MAX, float(p_prior)))
    lr_adjusted = max(0.001, float(lr_adjusted))  # guard divide-by-zero

    prior_odds = p_prior / (1.0 - p_prior)
    posterior_odds = prior_odds * lr_adjusted
    p_posterior_raw = posterior_odds / (1.0 + posterior_odds)
    p_posterior = max(_P_MIN, min(_P_MAX, p_posterior_raw))
    delta_p = round(p_posterior - p_prior, 6)

    return {
        "p_prior": round(p_prior, 6),
        "lr_adjusted": round(lr_adjusted, 6),
        "p_posterior": round(p_posterior, 6),
        "delta_p": delta_p,
    }


def adjust_lr_toward_neutral(lr_raw: float, noise_discount_factor: float) -> float:
    """
    Discount evidence toward neutral LR=1.0.

    This preserves the Bayesian meaning of a likelihood ratio:
      - LR > 1.0 remains supportive, but weaker after discount.
      - LR = 1.0 remains neutral under every discount.
      - LR < 1.0 remains adverse, but weaker after discount.
    """
    lr = max(0.001, float(lr_raw))
    ndf = max(0.0, min(1.0, float(noise_discount_factor)))
    return round(1.0 + (lr - 1.0) * (1.0 - ndf), 6)


# ---------------------------------------------------------------------------
# Multi-event sequential update
# ---------------------------------------------------------------------------

def update_thesis(
    thesis_id: str,
    thesis_type: str,
    p_prior: float,
    events: List[Dict[str, Any]],
    lr_table: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply a sequence of classified events to a thesis sequentially.
    Posterior of event N becomes prior of event N+1.

    Args:
        thesis_id:   ID of the thesis being updated.
        thesis_type: Type key for LR table lookup (e.g. "GOLD_THESIS").
        p_prior:     Starting probability before any events.
        events:      List of dicts from event_classifier.classify_event().
        lr_table:    Optional pre-loaded LR table (for testing).

    Returns dict with:
        thesis_id, thesis_type, p_prior_initial, p_posterior_final,
        delta_p_total, events_applied[], lr_lookups[]
    """
    p_current = max(_P_MIN, min(_P_MAX, float(p_prior)))
    p_initial = p_current
    events_applied = []
    lr_lookups = []

    for event in events:
        event_class = str(event.get("event_class", "UNKNOWN"))
        ndf = float(event.get("noise_discount_factor", 0.0))

        lr_result = get_lr(event_class, thesis_type, ndf, lr_table)
        posterior_result = compute_posterior(p_current, lr_result["lr_adjusted"])

        events_applied.append({
            "event_class": event_class,
            "source_tier": event.get("source_tier", 2),
            "noise_discount_factor": ndf,
            "p_before": round(p_current, 6),
            "p_after": posterior_result["p_posterior"],
            "delta_p": posterior_result["delta_p"],
        })
        lr_lookups.append(lr_result)
        p_current = posterior_result["p_posterior"]

    return {
        "thesis_id": thesis_id,
        "thesis_type": thesis_type,
        "p_prior_initial": round(p_initial, 6),
        "p_posterior_final": round(p_current, 6),
        "delta_p_total": round(p_current - p_initial, 6),
        "events_applied": events_applied,
        "lr_lookups": lr_lookups,
        "manual_execution_required": True,
        "llm_order_generation": False,
    }
