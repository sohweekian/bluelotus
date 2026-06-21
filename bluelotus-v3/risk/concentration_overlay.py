from __future__ import annotations

from typing import Any, Dict


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_concentration_overlay(positions: Dict[str, Dict[str, Any]], total_assets: float) -> Dict[str, Any]:
    weights = []
    cluster_totals: Dict[str, float] = {}
    for ticker, row in positions.items():
        value = _num(row.get("market_value") or row.get("market_val") or row.get("mkt_val") or row.get("value"))
        weight = value / total_assets if total_assets else 0.0
        weights.append(weight)
        thesis = str(row.get("thesis") or row.get("sector") or "UNMAPPED").upper()
        if any(token in thesis for token in ("GOLD", "MINER", "AU", "NEM", "AEM")):
            cluster = "GOLD_MINERS"
        elif ticker in {"BKSY", "LUNR", "RKLB", "ASTS", "PL"}:
            cluster = "SPACE_HIGH_BETA"
        elif ticker in {"QUBT", "QBTS", "IONQ", "RGTI"}:
            cluster = "QUANTUM_HIGH_BETA"
        else:
            cluster = "OTHER"
        cluster_totals[cluster] = cluster_totals.get(cluster, 0.0) + weight
    largest = max(weights) if weights else 0.0
    largest_cluster = max(cluster_totals.values()) if cluster_totals else 0.0
    status = "CONCENTRATION_REVIEW" if largest > 0.15 or largest_cluster > 0.35 else "PASS"
    return {
        "largest_position_weight": round(largest, 6),
        "cluster_concentration": round(largest_cluster, 6),
        "cluster_weights": {k: round(v, 6) for k, v in sorted(cluster_totals.items())},
        "concentration_overlay_status": status,
    }

