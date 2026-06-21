from __future__ import annotations

from typing import Any, Dict

from .risk_overlay_schema import HEDGE_TICKERS


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_hedge_overlay(positions: Dict[str, Dict[str, Any]], total_assets: float) -> Dict[str, Any]:
    hedge_value = 0.0
    for ticker, row in positions.items():
        if ticker in HEDGE_TICKERS:
            hedge_value += _num(row.get("market_value") or row.get("market_val") or row.get("mkt_val") or row.get("value"))
    target_hedge = max(0.0, total_assets * 0.02)
    gap = max(0.0, target_hedge - hedge_value)
    status = "HEDGE_PRESENT" if hedge_value > 0 else "HEDGE_GAP"
    return {
        "hedge_value": round(hedge_value, 2),
        "hedge_target_usd": round(target_hedge, 2),
        "hedge_gap_usd": round(gap, 2),
        "hedge_overlay_status": status,
    }

