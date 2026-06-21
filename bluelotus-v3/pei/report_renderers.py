from __future__ import annotations

from typing import Any, Dict, List


def _text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_text(v)}" for k, v in value.items())
    if value is None:
        return ""
    return str(value)


def render_pei_text_section(pei: Dict[str, Any]) -> str:
    line = "=" * 78
    lines = [
        line,
        "PEI · PROSPECTIVE EVENT INTELLIGENCE",
        "Event Pathways / Scenario Trees / Portfolio Preparation",
        line,
        f"Status                 : {pei.get('status', 'UNKNOWN')}",
        f"Version                : {pei.get('version', '')}",
        f"Generated SGT          : {pei.get('generated_at_sgt', '')}",
        f"Governance Pack ID     : {pei.get('governance_pack_id', '')}",
        f"Report Binding ID      : {pei.get('report_memory_binding_id', '')}",
        f"Execution Authority    : {pei.get('execution_authority', 'CIO_ONLY_MANUAL')}",
        f"Order Routing Enabled  : {pei.get('order_routing_enabled', False)}",
        f"Orders Generated       : {pei.get('orders_generated', 0)}",
        "",
        "Doctrine:",
        "Forecast events, not prices. Forecast pathways, not headlines. Map pathways to sleeves. Bind all interpretation to law.",
        "",
        "1. Active PEI Events",
    ]
    for event in pei.get("active_events", [])[:8]:
        lines.append(f"- {event.get('event_title')} [{event.get('event_type')}] | resolves {event.get('resolution_date')}")
    lines.extend(["", "2. Scenario Tree Summary / Branch Probability Table"])
    for tree in pei.get("scenario_trees", [])[:5]:
        event = tree.get("event", {})
        lines.append(f"Event: {event.get('event_title')}")
        for branch in tree.get("branches", []):
            lines.append(
                f"  - {branch.get('branch_name'):<36} "
                f"P={float(branch.get('branch_probability') or 0):.0%} | "
                f"Allowed: {branch.get('allowed_action')} | Blocked: {branch.get('blocked_action')}"
            )
    lines.extend(["", "3. Event-to-Sleeve Transmission Map"])
    for row in pei.get("event_to_sleeve_map", [])[:18]:
        lines.append(
            f"- {row.get('affected_sleeve')} | {row.get('expected_direction')} | "
            f"{row.get('transmission_channel')} | Allowed: {row.get('allowed_action')} | Blocked: {row.get('blocked_action')}"
        )
    lines.extend(["", "4. CIO Playbook"])
    for row in pei.get("portfolio_playbook", [])[:12]:
        lines.append(
            f"- {row.get('event_title')} / {row.get('scenario_branch')} "
            f"({float(row.get('probability') or 0):.0%}): {row.get('allowed_action')} | BLOCKED: {row.get('blocked_action')}"
        )
    lines.extend(["", "5. Forecast Resolution Schedule"])
    for forecast in pei.get("forecast_registry", [])[:12]:
        lines.append(
            f"- {forecast.get('branch_name')} | P={float(forecast.get('probability') or 0):.0%} | "
            f"resolves {forecast.get('resolution_date')} | criteria: {_text(forecast.get('resolution_criteria'))[:140]}"
        )
    lines.extend([
        "",
        "6. Brier / CRS Accountability Status",
        f"Brier Status           : {(pei.get('brier_status') or {}).get('status', 'COLLECTING')}",
        f"Resolved Forecasts     : {(pei.get('brier_status') or {}).get('resolved_forecasts', 0)}",
        f"CRS Status             : {(pei.get('crs_decomposition') or {}).get('status', 'COLLECTING')}",
        "",
        "7. Reflexive Suppression",
    ])
    suppression = pei.get("reflexive_suppression") or {}
    lines.append(
        f"{suppression.get('ticker', 'ASTS')}: {suppression.get('classification', 'UNKNOWN')} | "
        f"{suppression.get('action_mapping', '')}"
    )
    lines.extend(["", "8. Oscillation Engine"])
    for ticker, row in (pei.get("oscillation_engine") or {}).items():
        if isinstance(row, dict):
            lines.append(
                f"- {ticker}: mean={row.get('behavioral_mean')} support={row.get('support_band')} "
                f"trim={row.get('upper_harvest_band')} reload_allowed={row.get('reload_allowed')}"
            )
    lines.extend(["", "9. Kill Condition Watch"])
    for item in (pei.get("kill_condition_summary") or {}).get("kill_conditions", [])[:12]:
        lines.append(f"- {item}")
    lines.append(line)
    return "\n".join(lines).strip() + "\n"


