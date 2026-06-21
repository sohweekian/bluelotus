from __future__ import annotations

import math
from typing import Any, Dict, List


MIN_RESOLVED_FORECASTS = 30


def estimate_mutual_information(confirmed: int, contradicted: int) -> float:
    total = confirmed + contradicted
    if total <= 0:
        return 0.0
    p = confirmed / total
    if p in (0.0, 1.0):
        entropy = 0.0
    else:
        entropy = -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))
    return round(max(0.0, 1.0 - entropy), 6)


def build_source_capacity_record(source: Dict[str, Any], governance: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal_count = int(source.get("signal_count") or 0)
    confirmed = int(source.get("confirmed_count") or 0)
    contradicted = int(source.get("contradicted_count") or 0)
    unresolved = max(0, signal_count - confirmed - contradicted)
    resolved = confirmed + contradicted
    mi = estimate_mutual_information(confirmed, contradicted)
    collecting = resolved < MIN_RESOLVED_FORECASTS
    record = {
        "source_name": source.get("source") or source.get("source_name") or "UNKNOWN",
        "source_tier": int(source.get("tier") or source.get("source_tier") or 4),
        "signal_count": signal_count,
        "confirmed_count": confirmed,
        "contradicted_count": contradicted,
        "unresolved_count": unresolved,
        "estimated_mutual_information": mi,
        "estimated_channel_capacity": mi,
        "capacity_confidence": "INSUFFICIENT_RESOLVED_FORECASTS" if collecting else "VALIDATION_READY",
        "status": "CAPACITY_COLLECTING" if collecting else "CAPACITY_ESTIMATED",
        "validation_status": "NOT_YET_VALIDATED" if collecting else "EMPIRICAL_REVIEW_REQUIRED",
        "tier_upgrade_candidate": False,
        "tier_downgrade_candidate": False,
        "automatic_tier_change_allowed": False,
    }
    if governance:
        record.update(governance)
    return record


def build_source_capacity(dataset: Dict[str, Any], governance: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    sources = dataset.get("source_health")
    if not isinstance(sources, list):
        sources = []
    return [build_source_capacity_record(s, governance) for s in sources]
