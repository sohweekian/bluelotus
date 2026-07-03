from __future__ import annotations

import json
from typing import Any, Dict, List

from db.v3_db_connection import get_v3_connection
from pei.common import sgt_now, stable_id
from pei.scenario_action_classifier import classify_action


def build_portfolio_playbook(trees: List[Dict[str, Any]], sleeve_map: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_branch = {}
    for row in sleeve_map:
        by_branch.setdefault(row["branch_id"], []).append(row)
    playbook: List[Dict[str, Any]] = []
    for tree in trees:
        event = tree.get("event", {})
        for branch in tree.get("branches", []):
            action = classify_action(branch)
            playbook.append({
                "event_id": event.get("event_id"),
                "event_title": event.get("event_title"),
                "scenario_branch": branch.get("branch_name"),
                "probability": branch.get("branch_probability"),
                "evidence_for": branch.get("evidence_for", []),
                "evidence_against": branch.get("evidence_against", []),
                "confirmation_signals": branch.get("confirmation_signals", []),
                "kill_conditions": branch.get("kill_conditions", []),
                "affected_sleeves": [r["affected_sleeve"] for r in by_branch.get(branch["branch_id"], [])],
                "allowed_action": action["allowed_action"],
                "blocked_action": action["blocked_action"],
                "execution_authority": "CIO_ONLY_MANUAL",
                "order_routing_enabled": False,
                "orders_generated": 0,
                "cio_interpretation": (
                    "Prepare for this branch under CIO_ONLY_MANUAL. "
                    "No execution is authorized by PEI."
                ),
                "forecast_resolution_date": event.get("resolution_date"),
            })
    return playbook


def persist_playbook(playbook: List[Dict[str, Any]]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        for row in playbook:
            playbook_id = stable_id("PEI_PLAYBOOK", row.get("event_id"), row.get("scenario_branch"))
            cur.execute(
                """
                INSERT INTO pei_portfolio_playbooks (playbook_id, event_id, playbook_json, created_at)
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE playbook_json=VALUES(playbook_json), created_at=VALUES(created_at)
                """,
                (playbook_id, row.get("event_id"), json.dumps(row), sgt_now()),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()
