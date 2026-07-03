"""
BlueLotus V3 — NITE-PEI Sub-Engine E6b: Hedge Action Gate
==========================================================
Governs sizing of VXX and VIXY hedge positions ONLY.

CRITICAL ARCHITECTURAL INVARIANT (BLV3-DOCTRINE-007):
    This gate NEVER calls equity_action_gate.
    This gate ONLY touches VXX and VIXY.
    No de-risk CKRI signal may reduce hedge positions.
    High CKRI increases the case FOR hedges, never against them.

Hedge sizing formula (from thesis §16):
    implied_hedge_ratio = portfolio_beta / hedge_effectiveness
    hedge_value_target  = nav_total × implied_hedge_ratio × hedge_allocation_pct
    delta_vs_current    = hedge_value_target - current_hedge_value

ALL OUTPUTS ARE ADVISORY ONLY.
MANUAL_EXECUTION_REQUIRED: TRUE at all times.

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Doctrine constant — only these tickers are governed by this gate
# ---------------------------------------------------------------------------

HEDGE_TICKERS: frozenset[str] = frozenset({"VXX", "VIXY"})

"""
HEDGE ONLY gate.
Governs VXX/VIXY sizing exclusively. Never calls equity_action_gate.
"""

# Default hedge parameters (thesis §16 — conservative starting values)
_DEFAULT_HEDGE_EFFECTIVENESS = 0.80   # VXX/VIXY capture ~80% of market vol spike
_DEFAULT_HEDGE_ALLOCATION_PCT = 0.05  # Target 5% of NAV in hedge instruments


def _sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Current hedge value reader
# ---------------------------------------------------------------------------

def _get_current_hedge_value(
    positions: Dict[str, Any],
) -> Dict[str, float]:
    """
    Read current market value of VXX and VIXY from positions dict.

    Returns {ticker: value_usd} for each hedge ticker found.
    """
    values: Dict[str, float] = {}
    for ticker in HEDGE_TICKERS:
        pos = (
            positions.get(ticker.upper())
            or positions.get(ticker.lower())
            or {}
        )
        if isinstance(pos, dict):
            val = pos.get("market_value") or pos.get("value") or 0.0
            try:
                values[ticker] = float(val)
            except (TypeError, ValueError):
                values[ticker] = 0.0
        else:
            values[ticker] = 0.0
    return values


# ---------------------------------------------------------------------------
# CKRI → hedge posture multiplier
# ---------------------------------------------------------------------------

_CKRI_HEDGE_MULTIPLIER: Dict[str, float] = {
    "CLEAR":    1.00,   # Maintain baseline hedge
    "WATCH":    1.00,   # Maintain baseline hedge
    "ELEVATED": 1.10,   # +10% above target (CIO review)
    "HIGH":     1.25,   # +25% above target (CIO review)
    "CRITICAL": 1.50,   # +50% above target (CIO review — consider increasing)
}


# ---------------------------------------------------------------------------
# Primary hedge sizing advisory
# ---------------------------------------------------------------------------

def hedge_sizing_advisory(
    portfolio_beta: float,
    dataset: Dict[str, Any],
    ckri_zone: str = "CLEAR",
    hedge_effectiveness: float = _DEFAULT_HEDGE_EFFECTIVENESS,
    hedge_allocation_pct: float = _DEFAULT_HEDGE_ALLOCATION_PCT,
) -> Dict[str, Any]:
    """
    Compute hedge sizing advisory for VXX/VIXY.

    Args:
        portfolio_beta:      Current portfolio beta vs. market.
        dataset:             Full dataset dict for portfolio values.
        ckri_zone:           Current CKRI zone (HIGH/CRITICAL increases hedge target).
        hedge_effectiveness: Fraction of vol spike captured by VXX/VIXY (default 0.80).
        hedge_allocation_pct: Target fraction of NAV in hedge sleeve (default 0.05).

    Returns:
        Advisory dict with current vs. target hedge values and delta.
        manual_execution_required = True always.
        llm_order_generation = False always.
        order_routing_enabled = False always.

    BLV3-DOCTRINE-007: This gate governs VXX/VIXY ONLY. Equity sleeve is equity_action_gate.py.
    """
    portfolio = dataset.get("portfolio") or {}
    nav_total = 0.0
    try:
        nav_total = float(
            portfolio.get("total_value")
            or portfolio.get("nav")
            or 0.0
        )
    except (TypeError, ValueError):
        nav_total = 0.0

    positions = portfolio.get("positions") or {}
    current_hedge_values = _get_current_hedge_value(positions)
    current_hedge_total = round(sum(current_hedge_values.values()), 2)

    # Implied hedge ratio from beta
    beta = float(portfolio_beta)
    eff = float(hedge_effectiveness) if float(hedge_effectiveness) > 0 else _DEFAULT_HEDGE_EFFECTIVENESS
    implied_ratio = beta / eff

    # Base target hedge value
    base_target = nav_total * float(hedge_allocation_pct) * implied_ratio

    # CKRI multiplier — high risk INCREASES hedge target, never reduces it
    ckri_mult = _CKRI_HEDGE_MULTIPLIER.get(str(ckri_zone).upper(), 1.00)
    hedge_target_usd = round(base_target * ckri_mult, 2)

    delta_usd = round(hedge_target_usd - current_hedge_total, 2)

    if delta_usd > 0:
        action = f"CONSIDER_HEDGE_ADD — target ${hedge_target_usd:,.0f}, delta +${delta_usd:,.0f}"
    elif delta_usd < 0:
        action = f"HEDGE_NEAR_OR_ABOVE_TARGET — no action required (${abs(delta_usd):,.0f} above target)"
    else:
        action = "HEDGE_AT_TARGET — HOLD"

    return {
        "gate": "hedge_action_gate",
        "doctrine_ref": "BLV3-DOCTRINE-007",
        "generated_at_sgt": _sgt_now(),
        "ckri_zone": ckri_zone,
        "ckri_hedge_multiplier": ckri_mult,
        "portfolio_beta": round(beta, 4),
        "hedge_effectiveness": round(eff, 4),
        "implied_hedge_ratio": round(implied_ratio, 4),
        "nav_total": nav_total,
        "hedge_allocation_pct": hedge_allocation_pct,
        "base_target_usd": round(base_target, 2),
        "hedge_target_usd_after_ckri": hedge_target_usd,
        "current_hedge_values": current_hedge_values,
        "current_hedge_total_usd": current_hedge_total,
        "delta_usd": delta_usd,
        "action": action,
        "hedge_tickers_governed": sorted(HEDGE_TICKERS),
        "note": (
            "Hedge instruments only. VXX/VIXY governed by this gate exclusively. "
            "High CKRI INCREASES hedge target — never reduces it. "
            "Equity de-risk is equity_action_gate.py."
        ),
        "manual_execution_required": True,
        "llm_order_generation": False,
        "order_routing_enabled": False,
    }


# ---------------------------------------------------------------------------
# Hedge status snapshot (for nite_pei{} block insertion)
# ---------------------------------------------------------------------------

def hedge_status_snapshot(
    dataset: Dict[str, Any],
    ckri_zone: str = "CLEAR",
) -> Dict[str, Any]:
    """
    Lightweight hedge status check — current VXX/VIXY values and zone flag.

    Used by cio_advisory_renderer to populate nite_pei{} hedge_status section.
    """
    portfolio = dataset.get("portfolio") or {}
    positions = portfolio.get("positions") or {}
    current_hedge_values = _get_current_hedge_value(positions)
    current_hedge_total = sum(current_hedge_values.values())

    cio_attention = ckri_zone in ("HIGH", "CRITICAL") and current_hedge_total == 0.0

    return {
        "hedge_tickers": sorted(HEDGE_TICKERS),
        "current_values_usd": current_hedge_values,
        "current_total_usd": round(current_hedge_total, 2),
        "ckri_zone": ckri_zone,
        "cio_attention_required": cio_attention,
        "note": "CKRI HIGH/CRITICAL with zero hedge position requires CIO review." if cio_attention else "",
        "manual_execution_required": True,
        "llm_order_generation": False,
    }
