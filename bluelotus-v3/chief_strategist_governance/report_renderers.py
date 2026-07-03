from __future__ import annotations

from typing import Any, Dict, List


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(_str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}={_str(v)}" for k, v in value.items())
    return str(value)


def _csg(dataset: Dict[str, Any]) -> Dict[str, Any]:
    value = dataset.get("chief_strategist_governance") or {}
    return value if isinstance(value, dict) else {}


def _active(dataset: Dict[str, Any]) -> Dict[str, Any]:
    value = dataset.get("active_thesis_reconciliation") or {}
    return value if isinstance(value, dict) else {}


def _matrix(dataset: Dict[str, Any]) -> Dict[str, Any]:
    value = dataset.get("strategic_tactical_reconciliation_matrix") or {}
    return value if isinstance(value, dict) else {}


def _event_map(dataset: Dict[str, Any]) -> Dict[str, Any]:
    value = dataset.get("event_thesis_map") or {}
    return value if isinstance(value, dict) else {}


def governance_is_active(dataset: Dict[str, Any]) -> bool:
    csg = _csg(dataset)
    return (
        csg.get("status") == "ACTIVE"
        and csg.get("mandatory_for_chief_strategist") is True
        and bool(dataset.get("active_thesis_reconciliation"))
        and bool(dataset.get("strategic_tactical_reconciliation_matrix"))
    )


def build_cs_governance_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    csg = _csg(dataset)
    rows: List[List[Any]] = [
        ["governance_version", csg.get("governance_version", ""), "DATA_CONFIRMED", "chief_strategist_governance"],
        ["status", csg.get("status", "MISSING"), "DATA_CONFIRMED", "chief_strategist_governance"],
        ["mandatory_for_chief_strategist", csg.get("mandatory_for_chief_strategist", ""), "DATA_CONFIRMED", "chief_strategist_governance"],
        ["generated_at", csg.get("generated_at", ""), "DATA_CONFIRMED", "chief_strategist_governance"],
    ]
    for idx, source in enumerate(csg.get("source_priority") or [], start=1):
        rows.append([f"source_priority_{idx}", source, "DATA_CONFIRMED", "chief_strategist_governance"])
    for rule in csg.get("hard_rules") or []:
        rows.append(["hard_rule", rule, "GOVERNANCE_RULE", "chief_strategist_governance"])
    for point in dataset.get("required_briefing_points") or []:
        rows.append(["required_briefing_point", point, "GOVERNANCE_RULE", "required_briefing_points"])
    for item in dataset.get("forbidden_interpretations") or []:
        rows.append(["forbidden_interpretation", item, "GOVERNANCE_RULE", "forbidden_interpretations"])
    return rows


def build_thesis_reconciliation_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    active = _active(dataset)
    rows: List[List[Any]] = []
    for thesis_key, payload in active.items():
        if not isinstance(payload, dict) or thesis_key in ("schema_version", "generated_at"):
            continue
        rows.append([
            thesis_key,
            payload.get("strategic_thesis", ""),
            payload.get("tactical_state", ""),
            payload.get("allowed_interpretation", ""),
            payload.get("forbidden_interpretation", ""),
            _str(payload.get("required_kill_conditions") or []),
        ])
    return rows


def build_event_thesis_map_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    events = _event_map(dataset).get("events") or []
    rows: List[List[Any]] = []
    for event in events:
        if isinstance(event, dict):
            rows.append([
                event.get("event_key", ""),
                event.get("thesis_id", ""),
                event.get("relationship", ""),
                event.get("reconciliation_note", ""),
            ])
    return rows


def build_reconciliation_matrix_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    rows: List[List[Any]] = []
    for row in _matrix(dataset).get("rows") or []:
        if isinstance(row, dict):
            rows.append([
                row.get("claim_tag", ""),
                row.get("strategic_context_required", ""),
                row.get("allowed_output", ""),
                row.get("blocked_output", ""),
            ])
    return rows


def render_csg_text_section(dataset: Dict[str, Any]) -> str:
    csg = _csg(dataset)
    active = _active(dataset)
    matrix_rows = build_reconciliation_matrix_rows(dataset)
    event_rows = build_event_thesis_map_rows(dataset)

    lines: List[str] = [
        "",
        "================================================================================",
        "CHIEF STRATEGIST GOVERNANCE LAYER",
        "================================================================================",
        f"Governance Version : {csg.get('governance_version', 'MISSING')}",
        f"Status             : {csg.get('status', 'MISSING')}",
        f"Mandatory          : {csg.get('mandatory_for_chief_strategist', False)}",
        f"Generated          : {csg.get('generated_at', '')}",
        "",
        "Doctrine:",
        "- Tactical score modifies timing; tactical score does not invalidate structural thesis unless kill condition triggered.",
        "- Structural thesis invalidation requires explicit kill-condition evidence and source reconciliation.",
        "- CIO_ONLY_MANUAL remains intact. Order routing remains disabled.",
        "",
        "Source Priority:",
    ]
    for idx, source in enumerate(csg.get("source_priority") or [], start=1):
        lines.append(f"{idx}. {source}")

    lines.extend(["", "Active Thesis Reconciliation:"])
    for thesis_key, payload in active.items():
        if not isinstance(payload, dict) or thesis_key in ("schema_version", "generated_at"):
            continue
        lines.extend([
            f"- {thesis_key}",
            f"  Strategic Thesis       : {payload.get('strategic_thesis', '')}",
            f"  Tactical State         : {payload.get('tactical_state', '')}",
            f"  Allowed Interpretation : {payload.get('allowed_interpretation', '')}",
            f"  Forbidden Interpretation: {payload.get('forbidden_interpretation', '')}",
            f"  Kill Conditions        : {_str(payload.get('required_kill_conditions') or [])}",
        ])

    lines.extend(["", "Strategic / Tactical Reconciliation Matrix:"])
    for row in matrix_rows:
        lines.append(f"- {row[0]} | Required: {row[1]} | Allowed: {row[2]} | Blocked: {row[3]}")

    lines.extend(["", "Event / Thesis Map:"])
    for event_key, thesis_id, relationship, note in event_rows:
        lines.append(f"- {event_key} -> {thesis_id} ({relationship}): {note}")

    forbidden = dataset.get("forbidden_interpretations") or []
    if forbidden:
        lines.extend(["", "Forbidden Interpretations:"])
        lines.extend(f"- {item}" for item in forbidden)

    return "\n".join(lines).strip() + "\n"


def append_csg_text_section(report_text: str, dataset: Dict[str, Any]) -> str:
    section = render_csg_text_section(dataset).strip()
    marker = "CHIEF STRATEGIST GOVERNANCE LAYER"
    if marker in report_text:
        return report_text
    anchor = "\n================================================================================\nREPORT QA FOOTER"
    if anchor in report_text:
        return report_text.replace(anchor, "\n" + section + anchor, 1)
    return report_text.rstrip() + "\n\n" + section + "\n"
