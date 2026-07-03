from __future__ import annotations

from typing import Any, Dict


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_cash_overlay(portfolio: Dict[str, Any], orders: Dict[str, Any] | None = None) -> Dict[str, Any]:
    orders = orders or {}
    total_assets = _num(portfolio.get("total_assets", portfolio.get("total_value")))
    cash = _num(portfolio.get("cash"))
    cash_floor = _num(portfolio.get("cash_floor"), 0.0)
    pending_cash = 0.0
    for row in orders.get("open_orders") or []:
        if isinstance(row, dict):
            pending_cash += max(0.0, _num(row.get("estimated_value") or row.get("notional") or row.get("amount")))
    cash_available = max(0.0, cash - pending_cash - cash_floor)
    cash_weight = cash / total_assets if total_assets else 0.0
    if cash_weight >= 0.70:
        status = "CASH_FORTRESS_ACTIVE"
    elif cash_available <= 0:
        status = "CASH_CONSTRAINED"
    else:
        status = "CASH_AVAILABLE"
    return {
        "cash": round(cash, 2),
        "cash_weight": round(cash_weight, 6),
        "cash_floor": round(cash_floor, 2),
        "open_order_cash_reserved": round(pending_cash, 2),
        "cash_available_after_open_orders": round(cash_available, 2),
        "cash_overlay_status": status,
    }

