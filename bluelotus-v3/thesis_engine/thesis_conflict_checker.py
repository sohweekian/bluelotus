from __future__ import annotations

from typing import Any, Dict, List


def check_thesis_conflicts(thesis_registry: Dict[str, Any]) -> List[Dict[str, str]]:
    theses = thesis_registry.get("theses", {})
    if not isinstance(theses, dict):
        return []
    inactive = [key for key, value in theses.items() if isinstance(value, dict) and value.get("status") == "archived"]
    return [{"thesis_id": str(item), "conflict": "archived thesis should not drive live action"} for item in inactive]
