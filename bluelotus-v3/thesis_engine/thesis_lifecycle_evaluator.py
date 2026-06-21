from __future__ import annotations

from typing import Any, Dict


def evaluate_lifecycle(thesis_registry: Dict[str, Any]) -> Dict[str, str]:
    theses = thesis_registry.get("theses", {})
    if not isinstance(theses, dict):
        return {}
    return {str(thesis_id): str(config.get("status", "watch")) for thesis_id, config in theses.items() if isinstance(config, dict)}
