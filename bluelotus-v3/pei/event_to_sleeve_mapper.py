from __future__ import annotations

import json
from typing import Any, Dict, List

from db.v3_db_connection import get_v3_connection
from pei.sleeve_transmission_rules import SLEEVE_TRANSMISSION_RULES


def map_branch_to_sleeves(branch: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sleeve in branch.get("affected_sleeves") or []:
        channels = SLEEVE_TRANSMISSION_RULES.get(sleeve, ["NARRATIVE_SURVIVAL"])
        blocked = branch.get("blocked_action", "Add risk")
        allowed = branch.get("allowed_action", "Hold / observe")
        probability = float(branch.get("branch_probability") or 0)
        direction = "POSITIVE" if "relief" in branch.get("branch_name", "").lower() else "NEGATIVE" if probability >= 0.35 and ("hawkish" in branch.get("branch_name", "").lower() or "unwind" in branch.get("branch_name", "").lower() or "breakdown" in branch.get("branch_name", "").lower()) else "CONDITIONAL"
        rows.append({
            "event_id": branch.get("event_id", ""),
            "branch_id": branch.get("branch_id", ""),
            "affected_sleeve": sleeve,
            "expected_direction": direction,
            "confidence": round(max(0.35, min(0.85, probability + 0.25)), 2),
            "transmission_channel": channels[0],
            "all_transmission_channels": channels,
            "allowed_action": allowed,
            "blocked_action": blocked,
            "required_confirmation": "; ".join((branch.get("confirmation_signals") or [])[:3]),
            "kill_condition": "; ".join((branch.get("kill_conditions") or [])[:2]),
        })
    return rows


def build_sleeve_map(trees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapped: List[Dict[str, Any]] = []
    for tree in trees:
        for branch in tree.get("branches", []):
            mapped.extend(map_branch_to_sleeves(branch))
    return mapped


def persist_sleeve_map(rows: List[Dict[str, Any]]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        for row in rows:
            cur.execute(
                """
                INSERT INTO pei_event_to_sleeve_map (
                    event_id, branch_id, sleeve, expected_direction, confidence,
                    transmission_channel, allowed_action, blocked_action,
                    required_confirmation, kill_condition
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    row["event_id"], row["branch_id"], row["affected_sleeve"],
                    row["expected_direction"], row["confidence"],
                    row["transmission_channel"], row["allowed_action"],
                    row["blocked_action"], row["required_confirmation"], row["kill_condition"],
                ),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()
