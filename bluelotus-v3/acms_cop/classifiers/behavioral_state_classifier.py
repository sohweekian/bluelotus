from __future__ import annotations

from typing import Any, Dict

from acms_cop.classifiers.flow_collision_classifier import INFLOW_LABELS, OUTFLOW_LABELS, normalize_direction


ALLOWED_STATES = {
    "CLEAN_ACCUMULATION",
    "DISTRIBUTION_INTO_STRENGTH",
    "FORCED_LIQUIDATION",
    "SHORT_COVERING_RALLY",
    "ACCUMULATION_INTO_WEAKNESS",
    "HEDGED_RISK_ON",
    "REGIME_TRANSITION",
    "STRUCTURAL_SUPPRESSION",
    "UNCLASSIFIED",
}


def _meaning(state: str) -> str:
    return {
        "CLEAN_ACCUMULATION": "Institutional sponsorship appears aligned with price.",
        "DISTRIBUTION_INTO_STRENGTH": "Strength may be used as liquidity for distribution.",
        "FORCED_LIQUIDATION": "Selling pressure and price weakness point to liquidation risk.",
        "SHORT_COVERING_RALLY": "Upside may be mechanical rather than durable sponsorship.",
        "ACCUMULATION_INTO_WEAKNESS": "Institutions may be absorbing weakness while thesis remains intact.",
        "HEDGED_RISK_ON": "Risk appetite is present but hedges remain bid.",
        "REGIME_TRANSITION": "Signals conflict; wait for confirmation before scaling.",
        "STRUCTURAL_SUPPRESSION": "Capital diversion or structural pressure suppresses the theme.",
        "UNCLASSIFIED": "Evidence is insufficient for a behavioral-market label.",
    }.get(state, "Evidence is insufficient for a behavioral-market label.")


def classify_behavioral_state(
    price_direction: Any,
    flow_bias: Any,
    causal_status: Any = "UNCONFIRMED",
    hedge_demand_score: Any = 0,
    regime_label: Any = "",
    institutional_selling_present: bool = False,
    liquidity_stress_active: bool = False,
    high_beta_weakness_prior: bool = False,
    policy_event_active: bool = False,
    cross_market_inconsistent: bool = False,
    mega_event_diverts_capital: bool = False,
    thesis_intact: bool = True,
    vix_rising: bool = False,
    credit_weakening: bool = False,
) -> Dict[str, Any]:
    direction = normalize_direction(price_direction)
    bias = str(flow_bias or "").strip().upper()
    causal = str(causal_status or "UNCONFIRMED").upper()
    regime = str(regime_label or "").upper()
    try:
        hedge = float(hedge_demand_score or 0)
    except (TypeError, ValueError):
        hedge = 0.0

    state = "UNCLASSIFIED"
    secondary = "NONE"
    confidence = 0.45
    blocked = []
    posture = "REVIEW"

    if mega_event_diverts_capital:
        state, confidence = "STRUCTURAL_SUPPRESSION", 0.62
        blocked.append("SCALE_IN_UNTIL_CAPITAL_DIVERSION_CLEARS")
    elif policy_event_active or cross_market_inconsistent or "NEUTRAL" in regime:
        state, confidence = "REGIME_TRANSITION", 0.58
        blocked.append("SECOND_TRANCHE_ADD")
    elif direction == "UP" and bias in INFLOW_LABELS and causal in {"CONFIRMED", "PARTIAL_CONFIRMED"} and hedge < 0.7 and "RISK_OFF" not in regime:
        state, confidence, posture = "CLEAN_ACCUMULATION", 0.82, "WATCH"
    elif direction == "UP" and bias in OUTFLOW_LABELS and causal in {"UNCONFIRMED", "PARTIAL"}:
        state, confidence = "DISTRIBUTION_INTO_STRENGTH", 0.74
        if institutional_selling_present:
            confidence = 0.82
        blocked.append("CHASE_STRENGTH")
    elif direction == "DOWN" and bias in OUTFLOW_LABELS and (vix_rising or credit_weakening or liquidity_stress_active):
        state, confidence = "FORCED_LIQUIDATION", 0.86
        blocked.append("ADD_RISK")
    elif direction == "UP" and bias not in INFLOW_LABELS and high_beta_weakness_prior and hedge >= 0.5:
        state, confidence = "SHORT_COVERING_RALLY", 0.68
        blocked.append("TREAT_AS_CONFIRMED_RISK_ON")
    elif direction in {"DOWN", "FLAT"} and bias in INFLOW_LABELS and thesis_intact and not liquidity_stress_active:
        state, confidence, posture = "ACCUMULATION_INTO_WEAKNESS", 0.72, "WATCH"
        blocked.append("SECOND_TRANCHE_WITHOUT_CONFIRMATION")
    elif direction == "UP" and hedge >= 0.5 and "RISK_ON" not in regime:
        state, confidence = "HEDGED_RISK_ON", 0.66
        secondary = "REGIME_TRANSITION"
        blocked.append("ASSUME_FULL_RISK_ON")

    return {
        "acms_state": state,
        "secondary_state": secondary,
        "confidence": confidence,
        "cio_meaning": _meaning(state),
        "recommended_posture": posture,
        "blocked_actions_json": blocked,
    }

