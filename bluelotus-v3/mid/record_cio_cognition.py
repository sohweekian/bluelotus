#!/usr/bin/env python3
"""
BlueLotus MID -- CIO cognition journal recorder.

Records CIO Strategic Thinking / Planning / Execution intent into MySQL and
exports a latest JSON snapshot. This is a cognition and governance layer only:
it never calls broker APIs and never creates, modifies, cancels, or routes
orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_NOTES_FILE = PROJECT_ROOT / "data" / "cio" / "cio_cognition_manual_latest.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "cio" / "cio_cognition_latest.json"

AUTHOR = "CIO"
PLATFORM_TEAM = "Codex & Claude Code Windows Platform Team"


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


def sf(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def clean_text(value: Any, max_len: int = 800) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def safe_id(*parts: Any, max_len: int = 92) -> str:
    text = "-".join(str(p or "") for p in parts)
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return text[:max_len]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("dataset_raw.json must be a JSON object")
    return data


def load_manual_notes(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def get_connection():
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection as _get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    return _get_connection()


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def active_flags(dataset: Dict[str, Any]) -> List[str]:
    cm = dataset.get("cross_market_confirmation") if isinstance(dataset.get("cross_market_confirmation"), dict) else {}
    flags = cm.get("interpretation_flags") if isinstance(cm.get("interpretation_flags"), dict) else {}
    return sorted(str(k) for k, v in flags.items() if v)


def top_theses(dataset: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    tl = dataset.get("thesis_lifecycle") if isinstance(dataset.get("thesis_lifecycle"), dict) else {}
    theses = tl.get("theses") if isinstance(tl.get("theses"), list) else []
    rows = [r for r in theses if isinstance(r, dict)]
    rows.sort(key=lambda r: (str(r.get("priority") or "P9"), -(sf(r.get("current_probability"), 0) or 0)))
    return rows[:limit]


def pending_decisions(dataset: Dict[str, Any], limit: int = 12) -> List[Dict[str, Any]]:
    cdj = dataset.get("cio_decisions") if isinstance(dataset.get("cio_decisions"), dict) else {}
    rows = cdj.get("decisions") if isinstance(cdj.get("decisions"), list) else []
    out = [r for r in rows if isinstance(r, dict)]
    out.sort(key=lambda r: (str(r.get("priority") or "P9"), str(r.get("decision_type") or ""), str(r.get("ticker") or "")))
    return out[:limit]


def build_key_risks(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    risk = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    for breach in risk.get("constraint_breaches") or []:
        if isinstance(breach, dict):
            risks.append({"source": "risk_model.constraint_breaches", **breach})
    execution = dataset.get("execution") if isinstance(dataset.get("execution"), dict) else {}
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    open_orders = orders.get("open_orders") if isinstance(orders.get("open_orders"), list) else []
    if open_orders:
        risks.append({
            "source": "orders.open_orders",
            "risk": "Open broker orders require CIO thesis review before market open.",
            "open_order_count": len(open_orders),
            "tickers": [str(r.get("ticker") or r.get("code") or "").replace("US.", "") for r in open_orders if isinstance(r, dict)],
        })
    if execution.get("order_routing_enabled"):
        risks.append({"source": "execution", "risk": "Order routing unexpectedly enabled", "severity": "CRITICAL"})
    return risks[:20]


def default_strategic_thinking(dataset: Dict[str, Any]) -> str:
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    flags = active_flags(dataset)
    thesis_names = [str(t.get("thesis_id") or t.get("thesis_name") or "") for t in top_theses(dataset, 5)]
    return clean_text(
        "CIO cognition capture: interpret current regime, thesis status, and forecast confidence before any capital decision. "
        f"Regime is {regime.get('regime') or regime.get('regime_short') or 'UNKNOWN'} with action {regime.get('action') or 'UNKNOWN'}. "
        f"Active cross-market flags: {', '.join(flags) if flags else 'none'}. "
        f"Primary theses requiring judgment: {', '.join(thesis_names) if thesis_names else 'none exported'}. "
        "Objective is to separate repeatable edge from lucky correctness and to record why wrong theses could lead to wrong CIO decisions.",
        1600,
    )


def default_planning(dataset: Dict[str, Any]) -> str:
    decisions = pending_decisions(dataset, 8)
    decision_text = ", ".join(
        f"{d.get('decision_type')}:{d.get('ticker') or 'PORT'}:{d.get('priority')}"
        for d in decisions
    )
    return clean_text(
        "Planning discipline: review pending CIO decision prompts, check thesis contradictions, verify kill conditions, and decide whether the correct action is HOLD, WAIT, reduce risk, cancel stale intent, or continue observation. "
        f"Pending decision queue sample: {decision_text if decision_text else 'none'}. "
        "All planning remains research and governance only until the CIO manually acts outside this system.",
        1600,
    )


def default_execution_intent(dataset: Dict[str, Any]) -> str:
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    return clean_text(
        f"Execution intent is CIO_ONLY_MANUAL. Pipeline generated orders: NO. Broker order routing: DISABLED. Open broker orders visible for review: {orders.get('open_order_count', 0)}. "
        "Any live order change, cancellation, or new trade must be performed manually by the CIO after reviewing thesis, risk, and planning notes.",
        1200,
    )


def build_follow_up(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    follow_up = []
    for thesis in top_theses(dataset, 6):
        follow_up.append({
            "type": "THESIS_REVIEW",
            "thesis_id": thesis.get("thesis_id"),
            "status": thesis.get("status"),
            "question": "Is this thesis repeatable edge, lucky correctness, wrong but explainable, or wrong and dangerous?",
        })
    for decision in pending_decisions(dataset, 6):
        follow_up.append({
            "type": "CIO_DECISION_REVIEW",
            "decision_id": decision.get("decision_id"),
            "ticker": decision.get("ticker"),
            "decision_type": decision.get("decision_type"),
            "question": "Should CIO accept, defer, reject, or mark this recommendation as contradicted by thesis?",
        })
    return follow_up


def build_journal(dataset: Dict[str, Any], dataset_path: Path, manual: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    archive = dataset.get("report_archive") if isinstance(dataset.get("report_archive"), dict) else {}
    iq = dataset.get("institutional_quant") if isinstance(dataset.get("institutional_quant"), dict) else {}
    dataset_sha = sha256_file(dataset_path)
    generated = meta.get("generated_at") or datetime.now().isoformat(timespec="seconds")
    journal_id = manual.get("journal_id") or safe_id("CIOCOG", str(generated)[:19], dataset_sha[:12])
    now = datetime.now()

    linked_theses = [
        {
            "thesis_id": t.get("thesis_id"),
            "thesis_name": t.get("thesis_name"),
            "status": t.get("status"),
            "priority": t.get("priority"),
            "probability": t.get("current_probability"),
            "confidence": t.get("confidence"),
        }
        for t in top_theses(dataset, 10)
    ]
    linked_decisions = [
        {
            "decision_id": d.get("decision_id"),
            "decision_type": d.get("decision_type"),
            "priority": d.get("priority"),
            "ticker": d.get("ticker"),
            "status": d.get("status"),
        }
        for d in pending_decisions(dataset, 20)
    ]

    entry = {
        "journal_id": journal_id,
        "journal_ts": manual.get("journal_ts") or now.isoformat(sep=" ", timespec="seconds"),
        "source_cycle_ts": generated,
        "source_report_archive_id": archive.get("id") or archive.get("archive_id"),
        "source_dataset_sha256": dataset_sha,
        "entry_type": manual.get("entry_type") or "CIO_DAILY_REVIEW",
        "status": manual.get("status") or "RECORDED",
        "priority": manual.get("priority") or ("P1" if regime.get("regime") == "RISK OFF" else "P2"),
        "regime": regime.get("regime") or regime.get("regime_short"),
        "cio_action": manual.get("cio_action") or regime.get("action") or archive.get("cio_action"),
        "confidence": sf(manual.get("confidence"), sf(archive.get("confidence"), None)),
        "strategic_thinking": manual.get("strategic_thinking") or default_strategic_thinking(dataset),
        "planning": manual.get("planning") or default_planning(dataset),
        "execution_intent": manual.get("execution_intent") or default_execution_intent(dataset),
        "non_execution_rationale": manual.get("non_execution_rationale") or "No automated execution. This record exists to preserve CIO reasoning, not to route capital.",
        "key_risks": manual.get("key_risks") or build_key_risks(dataset),
        "evidence_refs": manual.get("evidence_refs") or {
            "dataset_generated_at": generated,
            "dataset_sha256": dataset_sha,
            "quant_readiness": iq.get("readiness_score"),
            "quant_label": iq.get("readiness_label"),
            "active_flags": active_flags(dataset),
            "report_archive_id": archive.get("id") or archive.get("archive_id"),
        },
        "linked_theses": manual.get("linked_theses") or linked_theses,
        "linked_decisions": manual.get("linked_decisions") or linked_decisions,
        "follow_up": manual.get("follow_up") or build_follow_up(dataset),
        "author": manual.get("author") or AUTHOR,
        "platform_team": PLATFORM_TEAM,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_generated": False,
    }
    return entry


def assessment_from_thesis(thesis: Dict[str, Any]) -> str:
    status = str(thesis.get("status") or "").upper()
    prob = sf(thesis.get("current_probability"), 0) or 0
    if status == "CONFIRMED" and prob >= 0.62:
        return "EDGE_CANDIDATE_REVIEW"
    if status == "CONTRADICTED":
        return "MISTAKE_REVIEW"
    return "WATCH"


def build_thesis_reviews(journal: Dict[str, Any], dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews = []
    for thesis in top_theses(dataset, 12):
        tid = str(thesis.get("thesis_id") or "")
        if not tid:
            continue
        review_id = safe_id("CIOTR", journal["journal_id"], tid, max_len=124)
        reviews.append({
            "review_id": review_id,
            "journal_id": journal["journal_id"],
            "thesis_id": tid,
            "review_ts": journal["journal_ts"],
            "status_at_review": thesis.get("status"),
            "probability_at_review": thesis.get("current_probability"),
            "confidence_at_review": thesis.get("confidence"),
            "cio_assessment": assessment_from_thesis(thesis),
            "strategic_note": (
                "Check whether this thesis has repeatable edge across future cycles, not merely one correct print."
            ),
            "planning_note": (
                "Track evidence, contradiction, kill condition, and future Brier/outcome linkage before increasing trust."
            ),
            "execution_note": "No execution generated. Any action remains CIO manual.",
            "kill_condition_review": thesis.get("kill_condition"),
            "repeatability_hypothesis": (
                "Repeatability requires similar regime, similar signal pattern, and repeated outcome confirmation."
            ),
            "mistake_risk": (
                "If confidence rises faster than resolved evidence, this thesis can lead to a wrong CIO decision."
            ),
            "evidence": thesis.get("evidence") or [],
            "contradictions": thesis.get("contradictions") or [],
            "follow_up": [
                "Classify after outcome: correct-repeatable, correct-lucky, wrong-explainable, wrong-dangerous.",
                "Link matured forecasts/Brier results when available.",
            ],
            "author": journal.get("author") or AUTHOR,
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_generated": False,
        })
    return reviews


def insert_database(journal: Dict[str, Any], reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    ensure_tables()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO cio_cognition_journal (
                journal_id, journal_ts, source_cycle_ts, source_report_archive_id,
                source_dataset_sha256, entry_type, status, priority, regime,
                cio_action, confidence, strategic_thinking, planning,
                execution_intent, non_execution_rationale, key_risks_json,
                evidence_refs_json, linked_theses_json, linked_decisions_json,
                follow_up_json, author, execution_authority, order_generated
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                CAST(%s AS JSON),CAST(%s AS JSON),%s,%s,%s
            )
            ON DUPLICATE KEY UPDATE
                journal_ts = VALUES(journal_ts),
                source_cycle_ts = VALUES(source_cycle_ts),
                source_report_archive_id = VALUES(source_report_archive_id),
                source_dataset_sha256 = VALUES(source_dataset_sha256),
                entry_type = VALUES(entry_type),
                status = VALUES(status),
                priority = VALUES(priority),
                regime = VALUES(regime),
                cio_action = VALUES(cio_action),
                confidence = VALUES(confidence),
                strategic_thinking = VALUES(strategic_thinking),
                planning = VALUES(planning),
                execution_intent = VALUES(execution_intent),
                non_execution_rationale = VALUES(non_execution_rationale),
                key_risks_json = VALUES(key_risks_json),
                evidence_refs_json = VALUES(evidence_refs_json),
                linked_theses_json = VALUES(linked_theses_json),
                linked_decisions_json = VALUES(linked_decisions_json),
                follow_up_json = VALUES(follow_up_json),
                author = VALUES(author),
                execution_authority = VALUES(execution_authority),
                order_generated = FALSE
            """,
            (
                journal["journal_id"],
                journal["journal_ts"],
                journal.get("source_cycle_ts"),
                journal.get("source_report_archive_id"),
                journal.get("source_dataset_sha256"),
                journal.get("entry_type"),
                journal.get("status"),
                journal.get("priority"),
                journal.get("regime"),
                journal.get("cio_action"),
                journal.get("confidence"),
                journal.get("strategic_thinking"),
                journal.get("planning"),
                journal.get("execution_intent"),
                journal.get("non_execution_rationale"),
                json_dumps(journal.get("key_risks") or []),
                json_dumps(journal.get("evidence_refs") or {}),
                json_dumps(journal.get("linked_theses") or []),
                json_dumps(journal.get("linked_decisions") or []),
                json_dumps(journal.get("follow_up") or []),
                journal.get("author") or AUTHOR,
                "CIO_ONLY_MANUAL",
                False,
            ),
        )

        for review in reviews:
            cur.execute(
                """
                INSERT INTO cio_thesis_reviews (
                    review_id, journal_id, thesis_id, review_ts, status_at_review,
                    probability_at_review, confidence_at_review, cio_assessment,
                    strategic_note, planning_note, execution_note, kill_condition_review,
                    repeatability_hypothesis, mistake_risk, evidence_json,
                    contradiction_json, follow_up_json, author, execution_authority,
                    order_generated
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),%s,%s,%s
                )
                ON DUPLICATE KEY UPDATE
                    review_ts = VALUES(review_ts),
                    status_at_review = VALUES(status_at_review),
                    probability_at_review = VALUES(probability_at_review),
                    confidence_at_review = VALUES(confidence_at_review),
                    cio_assessment = VALUES(cio_assessment),
                    strategic_note = VALUES(strategic_note),
                    planning_note = VALUES(planning_note),
                    execution_note = VALUES(execution_note),
                    kill_condition_review = VALUES(kill_condition_review),
                    repeatability_hypothesis = VALUES(repeatability_hypothesis),
                    mistake_risk = VALUES(mistake_risk),
                    evidence_json = VALUES(evidence_json),
                    contradiction_json = VALUES(contradiction_json),
                    follow_up_json = VALUES(follow_up_json),
                    author = VALUES(author),
                    execution_authority = VALUES(execution_authority),
                    order_generated = FALSE
                """,
                (
                    review["review_id"],
                    review["journal_id"],
                    review["thesis_id"],
                    review["review_ts"],
                    review.get("status_at_review"),
                    review.get("probability_at_review"),
                    review.get("confidence_at_review"),
                    review.get("cio_assessment"),
                    review.get("strategic_note"),
                    review.get("planning_note"),
                    review.get("execution_note"),
                    review.get("kill_condition_review"),
                    review.get("repeatability_hypothesis"),
                    review.get("mistake_risk"),
                    json_dumps(review.get("evidence") or []),
                    json_dumps(review.get("contradictions") or []),
                    json_dumps(review.get("follow_up") or []),
                    review.get("author") or AUTHOR,
                    "CIO_ONLY_MANUAL",
                    False,
                ),
            )

        conn.commit()
        cur.execute(
            """
            SELECT journal_id, journal_ts, source_cycle_ts, source_report_archive_id,
                   source_dataset_sha256, entry_type, status, priority, regime,
                   cio_action, confidence, strategic_thinking, planning,
                   execution_intent, non_execution_rationale, key_risks_json,
                   evidence_refs_json, linked_theses_json, linked_decisions_json,
                   follow_up_json, author, execution_authority, order_generated,
                   created_at, updated_at
            FROM cio_cognition_journal
            ORDER BY journal_ts DESC, id DESC
            LIMIT 20
            """
        )
        journal_rows = cur.fetchall()
        cur.execute(
            """
            SELECT review_id, journal_id, thesis_id, review_ts, status_at_review,
                   probability_at_review, confidence_at_review, cio_assessment,
                   strategic_note, planning_note, execution_note, kill_condition_review,
                   repeatability_hypothesis, mistake_risk, evidence_json,
                   contradiction_json, follow_up_json, author, execution_authority,
                   order_generated, updated_at
            FROM cio_thesis_reviews
            WHERE journal_id = %s
            ORDER BY thesis_id
            """,
            (journal["journal_id"],),
        )
        review_rows = cur.fetchall()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for row in journal_rows:
        for key in ("key_risks_json", "evidence_refs_json", "linked_theses_json", "linked_decisions_json", "follow_up_json"):
            if key in row:
                new_key = key.replace("_json", "")
                try:
                    row[new_key] = json.loads(row.pop(key) or "null")
                except Exception:
                    row[new_key] = row.pop(key)
    for row in review_rows:
        for key in ("evidence_json", "contradiction_json", "follow_up_json"):
            if key in row:
                new_key = "contradictions" if key == "contradiction_json" else key.replace("_json", "")
                try:
                    row[new_key] = json.loads(row.pop(key) or "null")
                except Exception:
                    row[new_key] = row.pop(key)

    return {
        "status": "operational",
        "version": "v1.0",
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "source": "record_cio_cognition.py",
        "platform_team": PLATFORM_TEAM,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_generation_enabled": False,
        "orders_generated": 0,
        "journal_id": journal["journal_id"],
        "review_count": len(reviews),
        "latest_journals": json_safe(journal_rows),
        "latest_thesis_reviews": json_safe(review_rows),
        "doctrine": "CIO cognition ledger only. It records thinking, planning, execution intent, thesis reviews, and mistake-learning prompts. It never routes broker orders.",
    }


