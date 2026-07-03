"""
BlueLotus V3 — NITE-PEI: Kelly-NITE Coupling + Entropy-NITE Coherence Gate
=============================================================================
Wires the NITE-PEI posterior probability into the Kelly ESM position-sizing
formula, with dynamic fractional adjustment via the Entropy-NITE Coherence Gate.

Kelly formula (Thorp quarter-Kelly default):
    b   = analyst_consensus_upside_pct  (payoff ratio)
    p   = P_posterior  (from NITE-PEI E3 Bayesian Updater)
    q   = 1 - p
    f*_full  = (b×p - q) / b
    f*_kelly = max(0.0, f*_full × fractional_multiplier)

Entropy-NITE Coherence Gate:
    H_norm    = signal_entropy_normalized (from SEM acms_cop/classifiers)
    dispersion = std dev of PEI scenario branch probabilities
    coherence  = 1 - (H_norm × 0.5 + dispersion × 0.5)  → [0, 1]
    fractional_multiplier = 0.05 + (0.35 - 0.05) × coherence

    At max uncertainty (H_norm=1, dispersion=1): multiplier ≈ 0.05 (5% Kelly)
    At max clarity   (H_norm=0, dispersion=0): multiplier ≈ 0.35 (35% Kelly)

ALL OUTPUTS ARE ADVISORY ONLY.
MANUAL_EXECUTION_REQUIRED: TRUE at all times.

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

from acms_cop.classifiers.signal_entropy_classifier import build_signal_entropy


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FRACTIONAL_MIN = 0.05   # Minimum fractional Kelly (max uncertainty)
_FRACTIONAL_MAX = 0.35   # Maximum fractional Kelly (max clarity)
_DEFAULT_H_NORM = 0.50   # Default H_norm when SEM data unavailable
_DEFAULT_DISPERSION = 0.50  # Default dispersion when PEI data unavailable

_PEI_LATEST_PATH = Path(r"C:\bluelotus3\data\pei\prospective_event_intelligence_latest.json")


# ---------------------------------------------------------------------------
# Entropy-NITE Coherence Gate
# ---------------------------------------------------------------------------

def get_h_norm_for_tickers(
    tickers: List[str],
    dataset: Dict[str, Any],
) -> float:
    """
    Compute mean signal_entropy_normalized across affected tickers.
    Uses acms_cop.classifiers.signal_entropy_classifier.build_signal_entropy.

    Returns H_norm in [0, 1]. Defaults to 0.5 if no relevant data found.
    """
    if not tickers or not dataset:
        return _DEFAULT_H_NORM

    try:
        records = build_signal_entropy(dataset)
        matching = [
            r["signal_entropy_normalized"]
            for r in records
            if r.get("ticker", "").upper() in [t.upper() for t in tickers]
        ]
        if matching:
            return round(sum(matching) / len(matching), 6)
    except Exception:  # noqa: BLE001 — dataset may be missing required keys
        pass
    return _DEFAULT_H_NORM


def get_branch_dispersion(
    thesis_id: str,
    pei_latest_path: Optional[Path] = None,
) -> float:
    """
    Compute std dev of PEI scenario branch probabilities for this thesis.
    Reads from the PEI latest JSON if available.

    Returns dispersion in [0, 1]. Defaults to 0.5 if PEI data unavailable.
    """
    target = pei_latest_path or _PEI_LATEST_PATH
    if not Path(target).exists():
        return _DEFAULT_DISPERSION

    try:
        data = json.loads(Path(target).read_text(encoding="utf-8"))
        scenario_trees = data.get("scenario_trees", [])

        # Collect branch probabilities for trees related to this thesis
        branch_probs: List[float] = []
        for tree in scenario_trees:
            if str(thesis_id).upper() in str(tree.get("event_type", "")).upper():
                branches = tree.get("branches", [])
                for branch in branches:
                    p = branch.get("probability") or branch.get("branch_probability")
                    if p is not None:
                        branch_probs.append(float(p))

        if len(branch_probs) >= 2:
            return round(min(1.0, statistics.stdev(branch_probs)), 6)
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_DISPERSION


def compute_coherence(h_norm: float, dispersion: float) -> float:
    """
    Compute the Entropy-NITE Coherence Score.

    coherence = 1 - (H_norm × 0.5 + dispersion × 0.5)
    Clamped to [0, 1].
    """
    raw = 1.0 - (float(h_norm) * 0.5 + float(dispersion) * 0.5)
    return round(max(0.0, min(1.0, raw)), 6)


def compute_fractional_multiplier(coherence: float) -> float:
    """
    Linear interpolation from coherence [0, 1] to fractional Kelly [0.05, 0.35].

    coherence = 0.0 → 0.05 (minimum, maximum uncertainty)
    coherence = 1.0 → 0.35 (maximum, maximum clarity)
    """
    lerp = _FRACTIONAL_MIN + (_FRACTIONAL_MAX - _FRACTIONAL_MIN) * float(coherence)
    return round(max(_FRACTIONAL_MIN, min(_FRACTIONAL_MAX, lerp)), 6)


# ---------------------------------------------------------------------------
# Kelly computation
# ---------------------------------------------------------------------------

def compute_kelly(
    p_posterior: float,
    analyst_upside_pct: float,
    fractional_multiplier: float,
    coherence_score: float = 0.50,
    h_norm_used: float = _DEFAULT_H_NORM,
    dispersion_used: float = _DEFAULT_DISPERSION,
) -> Dict[str, Any]:
    """
    Compute Kelly-NITE position sizing fraction.

    Args:
        p_posterior:          NITE-PEI updated thesis probability.
        analyst_upside_pct:   Analyst consensus upside as decimal (e.g. 0.15 = 15%).
        fractional_multiplier: From compute_fractional_multiplier(coherence).
        coherence_score:      For reporting.
        h_norm_used:          For reporting.
        dispersion_used:      For reporting.

    Returns dict with f_star_full, f_star_kelly, fractional_multiplier, etc.
    """
    p = max(0.0, min(1.0, float(p_posterior)))
    q = 1.0 - p
    b = float(analyst_upside_pct)

    if b <= 0:
        f_star_full = 0.0
    else:
        f_star_full = (b * p - q) / b

    f_star_kelly = max(0.0, f_star_full * float(fractional_multiplier))

    return {
        "p_posterior_used": round(p, 6),
        "analyst_upside_pct": round(b, 6),
        "f_star_full": round(f_star_full, 6),
        "fractional_multiplier": round(float(fractional_multiplier), 6),
        "f_star_kelly": round(f_star_kelly, 6),
        "coherence_score": round(float(coherence_score), 6),
        "h_norm_used": round(float(h_norm_used), 6),
        "dispersion_used": round(float(dispersion_used), 6),
        "manual_execution_required": True,
        "llm_order_generation": False,
    }


# ---------------------------------------------------------------------------
# Target USD vector
# ---------------------------------------------------------------------------

def compute_target_vector(
    thesis_id: str,
    f_star_kelly: float,
    dataset: Dict[str, Any],
    affected_tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Translate f*_kelly into a target USD sleeve and delta vs. current.

    Reads portfolio data from dataset["portfolio"]. Falls back to 0 if absent.

    Returns:
        target_usd_sleeve, current_usd_sleeve, delta_usd, advisory_text
    """
    portfolio = dataset.get("portfolio") or {}
    nav_total = 0.0
    try:
        nav_total = float(portfolio.get("total_value") or portfolio.get("nav") or 0.0)
    except (TypeError, ValueError):
        nav_total = 0.0

    target_usd = round(nav_total * float(f_star_kelly), 2)

    # Sum current holdings for affected tickers
    positions = portfolio.get("positions") or {}
    current_usd = 0.0
    if affected_tickers and isinstance(positions, dict):
        for ticker in affected_tickers:
            pos = positions.get(ticker.upper()) or positions.get(ticker.lower()) or {}
            if isinstance(pos, dict):
                val = pos.get("market_value") or pos.get("value") or 0.0
                try:
                    current_usd += float(val)
                except (TypeError, ValueError):
                    pass

    current_usd = round(current_usd, 2)
    delta_usd = round(target_usd - current_usd, 2)

    if delta_usd > 0:
        advisory_text = f"THESIS STRENGTHENED — CONSIDER ADD of ${delta_usd:,.0f}"
    elif delta_usd < 0:
        advisory_text = f"THESIS WEAKENED — CONSIDER REDUCE of ${abs(delta_usd):,.0f}"
    else:
        advisory_text = "POSITION NEAR KELLY TARGET — HOLD"

    return {
        "thesis_id": thesis_id,
        "nav_total": nav_total,
        "f_star_kelly": round(float(f_star_kelly), 6),
        "target_usd_sleeve": target_usd,
        "current_usd_sleeve": current_usd,
        "delta_usd": delta_usd,
        "advisory_text": advisory_text,
        "manual_execution_required": True,
        "llm_order_generation": False,
    }


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def build_kelly_advisory(
    thesis_id: str,
    thesis_type: str,
    p_posterior: float,
    analyst_upside_pct: float,
    affected_tickers: List[str],
    dataset: Dict[str, Any],
    pei_latest_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Full Kelly-NITE advisory computation in one call.

    Returns a combined dict suitable for inclusion in the nite_pei{} canonical block.
    """
    h_norm = get_h_norm_for_tickers(affected_tickers, dataset)
    dispersion = get_branch_dispersion(thesis_id, pei_latest_path)
    coherence = compute_coherence(h_norm, dispersion)
    frac_mult = compute_fractional_multiplier(coherence)

    kelly_result = compute_kelly(
        p_posterior=p_posterior,
        analyst_upside_pct=analyst_upside_pct,
        fractional_multiplier=frac_mult,
        coherence_score=coherence,
        h_norm_used=h_norm,
        dispersion_used=dispersion,
    )

    vector = compute_target_vector(thesis_id, kelly_result["f_star_kelly"], dataset, affected_tickers)

    return {
        "thesis_id": thesis_id,
        "thesis_type": thesis_type,
        **kelly_result,
        **{k: v for k, v in vector.items() if k not in kelly_result and k != "thesis_id"},
    }
