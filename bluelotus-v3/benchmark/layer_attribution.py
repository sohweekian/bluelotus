from __future__ import annotations

from typing import Any, Dict, List


def build_layer_attribution(dataset: Dict[str, Any]) -> List[Dict[str, object]]:
    pipeline = dataset.get("deterministic_pipeline_v3_2") if isinstance(dataset.get("deterministic_pipeline_v3_2"), dict) else {}
    stages = pipeline.get("stages") if isinstance(pipeline.get("stages"), list) else []
    out = []
    for stage in stages:
        if isinstance(stage, dict):
            out.append({
                "layer": stage.get("stage_name"),
                "status": stage.get("status"),
                "warning_count": len(stage.get("warnings") or []),
                "error_count": len(stage.get("errors") or []),
                "orders_generated": 0,
                "order_routing_enabled": False,
            })
    return out

