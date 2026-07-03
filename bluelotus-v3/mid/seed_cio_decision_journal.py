#!/usr/bin/env python3
"""
BlueLotus MID -- CIO decision journal seeder.

Creates research-only CIO review records from portfolio targets and risk model
breaches. This is not an order system. It never calls broker order methods and
every row has order_generated = false unless the CIO updates it manually later.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "audit" / "cio_decision_journal_latest.json"


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def load_dataset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("dataset_raw.json must be a JSON object")
    return data


def safe_id(*parts: Any) -> str:
    text = "-".join(str(p or "") for p in parts)
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return text[:92]


def build_target_decisions(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets = dataset.get("portfolio_targets") if isinstance(dataset.get("portfolio_targets"), dict) else {}
    run_id = str(targets.get("run_id") or "portfolio-targets")
    actions = targets.get("actions") if isinstance(targets.get("actions"), list) else []
    rows: List[Dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        ticker = str(action.get("ticker") or "").upper()
        current_weight = sf(action.get("current_weight"))
        target_weight = sf(action.get("target_weight"))
        delta = target_weight - current_weight
        priority = "P1" if abs(delta) >= 0.05 else "P2"
        rows.append({
            "decision_id": safe_id("CDJ", run_id, ticker, action.get("action_type")),
            "source_run_id": run_id,
            "decision_type": "TARGET_WEIGHT_REVIEW",
            "status": "RESEARCH_PENDING_CIO_REVIEW",
            "priority": priority,
            "ticker": ticker or None,
            "thesis_id": None,
            "current_weight": current_weight,
            "target_weight": target_weight,
            "delta_weight": delta,
            "recommendation": {
                "source": "portfolio_targets",
                "action": action,
                "objective": targets.get("objective"),
                "execution_protocol": targets.get("execution_protocol"),
                "order_instruction": "NONE",
                "research_only": True,
            },
        })
    return rows


def build_risk_decisions(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    risk = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    run_id = str(risk.get("run_id") or "risk-model")
    breaches = risk.get("constraint_breaches") if isinstance(risk.get("constraint_breaches"), list) else []
    rows: List[Dict[str, Any]] = []
    for breach in breaches:
        if not isinstance(breach, dict):
            continue
        ticker = str(breach.get("ticker") or "").upper() or None
        sector = breach.get("sector")
        breach_key = ticker or sector or breach.get("type")
        priority = "P1" if str(breach.get("type")) == "max_theme_weight" else "P2"
        rows.append({
            "decision_id": safe_id("CDJ", run_id, "BREACH", breach.get("type"), breach_key),
            "source_run_id": run_id,
            "decision_type": "RISK_BREACH_REVIEW",
            "status": "RESEARCH_PENDING_CIO_REVIEW",
            "priority": priority,
            "ticker": ticker,
            "thesis_id": None,
            "current_weight": sf(breach.get("value")),
            "target_weight": sf(breach.get("limit")),
            "delta_weight": sf(breach.get("limit")) - sf(breach.get("value")),
            "recommendation": {
                "source": "risk_model",
                "breach": breach,
                "portfolio_var": risk.get("historical_var"),
                "execution_protocol": risk.get("execution_protocol"),
                "order_instruction": "NONE",
                "research_only": True,
            },
        })

    portfolio_value = sf(risk.get("portfolio_value"))
    var_95 = sf(((risk.get("historical_var") or {}).get("confidence_95") or {}).get("daily_dollars"))
    if portfolio_value > 0 and var_95 / portfolio_value >= 0.05:
        rows.append({
            "decision_id": safe_id("CDJ", run_id, "VAR95", "PORTFOLIO"),
            "source_run_id": run_id,
            "decision_type": "PORTFOLIO_VAR_REVIEW",
            "status": "RESEARCH_PENDING_CIO_REVIEW",
            "priority": "P1",
            "ticker": None,
            "thesis_id": None,
            "current_weight": var_95 / portfolio_value,
            "target_weight": 0.05,
            "delta_weight": 0.05 - (var_95 / portfolio_value),
            "recommendation": {
                "source": "risk_model",
                "reason": "Daily VaR95 exceeds 5% of total assets.",
                "portfolio_value": portfolio_value,
                "var_95_daily_dollars": var_95,
                "var_95_daily_pct_of_assets": var_95 / portfolio_value,
                "order_instruction": "NONE",
                "research_only": True,
            },
        })
    return rows


def insert_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    sys.path.insert(0, str(PROJECT_ROOT))

    from dotenv import load_dotenv
    from core.db import close_cycle_conn, get_connection, write_raw_signal
    from mid.institutional_upgrade_tables import create_tables

    load_dotenv(PROJECT_ROOT / ".env")
    create_tables()
    now = datetime.now()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        for row in rows:
            cur.execute(
                """
                INSERT INTO cio_decision_journal (
                    decision_id, decision_ts, source_run_id, decision_type, status,
                    priority, ticker, thesis_id, current_weight, target_weight,
                    delta_weight, research_recommendation_json, execution_authority,
                    order_generated
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON),%s,%s)
                ON DUPLICATE KEY UPDATE
                    source_run_id = VALUES(source_run_id),
                    decision_type = VALUES(decision_type),
                    status = IF(cio_decision IS NULL, VALUES(status), status),
                    priority = VALUES(priority),
                    current_weight = VALUES(current_weight),
                    target_weight = VALUES(target_weight),
                    delta_weight = VALUES(delta_weight),
                    research_recommendation_json = VALUES(research_recommendation_json),
                    execution_authority = VALUES(execution_authority),
                    order_generated = order_generated
                """,
                (
                    row["decision_id"],
                    now,
                    row.get("source_run_id"),
                    row["decision_type"],
                    row["status"],
                    row["priority"],
                    row.get("ticker"),
                    row.get("thesis_id"),
                    row.get("current_weight"),
                    row.get("target_weight"),
                    row.get("delta_weight"),
                    json_dumps(row.get("recommendation", {})),
                    "CIO_ONLY_MANUAL",
                    False,
                ),
            )
        conn.commit()
        cur.execute(
            """
            SELECT decision_id, decision_ts, source_run_id, decision_type, status,
                   priority, ticker, thesis_id, current_weight, target_weight,
                   delta_weight, cio_decision, execution_authority, order_generated,
                   updated_at
            FROM cio_decision_journal
            ORDER BY decision_ts DESC, priority ASC, id DESC
            LIMIT 100
            """
        )
        latest = cur.fetchall()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary = {
        "status": "operational",
        "generated_at": now.isoformat(sep=" ", timespec="seconds"),
        "source": "seed_cio_decision_journal.py",
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_generation_enabled": False,
        "rows_seeded": len(rows),
        "pending_review_count": sum(1 for r in latest if str(r.get("status") or "").startswith("RESEARCH_PENDING")),
        "latest_decisions": json_safe(latest),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        write_raw_signal(
            source="CIO_Decision_Journal",
            ingestion_method="research_only_decision_journal",
            raw_payload=summary,
            raw_text=(
                f"CIO decision journal seeded: {summary['rows_seeded']} rows | "
                f"pending {summary['pending_review_count']} | no orders generated"
            ),
            signal_type="governance",
            suspected_category="CIO_RESEARCH_DECISION_LEDGER",
            suspected_entities=[r.get("ticker") for r in rows if r.get("ticker")],
            suspected_impact="medium",
            quality_score=1.0,
            quality_flags={
                "cio_only_manual": True,
                "order_generation_enabled": False,
                "orders_generated": False,
            },
        )
    finally:
        close_cycle_conn()
    return summary


def run(dataset_path: Path) -> Dict[str, Any]:
    dataset = load_dataset(dataset_path)
    rows = build_target_decisions(dataset) + build_risk_decisions(dataset)
    return insert_rows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed research-only CIO decision journal")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()

    summary = run(args.dataset)
    print("CIO decision journal seeded.")
    print(f"Rows seeded   : {summary['rows_seeded']}")
    print(f"Pending review: {summary['pending_review_count']}")
    print("Orders        : none generated")


if __name__ == "__main__":
    main()

