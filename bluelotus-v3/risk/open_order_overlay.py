from __future__ import annotations

from typing import Any, Dict, List


def build_open_order_overlay(orders: Dict[str, Any] | None) -> Dict[str, Any]:
    orders = orders or {}
    open_orders: List[Dict[str, Any]] = [row for row in (orders.get("open_orders") or []) if isinstance(row, dict)]
    statuses = sorted({str(row.get("status") or "UNKNOWN").upper() for row in open_orders})
    return {
        "open_order_count": len(open_orders),
        "open_order_statuses": statuses,
        "orders_generated": 0,
        "order_routing_enabled": False,
        "open_order_overlay_status": "WAITING_CIO_MANUAL_SUBMIT" if open_orders else "NO_OPEN_ORDERS",
    }

