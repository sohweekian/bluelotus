from __future__ import annotations

from typing import Any, Dict


def build_replay_input(dataset: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    return {
        "dataset_generated_at": meta.get("generated_at"),
        "portfolio": dataset.get("portfolio") or {},
        "canonical": dataset.get("canonical") or {},
        "point_in_time": True,
    }

