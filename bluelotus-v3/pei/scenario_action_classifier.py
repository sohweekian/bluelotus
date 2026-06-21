from __future__ import annotations

from typing import Any, Dict


def classify_action(branch: Dict[str, Any]) -> Dict[str, Any]:
    allowed = str(branch.get("allowed_action") or "HOLD / OBSERVE")
    blocked = str(branch.get("blocked_action") or "Add risk")
    return {
        "allowed_action": allowed,
        "blocked_action": blocked,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
        "action_is_instruction": False,
    }
