from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from acms_cop.classifiers.signal_entropy_classifier import build_signal_entropy
from acms_cop.classifiers.source_capacity_tracker import build_source_capacity
from acms_cop.learning.cost_basis_reconciler import build_cost_basis_reconciliation
from acms_cop.learning.hedge_ratio_reviewer import build_hedge_ratio_review
from acms_cop.learning.kelly_edge_calculator import build_kelly_sizing_advisory


STR_VERSION = "str_v0.1"


def _sgt_now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S SGT")


def _apply_kelly_pei_fusion(dataset: Dict[str, Any], kelly: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pei = dataset.get("prospective_event_intelligence") if isinstance(dataset.get("prospective_event_intelligence"), dict) else {}
    pei_text = str(pei).upper()
    macro_gated = any(token in pei_text for token in ("WARSH", "BOJ", "ADD RISK", "BLOCKED", "MACRO"))
    macro_gated_tickers = {"PL", "QUBT", "LUNR", "QBTS"}
    for row in kelly:
        ticker = str(row.get("ticker") or "").upper()
        status = str(row.get("kelly_status") or "")
        if "HEDGE_INSTRUMENT_EXCLUDED" in status:
            fused = "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
        elif "INSUFFICIENT" in status:
            fused = "KELLY_INSUFFICIENT_DATA"
        elif "NO_SIZE" in status:
            fused = "KELLY_NO_SIZE"
        elif ticker in macro_gated_tickers and macro_gated:
            fused = "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED"
        elif "SUPPORTS" in status:
            fused = "KELLY_SUPPORTED_AND_MACRO_CLEAR"
        else:
            fused = "CIO_REVIEW_REQUIRED"
        row["kelly_pei_fused_status"] = fused
    return kelly


def str_governance_context(dataset: Dict[str, Any]) -> Dict[str, Any]:
    law = dataset.get("law_governance_binding") if isinstance(dataset.get("law_governance_binding"), dict) else {}
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    return {
        "run_id": str(meta.get("cycle_id") or meta.get("cycle_ts") or meta.get("generated_at") or _sgt_now_text()),
        "cycle_timestamp": str(meta.get("cycle_ts") or meta.get("generated_at") or _sgt_now_text()),
        "dataset_timestamp": str(meta.get("generated_at") or _sgt_now_text()),
        "report_binding_id": str(law.get("report_memory_binding_id") or law.get("binding_hash") or "UNBOUND"),
        "governance_pack_id": str(law.get("governance_pack_id") or "UNBOUND"),
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "created_at": _sgt_now_text(),
    }


def build_shannon_thorp_refinement(dataset: Dict[str, Any], persist: bool = False) -> Dict[str, Any]:
    governance = str_governance_context(dataset)
    signal_entropy = build_signal_entropy(dataset, governance)
    source_capacity = build_source_capacity(dataset, governance)
    cost_basis = build_cost_basis_reconciliation(dataset, governance)
    kelly = _apply_kelly_pei_fusion(dataset, build_kelly_sizing_advisory(dataset, governance))
    hedge = build_hedge_ratio_review(dataset, governance)
    summary = {
        **governance,
        "status": "OPERATIONAL",
        "version": STR_VERSION,
        "generated_at": _sgt_now_text(),
        "signal_entropy_count": len(signal_entropy),
        "source_capacity_count": len(source_capacity),
        "cost_basis_conflict_count": sum(1 for r in cost_basis if str(r.get("resolution_status", "")).startswith("UNRESOLVED")),
        "kelly_advisory_count": len(kelly),
        "hedge_status": hedge.get("hedge_status", "UNKNOWN"),
        "research_only": True,
        "advisory_only": True,
        "thesis_authority": "RESEARCH / PROPOSAL / PREPARATION ONLY",
    }
    return {
        **governance,
        "status": "OPERATIONAL",
        "version": STR_VERSION,
        "generated_at": summary["generated_at"],
        "governance_pack_id": governance["governance_pack_id"],
        "report_memory_binding_id": governance["report_binding_id"],
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "signal_entropy": signal_entropy,
        "source_capacity": source_capacity,
        "cost_basis_reconciliation": cost_basis,
        "kelly_sizing_advisory": kelly,
        "hedge_ratio_review": hedge,
        "brier_logging_status": "COLLECTING",
        "cycle_summary": summary,
        "doctrine": {
            "research_only": True,
            "no_order_generation": True,
            "no_broker_routing": True,
            "does_not_override_cio_only_manual": True,
            "thesis_statement": "It adds numbers beside existing labels; it does not execute.",
        },
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return ""
    return str(value)


def str_summary_rows(str_data: Dict[str, Any]) -> List[List[Any]]:
    summary = str_data.get("cycle_summary") if isinstance(str_data.get("cycle_summary"), dict) else {}
    return [
        ["Field", "Value"],
        ["Status", str_data.get("status", "MISSING")],
        ["Version", str_data.get("version", "")],
        ["Generated At", str_data.get("generated_at", "")],
        ["Governance Pack", str_data.get("governance_pack_id", "")],
        ["Report Binding", str_data.get("report_memory_binding_id", "")],
        ["Execution Authority", str_data.get("execution_authority", "CIO_ONLY_MANUAL")],
        ["Order Routing Enabled", str(str_data.get("order_routing_enabled", False))],
        ["System Orders Generated", str(str_data.get("system_orders_generated", 0))],
        ["Signal Entropy Records", summary.get("signal_entropy_count", 0)],
        ["Source Capacity Records", summary.get("source_capacity_count", 0)],
        ["Cost Basis Conflicts", summary.get("cost_basis_conflict_count", 0)],
        ["Kelly Advisory Records", summary.get("kelly_advisory_count", 0)],
        ["Hedge Status", summary.get("hedge_status", "")],
        ["Doctrine", "STR is research-only. It does not generate orders or route broker orders."],
    ]


def signal_entropy_rows(str_data: Dict[str, Any]) -> List[List[Any]]:
    rows = [["Ticker", "Old Label", "Entropy Raw", "Entropy Norm", "Category Count", "Clean Weight", "Dirty Weight", "Classification"]]
    for r in str_data.get("signal_entropy", [])[:80]:
        rows.append([
            r.get("ticker"), r.get("old_label"), r.get("signal_entropy_raw"), r.get("signal_entropy_normalized"),
            r.get("evidence_category_count"), r.get("clean_signal_weight"), r.get("dirty_signal_weight"), r.get("classification"),
        ])
    return rows


def source_capacity_rows(str_data: Dict[str, Any]) -> List[List[Any]]:
    rows = [["Source", "Tier", "Signals", "Confirmed", "Contradicted", "Unresolved", "Capacity", "Confidence", "Status"]]
    for r in str_data.get("source_capacity", [])[:80]:
        rows.append([
            r.get("source_name"), r.get("source_tier"), r.get("signal_count"), r.get("confirmed_count"),
            r.get("contradicted_count"), r.get("unresolved_count"), r.get("estimated_channel_capacity"),
            r.get("capacity_confidence"), r.get("status"),
        ])
    return rows


def cost_basis_rows(str_data: Dict[str, Any]) -> List[List[Any]]:
    rows = [["Ticker", "Broker P/L", "Computed P/L", "Third Witness", "Delta B-C", "Selected Source", "Status", "CIO Review"]]
    for r in str_data.get("cost_basis_reconciliation", []):
        rows.append([
            r.get("ticker"), r.get("broker_unrealized"), r.get("computed_unrealized"), r.get("third_witness_unrealized"),
            r.get("delta_broker_vs_computed"), r.get("selected_source"), r.get("resolution_status"), r.get("cio_review_required"),
        ])
    return rows


def kelly_rows(str_data: Dict[str, Any]) -> List[List[Any]]:
    rows = [[
        "Ticker", "Sleeve ID", "Sleeve Role", "Sleeve Policy", "Sleeve Limit USD",
        "Kill Condition Refs", "Kelly Advisory USD", "Current Position USD",
        "Delta", "Delta %", "Input Status", "Full Kelly", "Kelly Status",
        "Kelly PEI Fused Status",
    ]]
    for r in str_data.get("kelly_sizing_advisory", [])[:80]:
        rows.append([
            r.get("ticker"), r.get("sleeve_id"), r.get("sleeve_role"), r.get("sleeve_policy"),
            r.get("sleeve_limit_usd"), "; ".join(str(x) for x in (r.get("kill_condition_refs") or [])),
            r.get("capped_advisory_usd"), r.get("current_position_usd"),
            r.get("current_vs_advisory_delta"), r.get("current_vs_advisory_pct"),
            r.get("kelly_input_status"), r.get("full_kelly_fraction"),
            r.get("kelly_status"), r.get("kelly_pei_fused_status"),
        ])
    return rows


def hedge_rows(str_data: Dict[str, Any]) -> List[List[Any]]:
    h = str_data.get("hedge_ratio_review") if isinstance(str_data.get("hedge_ratio_review"), dict) else {}
    return [
        ["Field", "Value"],
        ["Portfolio Beta To SPY", h.get("portfolio_beta_to_spy")],
        ["Hedge Effectiveness", h.get("hedge_effectiveness")],
        ["Current Hedge Value", h.get("current_hedge_value")],
        ["Current Hedge % Market Value", h.get("current_hedge_pct_of_market_value")],
        ["Implied Full Hedge Value", h.get("implied_full_hedge_value")],
        ["Fractional Hedge Value", h.get("fractional_hedge_value")],
        ["Hedge Gap USD", h.get("hedge_gap_usd")],
        ["Hedge Status", h.get("hedge_status")],
        ["Advisory Only", str(h.get("advisory_only", True))],
    ]


def render_str_text_section(str_data: Dict[str, Any]) -> str:
    if not str_data:
        return "\nSTR - SIGNAL, ENTROPY, AND EDGE\nStatus: MISSING\n"
    lines = [
        "STR - SIGNAL, ENTROPY, AND EDGE",
        "=" * 34,
        f"Status: {str_data.get('status', 'UNKNOWN')} | Version: {str_data.get('version', '')}",
        f"Governance Pack: {str_data.get('governance_pack_id', '')}",
        f"Report Binding: {str_data.get('report_memory_binding_id', '')}",
        "Execution: CIO_ONLY_MANUAL | Order Routing: FALSE | System Orders Generated: 0",
        "",
        "STR-1 Signal Entropy Table",
    ]
    for r in str_data.get("signal_entropy", [])[:12]:
        lines.append(
            f"- {r.get('ticker')}: old={r.get('old_label')} | entropy={_fmt(r.get('signal_entropy_normalized'))}/1.00 | {r.get('classification')}"
        )
    lines.extend(["", "STR-2 Source Capacity Watch"])
    for r in str_data.get("source_capacity", [])[:10]:
        lines.append(
            f"- {r.get('source_name')}: T{r.get('source_tier')} | signals={r.get('signal_count')} | {r.get('status')} / {r.get('capacity_confidence')}"
        )
    lines.extend(["", "STR-3 Cost Basis Reconciliation"])
    for r in str_data.get("cost_basis_reconciliation", []):
        lines.append(
            f"- {r.get('ticker')}: broker={r.get('broker_unrealized')} computed={r.get('computed_unrealized')} "
            f"third={r.get('third_witness_unrealized')} | {r.get('resolution_status')} | selected={r.get('selected_source')}"
        )
    lines.extend(["", "STR-4 Kelly Advisory Sizing"])
    for r in str_data.get("kelly_sizing_advisory", [])[:12]:
        lines.append(
            f"- {r.get('ticker')}: b={_fmt(r.get('kelly_b'))} p={_fmt(r.get('kelly_p'))} q={_fmt(r.get('kelly_q'))} "
            f"input={r.get('kelly_input_status')} full={_fmt(r.get('full_kelly_fraction'))} quarter=${r.get('quarter_kelly_usd')} "
            f"cap=${r.get('capped_advisory_size_usd')} | {r.get('kelly_status')}"
        )
    lines.extend(["", "STR-5 Hedge Ratio Review"])
    h = str_data.get("hedge_ratio_review") or {}
    lines.append(
        f"- hedge_value=${h.get('current_hedge_value')} | fractional_target=${h.get('fractional_hedge_value')} "
        f"| gap=${h.get('hedge_gap_usd')} | {h.get('hedge_status')}"
    )
    lines.append(
        "- Hedge ratio review is advisory only. It does not create a hedge order. "
        "It does not recommend automatic VXX/VIXY sizing. CIO_ONLY_MANUAL remains supreme."
    )
    lines.extend([
        "",
        "STR-6 STR Governance Footer",
        "STR is research-only.",
        "STR does not generate orders.",
        "STR does not route orders.",
        "STR does not override CIO_ONLY_MANUAL.",
        "STR adds numbers beside existing labels.",
        "STR adds advisory formula sizing beside CIO sizing.",
        "STR adds a third-witness reconciliation pathway for cost-basis conflicts.",
    ])
    return "\n".join(lines)