def pei_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    rows: List[List[Any]] = [
        ["Field", "Value", "Certainty", "Source Layer"],
        ["PEI Status", pei.get("status", ""), "DATA_CONFIRMED", "prospective_event_intelligence"],
        ["Version", pei.get("version", ""), "DATA_CONFIRMED", "prospective_event_intelligence"],
        ["Governance Pack ID", pei.get("governance_pack_id", ""), "LAW_BOUND", "law_governance_memory"],
        ["Report Binding ID", pei.get("report_memory_binding_id", ""), "LAW_BOUND", "law_governance_memory"],
        ["Execution Authority", pei.get("execution_authority", ""), "GOVERNANCE_RULE", "execution_doctrine"],
        ["Order Routing Enabled", pei.get("order_routing_enabled", False), "GOVERNANCE_RULE", "execution_doctrine"],
        ["Orders Generated", pei.get("orders_generated", 0), "GOVERNANCE_RULE", "execution_doctrine"],
    ]
    for event in pei.get("active_events", [])[:10]:
        rows.append(["Active Event", f"{event.get('event_title')} [{event.get('event_type')}]", "MODEL_INFERRED", "pei_event_registry"])
    return rows


def pei_event_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    return [["event_id", "event_type", "event_title", "resolution_date", "affected_sleeves"], *[
        [e.get("event_id"), e.get("event_type"), e.get("event_title"), e.get("resolution_date"), _text(e.get("affected_sleeves"))]
        for e in pei.get("active_events", [])
    ]]


def pei_branch_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    rows = [["event_title", "branch", "probability", "allowed_action", "blocked_action", "kill_conditions"]]
    for tree in pei.get("scenario_trees", []):
        title = (tree.get("event") or {}).get("event_title")
        for branch in tree.get("branches", []):
            rows.append([title, branch.get("branch_name"), branch.get("branch_probability"), branch.get("allowed_action"), branch.get("blocked_action"), _text(branch.get("kill_conditions"))])
    return rows


def pei_sleeve_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    return [["branch_id", "sleeve", "direction", "confidence", "channel", "allowed", "blocked"], *[
        [r.get("branch_id"), r.get("affected_sleeve"), r.get("expected_direction"), r.get("confidence"), r.get("transmission_channel"), r.get("allowed_action"), r.get("blocked_action")]
        for r in pei.get("event_to_sleeve_map", [])
    ]]


def pei_playbook_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    return [["event", "branch", "probability", "sleeves", "allowed_action", "blocked_action", "resolution_date"], *[
        [r.get("event_title"), r.get("scenario_branch"), r.get("probability"), _text(r.get("affected_sleeves")), r.get("allowed_action"), r.get("blocked_action"), r.get("forecast_resolution_date")]
        for r in pei.get("portfolio_playbook", [])
    ]]


def pei_forecast_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    return [["forecast_id", "event_id", "branch", "probability", "resolution_date", "criteria", "routing_enabled", "orders_generated"], *[
        [f.get("forecast_id"), f.get("event_id"), f.get("branch_name"), f.get("probability"), f.get("resolution_date"), _text(f.get("resolution_criteria")), f.get("routing_enabled"), f.get("orders_generated")]
        for f in pei.get("forecast_registry", [])
    ]]


def pei_brier_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    brier = pei.get("brier_status") or {}
    crs = pei.get("crs_decomposition") or {}
    return [["Field", "Value"], *[[k, v] for k, v in {**brier, **{f"crs_{k}": v for k, v in crs.items()}}.items()]]


def pei_suppression_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    s = pei.get("reflexive_suppression") or {}
    rows = [["Field", "Value"], ["ticker", s.get("ticker")], ["classification", s.get("classification")], ["action_mapping", s.get("action_mapping")]]
    for k, v in (s.get("criteria") or {}).items():
        rows.append([k, v])
    return rows


def pei_oscillation_rows(pei: Dict[str, Any]) -> List[List[Any]]:
    rows = [["ticker", "status", "sample_size", "mean", "support_band", "trim_band", "reload_allowed", "regime_broken"]]
    for ticker, row in (pei.get("oscillation_engine") or {}).items():
        if isinstance(row, dict):
            rows.append([ticker, row.get("status"), row.get("sample_size"), row.get("behavioral_mean"), _text(row.get("support_band")), _text(row.get("upper_harvest_band")), row.get("reload_allowed"), row.get("regime_broken")])
    return rows
