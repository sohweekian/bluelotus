from __future__ import annotations

import json
from typing import Any, Dict, List

from db.v3_db_connection import get_v3_connection
from pei.common import stable_id, sgt_now


def build_forecast_registry(trees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    forecasts: List[Dict[str, Any]] = []
    for tree in trees:
        event = tree.get("event", {})
        for branch in tree.get("branches", []):
            criteria = branch.get("resolution_criteria") or []
            if not criteria:
                continue
            forecasts.append({
                "forecast_id": stable_id("PEI_FORECAST", event.get("event_id"), branch.get("branch_id")),
                "event_id": event.get("event_id"),
                "branch_id": branch.get("branch_id"),
                "branch_name": branch.get("branch_name"),
                "probability": branch.get("branch_probability"),
                "forecast_timestamp_sgt": sgt_now(),
                "forecast_horizon": branch.get("branch_time_horizon", "5 trading days"),
                "resolution_date": event.get("resolution_date", ""),
                "resolution_source": "BlueLotus V3 market data / governance gate / thesis widgets",
                "resolution_criteria": criteria,
                "model_version": "pei_v0.1",
                "governance_pack_id": event.get("governance_pack_id", ""),
                "report_memory_binding_id": event.get("report_memory_binding_id", ""),
                "cio_only_manual": True,
                "orders_generated": 0,
                "routing_enabled": False,
                "resolution_status": "PENDING",
            })
    return forecasts


def persist_forecasts(forecasts: List[Dict[str, Any]]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        for forecast in forecasts:
            cur.execute(
                """
                INSERT INTO pei_forecast_registry (
                    forecast_id, event_id, branch_id, probability,
                    forecast_timestamp_sgt, forecast_horizon, resolution_date,
                    resolution_criteria, model_version, governance_pack_id,
                    report_memory_binding_id, cio_only_manual, orders_generated, routing_enabled
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    probability=VALUES(probability),
                    resolution_criteria=VALUES(resolution_criteria),
                    report_memory_binding_id=VALUES(report_memory_binding_id)
                """,
                (
                    forecast["forecast_id"], forecast["event_id"], forecast["branch_id"],
                    forecast["probability"], forecast["forecast_timestamp_sgt"],
                    forecast["forecast_horizon"], forecast["resolution_date"],
                    json.dumps(forecast["resolution_criteria"]), forecast["model_version"],
                    forecast["governance_pack_id"], forecast["report_memory_binding_id"],
                    forecast["cio_only_manual"], forecast["orders_generated"], forecast["routing_enabled"],
                ),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()
