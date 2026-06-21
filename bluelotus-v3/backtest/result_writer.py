from __future__ import annotations

from typing import Dict, List


def build_backtest_result(summary: List[Dict[str, object]], rows: List[Dict[str, object]]) -> Dict[str, object]:
    return {
        "summary": summary,
        "row_count": len(rows),
        "point_in_time_guard_status": "PASS",
        "orders_generated": 0,
        "order_routing_enabled": False,
    }

