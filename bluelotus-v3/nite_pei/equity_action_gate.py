"""
BlueLotus V3 — NITE-PEI Sub-Engine E6a: Equity Action Gate
===========================================================
Routes NITE-PEI CKRI de-risk signals to equity sleeve advisory.

CRITICAL ARCHITECTURAL INVARIANT (BLV3-DOCTRINE-007):
    VXX and VIXY are PERMANENTLY EXCLUDED from this gate.
    All hedge instruments are governed by hedge_action_gate.py ONLY.
    De-risk from CKRI must never touch hedge positions.

ALL OUTPUTS ARE ADVISORY ONLY.
MANUAL_EXECUTION_REQUIRED: TRUE at all times.

GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Doctrine constant — permanent exclusion list for this gate
# ---------------------------------------------------------------------------

HEDGE_TICKERS: frozenset[str] = frozenset({"VXX", "VIXY"})

"""
EQUITY ONLY gate.
VXX and VIXY are explicitly excluded — see hedge_action_gate.py.
This enforcement is architectural (frozenset constant), not advisory.
"""


def _sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# CKRI zone → de-risk action lookup
# ---------------------------------------------------------------------------

_CKRI_ACTION_MAP: Dict[str, str] = {
    "CLEAR":    "NO_ACTION",
    "WATCH":    "MONITOR — reduce new adds only",
    "ELEVATED": "FREEZE_NEW_ADDS — CIO review required",
    "HIGH":     "RISK_REVIEW_REQUIRED — consider equity de-risk",
    "CRITICAL": "RAISE_CASH_REVIEW — significant equity de-risk advisory",
}


def _filter_equity_tickers(tickers: List[str]) -> List[str]:
    """Return tickers with hedge instruments stripped out."""
    return [t for t in tickers if t.upper() not in HEDGE_TICKERS]


# ---------------------------------------------------------------------------
# Primary advisory function
# ---------------------------------------------------------------------------

def equity_de_risk_advisory(
    ckri_zone: str,
    theses: List[Dict[str, Any]],
    dataset: Dict[str, Any],
    affected_tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Produce an equity sleeve de-risk advisory based on CKRI zone.

    Args:
        ckri_zone:         CKRI zone string from ckri_calculator.compute_ckri().
        theses:            List of active thesis dicts (for affected ticker extraction).
        dataset:           Full dataset dict (for portfolio value lookups).
        affected_tickers:  Optional override list of tickers. VXX/VIXY auto-excluded.

    Returns:
        Advisory dict. Never contains VXX or VIXY.
        manual_execution_required = True always.
        llm_order_generation = False always.
        order_routing_enabled = False always.

    BLV3-DOCTRINE-007: This gate handles equity ONLY. Hedge sizing is in hedge_action_gate.py.
    """
    # Collect equity tickers — strip hedge tickers at every entry point
    if affected_tickers is not None:
        equity_tickers = _filter_equity_tickers(affected_tickers)
    else:
        raw_tickers: List[str] = []
        for thesis in theses:
            raw_tickers.extend(thesis.get("affected_tickers", []))
            raw_tickers.extend(thesis.get("mapped_assets", {}).get("equities", []))
        equity_tickers = _filter_equity_tickers(list(dict.fromkeys(raw_tickers)))

    # Validate no hedge tickers leaked through (defensive invariant)
    hedge_leak = [t for t in equity_tickers if t.upper() in HEDGE_TICKERS]
    if hedge_leak:
        # This should never happen due to _filter_equity_tickers above.
        # Belt-and-suspenders: remove them and flag in advisory.
        equity_tickers = [t for t in equity_tickers if t.upper() not in HEDGE_TICKERS]

    # Portfolio NAV
    nav_total = 0.0
    try:
        portfolio = dataset.get("portfolio") or {}
        nav_total = float(
            portfolio.get("total_value")
            or portfolio.get("nav")
            or 0.0
        )
    except (TypeError, ValueError):
        nav_total = 0.0

    # Zone action
    action = _CKRI_ACTION_MAP.get(ckri_zone.upper(), "UNKNOWN_ZONE — CIO review required")

    # De-risk magnitude (advisory percentage of equity sleeve to review)
    de_risk_pct = {
        "CLEAR":    0.00,
        "WATCH":    0.00,
        "ELEVATED": 0.00,
        "HIGH":     0.10,   # Suggest reviewing up to 10% of equity sleeve
        "CRITICAL": 0.25,   # Suggest reviewing up to 25% of equity sleeve
    }.get(ckri_zone.upper(), 0.00)

    equity_review_usd = round(nav_total * de_risk_pct, 2)

    return {
        "gate": "equity_action_gate",
        "doctrine_ref": "BLV3-DOCTRINE-007",
        "generated_at_sgt": _sgt_now(),
        "ckri_zone": ckri_zone,
        "action": action,
        "de_risk_pct_advisory": de_risk_pct,
        "equity_review_usd_advisory": equity_review_usd,
        "nav_total": nav_total,
        "equity_tickers_in_scope": equity_tickers,
        "hedge_tickers_excluded": sorted(HEDGE_TICKERS),
        "hedge_leak_detected": bool(hedge_leak),
        "note": (
            "Advisory only. VXX/VIXY permanently excluded from this gate. "
            "All hedge sizing governed exclusively by hedge_action_gate."
        ),
        "manual_execution_required": True,
        "llm_order_generation": False,
        "order_routing_enabled": False,
    }


# ---------------------------------------------------------------------------
# Per-thesis equity position review (used when CKRI >= HIGH)
# ---------------------------------------------------------------------------

def per_thesis_equity_review(
    theses: List[Dict[str, Any]],
    ckri_zone: str,
    dataset: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    For each thesis, produce an equity position review entry.

    Only active/watch theses are included.
    Kill conditions with state TRIGGERED or CONFIRMED are flagged.
    Hedge tickers excluded throughout.

    Returns list of per-thesis equity review dicts.
    """
    if ckri_zone not in ("HIGH", "CRITICAL"):
        return []

    reviews = []
    portfolio = dataset.get("portfolio") or {}
    positions = portfolio.get("positions") or {}

    for thesis in theses:
        if str(thesis.get("status", "")).lower() not in ("active", "watch"):
            continue

        thesis_id = str(thesis.get("thesis_id") or thesis.get("id", "UNKNOWN"))
        raw_tickers = (
            thesis.get("affected_tickers", [])
            + thesis.get("mapped_assets", {}).get("equities", [])
        )
        equity_tickers = _filter_equity_tickers(list(dict.fromkeys(raw_tickers)))

        # Current market value of equity sleeve for this thesis
        current_value = 0.0
        if isinstance(positions, dict):
            for ticker in equity_tickers:
                pos = (
                    positions.get(ticker.upper())
                    or positions.get(ticker.lower())
                    or {}
                )
                if isinstance(pos, dict):
                    val = pos.get("market_value") or pos.get("value") or 0.0
                    try:
                        current_value += float(val)
                    except (TypeError, ValueError):
                        pass

        # Worst kill state
        kill_conditions = thesis.get("kill_conditions", [])
        triggered_kills = [
            kc.get("kill_id", "UNKNOWN")
            for kc in kill_conditions
            if str(kc.get("current_state", "")).upper() in ("TRIGGERED", "CONFIRMED")
        ]

        reviews.append({
            "thesis_id": thesis_id,
            "equity_tickers": equity_tickers,
            "current_equity_value_usd": round(current_value, 2),
            "triggered_kill_ids": triggered_kills,
            "cio_review_flag": bool(triggered_kills),
            "manual_execution_required": True,
            "llm_order_generation": False,
        })

    return reviews
