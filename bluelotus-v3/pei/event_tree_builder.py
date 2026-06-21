from __future__ import annotations

import json
from typing import Dict, List

from db.v3_db_connection import get_v3_connection
from pei.common import stable_id, sgt_now
from pei.event_branch_schema import PEIBranch
from pei.event_schema import PEIEvent


def _branches_for_event(event: PEIEvent) -> List[PEIBranch]:
    if event.event_type == "FED_POLICY":
        specs = [
            ("Hawkish repricing persists", 0.40, "Yields and USD stay firm; high beta remains under pressure.", "HOLD / hedge retain", "Add risk / second tranche"),
            ("Inflation relief offsets hawkishness", 0.30, "Rates ease and risk appetite recovers despite hawkish rhetoric.", "Hold scouts; review trims into strength", "Chase open"),
            ("Risk rally fades under liquidity pressure", 0.30, "Volatility and credit stress return while growth fades.", "Preserve cash / de-risk review", "DCA / scale-in"),
        ]
    elif event.event_type == "YEN_CARRY_RISK":
        specs = [
            ("Carry unwind active", 0.45, "Yen strengthens, vol spikes, high beta sells off.", "Hedge retain / cash preserve", "Add risk"),
            ("Carry stress stabilizes", 0.30, "USDJPY stabilizes and volatility fades.", "Hold scouts / observe", "Second tranche"),
            ("BOJ signal fades", 0.25, "Policy fear fades and global risk resumes.", "Trim hedge review", "Automatic risk-on"),
        ]
    elif event.event_type == "PRIVATE_MARKET_CAPITAL_ABSORPTION":
        specs = [
            ("Reflexive suppression confirmed", 0.45, "Proxy weakness mean-reverts while own catalysts remain intact.", "HOLD / OBSERVE; pullback-only review", "Panic de-risk"),
            ("Thesis breakdown likely", 0.25, "Proxy and space basket fail with catalyst deterioration.", "De-risk review", "Reload weakness"),
            ("Broad risk-off contamination", 0.30, "Weakness reflects macro/liquidity stress rather than pure suppression.", "Add blocked / hedge retain", "DCA / scale-in"),
        ]
    else:
        specs = [
            ("Base branch confirms", 0.40, "Primary catalyst survives.", "Hold / observe", "Second tranche"),
            ("Contradiction branch", 0.35, "Contradictory evidence dominates.", "Add blocked", "Add risk"),
            ("Failure branch", 0.25, "Kill condition triggers.", "De-risk review", "DCA"),
        ]
    branches: List[PEIBranch] = []
    for name, probability, description, allowed, blocked in specs:
        branches.append(
            PEIBranch(
                branch_id=stable_id("PEI_BRANCH", event.event_id, name),
                event_id=event.event_id,
                branch_name=name,
                branch_description=description,
                branch_probability=probability,
                branch_time_horizon="5-10 trading days",
                evidence_for=event.confirmation_signals[:3],
                evidence_against=event.contradiction_signals[:3],
                confirmation_signals=event.confirmation_signals,
                contradiction_signals=event.contradiction_signals,
                kill_conditions=event.kill_conditions,
                affected_sleeves=event.affected_sleeves,
                allowed_action=allowed,
                blocked_action=blocked,
                resolution_criteria=event.resolution_criteria,
            )
        )
    total = sum(b.branch_probability for b in branches) or 1.0
    for branch in branches:
        branch.branch_probability = round(branch.branch_probability / total, 4)
    return branches


def build_scenario_trees(events: List[PEIEvent]) -> List[Dict]:
    trees: List[Dict] = []
    for event in events:
        branches = _branches_for_event(event)
        event.scenario_branches = [b.to_dict() for b in branches]
        event.branch_probabilities = {b.branch_name: b.branch_probability for b in branches}
        trees.append({"event": event.to_dict(), "branches": [b.to_dict() for b in branches]})
    return trees


def persist_branches(trees: List[Dict]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        now = sgt_now()
        for tree in trees:
            for branch in tree["branches"]:
                cur.execute(
                    """
                    INSERT INTO pei_event_branches (
                        branch_id, event_id, branch_name, branch_description,
                        branch_probability, branch_time_horizon, evidence_for,
                        evidence_against, confirmation_signals, contradiction_signals,
                        kill_conditions, affected_sleeves, allowed_action,
                        blocked_action, resolution_criteria, resolution_status
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        branch_probability=VALUES(branch_probability),
                        evidence_for=VALUES(evidence_for),
                        evidence_against=VALUES(evidence_against),
                        resolution_status=VALUES(resolution_status)
                    """,
                    (
                        branch["branch_id"],
                        branch["event_id"],
                        branch["branch_name"],
                        branch["branch_description"],
                        branch["branch_probability"],
                        branch["branch_time_horizon"],
                        json.dumps(branch["evidence_for"]),
                        json.dumps(branch["evidence_against"]),
                        json.dumps(branch["confirmation_signals"]),
                        json.dumps(branch["contradiction_signals"]),
                        json.dumps(branch["kill_conditions"]),
                        json.dumps(branch["affected_sleeves"]),
                        branch["allowed_action"],
                        branch["blocked_action"],
                        json.dumps(branch["resolution_criteria"]),
                        branch["resolution_status"],
                    ),
                )
                cur.execute(
                    "INSERT INTO pei_event_branch_probabilities (branch_id,event_id,probability,updated_at,evidence) VALUES (%s,%s,%s,%s,%s)",
                    (branch["branch_id"], branch["event_id"], branch["branch_probability"], now, json.dumps(branch["evidence_for"])),
                )
        conn.commit()
        cur.close()
    finally:
        conn.close()
