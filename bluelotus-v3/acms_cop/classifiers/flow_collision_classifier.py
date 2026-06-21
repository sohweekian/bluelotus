from __future__ import annotations

from typing import Any, Dict


INFLOW_LABELS = {"INFLOW", "ACCUMULATE"}
OUTFLOW_LABELS = {"OUTFLOW", "DISTRIBUTE"}


def normalize_direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"UP", "RISK_ON", "POSITIVE"} or text.startswith("+"):
        return "UP"
    if text in {"DOWN", "RISK_OFF", "NEGATIVE"} or text.startswith("-"):
        return "DOWN"
    return "FLAT" if text in {"FLAT", "UNCHANGED", "0", "NONE"} else text


def classify_flow_collision(
    price_direction: Any,
    flow_bias: Any,
    main_net_flow: Any = None,
    hedge_demand_score: Any = None,
    causal_status: Any = None,
) -> Dict[str, Any]:
    direction = normalize_direction(price_direction)
    bias = str(flow_bias or "").strip().upper()
    if bias in INFLOW_LABELS:
        flow_direction = "INFLOW"
    elif bias in OUTFLOW_LABELS:
        flow_direction = "OUTFLOW"
    elif main_net_flow is not None:
        try:
            flow_direction = "INFLOW" if float(main_net_flow) >= 0 else "OUTFLOW"
        except (TypeError, ValueError):
            flow_direction = "UNKNOWN"
    else:
        flow_direction = "UNKNOWN"

    state = "UNCLASSIFIED"
    if direction == "UP" and bias in INFLOW_LABELS:
        state = "CLEAN_ACCUMULATION_CANDIDATE"
    elif direction == "UP" and bias in OUTFLOW_LABELS:
        state = "DISTRIBUTION_INTO_STRENGTH_CANDIDATE"
    elif direction == "DOWN" and bias in OUTFLOW_LABELS:
        state = "FORCED_LIQUIDATION_CANDIDATE"
    elif direction in {"DOWN", "FLAT"} and bias in INFLOW_LABELS:
        state = "ACCUMULATION_INTO_WEAKNESS_CANDIDATE"

    return {
        "price_direction": direction,
        "flow_bias": bias,
        "flow_direction": flow_direction,
        "flow_collision_state": state,
        "hedge_demand_score": hedge_demand_score,
        "causal_status": str(causal_status or "UNCONFIRMED").upper(),
    }

