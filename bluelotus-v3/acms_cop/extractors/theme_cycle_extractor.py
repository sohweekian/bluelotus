from __future__ import annotations

from typing import Any, Dict, List

from acms_cop.classifiers.behavioral_state_classifier import classify_behavioral_state
from acms_cop.classifiers.causal_status_classifier import classify_causal_status
from acms_cop.common import dominant, first_list, json_dumps, safe_float


def _direction_from_move(value: Any) -> str:
    move = safe_float(value, 0.0) or 0.0
    if move > 0.05:
        return "UP"
    if move < -0.05:
        return "DOWN"
    return "FLAT"


def extract_theme_cycles(dataset: Dict[str, Any], ticker_rows: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    events = first_list(dataset.get("event_correlations_all"), dataset.get("event_correlations"))
    ticker_rows = ticker_rows or []
    rows: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        theme = str(event.get("theme") or "").strip()
        if not theme:
            continue
        related = [r for r in ticker_rows if str(r.get("theme") or "").upper() == theme.upper()]
        direction = str(event.get("direction") or "")
        avg_move = safe_float(event.get("basket_move"))
        causal = classify_causal_status(
            event.get("evidence_tier"),
            event.get("direct_catalyst"),
            event.get("source_count"),
            event.get("review_flags"),
            direction,
        )
        behavior = classify_behavioral_state(
            _direction_from_move(avg_move),
            dominant([r.get("flow_bias") for r in related]) or "",
            causal_status=causal,
            regime_label=event.get("global_regime_context"),
            cross_market_inconsistent="CAUSAL_NOT_CONFIRMED" in direction.upper(),
        )
        rows.append({
            "theme": theme,
            "theme_direction": direction,
            "avg_move": avg_move,
            "positive_count": sum(1 for r in related if (safe_float(r.get("day_return"), 0.0) or 0.0) > 0),
            "total_count": len(related),
            "dominant_flow_bias": dominant([r.get("flow_bias") for r in related]),
            "net_main_flow": sum((safe_float(r.get("main_net_flow"), 0.0) or 0.0) for r in related),
            "causal_status": causal,
            "acms_state": behavior["acms_state"],
            "confidence": safe_float(event.get("confidence"), behavior["confidence"]),
            "cio_posture": behavior["recommended_posture"],
            "notes": str(event.get("why") or "")[:2000],
            "raw_theme_json": json_dumps(event),
        })
    return rows

