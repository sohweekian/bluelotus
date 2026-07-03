from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from zoneinfo import ZoneInfo

from llm_clients.config_loader import resolve_project_path


ADD_KEYWORDS = ("ADD", "BUY", "SCALE", "TRANCHE", "INCREASE")
REDUCE_KEYWORDS = ("REDUCE", "NO_ADD", "NO ADD", "BLOCK", "WAIT", "HOLD")
GOLD_TICKERS = {"AU", "NEM", "AEM", "B", "GLD", "GDX", "GDXJ"}


def build_contradiction_governance(
    cycle_context: Dict[str, Any],
    reports: List[Dict[str, Any]],
    briefing: Dict[str, Any],
    quality_summary: Dict[str, Any],
    agent_errors: List[Dict[str, Any]] | None = None,
    public_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build deterministic contradiction register and CIO decision strip."""
    cycle_id = str(cycle_context.get("cycle_id", "unknown"))
    created_at_sgt = sgt_now()
    operator_pack = cycle_context.get("operator_verdict_pack", {}) if isinstance(cycle_context.get("operator_verdict_pack"), dict) else {}
    operator_full = load_json_from_summary(operator_pack.get("source_summary", {}))
    dataset = load_json_from_summary(cycle_context.get("dataset_summary", {}))
    agent_errors = agent_errors or []

    blocked_actions = sorted(collect_blocked_actions(operator_pack, operator_full))
    allowed_actions = sorted(collect_allowed_actions(operator_pack, operator_full, reports))

    contradictions: List[Dict[str, Any]] = []
    add_contradictions(contradictions, rule_add_conflicts_with_block(cycle_id, blocked_actions, reports))
    add_contradictions(contradictions, rule_thesis_order_conflict(cycle_id, blocked_actions, dataset, reports, operator_full))
    add_contradictions(contradictions, rule_policy_concentration_conflict(cycle_id, dataset, operator_full))
    add_contradictions(contradictions, rule_degraded_posture_conflict(cycle_id, briefing, reports, agent_errors))
    add_contradictions(contradictions, rule_dashboard_freshness_conflict(cycle_id, public_state))
    add_contradictions(contradictions, rule_weak_agent_quality(cycle_id, quality_summary))

    register = {
        "schema_version": "bluelotus_v3_contradiction_register_v1.0",
        "cycle_id": cycle_id,
        "created_at_sgt": created_at_sgt,
        "contradiction_count": len(contradictions),
        "p1_count": sum(1 for item in contradictions if item.get("severity") == "P1"),
        "p2_count": sum(1 for item in contradictions if item.get("severity") == "P2"),
        "p3_count": sum(1 for item in contradictions if item.get("severity") == "P3"),
        "contradictions": contradictions,
        "manual_execution_required": True,
        "llm_order_generation": False,
        "order_routing_enabled": False,
    }
    decision_strip = build_cio_decision_strip(cycle_id, briefing, blocked_actions, allowed_actions, contradictions, created_at_sgt)
    return {
        "contradiction_register": register,
        "cio_decision_strip": decision_strip,
    }


def write_contradiction_governance(cycle_dir: Path, governance_payload: Dict[str, Any]) -> Dict[str, str]:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    governance_dir = cycle_dir / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    latest_dir = resolve_project_path("data/governance")
    latest_dir.mkdir(parents=True, exist_ok=True)

    register = governance_payload["contradiction_register"]
    strip = governance_payload["cio_decision_strip"]
    cycle_register = governance_dir / "contradiction_register.json"
    cycle_strip = governance_dir / "cio_decision_strip.json"
    latest_register = latest_dir / "contradiction_register_latest.json"
    latest_strip = latest_dir / "cio_decision_strip_latest.json"
    write_json(cycle_register, register)
    write_json(cycle_strip, strip)
    write_json(latest_register, register)
    write_json(latest_strip, strip)
    return {
        "cycle_contradiction_register": str(cycle_register),
        "cycle_cio_decision_strip": str(cycle_strip),
        "latest_contradiction_register": str(latest_register),
        "latest_cio_decision_strip": str(latest_strip),
    }


def build_cio_decision_strip(
    cycle_id: str,
    briefing: Dict[str, Any],
    blocked_actions: List[str],
    allowed_actions: List[str],
    contradictions: List[Dict[str, Any]],
    created_at_sgt: str,
) -> Dict[str, Any]:
    p1 = [item for item in contradictions if item.get("severity") == "P1"]
    p2 = [item for item in contradictions if item.get("severity") == "P2"]
    required = []
    for item in contradictions:
        if item.get("cio_attention_required"):
            required.append(str(item.get("conflict_statement", "")))
    posture = str(briefing.get("recommended_posture") or "REVIEW")
    if p1:
        posture = "CIO_VERIFICATION_REQUIRED"
    elif p2 and posture in {"WAIT", "HOLD"}:
        posture = "REVIEW"
    return {
        "schema_version": "bluelotus_v3_cio_decision_strip_v1.0",
        "cycle_id": cycle_id,
        "created_at_sgt": created_at_sgt,
        "posture": posture,
        "new_information": summarize_new_information(briefing, contradictions),
        "action_blocked": blocked_actions[:12],
        "action_permitted": allowed_actions[:12],
        "cio_decision_required": required[:8] if required else ["No contradiction-triggered CIO decision required."],
        "manual_execution_required": True,
        "llm_order_generation": False,
        "order_routing_enabled": False,
    }


def rule_add_conflicts_with_block(cycle_id: str, blocked_actions: List[str], reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not any(contains_any(action, ADD_KEYWORDS) for action in blocked_actions):
        return []
    findings = []
    for report in reports:
        observed = stringify_list(report.get("allowed_actions_observed", []))
        recommendation = str(report.get("recommendation_to_chief_strategist", ""))
        text = " ".join(observed + [recommendation])
        if contains_any(text, ADD_KEYWORDS):
            findings.append(contradiction(
                cycle_id,
                "P1",
                "execution_governance",
                "deterministic_operator_blocks",
                f"agent:{report.get('agent_id')}",
                "Agent allowed/recommended add-like action while deterministic operators contain add/scale/tranche blocks.",
                "Preserve deterministic block; CIO must manually review before any add-like exposure.",
            ))
    return findings


def rule_thesis_order_conflict(
    cycle_id: str,
    blocked_actions: List[str],
    dataset: Dict[str, Any],
    reports: List[Dict[str, Any]],
    operator_full: Dict[str, Any],
) -> List[Dict[str, Any]]:
    out = []
    orders = dataset.get("orders", {}) if isinstance(dataset.get("orders"), dict) else {}
    open_order_count = int_safe(orders.get("open_order_count"))
    order_text = json.dumps(orders, ensure_ascii=False, default=str)
    gold_blocked = "INCREASE_GOLD_THESIS_RISK" in blocked_actions or operator_blocked(operator_full, "gold_thesis", "INCREASE_GOLD_THESIS_RISK")
    if gold_blocked and open_order_count > 0 and any(ticker in order_text for ticker in GOLD_TICKERS):
        out.append(contradiction(
            cycle_id,
            "P1",
            "thesis_vs_order_book",
            "gold_thesis_operator",
            "moomoo_readonly_orders",
            "Gold thesis risk increase is blocked while open order book contains gold/miner-linked tickers.",
            "CIO must verify whether open orders are intentional support bids, stale orders, or should be cancelled.",
        ))
    for report in reports:
        affected = set(stringify_list(report.get("affected_assets", [])))
        observed = " ".join(stringify_list(report.get("allowed_actions_observed", [])) + stringify_list(report.get("blocked_actions_observed", [])))
        if affected.intersection(GOLD_TICKERS) and contains_any(observed, ADD_KEYWORDS) and gold_blocked:
            out.append(contradiction(
                cycle_id,
                "P2",
                "agent_vs_thesis",
                "gold_thesis_operator",
                f"agent:{report.get('agent_id')}",
                "Agent mentions gold/miner add-like action while gold thesis increase is blocked.",
                "Chief Strategist should surface gold/miner action as CIO-only review, not permitted action.",
            ))
    return out


def rule_policy_concentration_conflict(cycle_id: str, dataset: Dict[str, Any], operator_full: Dict[str, Any]) -> List[Dict[str, Any]]:
    risk = dataset.get("risk_metrics", {}) if isinstance(dataset.get("risk_metrics"), dict) else {}
    breaches = risk.get("constraint_breaches", [])
    largest = risk.get("largest_position", {}) if isinstance(risk.get("largest_position"), dict) else {}
    concentration_blocked = any("CONCENTRATION" in str(action).upper() for action in collect_blocked_actions({}, operator_full))
    has_breach = bool(breaches) or concentration_blocked
    if not has_breach:
        return []
    ticker = str(largest.get("ticker", "largest_position"))
    return [contradiction(
        cycle_id,
        "P2",
        "portfolio_policy_vs_risk",
        "portfolio_mandates",
        "risk_metrics",
        f"Portfolio policy/mandate must be reconciled with concentration warning for {ticker}.",
        "Use CIO policy as intent, but require explicit concentration acknowledgement before scaling.",
    )]


def rule_degraded_posture_conflict(
    cycle_id: str,
    briefing: Dict[str, Any],
    reports: List[Dict[str, Any]],
    agent_errors: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not agent_errors:
        return []
    posture = str(briefing.get("recommended_posture", ""))
    if posture not in {"CIO_VERIFICATION_REQUIRED", "REVIEW", "REDUCE_RISK_REVIEW", "RAISE_CASH_REVIEW", "HEDGE_REVIEW"}:
        return [contradiction(
            cycle_id,
            "P1",
            "agent_runtime_vs_report_posture",
            "agent_errors",
            "chief_strategist_briefing",
            "Agent council has runtime errors but Chief Strategist posture is not escalated to review.",
            "Escalate posture to CIO verification when current-cycle agent errors exist.",
        )]
    return [contradiction(
        cycle_id,
        "P3",
        "agent_runtime_observation",
        "agent_errors",
        "chief_strategist_briefing",
        "Agent council has runtime errors; posture is already review/escalated.",
        "Monitor Qwen runtime and preserve fallback/degraded labeling.",
        cio_attention_required=False,
    )]


def rule_dashboard_freshness_conflict(cycle_id: str, public_state: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not public_state:
        return []
    public_cycle = str(public_state.get("cycle_id", "")).strip()
    if public_cycle and public_cycle != cycle_id:
        return [contradiction(
            cycle_id,
            "P3",
            "publication_freshness",
            "latest_v3_cycle",
            "public_dashboard_state",
            f"Public dashboard cycle {public_cycle} differs from latest cycle {cycle_id}.",
            "Publish fresh artifacts or label dashboard as showing last valid cycle.",
            cio_attention_required=False,
        )]
    return []


def rule_weak_agent_quality(cycle_id: str, quality_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    failed_agents = stringify_list(quality_summary.get("failed_agents", []))
    if not failed_agents:
        return []
    return [contradiction(
        cycle_id,
        "P3",
        "agent_quality",
        "quality_scorer",
        "agent_council",
        "Agent JSON validated, but quality scorer flagged weak differentiated reasoning for: " + ", ".join(failed_agents[:8]),
        "Treat validated JSON as runtime success, not full reasoning success; use prompt/agent refinement backlog.",
        cio_attention_required=False,
    )]


def contradiction(
    cycle_id: str,
    severity: str,
    domain: str,
    source_a: str,
    source_b: str,
    conflict_statement: str,
    recommended_resolution_path: str,
    cio_attention_required: bool = True,
) -> Dict[str, Any]:
    base = f"{cycle_id}|{severity}|{domain}|{source_a}|{source_b}|{conflict_statement}"
    cid = re.sub(r"[^A-Z0-9]+", "_", base.upper()).strip("_")[:96]
    return {
        "contradiction_id": cid,
        "cycle_id": cycle_id,
        "severity": severity,
        "domain": domain,
        "source_a": source_a,
        "source_b": source_b,
        "conflict_statement": conflict_statement,
        "cio_attention_required": cio_attention_required,
        "recommended_resolution_path": recommended_resolution_path,
    }


def collect_blocked_actions(operator_pack: Dict[str, Any], operator_full: Dict[str, Any]) -> set[str]:
    out = set(stringify_list(operator_pack.get("blocked_actions", [])))
    summary = operator_full.get("summary", {}) if isinstance(operator_full.get("summary"), dict) else {}
    out.update(stringify_list(summary.get("blocked_actions", [])))
    operators = operator_full.get("operators", {}) if isinstance(operator_full.get("operators"), dict) else {}
    for op in operators.values():
        if isinstance(op, dict):
            out.update(stringify_list(op.get("blocked_actions", [])))
    return {item for item in out if item}


def collect_allowed_actions(operator_pack: Dict[str, Any], operator_full: Dict[str, Any], reports: List[Dict[str, Any]]) -> set[str]:
    out = set(stringify_list(operator_pack.get("allowed_actions", [])))
    out.update(stringify_list(operator_full.get("allowed_actions", [])))
    for report in reports:
        out.update(stringify_list(report.get("allowed_actions_observed", [])))
    return {item for item in out if item} or {"WAIT", "HOLD", "REVIEW"}


def operator_blocked(operator_full: Dict[str, Any], operator_name: str, action: str) -> bool:
    operators = operator_full.get("operators", {}) if isinstance(operator_full.get("operators"), dict) else {}
    op = operators.get(operator_name, {}) if isinstance(operators.get(operator_name), dict) else {}
    return action in stringify_list(op.get("blocked_actions", []))


def summarize_new_information(briefing: Dict[str, Any], contradictions: List[Dict[str, Any]]) -> List[str]:
    out = []
    summary = str(briefing.get("summary", "")).strip()
    if summary:
        out.append(summary[:500])
    if contradictions:
        out.append(f"{len(contradictions)} contradiction governance item(s) detected.")
    else:
        out.append("No contradiction governance items detected.")
    return out


def add_contradictions(target: List[Dict[str, Any]], items: Iterable[Dict[str, Any]]) -> None:
    seen = {item.get("contradiction_id") for item in target}
    for item in items:
        cid = item.get("contradiction_id")
        if cid not in seen:
            target.append(item)
            seen.add(cid)


def load_json_from_summary(summary: Any) -> Dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    path_text = str(summary.get("path", "")).strip()
    if path_text:
        path = Path(path_text)
        if path.exists():
            try:
                parsed = json.loads(path.read_text(encoding="utf-8-sig"))
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    excerpt = summary.get("excerpt")
    if isinstance(excerpt, str) and excerpt.strip():
        try:
            parsed = json.loads(excerpt)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def contains_any(text: Any, keywords: Tuple[str, ...]) -> bool:
    upper = str(text).upper()
    return any(keyword in upper for keyword in keywords)


def stringify_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def int_safe(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")

