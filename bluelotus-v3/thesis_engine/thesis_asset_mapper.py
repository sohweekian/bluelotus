from __future__ import annotations

from typing import Any, Dict, List


def map_thesis_assets(thesis_registry: Dict[str, Any]) -> Dict[str, List[str]]:
    theses = thesis_registry.get("theses", {})
    if not isinstance(theses, dict):
        return {}
    mapped: Dict[str, List[str]] = {}
    for thesis_id, config in theses.items():
        if isinstance(config, dict) and isinstance(config.get("mapped_assets"), list):
            mapped[str(thesis_id)] = [str(item) for item in config["mapped_assets"]]
    return mapped
