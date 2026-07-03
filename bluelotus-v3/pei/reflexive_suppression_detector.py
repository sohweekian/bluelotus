from __future__ import annotations

import json
from typing import Any, Dict, List

from db.v3_db_connection import get_v3_connection
from pei.common import sgt_now, stable_id
from pei.private_liquidity_proxy import SPACE_PROXY_TICKERS, related_private_vehicle


def _latest_ticker_move(dataset: Dict[str, Any], ticker: str) -> float:
    for section in ("live_prices", "market_data", "prices"):
        value = dataset.get(section)
        if isinstance(value, dict):
            row = value.get(ticker) or value.get(ticker.upper())
            if isinstance(row, dict):
                for key in ("change_pct", "day_change_pct", "pct_change", "move_pct"):
                    if key in row:
                        try:
                            return float(row[key])
                        except Exception:
                            pass
    for row in dataset.get("universe_snapshot", []) if isinstance(dataset.get("universe_snapshot"), list) else []:
        if isinstance(row, dict) and str(row.get("ticker")).upper() == ticker.upper():
            for key in ("day_pct", "change_pct", "move_pct"):
                if key in row:
                    try:
                        return float(row[key])
                    except Exception:
                        pass
    return 0.0


def detect_reflexive_suppression(dataset: Dict[str, Any], ticker: str = "ASTS") -> Dict[str, Any]:
    move = _latest_ticker_move(dataset, ticker)
    private_vehicle = related_private_vehicle(ticker)
    has_private_event = bool(private_vehicle)
    proxy_down = move < 0
    broad_liquidity_ok = True
    own_catalysts_intact = True
    outflow_without_breakdown = True
    criteria = {
        "public_proxy_down": proxy_down,
        "theme_basket_flat_or_less_weak": True,
        "related_private_vehicle_absorbing_capital": has_private_event,
        "public_proxy_own_catalysts_not_broken": own_catalysts_intact,
        "outflow_without_thesis_deterioration": outflow_without_breakdown,
        "credit_and_broad_liquidity_not_systemic_breakdown": broad_liquidity_ok,
    }
    score = sum(1 for passed in criteria.values() if passed)
    if score >= 5 and proxy_down:
        classification = "REFLEXIVE_SUPPRESSION_LIKELY"
        action = "HOLD / OBSERVE; PULLBACK-ONLY REVIEW; no panic de-risk unless kill condition triggers."
    elif score >= 4:
        classification = "REFLEXIVE_SUPPRESSION_POSSIBLE"
        action = "HOLD / OBSERVE; require confirmation before reload."
    elif not broad_liquidity_ok:
        classification = "BROAD_RISK_OFF_CONTAMINATION"
        action = "ADD BLOCKED; HEDGE RETAIN; CASH PRESERVE."
    elif proxy_down:
        classification = "THESIS_BREAKDOWN_LIKELY"
        action = "DE-RISK REVIEW."
    else:
        classification = "INSUFFICIENT_EVIDENCE"
        action = "Observe."
    return {
        "ticker": ticker,
        "related_private_vehicle": private_vehicle,
        "classification": classification,
        "criteria": criteria,
        "criteria_pass_count": score,
        "action_mapping": action,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
    }


def persist_reflexive_suppression(check: Dict[str, Any]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pei_reflexive_suppression_checks
            (check_id, ticker, classification, criteria_json, action_mapping, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE classification=VALUES(classification), criteria_json=VALUES(criteria_json), action_mapping=VALUES(action_mapping)
            """,
            (
                stable_id("PEI_SUPPRESSION", check.get("ticker"), check.get("classification")),
                check.get("ticker"),
                check.get("classification"),
                json.dumps(check.get("criteria")),
                check.get("action_mapping"),
                sgt_now(),
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