def write_raw_signal(summary: Dict[str, Any]) -> None:
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from core.db import write_raw_signal

        write_raw_signal(
            source="CIO_Cognition_Journal",
            ingestion_method="cio_cognition_record",
            raw_payload=summary,
            raw_text=(
                f"CIO cognition journal recorded: {summary.get('journal_id')} | "
                f"thesis reviews {summary.get('review_count')} | no orders generated"
            ),
            signal_type="CIO_COGNITION_RECORD",
        )
    except Exception:
        # Raw signal archive is useful but not mandatory for the journal itself.
        return


def main() -> None:
    ap = argparse.ArgumentParser(description="Record CIO strategic thinking / planning / execution cognition ledger")
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--notes-file", type=Path, default=DEFAULT_NOTES_FILE)
    ap.add_argument("--strategic-thinking", default="")
    ap.add_argument("--planning", default="")
    ap.add_argument("--execution-intent", default="")
    ap.add_argument("--non-execution-rationale", default="")
    ap.add_argument("--author", default=AUTHOR)
    args = ap.parse_args()

    dataset = load_dataset(args.dataset)
    manual = load_manual_notes(args.notes_file)
    if args.strategic_thinking:
        manual["strategic_thinking"] = args.strategic_thinking
    if args.planning:
        manual["planning"] = args.planning
    if args.execution_intent:
        manual["execution_intent"] = args.execution_intent
    if args.non_execution_rationale:
        manual["non_execution_rationale"] = args.non_execution_rationale
    if args.author:
        manual["author"] = args.author

    journal = build_journal(dataset, args.dataset, manual)
    reviews = build_thesis_reviews(journal, dataset)
    summary = insert_database(journal, reviews)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(summary), indent=2, ensure_ascii=False), encoding="utf-8")
    write_raw_signal(summary)
    print("CIO cognition journal recorded.")
    print(f"Journal ID : {summary.get('journal_id')}")
    print(f"Reviews    : {summary.get('review_count')}")
    print(f"Output     : {OUTPUT_PATH}")
    print("Doctrine   : CIO_ONLY_MANUAL; no broker order calls.")


if __name__ == "__main__":
    main()

