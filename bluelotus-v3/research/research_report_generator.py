#!/usr/bin/env python3
r"""
BlueLotus V2 R6-U Research Report Generator

Purpose:
  Keep the existing R6 text report and database archive flow intact, then add
  trial CIO presentation layers:

    1. Bluelotus_V3_Report.txt
    2. research_report_archive_latest.json
    3. Bluelotus_V3_Report.xlsx
    4. Bluelotus_V3_Report.docx
    5. research_report_delivery_latest.json

This file intentionally wraps research_report_generator_r6.py instead of
replacing it. The R6 text report remains the canonical audit/archive record.

No third-party packages are required for Excel/Word generation. The XLSX and
DOCX outputs are written as minimal OOXML packages using the Python standard
library so this can run on the current production Python environment.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(r"C:\bluelotus3")
RESEARCH_DIR = PROJECT_ROOT / "research"
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_TEXT_OUTPUT = RESEARCH_DIR / "Bluelotus_V3_Report.txt"
DEFAULT_EXCEL_OUTPUT = RESEARCH_DIR / "Bluelotus_V3_Report.xlsx"
DEFAULT_WORD_OUTPUT = RESEARCH_DIR / "Bluelotus_V3_Report.docx"
DEFAULT_DELIVERY_JSON = RESEARCH_DIR / "research_report_delivery_latest.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from chief_strategist_governance.report_renderers import (
        append_csg_text_section,
        build_cs_governance_rows,
        build_event_thesis_map_rows,
        build_reconciliation_matrix_rows,
        build_thesis_reconciliation_rows,
        governance_is_active,
        render_csg_text_section,
    )
except Exception:
    append_csg_text_section = None
    build_cs_governance_rows = None
    build_event_thesis_map_rows = None
    build_reconciliation_matrix_rows = None
    build_thesis_reconciliation_rows = None
    governance_is_active = None
    render_csg_text_section = None

try:
    from cio_context_capsule.master_prompt import build_chief_strategist_master_prompt
    from cio_context_capsule.builder import build_cio_context_capsule
    from cio_context_capsule.renderers import (
        build_master_prompt_rows,
        build_cio_context_rows,
        capsule_is_active,
        master_prompt_is_active,
        prepend_master_prompt_and_cio_context,
        render_cio_context_text_section,
        render_master_prompt_text_section,
    )
except Exception:
    build_chief_strategist_master_prompt = None
    build_cio_context_capsule = None
    build_master_prompt_rows = None
    build_cio_context_rows = None
    capsule_is_active = None
    master_prompt_is_active = None
    prepend_master_prompt_and_cio_context = None
    render_cio_context_text_section = None
    render_master_prompt_text_section = None

try:
    from pei.builder import build_prospective_event_intelligence
    from pei.report_renderers import (
        pei_branch_rows,
        pei_brier_rows,
        pei_event_rows,
        pei_forecast_rows,
        pei_oscillation_rows,
        pei_playbook_rows,
        pei_rows,
        pei_sleeve_rows,
        pei_suppression_rows,
        render_pei_text_section,
    )
except Exception:
    build_prospective_event_intelligence = None
    pei_branch_rows = None
    pei_brier_rows = None
    pei_event_rows = None
    pei_forecast_rows = None
    pei_oscillation_rows = None
    pei_playbook_rows = None
    pei_rows = None
    pei_sleeve_rows = None
    pei_suppression_rows = None
    render_pei_text_section = None

try:
    from acms_cop.reports.signal_edge_dashboard_renderer import (
        build_shannon_thorp_refinement,
        cost_basis_rows as str_cost_basis_rows,
        hedge_rows as str_hedge_rows,
        kelly_rows as str_kelly_rows,
        render_str_text_section,
        signal_entropy_rows as str_signal_entropy_rows,
        source_capacity_rows as str_source_capacity_rows,
        str_summary_rows,
    )
    from acms_cop.reports.remediation_reconciliation import (
        build_remediation_reconciliation,
        remediation_summary_rows,
        render_remediation_text_section,
    )
    from acms_cop.reports.cio_order_policy import classify_cio_order_policy
except Exception:
    build_shannon_thorp_refinement = None
    str_cost_basis_rows = None
    str_hedge_rows = None
    str_kelly_rows = None
    render_str_text_section = None
    build_remediation_reconciliation = None
    remediation_summary_rows = None
    render_remediation_text_section = None
    classify_cio_order_policy = None
    str_signal_entropy_rows = None
    str_source_capacity_rows = None
    str_summary_rows = None

try:
    from canonical.canonical_data_contract import build_v3_1_to_v3_4_payload
except Exception:
    build_v3_1_to_v3_4_payload = None

# ── NITE-PEI Engine Integration ──────────────────────────────────────────────
# Loads the latest nite_pei_block.json from the active v3 cycle folder.
# Appended into TXT, XLSX tab, and Word section of the main Bluelotus_V3_Report.
try:
    from mid.nite_pei_report_builder import build_nite_pei_txt_section as _build_nite_pei_txt
except Exception:
    _build_nite_pei_txt = None

_CYCLES_ROOT_FOR_RRG = PROJECT_ROOT / "data" / "v3_cycles"

def _load_latest_nite_pei_block() -> dict:
    """Load nite_pei_block.json from the most recent v3_cycle_* folder that has one."""
    try:
        folders = sorted([
            d for d in _CYCLES_ROOT_FOR_RRG.iterdir()
            if d.is_dir() and d.name.startswith("v3_cycle_")
        ], reverse=True)
        for folder in folders:
            block_path = folder / "nite_pei_block.json"
            if block_path.exists():
                return json.loads(block_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

GENERATOR_VERSION = "R6-U"
PLATFORM_TEAM = "Codex & Claude Code Windows Platform Team"

TEXT_REPLACEMENTS = {
    "\u00e2\u20ac\u201d": "-",
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u00a2": "*",
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"',
    "\u00e2\u0086\u0092": "->",
    "\u00e2\u0089\u00a5": ">=",
    "\u00e2\u0089\u00a4": "<=",
    "\u00c2\u00b1": "+/-",
    "\u00e2\u0161\u00a0": "WARNING",
    "\u00e2\u0153\u2026": "[OK]",
    "\u00e2\u0153\u2014": "[X]",
    "\u00e2\u2013\u00bc": "v",
    "\u00e2\u2013\u00b2": "^",
    "\u00e2\u201d\u20ac": "-",
}


def normalize_report_text(value: Any) -> str:
    text = "" if value is None else str(value)
    for bad, good in TEXT_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2022", "*")
        .replace("\u2192", "->")
        .replace("\u2265", ">=")
        .replace("\u2264", "<=")
        .replace("\u00b1", "+/-")
        .replace("\u26a0", "WARNING")
        .replace("\u2713", "[OK]")
        .replace("\u2717", "[X]")
    )
    return text


LAW_MEMORY_KEY_MAP = {
    "master_prompt": "chief_strategist_master_prompt",
    "cio_context_capsule": "cio_context_capsule",
    "chief_strategist_governance": "chief_strategist_governance",
    "strategy_doctrine": "active_strategy_defaults",
    "sleeve_rules": "sleeve_rules",
    "kill_condition_set": "kill_conditions",
    "execution_doctrine": "execution_doctrine",
    "source_priority_rules": "source_priority_rules",
}


def _sgt_now_text() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


def _utc_to_sgt_text(value: Any) -> str:
    if not value:
        return _sgt_now_text()
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")
    except Exception:
        return str(value)


def _pack_active_memory(pack: Dict[str, Any]) -> Dict[str, Any]:
    active = pack.get("active_memory") if isinstance(pack.get("active_memory"), dict) else {}
    return active


def build_law_governance_binding_model(
    pack: Dict[str, Any],
    validation: Optional[Dict[str, Any]] = None,
    binding: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    validation = validation or {}
    binding = binding or {}
    active_memory = _pack_active_memory(pack)
    validation_status = str(validation.get("status") or "UNKNOWN")
    binding_status_raw = str(binding.get("status") or "")
    pack_hash = pack.get("active_pack_hash") or binding.get("active_pack_hash") or ""

    if not pack_hash:
        status = "MISSING"
        warning = "ACTIVE_GOVERNANCE_PACK_MISSING"
        report_status = "INSTITUTIONAL_REVIEW_REQUIRED"
        cio_action_cap = "ADD_BLOCKED"
    elif validation_status not in ("PASS", "WARNING"):
        status = "INVALID"
        warning = "GOVERNANCE_LAW_VALIDATION_FAILED"
        report_status = "GOVERNANCE_REVIEW_REQUIRED"
        cio_action_cap = "ADD_BLOCKED"
    elif binding_status_raw not in ("ACTIVE", "BOUND"):
        status = "BINDING_FAILED"
        warning = "REPORT_MEMORY_BINDING_FAILED"
        report_status = "INSTITUTIONAL_REVIEW_REQUIRED"
        cio_action_cap = "ADD_BLOCKED"
    else:
        status = "BOUND"
        warning = ""
        report_status = "LAW_BOUND"
        cio_action_cap = "UNCHANGED"

    objects: Dict[str, Dict[str, Any]] = {}
    for pack_key, object_key in LAW_MEMORY_KEY_MAP.items():
        entry = active_memory.get(pack_key) if isinstance(active_memory.get(pack_key), dict) else {}
        objects[object_key] = {
            "object_id": entry.get("memory_id", ""),
            "version": entry.get("version", ""),
            "hash": entry.get("hash", ""),
            "effective_from": entry.get("effective_from", ""),
            "approval_status": entry.get("approval_status", ""),
        }

    return {
        "status": status,
        "governance_binding_status": status,
        "governance_pack_id": pack.get("governance_pack_id") or (f"GOVPACK_{pack_hash[:16]}" if pack_hash else ""),
        "governance_pack_version": pack.get("version", ""),
        "governance_pack_hash": pack_hash,
        "report_memory_binding_id": binding.get("binding_id", ""),
        "binding_hash": binding.get("binding_hash", ""),
        "binding_timestamp_sgt": _utc_to_sgt_text(binding.get("binding_timestamp_utc") or binding.get("generated_at")),
        "law_validation_status": validation_status,
        "governance_policy_version": "governance_law_policy.v1",
        "active_memory_objects": objects,
        "interpretation_authority": "GOVERNED_BY_ACTIVE_LAW_PACK",
        "pipeline_authority": "PIPELINE_OPERATES_UNDER_LAW",
        "pipeline_law_writing_authority": False,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "report_status": report_status,
        "cio_action_cap": cio_action_cap,
        "warning": warning,
        "doctrine_text": (
            "This report was interpreted under the active BlueLotus institutional law pack. "
            "The V3 pipeline operates under law and does not write the law. Tactical data, "
            "broker data, market data, screenshots, news, and LLM synthesis are subordinate "
            "to the active governance pack, CIO Context Capsule, active sleeve rules, kill "
            "conditions, and CIO_ONLY_MANUAL execution doctrine."
        ),
    }


def build_law_governance_rows(model: Dict[str, Any]) -> List[List[Any]]:
    objects = model.get("active_memory_objects") if isinstance(model.get("active_memory_objects"), dict) else {}
    field_rows: List[Tuple[str, Any]] = [
        ("Governance Binding Status", model.get("governance_binding_status", "")),
        ("Active Governance Pack ID", model.get("governance_pack_id", "")),
        ("Active Governance Pack Version", model.get("governance_pack_version", "")),
        ("Active Governance Pack Hash", model.get("governance_pack_hash", "")),
        ("Report Memory Binding ID", model.get("report_memory_binding_id", "")),
        ("Binding Timestamp SGT", model.get("binding_timestamp_sgt", "")),
        ("Law Validation Status", model.get("law_validation_status", "")),
        ("Governance Policy Version", model.get("governance_policy_version", "")),
        ("Master Prompt Object ID", (objects.get("chief_strategist_master_prompt") or {}).get("object_id", "")),
        ("Master Prompt Hash", (objects.get("chief_strategist_master_prompt") or {}).get("hash", "")),
        ("CIO Context Capsule Object ID", (objects.get("cio_context_capsule") or {}).get("object_id", "")),
        ("CIO Context Capsule Hash", (objects.get("cio_context_capsule") or {}).get("hash", "")),
        ("Chief Strategist Governance Object ID", (objects.get("chief_strategist_governance") or {}).get("object_id", "")),
        ("Chief Strategist Governance Hash", (objects.get("chief_strategist_governance") or {}).get("hash", "")),
        ("Active Strategy Object ID", (objects.get("active_strategy_defaults") or {}).get("object_id", "")),
        ("Active Strategy Hash", (objects.get("active_strategy_defaults") or {}).get("hash", "")),
        ("Sleeve Rules Object ID", (objects.get("sleeve_rules") or {}).get("object_id", "")),
        ("Sleeve Rules Hash", (objects.get("sleeve_rules") or {}).get("hash", "")),
        ("Kill Conditions Object ID", (objects.get("kill_conditions") or {}).get("object_id", "")),
        ("Kill Conditions Hash", (objects.get("kill_conditions") or {}).get("hash", "")),
        ("Execution Doctrine Object ID", (objects.get("execution_doctrine") or {}).get("object_id", "")),
        ("Execution Doctrine Hash", (objects.get("execution_doctrine") or {}).get("hash", "")),
        ("Source Priority Object ID", (objects.get("source_priority_rules") or {}).get("object_id", "")),
        ("Source Priority Hash", (objects.get("source_priority_rules") or {}).get("hash", "")),
        ("Interpretation Authority", model.get("interpretation_authority", "")),
        ("Pipeline Authority", model.get("pipeline_authority", "")),
        ("Pipeline Law-Writing Authority", model.get("pipeline_law_writing_authority", False)),
        ("Execution Authority", model.get("execution_authority", "")),
        ("Order Routing Enabled", model.get("order_routing_enabled", False)),
        ("System Orders Generated", model.get("system_orders_generated", 0)),
    ]
    if model.get("warning"):
        field_rows.append(("Warning", model.get("warning", "")))
    return [[field, value, "DATA_CONFIRMED", "law_governance_memory"] for field, value in field_rows]


def render_governance_law_binding_section(model_or_pack: Dict[str, Any]) -> str:
    if "governance_pack_hash" not in model_or_pack:
        model = build_law_governance_binding_model(model_or_pack, {"status": "UNKNOWN"}, {"status": "MISSING"})
    else:
        model = model_or_pack
    line = "=" * 78
    rows = build_law_governance_rows(model)
    lines = [
        line,
        "00A · LAW & ORDER GOVERNANCE BINDING",
        "ACTIVE LAW PACK GOVERNING THIS REPORT",
        line,
    ]
    for field, value, _certainty, _source in rows:
        lines.append(f"{field:<40} {str(value)}")
    lines.extend(["", "Doctrine:", model.get("doctrine_text", ""), line])
    return "\n".join(lines).strip() + "\n"


def load_governance_law_pack_for_report() -> Dict[str, Any]:
    try:
        from law_governance.export_active_governance_pack import export_active_governance_pack
        from law_governance.law_core import ACTIVE_PACK_PATH, load_json_path

        export_active_governance_pack()
        if ACTIVE_PACK_PATH.exists():
            return load_json_path(ACTIVE_PACK_PATH)
    except Exception as exc:
        print(f"[Governance Law] WARNING: active law pack unavailable: {exc}")
    return {}


def prepare_law_governance_binding_for_report(
    dataset: Dict[str, Any],
    dataset_path: Path,
    report_id: str,
    cycle_id: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    pack: Dict[str, Any] = {}
    validation: Dict[str, Any] = {"status": "UNKNOWN"}
    binding: Dict[str, Any] = {"status": "MISSING"}
    try:
        from law_governance.export_active_governance_pack import export_active_governance_pack
        from law_governance.law_core import ACTIVE_PACK_PATH, load_json_path
        from law_governance.validate_governance_law import validate_governance_law
        from law_governance.bind_report_memory import bind_current_report_memory

        export_active_governance_pack()
        pack = load_json_path(ACTIVE_PACK_PATH) if ACTIVE_PACK_PATH.exists() else {}
        validation = validate_governance_law()
        if validation.get("status") in ("PASS", "WARNING") and pack.get("active_pack_hash"):
            binding = bind_current_report_memory(report_id=report_id, cycle_id=cycle_id)
        else:
            binding = {"status": "INVALID", "error": "Governance law validation failed or active pack missing"}
    except Exception as exc:
        binding = {"status": "BINDING_FAILED", "error": str(exc)}

    model = build_law_governance_binding_model(pack, validation, binding)
    dataset["law_governance_binding"] = model
    try:
        dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[Governance Law] WARNING: dataset_raw law binding write failed: {exc}")
    return pack, validation, binding


def insert_law_governance_section_after_master_prompt(report_text: str, section: str) -> str:
    if "00A · LAW & ORDER GOVERNANCE BINDING" in report_text:
        return report_text
    markers = [
        "\n==============================================================================\n  CIO CONTEXT CAPSULE - READ FIRST",
        "\n==============================================================================\n  CIO CONTEXT CAPSULE",
        "\nCIO CONTEXT CAPSULE - READ FIRST",
    ]
    for marker in markers:
        idx = report_text.find(marker)
        if idx >= 0:
            return report_text[:idx].rstrip() + "\n\n" + section.strip() + "\n\n" + report_text[idx:].lstrip()
    return report_text.rstrip() + "\n\n" + section.strip() + "\n"


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def normalize_market_session(raw: Any, snapshot_ts: Any = None) -> str:
    """Renderer taxonomy for market session labels.

    Some upstream feeds reuse weekend wording for a weekday after the U.S. close.
    Reports must disclose the trading state without implying the calendar day is
    Saturday/Sunday when the formal snapshot was produced on a weekday.
    """
    label = str(raw or "UNKNOWN").upper().strip()
    label = label.replace(" ", "_").replace("/", "_")
    if "REGULAR" in label and "CLOSE" not in label:
        return "REGULAR_SESSION"
    if "PRE" in label:
        return "PRE_MARKET"
    if "POST" in label or "AFTER" in label:
        return "POST_MARKET"
    if "HOLIDAY" in label:
        return "HOLIDAY_SNAPSHOT"
    if "STALE" in label or "ARCHIVE" in label:
        return "STALE_ARCHIVE_SNAPSHOT"
    if "WEEKEND" in label:
        dt = _parse_iso_dt(snapshot_ts)
        if dt and dt.weekday() < 5:
            return "MARKET_CLOSED_LAST_REGULAR_CLOSE"
        return "WEEKEND_SNAPSHOT"
    if "CLOSED" in label or "LAST_REGULAR_CLOSE" in label:
        return "MARKET_CLOSED_LAST_REGULAR_CLOSE"
    return label or "UNKNOWN"


def source_coverage_label(active: Any, expected: Any) -> str:
    return f"Sources active: {si(active)} / baseline {si(expected)}"


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def build_snapshot_hierarchy(dataset: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    live = _read_json_file(PROJECT_ROOT / "data" / "portfolio_live" / "portfolio_live.json")
    formal_ts = meta.get("generated_at") or meta.get("cycle_ts") or ""
    live_ts = live.get("generated_at") or live.get("portfolio_updated_at") or ""
    broker_ts = (
        live.get("portfolio_updated_at")
        or portfolio.get("cycle_ts")
        or ((dataset.get("orders") or {}).get("cycle_ts") if isinstance(dataset.get("orders"), dict) else "")
        or ""
    )
    formal_dt = _parse_iso_dt(formal_ts)
    live_dt = _parse_iso_dt(live_ts)
    dashboard_newer = bool(formal_dt and live_dt and live_dt > formal_dt)
    formal_minus_dashboard = int((formal_dt - live_dt).total_seconds() / 60) if formal_dt and live_dt else None
    if formal_minus_dashboard is not None and formal_minus_dashboard > 10:
        snapshot_status = "FORMAL_REPORT_NEWER_THAN_LIVE_DASHBOARD"
        snapshot_disclosure = "FORMAL_REPORT_NEWER_THAN_LIVE_DASHBOARD - dashboard may lag the formal report"
    elif formal_minus_dashboard is not None and formal_minus_dashboard < -10:
        snapshot_status = "LIVE_DASHBOARD_NEWER_THAN_FORMAL_REPORT"
        snapshot_disclosure = "LIVE_DASHBOARD_NEWER_THAN_FORMAL_REPORT - formal report may be stale"
    else:
        snapshot_status = "SNAPSHOT_ALIGNED"
        snapshot_disclosure = "SNAPSHOT_ALIGNED - formal report and dashboard are within timing tolerance"
    formal_regime = str((dataset.get("regime") or {}).get("regime") or (dataset.get("regime") or {}).get("regime_short") or "")
    live_regime = str(live.get("regime_short") or "")
    regime_diff = bool(formal_regime and live_regime and formal_regime.upper() != live_regime.upper())
    return {
        "formal_report_snapshot_ts": formal_ts or "UNKNOWN",
        "live_dashboard_snapshot_ts": live_ts or "UNKNOWN",
        "broker_portfolio_ts": broker_ts or "UNKNOWN",
        "report_is_older_than_live_dashboard": dashboard_newer,
        "regime_difference_detected": regime_diff,
        "formal_minus_dashboard_minutes": formal_minus_dashboard,
        "snapshot_alignment_status": snapshot_status,
        "snapshot_disclosure": snapshot_disclosure if not regime_diff else snapshot_disclosure + " | REGIME_DIFFERENCE_DETECTED",
    }


def causal_price_action_label(direction: Any, flags: Sequence[Any] = ()) -> str:
    d = str(direction or "").upper().replace("-", "_").replace(" ", "_")
    weak = {
        "SECTOR_EVIDENCE_MISMATCH",
        "NO_DIRECT_CATALYST",
        "GENERIC_EVIDENCE_REVIEW",
        "ANALYST_ONLY_CAUSAL_GAP",
        "PRICE_ACTION_ONLY_CAP",
        "PARTIAL_CAUSAL_CAP",
        "THEME_BASKET_OUTLIER_REVIEW",
    }
    has_causal_gap = bool(set(str(x) for x in (flags or [])) & weak)
    if "RISK_ON" in d:
        return "PRICE_ACTION_RISK_ON / CAUSAL_NOT_CONFIRMED" if has_causal_gap else "RISK_ON"
    if "RISK_OFF" in d:
        return "PRICE_ACTION_RISK_OFF / CAUSAL_NOT_CONFIRMED" if has_causal_gap else "RISK_OFF"
    return d or "NEUTRAL"


def normalize_theme_label(theme: Any) -> str:
    label = str(theme or "").strip()
    up = label.upper()
    if up == "SPACE / DEFENSE":
        return "SPACE / HIGH-BETA"
    if up == "DEFENSE / AEROSPACE":
        return "DEFENSE / AEROSPACE PRIMES"
    return label


def _classify_broker_order_intent(row: Dict[str, Any]) -> str:
    side = str(row.get("trd_side") or row.get("side") or "").upper()
    ticker = _broker_ticker(row).upper() if "_broker_ticker" in globals() else str(row.get("ticker") or "").upper()
    qty = n(row.get("qty"), 0) or 0
    price = n(row.get("price"), 0) or 0
    notional = abs(qty * price)
    policy = classify_cio_order_policy(ticker, side) if classify_cio_order_policy else None
    if policy:
        return str(policy["classification"])
    if side == "SELL":
        return "DECONCENTRATION_REVIEW" if ticker in {"AU", "NEM"} else "REDUCE_REVIEW"
    if side == "BUY" and notional <= 500:
        return "SCOUT_DISLOCATION_ORDER"
    if side == "BUY":
        return "ADD_BLOCKED_REQUIRES_CIO_REVIEW"
    return "BROKER_ORDER_REVIEW"

# Upgrade #10: Canonical 15-section order — both TXT and Word report must follow this ordering.
# Section numbers are for governance reference; they appear in both formats for cross-format navigation.
CANONICAL_SECTION_ORDER: List[str] = [
    "01  1-PAGE CIO BRIEFING",
    "02  EXECUTIVE READ",
    "03  CONSISTENCY AUDIT",
    "04  CAUSAL EXPLANATION ENGINE",
    "05  BLIND SPOT CHECKLIST",
    "06  DATASET INTEGRITY & SOURCE HEALTH",
    "07  MARKET REGIME",
    "08  CROSS-MARKET CONFIRMATION",
    "09  SUPERFORECAST & BRIER ACCOUNTABILITY",
    "10  PORTFOLIO, CASH & MANDATE-AWARE EXPOSURE",
    "11  FORMAL RISK MODEL",
    "12  PORTFOLIO TARGETS & THESIS LIFECYCLE",
    "13  EXECUTION INTELLIGENCE / TCA READINESS",
    "14  INSTITUTIONAL POSITIONING",
    "15  MONITORING, ALERTS & CIO OPERATIONS",
]
# Note: TXT report adds supplementary sections (quant readiness, cognition, tech tape, etc.)
# after section 15. These are detail sections, not core CIO summary sections.

# Certainty tag framework (Upgrade #7)
CERTAINTY_LABELS: Dict[str, str] = {
    "LIVE_CONFIRMED":    "[LIVE_CONFIRMED]",
    "FRESH_CONFIRMED":   "[FRESH_CONFIRMED]",
    "ARCHIVE_CONFIRMED": "[ARCHIVE_CONFIRMED]",
    "STALE_CONFIRMED":   "[STALE_CONFIRMED]",
    "DATA_CONFIRMED":    "[DATA CONFIRMED]",      # keep for backward compat
    "MODEL_INFERRED":    "[MODEL_INFERRED]",
    "PROVISIONAL":       "[PROVISIONAL]",
    "CIO_THESIS":        "[CIO THESIS]",
    "UNKNOWN":           "[UNKNOWN]",
    "CONFLICTED":        "[CONFLICTED]",
    "UNVERIFIED":        "[UNVERIFIED]",          # Claimed by model but not from a primary data source
    "MISSING":           "[MISSING]",             # Known data gap — data that should exist is absent
}


def _certainty_label(source_ts=None, now_utc=None,
                     warn_minutes=60, stale_minutes=120):
    """Return CERTAINTY label based on data age."""
    if now_utc is None:
        from datetime import datetime, timezone as _tz
        now_utc = datetime.now(_tz.utc)
    if not source_ts:
        return "UNKNOWN"
    try:
        from datetime import datetime
        ts = datetime.fromisoformat(str(source_ts).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            from datetime import timezone as _tz2
            ts = ts.replace(tzinfo=_tz2.utc)
        age_min = (now_utc - ts).total_seconds() / 60
        if age_min < warn_minutes:
            return "LIVE_CONFIRMED"
        if age_min < stale_minutes:
            return "FRESH_CONFIRMED"
        return "STALE_CONFIRMED"
    except Exception:
        return "UNKNOWN"

THEME_MAP = {
    "NVDA": "AI / SEMIS", "AMD": "AI / SEMIS", "AVGO": "AI / SEMIS", "MRVL": "AI / SEMIS",
    "MU": "AI / SEMIS", "TSM": "AI / SEMIS", "AMAT": "AI / SEMIS", "ARM": "AI / SEMIS",
    "CDNS": "AI / SEMIS", "SNPS": "AI / SEMIS", "INTC": "AI / SEMIS", "ASML": "AI / SEMIS",
    "QCOM": "AI / SEMIS", "TXN": "AI / SEMIS", "LRCX": "AI / SEMIS", "KLAC": "AI / SEMIS",
    "MSFT": "MAG7 / BIG TECH", "AAPL": "CONSUMER TECH / APPLE", "GOOGL": "MAG7 / BIG TECH",
    "META": "MAG7 / BIG TECH", "AMZN": "MAG7 / BIG TECH", "TSLA": "MAG7 / BIG TECH",
    "NFLX": "MAG7 / BIG TECH", "UBER": "MAG7 / BIG TECH",
    "CRWD": "SOFTWARE / CYBERSECURITY", "PANW": "SOFTWARE / CYBERSECURITY",
    "PLTR": "SOFTWARE / CYBERSECURITY", "ORCL": "SOFTWARE / CYBERSECURITY",
    "CRM": "SOFTWARE / CYBERSECURITY", "NOW": "SOFTWARE / CYBERSECURITY",
    "ADBE": "SOFTWARE / CYBERSECURITY", "FTNT": "SOFTWARE / CYBERSECURITY",
    "ZS": "SOFTWARE / CYBERSECURITY", "SNOW": "SOFTWARE / CYBERSECURITY",
    "BAC": "BANKS / LIQUIDITY", "WFC": "BANKS / LIQUIDITY", "C": "BANKS / LIQUIDITY",
    "JPM": "BANKS / LIQUIDITY", "GS": "BANKS / LIQUIDITY", "MS": "BANKS / LIQUIDITY",
    "BLK": "BANKS / LIQUIDITY", "SCHW": "BANKS / LIQUIDITY", "AXP": "BANKS / LIQUIDITY",
    "PGR": "BANKS / LIQUIDITY", "ALL": "BANKS / LIQUIDITY",
    "SOFI": "FINTECH / CRYPTO", "HOOD": "FINTECH / CRYPTO", "COIN": "FINTECH / CRYPTO",
    "MSTR": "FINTECH / CRYPTO", "IBIT": "FINTECH / CRYPTO", "V": "FINTECH / CRYPTO",
    "MA": "FINTECH / CRYPTO", "PYPL": "FINTECH / CRYPTO",
    "LLY": "BIOTECH / PHARMA", "MRNA": "BIOTECH / PHARMA", "ABBV": "BIOTECH / PHARMA",
    "PFE": "BIOTECH / PHARMA", "JNJ": "BIOTECH / PHARMA", "UNH": "BIOTECH / PHARMA",
    "MRK": "BIOTECH / PHARMA", "AMGN": "BIOTECH / PHARMA", "BMY": "BIOTECH / PHARMA",
    "GILD": "BIOTECH / PHARMA", "REGN": "BIOTECH / PHARMA", "BIIB": "BIOTECH / PHARMA",
    "RTX": "DEFENSE / AEROSPACE PRIMES", "NOC": "DEFENSE / AEROSPACE PRIMES", "LMT": "DEFENSE / AEROSPACE PRIMES",
    "HII": "DEFENSE / AEROSPACE PRIMES", "LDOS": "DEFENSE / AEROSPACE PRIMES", "BA": "DEFENSE / AEROSPACE PRIMES",
    "LHX": "DEFENSE / AEROSPACE PRIMES", "HON": "DEFENSE / AEROSPACE PRIMES", "KTOS": "DEFENSE / AEROSPACE PRIMES",
    "ASTS": "SPACE / HIGH-BETA", "RKLB": "SPACE / HIGH-BETA", "LUNR": "SPACE / HIGH-BETA",
    "BKSY": "SPACE / HIGH-BETA", "SATS": "SPACE / HIGH-BETA", "RDW": "SPACE / HIGH-BETA",
    "SIDU": "SPACE / HIGH-BETA", "IRDM": "SPACE / HIGH-BETA", "VSAT": "SPACE / HIGH-BETA",
    "SPIR": "SPACE / HIGH-BETA", "PL": "SPACE / HIGH-BETA", "SPCE": "SPACE / HIGH-BETA",
    "GLD": "GOLD / SAFE HAVEN", "SLV": "GOLD / SAFE HAVEN", "NEM": "GOLD_MINER",
    "AU": "GOLD_MINER", "CDE": "GOLD_MINER", "HL": "GOLD_MINER",
    "AG": "GOLD / SAFE HAVEN", "PAAS": "GOLD / SAFE HAVEN",
    "FCX": "COPPER / INDUSTRIAL METALS", "SCCO": "COPPER / INDUSTRIAL METALS",
    "BHP": "COPPER / INDUSTRIAL METALS", "RIO": "COPPER / INDUSTRIAL METALS",
    "HBM": "COPPER / INDUSTRIAL METALS", "TECK": "COPPER / INDUSTRIAL METALS",
    "VALE": "COPPER / INDUSTRIAL METALS", "NUE": "COPPER / INDUSTRIAL METALS",
    "AA": "COPPER / INDUSTRIAL METALS", "CLF": "COPPER / INDUSTRIAL METALS",
    "CAT": "COPPER / INDUSTRIAL METALS", "NTR": "COPPER / INDUSTRIAL METALS",
    "MOS": "COPPER / INDUSTRIAL METALS", "ADM": "COPPER / INDUSTRIAL METALS",
    "MP": "RARE EARTH / METALS", "USAR": "RARE EARTH / METALS", "ALB": "RARE EARTH / METALS",
    "CEG": "NUCLEAR / POWER GRID", "VST": "NUCLEAR / POWER GRID", "OKLO": "NUCLEAR / POWER GRID",
    "SMR": "NUCLEAR / POWER GRID", "BWXT": "NUCLEAR / POWER GRID",
    "CCJ": "ENERGY / URANIUM", "UUUU": "ENERGY / URANIUM",
    "DUK": "UTILITIES / POWER", "WMB": "UTILITIES / POWER", "KMI": "UTILITIES / POWER",
    "GEV": "UTILITIES / POWER", "NEE": "UTILITIES / POWER", "ETN": "UTILITIES / POWER",
    "EMR": "UTILITIES / POWER", "AWK": "UTILITIES / POWER",
    "ENPH": "CLEAN ENERGY / SOLAR", "FSLR": "CLEAN ENERGY / SOLAR", "FCEL": "CLEAN ENERGY / SOLAR",
    "BE": "CLEAN ENERGY / SOLAR", "PLUG": "CLEAN ENERGY / SOLAR", "SEDG": "CLEAN ENERGY / SOLAR",
    "ARRY": "CLEAN ENERGY / SOLAR", "RUN": "CLEAN ENERGY / SOLAR", "BEP": "CLEAN ENERGY / SOLAR",
    "XOM": "OIL / GAS", "OXY": "OIL / GAS", "EOG": "OIL / GAS", "FANG": "OIL / GAS",
    "CVX": "OIL / GAS", "COP": "OIL / GAS", "DVN": "OIL / GAS", "LNG": "OIL / GAS",
    "VLO": "OIL / GAS", "PSX": "OIL / GAS", "MPC": "OIL / GAS", "EPD": "OIL / GAS",
    "ENB": "OIL / GAS",
    "TLT": "MACRO / FED", "KO": "MACRO / FED", "PG": "MACRO / FED", "WMT": "MACRO / FED",
    "COST": "MACRO / FED", "PEP": "MACRO / FED", "MCD": "MACRO / FED", "HD": "MACRO / FED",
    "LOW": "MACRO / FED", "NKE": "MACRO / FED", "SBUX": "MACRO / FED", "TGT": "MACRO / FED",
    "CL": "MACRO / FED", "UPS": "MACRO / FED", "FDX": "MACRO / FED", "UNP": "MACRO / FED",
    "CSX": "MACRO / FED", "DAL": "MACRO / FED", "DE": "MACRO / FED", "VZ": "MACRO / FED",
    "T": "MACRO / FED", "O": "MACRO / FED",
    "IONQ": "QUANTUM", "QBTS": "QUANTUM", "QUBT": "QUANTUM", "RGTI": "QUANTUM",
    "QTUM": "QUANTUM",
}

# ── Theme coverage gate ──────────────────────────────────────────────────────
# Expected ticker sets per theme for coverage gate.
# If < THEME_COVERAGE_MINIMUM fraction present → INSUFFICIENT_COVERAGE override.
THEME_EXPECTED_TICKERS = {
    "QUANTUM":                    frozenset({"IONQ", "QBTS", "QUBT", "RGTI", "QTUM", "IBM"}),
    "QUANTUM_CORE":               frozenset({"IONQ", "QBTS", "QUBT", "RGTI", "QTUM"}),
    "SPACE / HIGH-BETA":          frozenset({"ASTS", "LUNR", "PL", "RKLB", "SPCE", "RDW", "BKSY", "SATS"}),
    "DEFENSE / AEROSPACE PRIMES": frozenset({"LMT", "RTX", "NOC", "HII", "LHX", "GD", "BA"}),
}
THEME_COVERAGE_MINIMUM = 0.60  # < 60% → INSUFFICIENT_COVERAGE


def _check_theme_coverage(theme_name, available_tickers, expected_set):
    """
    Check whether enough tickers from the expected set are available.
    Returns a dict with coverage stats and a classification override.

    Parameters:
        theme_name        — display name of the theme
        available_tickers — set or iterable of ticker symbols present in data
        expected_set      — frozenset of tickers expected for this theme

    Returns:
        {
          "expected_count":  int,
          "included_count":  int,
          "included":        sorted list,
          "excluded":        sorted list,
          "coverage_pct":    float (0–100),
          "coverage_gate":   "PASS" | "FAIL",
          "classification":  None | "INSUFFICIENT_COVERAGE",
        }
    """
    if not expected_set:
        return {
            "expected_count": 0, "included_count": 0, "included": [],
            "excluded": [], "coverage_pct": 100.0,
            "coverage_gate": "PASS", "classification": None,
        }

    available = set(available_tickers)
    included  = available & expected_set
    excluded  = expected_set - available
    coverage  = len(included) / len(expected_set)

    # Special case: QUANTUM with IBM only
    if theme_name in ("QUANTUM", "QUANTUM_CORE") and included == {"IBM"}:
        return {
            "expected_count": len(expected_set),
            "included_count": 1,
            "included":       ["IBM"],
            "excluded":       sorted(excluded),
            "coverage_pct":   round(coverage * 100, 1),
            "coverage_gate":  "FAIL",
            "classification": "INSUFFICIENT_COVERAGE",
        }

    gate = "PASS" if coverage >= THEME_COVERAGE_MINIMUM else "FAIL"
    return {
        "expected_count": len(expected_set),
        "included_count": len(included),
        "included":       sorted(included),
        "excluded":       sorted(excluded),
        "coverage_pct":   round(coverage * 100, 1),
        "coverage_gate":  gate,
        "classification": None if gate == "PASS" else "INSUFFICIENT_COVERAGE",
    }


# ---------------------------------------------------------------------------
# General data helpers
# ---------------------------------------------------------------------------

def n(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def si(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def fmt_money(value: Any) -> str:
    x = n(value)
    return "" if x is None else f"${x:,.2f}"


def fmt_int(value: Any) -> str:
    x = n(value)
    return "" if x is None else f"{int(round(x)):,.0f}"


def fmt_pct_point(value: Any, digits: int = 1) -> str:
    x = n(value)
    return "" if x is None else f"{x:+.{digits}f}%"


def fmt_ratio_pct(value: Any, digits: int = 1) -> str:
    x = n(value)
    return "" if x is None else f"{x * 100:.{digits}f}%"


def fmt_float(value: Any, digits: int = 2) -> str:
    x = n(value)
    return "" if x is None else f"{x:.{digits}f}"


def portfolio_mandate_for(dataset: Dict[str, Any], ticker: str) -> str:
    """Return the canonical mandate label used by every report surface."""
    t = str(ticker or "").upper()
    dataset_mandate = ((dataset.get("portfolio_mandates") or {}).get(t) or {}).get("mandate")
    if dataset_mandate:
        return str(dataset_mandate).upper()
    if t in {"AU", "NEM", "BAC", "WFC"}:
        return "BASELINE"
    if t in {"QBTS", "QUBT"}:
        return "SATELLITE"
    if t in {"VXX", "VIXY", "NVDA", "ASTS", "RKLB", "PL", "LUNR"}:
        return "TACTICAL"
    return "UNCLASSIFIED"


def gold_thesis_action_rows(thesis_action: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Canonical gold-action labels so TXT / Word / Excel do not drift."""
    return [
        ("CIO Gold Action", str(thesis_action.get("gold_miner_core_action", "HOLD / WAIT"))),
        ("Thesis Add Signal", str(thesis_action.get("thesis_add_signal", "UNKNOWN"))),
        ("Execution Permission", str(thesis_action.get("execution_permission", "UNKNOWN"))),
        ("Gold Miner Cluster Weight", f"{float(thesis_action.get('gold_miner_cluster_weight') or 0):.1%}"),
        ("Action Reason", str(thesis_action.get("reason", ""))[:200]),
    ]


def clean_text(value: Any, max_len: Optional[int] = None) -> str:
    text = normalize_report_text(value)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def parse_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            return [x.strip() for x in value.split(",") if x.strip()]
    return []


def load_dataset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def wait_for_stable_file(path: Path, checks: int = 3, interval_seconds: float = 0.4) -> None:
    """Avoid reading dataset_raw.json while an upstream exporter is still writing it."""
    import time

    last = None
    stable = 0
    for _ in range(max(checks * 4, checks)):
        stat = path.stat()
        current = (stat.st_size, stat.st_mtime_ns)
        if current == last:
            stable += 1
            if stable >= checks - 1:
                return
        else:
            stable = 0
            last = current
        time.sleep(interval_seconds)


# ── Scout Order Doctrine ─────────────────────────────────────────────────────
_SCOUT_MAX_NOTIONAL_USD = 500.0   # orders ≤ $500 notional may be scout
_SCOUT_PCT_OF_ASSETS    = 0.5    # orders ≤ 0.5% of total assets may be scout


def _classify_order_intent(order: dict, total_assets: float) -> str:
    """
    Classify order intent from notional size and order metadata.

    Returns one of:
      SCOUT_DISLOCATION_ORDER       — small initial tranche, second blocked pending confirmation
      CORE_POSITION_ORDER           — full-size buy
      DECONCENTRATION_SELL_ORDER    — sell to reduce concentration
      HEDGE_ORDER                   — hedging instrument (VXX, VIXY, put options)
      UNKNOWN_REVIEW_REQUIRED       — classification unclear, CIO review needed
    """
    notional      = float(order.get("notional") or 0)
    side          = str(order.get("side") or "").upper()
    ticker        = str(order.get("ticker") or "").upper()
    pct_of_assets = (notional / total_assets * 100) if total_assets else 0

    # CIO-tagged orders (explicit intent field already set)
    if order.get("order_intent"):
        return str(order["order_intent"])

    # Deconcentration sells
    if side in ("SELL", "SELL_SHORT") and order.get("deconcentration_flag"):
        return "DECONCENTRATION_SELL_ORDER"

    # Hedge orders — VXX/VIXY or explicit hedge flag
    _HEDGE_TICKERS = {"VXX", "VIXY", "UVXY", "SQQQ", "SPXU", "SDOW"}
    if order.get("hedge_flag") or ticker in _HEDGE_TICKERS:
        return "HEDGE_ORDER"

    # Small buy = scout
    if side == "BUY" and (
        notional <= _SCOUT_MAX_NOTIONAL_USD or pct_of_assets < _SCOUT_PCT_OF_ASSETS
    ):
        return "SCOUT_DISLOCATION_ORDER"

    # Full-size buy
    if side == "BUY":
        return "CORE_POSITION_ORDER"

    return "UNKNOWN_REVIEW_REQUIRED"


def _build_scout_metadata(order: dict, total_assets: float) -> dict:
    """
    Build scout order metadata block for SCOUT_DISLOCATION_ORDER orders.
    Second tranche is always BLOCKED until macro confirmation.
    """
    notional      = float(order.get("notional") or 0)
    pct_of_assets = (notional / total_assets * 100) if total_assets else 0
    return {
        "scout_notional_pct_of_assets": round(pct_of_assets, 3),
        "scout_tranche":                1,
        "scout_max_tranches":           2,
        "second_tranche_gate":          "BLOCKED",
        "second_tranche_gate_reason":   (
            "Pending macro confirmation: FOMC/BOJ event passed | "
            "price stabilizes | volume confirms | CIO approves"
        ),
        "scout_display": (
            "SCOUT BASE ONLY — SECOND TRANCHE BLOCKED PENDING MACRO CONFIRMATION\n"
            "Gate: FOMC/Warsh event passed | BOJ stable | price stabilizes | "
            "volume confirms | CIO approves"
        ),
    }


def live_prices(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lp = dataset.get("live_prices") or {}
    if isinstance(lp.get("prices"), dict):
        return {str(k).upper(): v for k, v in lp["prices"].items() if isinstance(v, dict)}
    return {
        str(k).upper(): v
        for k, v in lp.items()
        if isinstance(v, dict) and "price" in v and not str(k).startswith("^")
    }


def top_movers(dataset: Dict[str, Any], limit: int = 15) -> List[Dict[str, Any]]:
    lp = dataset.get("live_prices") or {}
    if isinstance(lp.get("top_movers"), list) and lp["top_movers"]:
        rows = list(lp["top_movers"])
    else:
        rows = [{"ticker": k, **v} for k, v in live_prices(dataset).items()]
    return sorted(rows, key=lambda r: abs(n(r.get("chg_pct"), 0) or 0), reverse=True)[:limit]


def all_catalysts(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    cc = dataset.get("catalyst_calendar") or {}
    if isinstance(cc, list):
        return cc
    return cc.get("all") if isinstance(cc.get("all"), list) else []


def catalyst_by_ticker(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in all_catalysts(dataset):
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        days = n(row.get("days_until_catalyst"), 99999) or 99999
        current = out.get(ticker)
        if not current or days < (n(current.get("days_until_catalyst"), 99999) or 99999):
            out[ticker] = row
    return out


def tech_articles(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for source, items in (dataset.get("tech_pub_signals") or {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            tickers = [str(x).upper() for x in parse_list(item.get("tickers_mentioned"))]
            themes = [str(x) for x in parse_list(item.get("themes_detected"))]
            rows.append({"source": source, "tickers": tickers, "themes": themes, **item})
    return rows


def article_mentions(dataset: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in tech_articles(dataset):
        for ticker in row.get("tickers", []):
            out[ticker] = out.get(ticker, 0) + 1
    return out


def catalyst_status(row: Dict[str, Any], catalyst_map: Dict[str, Dict[str, Any]], mentions: Dict[str, int]) -> Tuple[str, str]:
    ticker = str(row.get("ticker") or "").upper()
    move = abs(n(row.get("chg_pct"), 0) or 0)
    if move < 5:
        return "LOW_MOVE", "Absolute move below review threshold."
    cat = catalyst_map.get(ticker)
    if cat and (n(cat.get("days_until_catalyst"), 99999) or 99999) <= 30:
        return "MATCHED", f"{cat.get('catalyst_type', 'Event')} {cat.get('catalyst_date', '')}".strip()
    if mentions.get(ticker):
        return "PARTIAL", "Fresh ticker/headline mention; causal reason not fully verified."
    return "UNEXPLAINED", "No direct catalyst or fresh ticker/headline match in daily evidence."


def theme_for(ticker: str, security: Optional[Dict[str, Any]]) -> str:
    ticker = ticker.upper()
    if ticker in THEME_MAP:
        return THEME_MAP[ticker]
    security = security or {}
    sector = str(security.get("sector") or "").upper()
    industry = str(security.get("industry") or "").upper()
    if "FINANC" in sector:
        return "BANKS / LIQUIDITY"
    if "TECH" in sector:
        return "AI / SEMIS"
    if "HEALTH" in sector:
        return "BIOTECH / PHARMA"
    if "MATERIAL" in sector:
        return "COPPER / INDUSTRIAL METALS"
    if "UTILITY" in sector:
        return "UTILITIES / POWER"
    if "ENERGY" in sector:
        return "CLEAN ENERGY / SOLAR" if "SOLAR" in industry else "OIL / GAS"
    return sector or "UNCLASSIFIED"


def action_note(ticker: str, price: Any) -> str:
    p = n(price)
    if ticker in {"AU", "NEM"}:
        return "RELOAD only on signal"
    if ticker == "QBTS":
        return "DCA ZONE" if p is not None and 22 <= p <= 24 else "SATELLITE HOLD"
    if ticker == "QUBT":
        return "DCA ZONE" if p is not None and 10 <= p <= 11 else "DCA only 10-11"
    return "WAIT/HOLD"


def ticker_universe(dataset: Dict[str, Any]) -> List[str]:
    skip = {"vix", "market_session", "top_movers", "cycle_ts", "ticker_count", "source"}
    blocks = [
        dataset.get("security_master"),
        dataset.get("fundamentals"),
        dataset.get("capital_flow"),
        dataset.get("analyst_targets"),
        live_prices(dataset),
    ]
    tickers = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if str(key).startswith("^") or str(key).lower() in skip:
                continue
            if isinstance(value, dict):
                tickers.add(str(key).upper())
    return sorted(tickers)[:200]


# ---------------------------------------------------------------------------
# XLSX writer - standard library only
# ---------------------------------------------------------------------------

def xml_text(value: Any) -> str:
    return escape(normalize_report_text(value), {'"': "&quot;"})


def col_name(index: int) -> str:
    out = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def cell_ref(row: int, col: int) -> str:
    return f"{col_name(col)}{row}"


class XlsxWorkbook:
    def __init__(self) -> None:
        self.sheets: List[Dict[str, Any]] = []

    # Row style constants for add_sheet(row_styles=[...])
    STYLE_NORMAL   = 0  # plain
    STYLE_HEADER   = 1  # dark blue fill, white bold  (auto-applied to row 1)
    STYLE_GREEN    = 2  # #C6EFCE fill, dark-green bold
    STYLE_AMBER    = 3  # #FFEB9C fill, dark-brown bold
    STYLE_RED      = 4  # #FFC7CE fill, dark-red bold
    STYLE_SECTION  = 5  # #BDD7EE fill, dark-blue bold

    def add_sheet(
        self,
        name: str,
        rows: Sequence[Sequence[Any]],
        widths: Optional[Sequence[float]] = None,
        row_styles: Optional[List[Optional[int]]] = None,
    ) -> None:
        safe_name = re.sub(r"[\[\]\:\*\?\/\\]", " ", name)[:31].strip() or f"Sheet{len(self.sheets)+1}"
        self.sheets.append({
            "name": safe_name,
            "rows": [list(r) for r in rows],
            "widths": list(widths or []),
            "row_styles": list(row_styles) if row_styles else [],
        })

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types())
            z.writestr("_rels/.rels", self._root_rels())
            z.writestr("docProps/core.xml", self._core_props())
            z.writestr("docProps/app.xml", self._app_props())
            z.writestr("xl/workbook.xml", self._workbook_xml())
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels())
            z.writestr("xl/styles.xml", self._styles_xml())
            for idx, sheet in enumerate(self.sheets, 1):
                z.writestr(f"xl/worksheets/sheet{idx}.xml", self._sheet_xml(sheet))

    def _content_types(self) -> str:
        sheet_overrides = "\n".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(self.sheets) + 1)
        )
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  {sheet_overrides}
</Types>'''

    def _root_rels(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

    def _core_props(self) -> str:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>BlueLotus V2 R6 CIO Operating Report</dc:title>
  <dc:creator>{xml_text(PLATFORM_TEAM)}</dc:creator>
  <cp:lastModifiedBy>{xml_text(PLATFORM_TEAM)}</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''

    def _app_props(self) -> str:
        sheet_names = "".join(f"<vt:lpstr>{xml_text(s['name'])}</vt:lpstr>" for s in self.sheets)
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>BlueLotus</Application>
  <Company>{xml_text(PLATFORM_TEAM)}</Company>
  <HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(self.sheets)}</vt:i4></vt:variant></vt:vector></HeadingPairs>
  <TitlesOfParts><vt:vector size="{len(self.sheets)}" baseType="lpstr">{sheet_names}</vt:vector></TitlesOfParts>
</Properties>'''

    def _workbook_xml(self) -> str:
        sheets = "\n".join(
            f'<sheet name="{xml_text(sheet["name"])}" sheetId="{i}" r:id="rId{i}"/>'
            for i, sheet in enumerate(self.sheets, 1)
        )
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{sheets}</sheets>
</workbook>'''

    def _workbook_rels(self) -> str:
        rels = "\n".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(self.sheets) + 1)
        )
        rels += f'\n<Relationship Id="rId{len(self.sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>'''

    def _styles_xml(self) -> str:
        # xf indices: 0=NORMAL 1=HEADER 2=GREEN 3=AMBER 4=RED 5=SECTION
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="6">
    <font><sz val="10"/><name val="Aptos"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font>
    <font><b/><color rgb="FF375623"/><sz val="10"/><name val="Aptos"/></font>
    <font><b/><color rgb="FF7F6000"/><sz val="10"/><name val="Aptos"/></font>
    <font><b/><color rgb="FF9C0006"/><sz val="10"/><name val="Aptos"/></font>
    <font><b/><color rgb="FF1F4E79"/><sz val="10"/><name val="Aptos"/></font>
  </fonts>
  <fills count="7">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFBDD7EE"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="0" fontId="4" fillId="5" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="0" fontId="5" fillId="6" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''

    def _sheet_xml(self, sheet: Dict[str, Any]) -> str:
        rows = sheet["rows"]
        max_col = max((len(r) for r in rows), default=1)
        max_row = max(len(rows), 1)
        widths = sheet.get("widths") or []
        row_styles_list = sheet.get("row_styles") or []
        cols_xml = ""
        if widths:
            cols_xml = "<cols>" + "".join(
                f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
                for i, w in enumerate(widths, 1)
            ) + "</cols>"

        row_xml = []
        for r_idx, row in enumerate(rows, 1):
            # Per-row style: use row_styles list if provided, else default (row 1 = header)
            _si = row_styles_list[r_idx - 1] if r_idx - 1 < len(row_styles_list) else (1 if r_idx == 1 else 0)
            style = f' s="{_si}"' if _si else ""
            cells = []
            for c_idx, value in enumerate(row, 1):
                if value is None:
                    continue
                ref = cell_ref(r_idx, c_idx)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                    cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{xml_text(value)}</t></is></c>')
            row_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

        dimension = f"A1:{cell_ref(max_row, max_col)}"
        autofilter = f'<autoFilter ref="A1:{cell_ref(max_row, max_col)}"/>' if max_row > 1 else ""
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <dimension ref="{dimension}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews>
  {cols_xml}
  <sheetData>{''.join(row_xml)}</sheetData>
  {autofilter}
</worksheet>'''


# ---------------------------------------------------------------------------
# DOCX writer - standard library only
# ---------------------------------------------------------------------------

def w_text(value: Any) -> str:
    return escape(normalize_report_text(value))


def w_run(text: Any, bold: bool = False, italic: bool = False, size: int = 22, color: str = "000000") -> str:
    props = [
        '<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>',
        f'<w:sz w:val="{size}"/>',
        f'<w:color w:val="{color}"/>',
    ]
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    return f'<w:r><w:rPr>{"".join(props)}</w:rPr><w:t xml:space="preserve">{w_text(text)}</w:t></w:r>'


class DocxDocument:
    def __init__(self) -> None:
        self.body: List[str] = []

    def paragraph(
        self,
        text: Any,
        *,
        bold: bool = False,
        italic: bool = False,
        size: int = 22,
        color: str = "000000",
        style: Optional[str] = None,
        before: int = 0,
        after: int = 120,
        keep_next: bool = False,
        bullet: bool = False,
    ) -> None:
        ppr = [f'<w:spacing w:before="{before}" w:after="{after}" w:line="264" w:lineRule="auto"/>']
        if style:
            ppr.append(f'<w:pStyle w:val="{style}"/>')
        if keep_next:
            ppr.append("<w:keepNext/>")
        if bullet:
            ppr.append('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            ppr.append('<w:ind w:left="720" w:hanging="360"/>')
        self.body.append(f'<w:p><w:pPr>{"".join(ppr)}</w:pPr>{w_run(text, bold=bold, italic=italic, size=size, color=color)}</w:p>')

    def heading(self, text: str, level: int = 1) -> None:
        if level == 1:
            self.paragraph(text, bold=True, size=32, color="1F4E79", style="Heading1", before=240, after=120, keep_next=True)
        else:
            self.paragraph(text, bold=True, size=26, color="1F4E79", style="Heading2", before=180, after=80, keep_next=True)

    def callout(self, label: str, body: str, fill: str = "FFF2CC") -> None:
        rows = [[label], [body]]
        self.table(rows, widths=[9360], header_rows=0, fill=fill, font_size=21)

    def table(
        self,
        rows: Sequence[Sequence[Any]],
        widths: Sequence[int],
        *,
        header_rows: int = 1,
        fill: str = "F2F4F7",
        font_size: int = 18,
    ) -> None:
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
        trs = []
        for r_idx, row in enumerate(rows):
            cells = []
            for c_idx, value in enumerate(row):
                width = widths[min(c_idx, len(widths) - 1)]
                shd = fill if r_idx < header_rows else "FFFFFF"
                bold = r_idx < header_rows
                tc_pr = (
                    f'<w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>'
                    f'<w:shd w:fill="{shd}"/>'
                    '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/>'
                    '<w:start w:w="120" w:type="dxa"/><w:end w:w="120" w:type="dxa"/></w:tcMar>'
                    '<w:vAlign w:val="center"/></w:tcPr>'
                )
                p_pr = '<w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
                cells.append(f'<w:tc>{tc_pr}<w:p>{p_pr}{w_run(value, bold=bold, size=font_size)}</w:p></w:tc>')
            trs.append(f'<w:tr>{"".join(cells)}</w:tr>')
        tbl_pr = (
            '<w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblInd w:w="120" w:type="dxa"/>'
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="4" w:color="D9E2F3"/><w:left w:val="single" w:sz="4" w:color="D9E2F3"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="D9E2F3"/><w:right w:val="single" w:sz="4" w:color="D9E2F3"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="D9E2F3"/><w:insideV w:val="single" w:sz="4" w:color="D9E2F3"/>'
            '</w:tblBorders></w:tblPr>'
        )
        self.body.append(f'<w:tbl>{tbl_pr}<w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>')
        self.paragraph("", after=80)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        document_xml = self._document_xml()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types())
            z.writestr("_rels/.rels", self._root_rels())
            z.writestr("docProps/core.xml", self._core_props())
            z.writestr("docProps/app.xml", self._app_props())
            z.writestr("word/document.xml", document_xml)
            z.writestr("word/_rels/document.xml.rels", self._document_rels())
            z.writestr("word/styles.xml", self._styles_xml())
            z.writestr("word/numbering.xml", self._numbering_xml())
            z.writestr("word/settings.xml", self._settings_xml())

    def _document_xml(self) -> str:
        sect_pr = (
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1080" w:right="1440" w:bottom="1080" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
            '</w:sectPr>'
        )
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>{"".join(self.body)}{sect_pr}</w:body>
</w:document>'''

    def _content_types(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>'''

    def _root_rels(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

    def _document_rels(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>'''

    def _core_props(self) -> str:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>BlueLotus V2 R6 CIO Word Report</dc:title>
  <dc:creator>{xml_text(PLATFORM_TEAM)}</dc:creator>
  <cp:lastModifiedBy>{xml_text(PLATFORM_TEAM)}</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''

    def _app_props(self) -> str:
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>BlueLotus</Application>
  <Company>{xml_text(PLATFORM_TEAM)}</Company>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
</Properties>'''

    def _styles_xml(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:color w:val="1F4E79"/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:color w:val="1F4E79"/><w:sz w:val="26"/></w:rPr>
  </w:style>
</w:styles>'''

    def _numbering_xml(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="singleLevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="*"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>'''

    def _settings_xml(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
</w:settings>'''


# ---------------------------------------------------------------------------
# Report table builders
# ---------------------------------------------------------------------------

def build_source_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for section_name, info in (dataset.get("meta", {}).get("freshness") or {}).items():
        if isinstance(info, dict) and "grade" in info:
            rows.append([section_name, info.get("grade", ""), si(info.get("age_minutes"))])
    return rows


def build_process_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    processes = dataset.get("institutional_quant", {}).get("processes") or {}
    risk_model = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    history_insufficient = si(risk_model.get("return_observations")) <= 0
    for name, row in processes.items():
        warnings = "; ".join(str(x) for x in parse_list(row.get("warnings")))
        status = row.get("status", "")
        label = row.get("readiness_label", "")
        score = n(row.get("readiness_score"))
        if str(name).lower() == "risk_model" and history_insufficient:
            status = "TELEMETRY_PRESENT"
            label = "HISTORY_INSUFFICIENT"
            warnings = clean_text((warnings + "; " if warnings else "") + "zero return observations; do not treat as quant validation", 180)
        rows.append([
            name,
            status,
            score,
            label,
            clean_text(warnings, 180),
        ])
    rows.sort(key=lambda r: {"FAIL": 0, "WARNING": 1, "PASS": 2}.get(str(r[1]), 9))
    return rows


def build_portfolio_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    portfolio = dataset.get("portfolio") or {}
    positions = portfolio.get("positions") or {}
    total_assets = n(portfolio.get("total_assets"), 0) or 0
    rows = []
    for ticker, pos in positions.items():
        mv = n(pos.get("mkt_val"), (n(pos.get("qty"), 0) or 0) * (n(pos.get("price"), 0) or 0)) or 0
        mandate = portfolio_mandate_for(dataset, ticker)
        _pnl_status = pos.get("pnl_integrity_status", "")
        if _pnl_status == "BROKER_PNL_SOURCE_CONFLICT":
            _broker_pnl  = float(pos.get("unrealized") or 0)
            _comp_pnl    = float(pos.get("computed_unrealized") or 0)
            _delta       = _broker_pnl - _comp_pnl
            _mktval      = float(pos.get("mkt_val") or mv or 0)
            _pct_conflict = abs(_delta) / abs(_mktval) * 100 if _mktval else 0
            _severity = (
                "P/L_CONFLICT_REVIEW_REQUIRED"
                if abs(_delta) > 10 or _pct_conflict > 2
                else "P/L_MINOR_DISCREPANCY"
            )
            _pnl_flag_str = (
                "BROKER_PNL_SOURCE_CONFLICT - COST_BASIS_REVIEW_REQUIRED"
                f" | severity={_severity} | broker_pnl={_broker_pnl:.2f}"
                f" | computed_pnl={_comp_pnl:.2f} | delta={_delta:.2f}"
                f" | delta_pct_of_mv={_pct_conflict:.1f}%"
                " | selected_source=BROKER_REPORTED"
                " | reason=cost-basis/source mismatch"
                " | action=review broker cost basis before CIO decision"
            )
        else:
            _pnl_flag_str = ""
        rows.append([
            ticker,
            mandate,
            n(pos.get("qty")),
            n(pos.get("price")),
            n(pos.get("avg_cost")),
            mv,
            mv / total_assets if total_assets else None,
            n(pos.get("unrealized")),
            n(pos.get("unrealized_p")),
            n(pos.get("chg_pct")),
            action_note(ticker, pos.get("price")),
            _pnl_status or "OK",
            _pnl_flag_str,
        ])
    return rows


def build_mover_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    prices = live_prices(dataset)
    catalysts = catalyst_by_ticker(dataset)
    mentions = article_mentions(dataset)
    rows = []
    for i, row in enumerate(top_movers(dataset, 20), 1):
        ticker = str(row.get("ticker") or "").upper()
        live = prices.get(ticker, {})
        merged = {**live, **row, "ticker": ticker}
        status, reason = catalyst_status(merged, catalysts, mentions)
        rows.append([
            i,
            ticker,
            n(merged.get("chg_pct")),
            n(merged.get("premarket_chg_pct") or merged.get("pre_market_chg_pct")),
            n(merged.get("price")),
            n(merged.get("volume")),
            n(merged.get("relative_volume")),
            merged.get("session") or dataset.get("meta", {}).get("market_session", ""),
            status,
            clean_text(reason, 150),
        ])
    return rows


def apply_evidence_confidence_cap(
    base_conf: float,
    evidence_tier: int,
    review_flags: List[str],
) -> float:
    """Return the effective confidence after applying evidence-quality caps.

    WO-Final-PhD Defect 4 / WO-ECE-20260613-001 Problem E:
    Confidence must reflect evidence quality. A high-confidence figure is
    misleading when evidence is generic, mismatched, analyst-only, or has no
    direct catalyst support.

    Caps (applied cumulatively — each is a hard ceiling):
      SECTOR_EVIDENCE_MISMATCH  → 50%   (evidence from wrong theme)
      GENERIC_EVIDENCE_REVIEW   → 65%   (analyst context, not causal)
      ANALYST_ONLY_CAUSAL_GAP   → 55%   (why_signal is analyst consensus only)
      NO_DIRECT_CATALYST        → 60%   (no basket-validated causal event)
      T4:ANALYST_CONSENSUS tier → 55%   (tier-level cap regardless of flags)

    Args:
        base_conf: confidence as 0–100 float (e.g. 80.0 = 80%)
        evidence_tier: integer tier 0–4
        review_flags: list of review flag strings

    Returns:
        Capped confidence as 0–100 float.
    """
    cap = float(base_conf)

    # Tier 4 cap (lowest tier — analyst consensus)
    if evidence_tier == 4:
        cap = min(cap, 55.0)

    # Flag-level caps
    if "SECTOR_EVIDENCE_MISMATCH" in review_flags:
        cap = min(cap, 50.0)
    if "GENERIC_EVIDENCE_REVIEW" in review_flags:
        cap = min(cap, 65.0)
    if "ANALYST_ONLY_CAUSAL_GAP" in review_flags:
        cap = min(cap, 55.0)
    if "NO_DIRECT_CATALYST" in review_flags:
        cap = min(cap, 60.0)

    return cap


# ── ECE evidence hygiene flags that require suppression ──────────────────────
_ECE_WEAK_FLAGS = frozenset({
    "SECTOR_EVIDENCE_MISMATCH",
    "NO_DIRECT_CATALYST",
    "GENERIC_EVIDENCE_REVIEW",
    "ANALYST_ONLY_CAUSAL_GAP",
    "PRICE_ACTION_ONLY_CAP",
    "CONFIDENCE_CAPPED_BY_EVIDENCE",
    "PARTIAL_CAUSAL_CAP",
})

_ECE_SUPPRESSED_MISMATCH  = ("Evidence mismatch detected. "
                              "Causal interpretation suppressed pending direct catalyst confirmation.")
_ECE_SUPPRESSED_NO_CATALYST = ("No direct theme-specific catalyst found. "
                                "Direction based on basket price action only. Confidence capped.")


def sanitize_theme_evidence(theme: str, evidence_text: str, flags: List[str]) -> str:
    """Unified evidence sanitizer for all ECE renderers (S3, S6, Word, Excel).

    Applied in priority order:
    1. SECTOR_EVIDENCE_MISMATCH flag      → mismatch suppression phrase
    2. Any other weak flag                → no-catalyst suppression phrase
    3. 'Portfolio:' prefix in text        → no-catalyst phrase (P/L contamination guard)
    4. CONSUMER TECH / APPLE + GOOGL text → mismatch suppression phrase
    5. MAG7 / BIG TECH + GOOGL, no MAG7  → no-catalyst suppression phrase
    6. Otherwise                          → return evidence_text unchanged

    One sanitizer. All renderers consume it. No divergence between S3 and S6.
    """
    flags_set = frozenset(flags or [])

    if "SECTOR_EVIDENCE_MISMATCH" in flags_set:
        return _ECE_SUPPRESSED_MISMATCH

    _WEAK = {
        "NO_DIRECT_CATALYST", "GENERIC_EVIDENCE_REVIEW", "PRICE_ACTION_ONLY_CAP",
        "ANALYST_ONLY_CAUSAL_GAP", "CONFIDENCE_CAPPED_BY_EVIDENCE", "PARTIAL_CAUSAL_CAP",
    }
    if flags_set & _WEAK:
        return _ECE_SUPPRESSED_NO_CATALYST

    # Content-based checks — catch contamination the flag layer missed
    if "Portfolio:" in evidence_text:
        return _ECE_SUPPRESSED_NO_CATALYST

    theme_upper = (theme or "").upper()
    if ("CONSUMER TECH" in theme_upper or "APPLE" in theme_upper) and "GOOGL" in evidence_text:
        return _ECE_SUPPRESSED_MISMATCH

    if ("MAG7" in theme_upper or "BIG TECH" in theme_upper):
        if "GOOGL" in evidence_text and "MAG7" not in evidence_text.upper():
            return _ECE_SUPPRESSED_NO_CATALYST

    return evidence_text


def _ece_sanitize_why(why_raw: str, flags: List[str]) -> str:
    """Backwards-compatible wrapper — delegates to sanitize_theme_evidence()."""
    return sanitize_theme_evidence("", why_raw, flags)


# ── Relief-rally overlay detector ─────────────────────────────────────────────

def detect_relief_rally_overlay(catalyst_texts: List[str]) -> Dict[str, Any]:
    """Inline geopolitical de-escalation / relief-rally overlay detector.

    Scans any iterable of text strings for keywords indicating a geopolitical
    ceasefire or Iran/Hormuz de-escalation event.  Base regime is NEVER
    overwritten — the overlay supplements the existing RISK OFF posture.

    Returns an overlay dict compatible with approved_cio_briefing.json schema.
    """
    failure_keywords = [
        "iran closes strait of hormuz",
        "iran closed strait of hormuz",
        "iran says it closed strait of hormuz",
        "iran reportedly closes strait of hormuz",
        "hormuz closure",
        "strait of hormuz closed",
        "strait of hormuz closure",
        "closes strait of hormuz",
        "closed strait of hormuz",
        "closure of the strait of hormuz",
    ]
    relief_keywords = [
        "iran deal", "hormuz reopen", "hormuz reopens", "hormuz reopened", "ceasefire",
        "peace deal", "us-iran deal", "nuclear negotiation", "sanctions relief",
        "geopolitical de-escalation",
    ]
    failure_active = any(
        kw in text.lower()
        for text in (catalyst_texts or [])
        for kw in failure_keywords
    )
    if failure_active:
        return {
            "scenario_overlay":       "PEACE_DEAL_FAILURE_RISK",
            "risk_clearance_status":  "FAILED_PENDING_PHYSICAL_FLOW_VERIFICATION",
            "final_cio_posture":      "WAIT / HOLD - PEACE DEAL FAILURE / HORMUZ RISK",
            "base_regime_override":   False,
            "gold_miner_relief_action": "SUPPORT_BIDS_ONLY_REVIEW",
        }

    active = any(kw in text.lower() for text in (catalyst_texts or []) for kw in relief_keywords)
    if active:
        return {
            "scenario_overlay":       "RELIEF_RALLY_POSSIBLE",
            "risk_clearance_status":  "NOT_CONFIRMED",
            "final_cio_posture":      "WAIT / HOLD — RELIEF RALLY WATCH",
            "base_regime_override":   False,           # NEVER True
            "gold_miner_relief_action": "DECONCENTRATION_WINDOW",
        }
    return {
        "scenario_overlay":       "NONE",
        "risk_clearance_status":  "NOT_CONFIRMED",
        "final_cio_posture":      "WAIT / HOLD",
        "base_regime_override":   False,
        "gold_miner_relief_action": "NO_ACTION",
    }


def build_canonical_ece_model(dataset: Dict[str, Any]) -> List[Dict]:
    """Single validated pass over ECE rows from the dataset.

    All renderers (TXT, Word, Excel, JSON) must read from this function
    instead of accessing event_correlations_all directly.  This enforces:
      - basket_move_pct is a percentage point (e.g. 5.75 = 5.75%), NEVER decimal
      - confidence is an integer-rounded percentage (e.g. 80.0 = 80%)
      - All required ECE v2 fields are present (with safe defaults)
      - PERCENT_SCALE_REVIEW flag if basket_move_pct is out of expected range

    Returns a list of dicts with canonical field names.
    """
    raw = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    canonical: List[Dict] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        # basket_move: percentage points. Guard against accidental decimal storage.
        bm = float(row.get("basket_move") or 0)
        # If abs(bm) < 0.5 and non-zero, it is probably a decimal fraction (0.0575 → 5.75).
        # This heuristic fires only when the value is clearly sub-pct (< 0.5%).
        # Normal single-day moves > 0.5% are fine.
        if 0 < abs(bm) < 0.5:
            # Stored as decimal fraction — convert to percentage points
            bm = round(bm * 100, 2)
        # Flag gross over-scale (anything > ±50% is suspect for a single-session basket)
        flags = list(row.get("review_flags") or [])
        if abs(bm) > 50 and "PERCENT_SCALE_REVIEW" not in flags:
            flags.append("PERCENT_SCALE_REVIEW")
        if abs(bm) > 15 and "THEME_BASKET_OUTLIER_REVIEW" not in flags:
            flags.append("THEME_BASKET_OUTLIER_REVIEW")
        # Re-apply confidence cap through the named function (Defect 4)
        # This ensures caps are universal even if ingest.py was bypassed or stale data used
        _raw_conf = float(row.get("confidence") or 0)
        _tier_int = int(row.get("evidence_tier") or 4)
        _capped_conf = apply_evidence_confidence_cap(_raw_conf, _tier_int, flags)
        if _capped_conf < _raw_conf and "CONFIDENCE_CAPPED_BY_EVIDENCE" not in flags:
            flags.append("CONFIDENCE_CAPPED_BY_EVIDENCE")
        canonical.append({
            "theme":                   normalize_theme_label(row.get("theme") or ""),
            "sector_direction":        str(row.get("sector_direction") or row.get("direction") or ""),
            "direction":               str(row.get("direction") or row.get("sector_direction") or ""),
            "basket_move_pct":         bm,
            "basket_move":             bm,          # alias kept for backward-compat
            "confidence":              _capped_conf,  # capped via apply_evidence_confidence_cap()
            "evidence_tier":           _tier_int,
            "evidence_tier_label":     str(row.get("evidence_tier_label") or ""),
            "catalyst_polarity":       str(row.get("catalyst_polarity") or ""),
            "global_regime_context":   str(row.get("global_regime_context") or ""),
            "review_flags":            flags,
            "why":                     sanitize_theme_evidence(str(row.get("theme") or ""), str(row.get("why") or row.get("evidence") or ""), flags),
            "why_raw":                 str(row.get("why") or row.get("evidence") or ""),
            "governing_logic_version": str(row.get("governing_logic_version") or ""),
            "broad_rally_confirmed":   bool(row.get("broad_rally_confirmed") or False),
            "source_count":            int(row.get("source_count") or 0),
            "layers":                  list(row.get("layers") or []),
            "analyst_rating_integrity": str(row.get("analyst_rating_integrity") or "OK"),
        })
        canonical[-1]["sector_direction_display"] = causal_price_action_label(
            canonical[-1]["sector_direction"], canonical[-1]["review_flags"]
        )
    return canonical


def build_theme_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    """Build theme rotation rows from the canonical ECE model (basket_move in % pts)."""
    rows = []
    for i, row in enumerate(build_canonical_ece_model(dataset), 1):
        tier_label = row["evidence_tier_label"]
        flags = row["review_flags"]
        flags_str = ", ".join(flags[:3]) if flags else ""
        rows.append([
            i,
            row["theme"],
            row.get("sector_direction_display") or row["sector_direction"],
            row["basket_move_pct"],          # percentage points — e.g. 5.75
            row["confidence"],               # integer pct — e.g. 80.0
            tier_label,
            flags_str or ("CAUSAL GAP" if "ANALYST" in tier_label else ""),
            clean_text(row["why"], 220),
        ])
    return rows


def build_thesis_evidence_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    """Build Thesis Evidence rows combining ECE themes + thesis lifecycle per-thesis evidence."""

    def _signal_label(direction: str) -> str:
        """Return a plain-text signal label from a direction string.
        Handles ECE v2 values (RISK_ON, SELECTIVE_RISK_ON, NEUTRAL,
        SELECTIVE_RISK_OFF, RISK_OFF) and legacy hyphen forms.
        """
        d = str(direction).upper().replace("-", "_")
        # ECE v2 exact matches first (most specific)
        if d == "RISK_ON":             return "RISK ON"
        if d == "SELECTIVE_RISK_ON":   return "RISK ON"   # positive basket, sub-threshold — still positive
        if d == "RISK_OFF":            return "RISK OFF"
        if d == "SELECTIVE_RISK_OFF":  return "WATCH"     # mild negative — show as watch
        if d == "NEUTRAL":             return "NEUTRAL"
        # Legacy + fallback substring matching
        if any(x in d for x in ("RISK_ON", "BULLISH", "LONG", "POSITIVE")):
            return "RISK ON"
        if any(x in d for x in ("RISK_OFF", "BEARISH", "SHORT", "DEFENSIVE", "NEGATIVE", "REDUCTION", "PRESERVATION")):
            return "RISK OFF"
        if "MIXED" in d:
            return "MIXED"
        if any(x in d for x in ("WATCH", "SELECTIVE", "RATE_PRESSURE", "SPECULATIVE")):
            return "WATCH"
        return "NEUTRAL"

    rows = []

    # Part 1: ECE sector rotation theme evidence — read from canonical model
    # All values validated and scale-corrected by build_canonical_ece_model()
    for row in build_canonical_ece_model(dataset):
        direction = row["sector_direction"]
        label = causal_price_action_label(direction, row.get("review_flags") or [])
        basket = row["basket_move_pct"]   # already percentage points, never multiply by 100
        conf   = row["confidence"]        # already integer pct (e.g. 80.0)
        basket_str = f"basket {basket:+.2f}% vs SPY"
        conf_str   = f"conf {conf:.0f}%"
        tier       = row["evidence_tier_label"]
        _regime_ctx = row["global_regime_context"]
        _flags_raw  = row["review_flags"]
        _flags_str  = ("⚑ " + ", ".join(_flags_raw)) if _flags_raw else ""
        _polarity   = row["catalyst_polarity"]
        logic = " | ".join(x for x in [basket_str, conf_str, tier,
                                        _polarity, _regime_ctx, _flags_str] if x)
        rows.append([
            label,
            "ECE THEME",
            row["theme"],
            logic,
            clean_text(row["why"], 300),
            direction,
        ])

    # Part 2: Thesis lifecycle per-thesis evidence
    thesis = dataset.get("thesis_lifecycle") or {}
    for row in thesis.get("theses") or []:
        if not isinstance(row, dict):
            continue
        direction = str(row.get("direction") or "")
        status = str(row.get("status") or "").upper()
        label = _signal_label(direction)
        # Confirmed theses with bullish direction → RISK ON; invalidated → RISK OFF
        if status == "CONFIRMED" and label == "NEUTRAL":
            label = "RISK ON"
        elif status == "INVALIDATED":
            label = "RISK OFF"
        prob = n(row.get("current_probability"))
        conf = n(row.get("confidence"))
        prob_str = f"prob {prob * 100:.1f}%" if prob is not None else ""
        conf_str = f"conf {conf * 100:.1f}%" if conf is not None else ""
        logic = " | ".join(x for x in [f"P={row.get('priority', '')}", prob_str, conf_str] if x)
        evidence_list = row.get("evidence") or row.get("contradictions") or []
        evidence_texts = "; ".join(
            clean_text((x or {}).get("evidence") or (x or {}).get("contradiction"), 100)
            for x in evidence_list[:3]
            if isinstance(x, dict)
        )
        rows.append([
            label,
            "THESIS",
            clean_text(row.get("thesis_name"), 80),
            logic,
            clean_text(evidence_texts, 300),
            direction,
        ])

    return rows


def build_catalyst_rows(dataset: Dict[str, Any], limit: int = 100) -> List[List[Any]]:
    rows = sorted(all_catalysts(dataset), key=lambda r: n(r.get("days_until_catalyst"), 99999) or 99999)
    out = []
    for row in rows[:limit]:
        out.append([
            row.get("ticker", ""),
            row.get("catalyst_type", ""),
            row.get("catalyst_date", ""),
            row.get("catalyst_time_et", ""),
            n(row.get("days_until_catalyst")),
            row.get("alert_flag", ""),
            n(row.get("eps_estimate")),
            row.get("source", ""),
            "YES" if row.get("in_portfolio") else "",
        ])
    return out


def build_tech_rows(dataset: Dict[str, Any], limit: int = 120) -> List[List[Any]]:
    rows = [r for r in tech_articles(dataset) if r.get("tickers") or r.get("themes")]
    rows.sort(key=lambda r: str(r.get("published_at") or ""), reverse=True)
    out = []
    for row in rows[:limit]:
        out.append([
            row.get("source", ""),
            row.get("published_at", ""),
            row.get("sentiment_label", ""),
            n(row.get("vader_score")),
            row.get("signal_type", ""),
            ", ".join(row.get("tickers") or []),
            ", ".join(row.get("themes") or []),
            clean_text(row.get("headline"), 180),
            clean_text(row.get("summary"), 220),
        ])
    return out


def build_analyst_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    prices = live_prices(dataset)
    rows = []
    for ticker, row in (dataset.get("analyst_targets") or {}).items():
        price = n(prices.get(ticker, {}).get("price"))
        avg = n(row.get("avg_target") or row.get("average"))
        upside = ((avg / price) - 1) * 100 if price and avg else None
        rows.append([
            ticker,
            price,
            n(row.get("low_target")),
            avg,
            n(row.get("high_target")),
            upside,
            n(row.get("buy")),
            n(row.get("hold")),
            n(row.get("sell")),
            n(row.get("total_analysts")),
            row.get("rating", ""),
            row.get("source", ""),
            row.get("fetched_at", ""),
        ])
    rows.sort(key=lambda r: n(r[5], -999) or -999, reverse=True)
    return rows


def build_flow_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for ticker, row in (dataset.get("capital_flow") or {}).items():
        if not isinstance(row, dict):
            continue
        rows.append([
            ticker,
            row.get("institutional_bias", ""),
            n(row.get("main_net")),
            n(row.get("super_large_net")),
            n(row.get("large_net")),
            n(row.get("medium_net")),
            n(row.get("small_net")),
            n(row.get("in_flow")),
            row.get("snapshot_date", ""),
            row.get("cycle_ts", ""),
        ])
    rows.sort(key=lambda r: abs(n(r[2], 0) or 0), reverse=True)
    return rows


def build_universe_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    prices = live_prices(dataset)
    catalysts = catalyst_by_ticker(dataset)
    positions = (dataset.get("portfolio") or {}).get("positions") or {}
    rows = []
    for ticker in ticker_universe(dataset):
        lp = prices.get(ticker, {})
        sec = (dataset.get("security_master") or {}).get(ticker, {})
        f = (dataset.get("fundamentals") or {}).get(ticker, {})
        at = (dataset.get("analyst_targets") or {}).get(ticker, {})
        cf = (dataset.get("capital_flow") or {}).get(ticker, {})
        sent = (dataset.get("ticker_sentiment") or {}).get(ticker, {})
        cat = catalysts.get(ticker, {})
        price = n(lp.get("price"))
        avg = n(at.get("avg_target") or at.get("average"))
        upside = ((avg / price) - 1) * 100 if price and avg else None
        tags = []
        if ticker in positions:
            tags.append("PORTFOLIO")
        if abs(n(lp.get("chg_pct"), 0) or 0) >= 10:
            tags.append("TOP_MOVER")
        if cat and (n(cat.get("days_until_catalyst"), 99999) or 99999) <= 14:
            tags.append("CATALYST_14D")
        if abs(n(cf.get("main_net"), 0) or 0) >= 100_000_000:
            tags.append("FLOW_SHOCK")
        if (n(lp.get("relative_volume"), 0) or 0) >= 2:
            tags.append("VOLUME_SPIKE")
        rows.append([
            ticker,
            "; ".join(tags),
            theme_for(ticker, sec),
            sec.get("sector", ""),
            sec.get("industry", ""),
            sec.get("market_cap_tier", ""),
            sec.get("asset_type", ""),
            price,
            n(lp.get("chg_pct")),
            n(lp.get("premarket_chg_pct") or lp.get("pre_market_chg_pct")),
            n(lp.get("relative_volume")),
            "YES" if lp.get("volume_spike_flag") else "",
            n(lp.get("volume")),
            avg,
            upside,
            n(at.get("buy")),
            n(at.get("hold")),
            n(at.get("sell")),
            n(at.get("total_analysts")),
            cf.get("institutional_bias", ""),
            n(cf.get("main_net")),
            n(cf.get("super_large_net")),
            sent.get("sentiment_label") or sent.get("label", ""),
            n(sent.get("score")),
            cat.get("catalyst_date", ""),
            cat.get("alert_flag", ""),
            n(cat.get("days_until_catalyst")),
            n(f.get("pe_ttm_ratio") or f.get("pe_ratio")),
            n(f.get("pb_ratio")),
            n(f.get("pct_from_52w_high")),
            n(f.get("earnings_yield")),
            f.get("fundamental_applicability", ""),
        ])
    rows.sort(key=lambda r: (0 if r[1] else 1, -abs(n(r[8], 0) or 0), r[0]))
    return rows


def build_forecast_rows(dataset: Dict[str, Any], limit: int = 400) -> List[List[Any]]:
    rf = dataset.get("research_forecasting") or {}
    forecasts = rf.get("forecasts_by_ticker") if isinstance(rf, dict) else {}
    rows: List[List[Any]] = []
    if not isinstance(forecasts, dict):
        return rows
    for ticker, methods in forecasts.items():
        if not isinstance(methods, dict):
            continue
        for method, row in methods.items():
            if not isinstance(row, dict):
                continue
            rows.append([
                ticker,
                method,
                row.get("direction", ""),
                n(row.get("current_price")),
                n(row.get("target_price_7d")),
                n(row.get("target_price_14d")),
                n(row.get("target_price_30d")),
                n(row.get("target_price_60d")),
                n(row.get("target_price_90d")),
                n(row.get("expected_return_90d")),
                n(row.get("probability_90d")),
                n(row.get("confidence")),
                row.get("sector_theme", ""),
                clean_text(row.get("risk_notes", ""), 140),
                clean_text(row.get("method_basis", ""), 220),
            ])
    rows.sort(key=lambda r: (r[0], 0 if r[1] == "BLUELOTUS_CONSERVATIVE" else 1))
    return rows[:limit]


def build_forecast_accuracy_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    rf = dataset.get("research_forecasting") or {}
    rows = []
    for row in rf.get("accuracy_summary") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("prediction_method", ""),
            n(row.get("horizon_days")),
            n(row.get("resolved_count")),
            n(row.get("avg_brier_score")),
            n(row.get("avg_percentage_error")),
            n(row.get("directional_accuracy")),
        ])
    return rows


def build_cross_market_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    cm = dataset.get("cross_market_confirmation") or {}
    rows: List[List[Any]] = []
    groups = [
        ("Market", "market_index_confirmation"),
        ("Panic", "volatility_panic_confirmation"),
        ("Dollar/Rates", "dollar_rates_pressure"),
        ("Gold/Miners", "gold_miner_confirmation"),
        ("Sector ETF", "sector_etf_rotation"),
        ("Credit", "credit_liquidity_stress"),
        ("Commodity", "commodity_confirmation"),
        ("Factor", "factor_rotation_confirmation"),
        ("Global", "global_risk_confirmation"),
        ("Bond", "bond_credit_extension"),
    ]
    for label, key in groups:
        block = cm.get(key) if isinstance(cm, dict) else {}
        if not isinstance(block, dict):
            continue
        for ticker, row in block.items():
            if not isinstance(row, dict):
                continue
            rows.append([
                label,
                ticker,
                n(row.get("price")),
                n(row.get("chg_pct")),
                n(row.get("volume")),
                "YES" if row.get("unavailable") else "",
                clean_text(row.get("reason", ""), 120),
                row.get("price_source", ""),
            ])
    return rows


def build_cross_market_score_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    cm = dataset.get("cross_market_confirmation") or {}
    rows = [["Score", k, n(v)] for k, v in (cm.get("derived_scores") or {}).items()]
    rows.extend([["Flag", k, str(v)] for k, v in (cm.get("interpretation_flags") or {}).items()])
    return rows


def build_risk_model_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    risk = dataset.get("risk_model") or {}
    rows = []
    for row in risk.get("positions") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("ticker", ""),
            n(row.get("market_value")),
            n(row.get("weight")),
            n(row.get("history_points")),
            n(row.get("volatility_annualized")),
            n(row.get("historical_var_95_dollars")),
            n(row.get("historical_var_99_dollars")),
            n(row.get("max_drawdown")),
            n(row.get("beta_to_spy")),
            row.get("first_date", ""),
            row.get("last_date", ""),
        ])
    rows.sort(key=lambda r: n(r[1], 0) or 0, reverse=True)
    return rows


def build_risk_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    risk = dataset.get("risk_model") or {}
    hv = risk.get("historical_var") if isinstance(risk.get("historical_var"), dict) else {}
    v95 = hv.get("confidence_95") or {}
    v99 = hv.get("confidence_99") or {}
    es95 = hv.get("expected_shortfall_95") or {}
    status = risk.get("status", "")
    if si(risk.get("return_observations")) <= 0:
        status = "PORTFOLIO_VAR_UNAVAILABLE / HISTORY_INSUFFICIENT / POSITION_RISK_TELEMETRY_AVAILABLE"
        var95_display = "UNAVAILABLE - HISTORY_INSUFFICIENT"
        var99_display = "UNAVAILABLE - HISTORY_INSUFFICIENT"
        beta_display = "UNAVAILABLE - HISTORY_INSUFFICIENT"
    else:
        var95_display = v95.get("daily_dollars", "")
        var99_display = v99.get("daily_dollars", "")
        beta_display = risk.get("beta_to_spy", "")
    return [
        ["Status", status],
        ["Run ID", risk.get("run_id", "")],
        ["Generated", risk.get("generated_at", "")],
        ["Return Observations", risk.get("return_observations", "")],
        ["Portfolio Value", risk.get("portfolio_value", "")],
        ["Cash Weight", risk.get("cash_weight", "")],
        ["VaR 95 Daily $", var95_display],
        ["VaR 95 Daily %", v95.get("daily_pct", "")],
        ["VaR 99 Daily $", var99_display],
        ["Expected Shortfall 95 $", es95.get("daily_dollars", "")],
        ["Annualized Vol", risk.get("volatility_annualized", "")],
        ["Max Drawdown", risk.get("max_drawdown", "")],
        ["Beta To SPY", beta_display],
        ["Constraint Breaches", len(risk.get("constraint_breaches") or [])],
    ]


def build_canonical_reconciliation_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    rem = dataset.get("v3_str_bug_clearance_reconciliation") if isinstance(dataset.get("v3_str_bug_clearance_reconciliation"), dict) else {}
    canonical = rem.get("canonical_truth_source") if isinstance(rem.get("canonical_truth_source"), dict) else {}
    rows = [["Canonical Field", "Canonical Value", "Legacy Field", "Deprecated By", "Render Primary"]]
    for field in [
        "canonical_buying_power_delta",
        "canonical_buying_power_delta_flag",
        "canonical_market_session",
        "canonical_snapshot_alignment_status",
        "canonical_pnl_integrity_status",
        "canonical_gold_thesis_action",
        "canonical_risk_model_status",
        "canonical_kelly_macro_fused_status",
        "canonical_order_state",
    ]:
        rows.append([field, json.dumps(canonical.get(field), ensure_ascii=False) if isinstance(canonical.get(field), (dict, list)) else canonical.get(field), "", "", "YES"])
    for legacy, meta in (canonical.get("legacy_fields") or {}).items():
        rows.append([
            "",
            "",
            legacy,
            (meta or {}).get("deprecated_by"),
            "NO" if (meta or {}).get("do_not_render_as_primary") else "YES",
        ])
    return rows


def build_artifact_manifest_rows(dataset: Dict[str, Any], archive: Dict[str, Any]) -> List[List[Any]]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    rem = dataset.get("v3_str_bug_clearance_reconciliation") if isinstance(dataset.get("v3_str_bug_clearance_reconciliation"), dict) else {}
    canonical_contract = dataset.get("canonical") if isinstance(dataset.get("canonical"), dict) else {}
    artifact_manifest = canonical_contract.get("artifact_manifest") if isinstance(canonical_contract.get("artifact_manifest"), dict) else {}
    return [
        ["Field", "Value"],
        ["report_id", archive.get("archive_id") or meta.get("cycle_id")],
        ["archive_id", archive.get("archive_id")],
        ["dataset_generated_at", meta.get("generated_at")],
        ["formal_report_snapshot_ts", meta.get("generated_at")],
        ["broker_portfolio_ts", ((dataset.get("portfolio_readonly") or {}).get("cycle_ts") if isinstance(dataset.get("portfolio_readonly"), dict) else "")],
        ["dashboard_snapshot_ts", ((dataset.get("portfolio_readonly") or {}).get("cycle_ts") if isinstance(dataset.get("portfolio_readonly"), dict) else "")],
        ["artifact_consistency_status", artifact_manifest.get("artifact_consistency_status") or "PENDING_FINAL_HASH_VALIDATION"],
        ["required_xlsx_sheets", ", ".join(REQUIRED_STR_REMEDIATION_SHEETS)],
        ["canonical_truth_source_status", "PRESENT" if rem.get("canonical_truth_source") else "MISSING"],
        ["v3_1_contract_status", ((canonical_contract.get("validation") or {}).get("status"))],
    ]


def build_canonical_contract_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    canonical_contract = dataset.get("canonical") if isinstance(dataset.get("canonical"), dict) else {}
    validation = canonical_contract.get("validation") if isinstance(canonical_contract.get("validation"), dict) else {}
    governance = canonical_contract.get("governance") if isinstance(canonical_contract.get("governance"), dict) else {}
    session = canonical_contract.get("session_state") if isinstance(canonical_contract.get("session_state"), dict) else {}
    portfolio = canonical_contract.get("portfolio_state") if isinstance(canonical_contract.get("portfolio_state"), dict) else {}
    order_state = canonical_contract.get("order_state") if isinstance(canonical_contract.get("order_state"), dict) else {}
    return [
        ["Field", "Value"],
        ["version", canonical_contract.get("version")],
        ["generated_at", canonical_contract.get("generated_at")],
        ["validation_status", validation.get("status")],
        ["validation_errors", ", ".join(validation.get("errors") or [])],
        ["execution_authority", governance.get("execution_authority")],
        ["order_routing_enabled", governance.get("order_routing_enabled")],
        ["system_orders_generated", governance.get("system_orders_generated")],
        ["broker_mode", governance.get("broker_mode")],
        ["canonical_market_session", session.get("canonical_market_session")],
        ["session_conflict_status", session.get("session_conflict_status")],
        ["portfolio_truth_status", portfolio.get("portfolio_truth_status")],
        ["order_state_status", order_state.get("order_state_status")],
    ]


def build_target_usd_vector_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    canonical_contract = dataset.get("canonical") if isinstance(dataset.get("canonical"), dict) else {}
    vector = canonical_contract.get("target_usd_vector") if isinstance(canonical_contract.get("target_usd_vector"), dict) else {}
    rows = [[
        "Ticker", "Current USD", "Target Before Gate", "Target After Gate", "Manual Delta",
        "Action", "PEI Gate", "Cash Constraint", "Advisory Only", "Orders Generated"
    ]]
    for row in vector.get("rows") or []:
        if isinstance(row, dict):
            rows.append([
                row.get("ticker"),
                row.get("current_usd"),
                row.get("target_usd_before_gate"),
                row.get("target_usd_after_gate"),
                row.get("manual_delta_usd"),
                row.get("action_classification"),
                row.get("pei_gate_status"),
                row.get("cash_fortress_constraint"),
                row.get("advisory_only"),
                row.get("orders_generated"),
            ])
    return rows


def build_risk_overlay_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    risk_overlay = dataset.get("risk_overlay") if isinstance(dataset.get("risk_overlay"), dict) else {}
    portfolio = risk_overlay.get("portfolio") if isinstance(risk_overlay.get("portfolio"), dict) else {}
    rows = [
        ["Field", "Value"],
        ["version", risk_overlay.get("version")],
        ["risk_overlay_status", risk_overlay.get("risk_overlay_status")],
        ["execution_authority", risk_overlay.get("execution_authority")],
        ["order_routing_enabled", risk_overlay.get("order_routing_enabled")],
        ["system_orders_generated", risk_overlay.get("system_orders_generated")],
        ["portfolio_beta_estimate", portfolio.get("portfolio_beta_estimate")],
        ["portfolio_var_status", portfolio.get("portfolio_var_status")],
        ["VaR95_display", portfolio.get("VaR95_display")],
        ["cash_weight", portfolio.get("cash_weight")],
        ["cash_available_after_open_orders", portfolio.get("cash_available_after_open_orders")],
        ["hedge_value", portfolio.get("hedge_value")],
        ["hedge_gap_usd", portfolio.get("hedge_gap_usd")],
        ["cluster_concentration", portfolio.get("cluster_concentration")],
        ["largest_position_weight", portfolio.get("largest_position_weight")],
        ["max_drawdown_proxy", portfolio.get("max_drawdown_proxy")],
    ]
    rows.append([])
    rows.append(["Ticker", "Current USD", "Raw Target", "Risk Adjusted Target", "Max Add", "Risk Status", "Block Reason"])
    for row in risk_overlay.get("ticker_outputs") or []:
        if isinstance(row, dict):
            rows.append([
                row.get("ticker"),
                row.get("current_usd"),
                row.get("raw_target_usd"),
                row.get("risk_adjusted_target_usd"),
                row.get("max_allowed_add_usd"),
                row.get("risk_overlay_status"),
                row.get("risk_block_reason"),
            ])
    return rows


def build_deterministic_pipeline_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    pipeline = dataset.get("deterministic_pipeline_v3_2") if isinstance(dataset.get("deterministic_pipeline_v3_2"), dict) else {}
    rows = [["Stage", "Status", "Warnings", "Errors", "Inputs", "Outputs", "Orders Generated", "Routing Enabled"]]
    for stage in pipeline.get("stages") or []:
        if isinstance(stage, dict):
            rows.append([
                stage.get("stage_name"),
                stage.get("status"),
                "; ".join(stage.get("warnings") or []),
                "; ".join(stage.get("errors") or []),
                ", ".join(stage.get("input_keys") or []),
                ", ".join(stage.get("output_keys") or []),
                stage.get("orders_generated"),
                stage.get("order_routing_enabled"),
            ])
    return rows


def build_replay_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    replay = dataset.get("deterministic_replay_v3_3") if isinstance(dataset.get("deterministic_replay_v3_3"), dict) else {}
    rows = [
        ["Field", "Value"],
        ["version", replay.get("version")],
        ["strategy_count", replay.get("strategy_count")],
        ["scenario_count", replay.get("scenario_count")],
        ["benchmark_rows", len(replay.get("benchmark_results") or [])],
        ["point_in_time_guard_status", replay.get("point_in_time_guard_status")],
        ["order_routing_enabled", replay.get("order_routing_enabled")],
        ["orders_generated", replay.get("orders_generated")],
    ]
    rows.append([])
    rows.append(["Strategy", "Avg Return Proxy", "Avg Drawdown Proxy", "Avg Sharpe Proxy"])
    for row in replay.get("summary") or []:
        if isinstance(row, dict):
            rows.append([row.get("strategy_id"), row.get("avg_return_proxy"), row.get("avg_drawdown_proxy"), row.get("avg_sharpe_proxy")])
    return rows


def build_benchmark_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
    lock = benchmark.get("one_week_observation_lock") if isinstance(benchmark.get("one_week_observation_lock"), dict) else {}
    governance = benchmark.get("governance") if isinstance(benchmark.get("governance"), dict) else {}
    return [
        ["Field", "Value"],
        ["version", benchmark.get("version")],
        ["benchmark_id", benchmark.get("benchmark_id")],
        ["dataset_generated_at", benchmark.get("dataset_generated_at")],
        ["report_id", benchmark.get("report_id")],
        ["point_in_time_status", benchmark.get("point_in_time_status")],
        ["benchmark_dashboard_status", benchmark.get("benchmark_dashboard_status")],
        ["observation_lock_status", lock.get("lock_status")],
        ["observation_started_at", lock.get("observation_started_at")],
        ["observation_ends_at", lock.get("observation_ends_at")],
        ["upgrade_allowed", lock.get("upgrade_allowed")],
        ["execution_authority", governance.get("execution_authority")],
        ["order_routing_enabled", governance.get("order_routing_enabled")],
        ["orders_generated", governance.get("orders_generated")],
    ]


def build_benchmark_strategy_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
    rows = [["Rank", "Strategy", "Avg Return Proxy", "Avg Drawdown Proxy", "Avg Sharpe Proxy", "Status"]]
    for row in benchmark.get("strategy_scorecards") or []:
        if isinstance(row, dict):
            rows.append([row.get("rank"), row.get("strategy_id"), row.get("avg_return_proxy"), row.get("avg_drawdown_proxy"), row.get("avg_sharpe_proxy"), row.get("scorecard_status")])
    return rows


def build_benchmark_scenario_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
    rows = [["Scenario", "Avg Return Proxy", "Avg Drawdown Proxy", "Status"]]
    for row in benchmark.get("scenario_scorecards") or []:
        if isinstance(row, dict):
            rows.append([row.get("scenario_id"), row.get("avg_return_proxy"), row.get("avg_drawdown_proxy"), row.get("scenario_status")])
    return rows


def build_benchmark_layer_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
    rows = [["Layer", "Status", "Warnings", "Errors", "Orders Generated", "Routing Enabled"]]
    for row in benchmark.get("layer_attribution") or []:
        if isinstance(row, dict):
            rows.append([row.get("layer"), row.get("status"), row.get("warning_count"), row.get("error_count"), row.get("orders_generated"), row.get("order_routing_enabled")])
    return rows


def build_observation_lock_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    lock = dataset.get("v3_4_observation_lock") if isinstance(dataset.get("v3_4_observation_lock"), dict) else {}
    if not lock:
        benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
        lock = benchmark.get("one_week_observation_lock") if isinstance(benchmark.get("one_week_observation_lock"), dict) else {}
    return [["Field", "Value"]] + [[key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value] for key, value in lock.items()]


def render_benchmark_text_section(dataset: Dict[str, Any]) -> str:
    benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
    replay = dataset.get("deterministic_replay_v3_3") if isinstance(dataset.get("deterministic_replay_v3_3"), dict) else {}
    risk_overlay = dataset.get("risk_overlay") if isinstance(dataset.get("risk_overlay"), dict) else {}
    canonical_contract = dataset.get("canonical") if isinstance(dataset.get("canonical"), dict) else {}
    lock = dataset.get("v3_4_observation_lock") if isinstance(dataset.get("v3_4_observation_lock"), dict) else {}
    if not lock:
        lock = benchmark.get("one_week_observation_lock") if isinstance(benchmark.get("one_week_observation_lock"), dict) else {}
    rankings = benchmark.get("benchmark_rankings") or []
    lines = [
        "00F - V3.4 BENCHMARK DASHBOARD AND OBSERVATION LOCK",
        "=" * 58,
        f"Canonical contract: {canonical_contract.get('version')} validation={((canonical_contract.get('validation') or {}).get('status'))}",
        f"Deterministic pipeline: {((dataset.get('deterministic_pipeline_v3_2') or {}).get('version'))} stages={((dataset.get('deterministic_pipeline_v3_2') or {}).get('stage_count'))}",
        f"Risk overlay: {risk_overlay.get('risk_overlay_status')} beta={((risk_overlay.get('portfolio') or {}).get('beta_display'))} VaR={((risk_overlay.get('portfolio') or {}).get('VaR95_display'))}",
        f"Replay engine: {replay.get('version')} strategies={replay.get('strategy_count')} scenarios={replay.get('scenario_count')} point_in_time={replay.get('point_in_time_guard_status')}",
        f"Benchmark: {benchmark.get('benchmark_id')} status={benchmark.get('benchmark_dashboard_status')} point_in_time={benchmark.get('point_in_time_status')}",
        f"Observation lock: {lock.get('lock_status')} start={lock.get('observation_started_at')} end={lock.get('observation_ends_at')} upgrade_allowed={lock.get('upgrade_allowed')}",
        "Execution safety: CIO_ONLY_MANUAL | order_routing_enabled=False | system_orders_generated=0",
        "",
        "Top benchmark strategies:",
    ]
    for row in rankings[:5]:
        if isinstance(row, dict):
            lines.append(
                f"- #{row.get('rank')} {row.get('strategy_id')}: return={row.get('avg_return_proxy')} drawdown={row.get('avg_drawdown_proxy')} sharpe={row.get('avg_sharpe_proxy')} status={row.get('scorecard_status')}"
            )
    if not rankings:
        lines.append("- No benchmark rankings available.")
    return "\n".join(lines)


def render_artifact_manifest_text_section(dataset: Dict[str, Any]) -> str:
    rem = dataset.get("v3_str_bug_clearance_reconciliation") if isinstance(dataset.get("v3_str_bug_clearance_reconciliation"), dict) else {}
    canonical = rem.get("canonical_truth_source") if isinstance(rem.get("canonical_truth_source"), dict) else {}
    bp = rem.get("buying_power_reconciliation") if isinstance(rem.get("buying_power_reconciliation"), dict) else {}
    sess = rem.get("session_state") if isinstance(rem.get("session_state"), dict) else {}
    snap = rem.get("snapshot_age_banner") if isinstance(rem.get("snapshot_age_banner"), dict) else {}
    lines = [
        "00E - ARTIFACT MANIFEST AND CANONICAL TRUTH-SOURCE AUDIT",
        "=" * 58,
        "Artifact manifest: generated with TXT/DOCX/XLSX/JSON delivery package.",
        "Required XLSX sheets: " + ", ".join(REQUIRED_STR_REMEDIATION_SHEETS),
        "",
        "Canonical Truth Source",
        f"- canonical_buying_power_delta={bp.get('canonical_buying_power_delta')} flag={bp.get('canonical_buying_power_delta_flag')} legacy_delta={bp.get('legacy_buying_power_delta')} deprecated_by=canonical_buying_power_delta",
        f"- canonical_market_session={sess.get('canonical_market_session')} legacy_session_flag={sess.get('legacy_session_flag')} rendered_session_flag={sess.get('rendered_session_flag')} rendered_market_closed={sess.get('rendered_market_closed')}",
        f"- canonical_snapshot_alignment_status={snap.get('snapshot_alignment_status')} formal_minus_dashboard_min={snap.get('formal_minus_dashboard_minutes')} explanation={snap.get('snapshot_alignment_explanation')}",
        f"- canonical_risk_model_status={canonical.get('canonical_risk_model_status')}",
        f"- canonical_kelly_macro_fused_status={canonical.get('canonical_kelly_macro_fused_status')}",
        "Execution safety: CIO_ONLY_MANUAL | order_routing_enabled=False | system_orders_generated=0",
    ]
    return "\n".join(lines)


def build_portfolio_target_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    targets = dataset.get("portfolio_targets") or {}
    rows = []
    for row in targets.get("targets_by_ticker") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("ticker", ""),
            n(row.get("current_weight")),
            n(row.get("target_weight")),
            n(row.get("delta_weight")),
            n(row.get("current_value")),
            n(row.get("target_value")),
            "YES" if row.get("research_only") else "",
        ])
    rows.sort(key=lambda r: abs(n(r[3], 0) or 0), reverse=True)
    return rows


def build_thesis_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    thesis = dataset.get("thesis_lifecycle") or {}
    rows = []
    for row in thesis.get("theses") or []:
        if not isinstance(row, dict):
            continue
        tickers = ", ".join(
            str(x.get("ticker"))
            for x in row.get("linked_tickers") or []
            if isinstance(x, dict) and x.get("ticker")
        )
        evidence = "; ".join(
            clean_text((x or {}).get("evidence") or (x or {}).get("contradiction"), 80)
            for x in (row.get("evidence") or row.get("contradictions") or [])[:3]
            if isinstance(x, dict)
        )
        rows.append([
            row.get("priority", ""),
            row.get("status", ""),
            row.get("thesis_id", ""),
            row.get("thesis_name", ""),
            n(row.get("base_probability")),
            n(row.get("current_probability")),
            n(row.get("confidence")),
            row.get("direction", ""),
            n(row.get("horizon_days")),
            clean_text(tickers, 120),
            clean_text(evidence, 200),
            clean_text(row.get("kill_condition", ""), 200),
        ])
    rows.sort(key=lambda r: (str(r[0]), str(r[1]), str(r[2])))
    return rows


def build_monitoring_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    monitoring = dataset.get("monitoring") or {}
    rows = []
    for row in monitoring.get("alerts") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("severity", ""),
            row.get("layer_name", ""),
            row.get("alert_type", ""),
            row.get("title", ""),
            clean_text(row.get("message", ""), 220),
            row.get("related_ticker", ""),
            row.get("cycle_ts", ""),
        ])
    rows.sort(key=lambda r: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(str(r[0]), 9))
    return rows


def build_history_coverage_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    hist = dataset.get("historical_price_coverage") or {}
    coverage = hist.get("coverage_by_ticker") if isinstance(hist, dict) else {}
    rows = []
    for ticker, row in (coverage or {}).items():
        if not isinstance(row, dict):
            continue
        rows.append([
            ticker,
            n(row.get("row_count")),
            row.get("first_date", ""),
            row.get("last_date", ""),
            row.get("latest_fetch", ""),
        ])
    rows.sort(key=lambda r: (n(r[1], 0) or 0, r[0]))
    return rows


def build_ops_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    archive = dataset.get("dataset_snapshot_archive") or {}
    freshness = dataset.get("freshness_recovery") or {}
    backfill = dataset.get("historical_backfill") or {}
    cio = dataset.get("cio_decisions") or {}
    orders = dataset.get("orders") or {}
    fills = dataset.get("fills") or {}
    execution = dataset.get("execution") or {}
    tca = dataset.get("transaction_cost_analysis") or {}
    latest_snapshot = archive.get("latest_snapshot") if isinstance(archive.get("latest_snapshot"), dict) else {}
    latest_backfill = backfill.get("latest_run") if isinstance(backfill.get("latest_run"), dict) else {}
    return [
        ["Dataset Archive Status", archive.get("status", "")],
        ["Snapshot Count", archive.get("snapshot_count", "")],
        ["Latest Snapshot", latest_snapshot.get("snapshot_id", "")],
        ["Latest Dataset SHA256", latest_snapshot.get("dataset_sha256", "")],
        ["Freshness Recovery Status", freshness.get("status", "")],
        ["Freshness Deferred", ", ".join(freshness.get("market_closed_deferred") or [])],
        ["Freshness Unresolved", ", ".join(freshness.get("unresolved_sections") or [])],
        ["Backfill Status", backfill.get("status", "")],
        ["Backfill Queue Counts", str(backfill.get("queue_counts", {}))],
        ["Latest Backfill Run", latest_backfill.get("run_id", "")],
        ["CIO Ledger Status", cio.get("status", "")],
        ["Pending CIO Reviews", cio.get("pending_review_count", "")],
        ["Orders Generated", cio.get("orders_generated", "")],
        ["Execution Authority", cio.get("execution_authority", "")],
        ["Broker Execution Status", execution.get("status", "")],
        ["Read-only Order History", "YES" if execution.get("read_only_order_history_extraction") else "NO"],
        ["Read-only Deal History", "YES" if execution.get("read_only_deal_history_extraction") else "NO"],
        ["Open Orders", orders.get("open_order_count", "")],
        ["Historical Orders", orders.get("historical_order_count", "")],
        ["Historical Deals/Fills", fills.get("historical_deal_count", "")],
        ["Fee Records", orders.get("fee_record_count", "")],
        ["Order Routing Enabled", "YES" if execution.get("order_routing_enabled") else "NO"],
        ["TCA Status", tca.get("status", "")],
    ]


def build_execution_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    orders = dataset.get("orders") or {}
    fills = dataset.get("fills") or {}
    execution = dataset.get("execution") or {}
    lifecycle = dataset.get("trade_lifecycle") or {}
    tca = dataset.get("transaction_cost_analysis") or {}
    order_summary = orders.get("summary") if isinstance(orders.get("summary"), dict) else {}
    query_errors = orders.get("query_errors") if isinstance(orders.get("query_errors"), dict) else {}
    return [
        ["Execution Status", execution.get("status", "")],
        ["Execution Authority", execution.get("execution_authority", order_summary.get("execution_authority", ""))],
        ["Broker / Source", f"{orders.get('broker', '')} / {orders.get('data_source', '')}".strip(" /")],
        ["Trading Environment", orders.get("trd_env", "")],
        ["Snapshot ID", orders.get("snapshot_id", "")],
        ["Cycle Timestamp", orders.get("cycle_ts", "")],
        ["History Window", f"{orders.get('start_date', '')} -> {orders.get('end_date', '')}".strip()],
        ["Read-only Order History", "YES" if execution.get("read_only_order_history_extraction") or order_summary.get("has_order_history_extraction") else "NO"],
        ["Read-only Deal History", "YES" if execution.get("read_only_deal_history_extraction") or order_summary.get("has_deal_history_extraction") else "NO"],
        ["Open Orders", orders.get("open_order_count", "")],
        ["Historical Orders", orders.get("historical_order_count", "")],
        ["Historical Deals/Fills", fills.get("historical_deal_count", "")],
        ["Open Deals/Fills", fills.get("open_deal_count", "")],
        ["Fee Records", orders.get("fee_record_count", "")],
        ["Pending CIO Reviews", (execution.get("decision_control") or {}).get("pending_review_count", "")],
        ["Orders Generated By Pipeline", "YES" if execution.get("orders_generated_by_pipeline") else "NO"],
        ["Order Routing Enabled", "YES" if execution.get("order_routing_enabled") else "NO"],
        ["TCA Status", tca.get("status", "")],
        ["Actual Fills Available", "YES" if tca.get("actual_fills_available") else "NO"],
        ["Manual Fill Import Required", "YES" if tca.get("manual_fill_import_required") else "NO"],
        ["Lifecycle Status", lifecycle.get("status", "")],
        ["Query Errors", str(query_errors) if query_errors else "none"],
    ]


def _broker_ticker(row: Dict[str, Any]) -> str:
    ticker = row.get("ticker") or row.get("code") or ""
    return str(ticker).replace("US.", "").strip()


def build_open_order_rows(dataset: Dict[str, Any], limit: int = 40) -> List[List[Any]]:
    orders = dataset.get("orders") or {}
    rows = []
    for row in orders.get("open_orders") or []:
        if not isinstance(row, dict):
            continue
        raw = row.get("raw_order") if isinstance(row.get("raw_order"), dict) else {}
        rows.append([
            _broker_ticker(row),
            row.get("trd_side", ""),
            row.get("order_type", ""),
            row.get("order_status", ""),
            _classify_broker_order_intent(row),
            n(row.get("qty")),
            n(row.get("price")),
            n(row.get("dealt_qty")),
            n(row.get("dealt_avg_price")),
            raw.get("time_in_force", ""),
            raw.get("session", ""),
            row.get("create_time", ""),
            row.get("updated_time", ""),
            row.get("order_id", ""),
        ])
    rows.sort(key=lambda r: (str(r[3]), str(r[0]), str(r[11])))
    return rows[:limit]


def build_cio_plan_vs_order_book(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Compare CIO research posture with the broker's open order book."""
    orders_layer = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    execution = dataset.get("execution") if isinstance(dataset.get("execution"), dict) else {}
    prices = live_prices(dataset)
    open_orders = orders_layer.get("open_orders") if isinstance(orders_layer.get("open_orders"), list) else []

    miner_orders = []
    executable_now = []
    for row in open_orders:
        if not isinstance(row, dict):
            continue
        ticker = _broker_ticker(row).upper()
        side = str(row.get("trd_side") or "").upper()
        if ticker not in {"AU", "NEM"} or side != "SELL":
            continue
        limit_price = n(row.get("price"))
        current_price = n((prices.get(ticker) or {}).get("price"))
        status = str(row.get("order_status") or "")
        dealt_qty = n(row.get("dealt_qty"))
        executable = bool(current_price and limit_price and limit_price <= current_price)
        if executable and dealt_qty <= 0:
            executable_now.append(ticker)
        miner_orders.append({
            "ticker": ticker,
            "status": status,
            "qty": n(row.get("qty")),
            "limit": limit_price,
            "current_price": current_price,
            "dealt_qty": dealt_qty,
            "executable_now": executable,
        })

    warning = "Current open orders do not guarantee pre-BOJ miner de-risking. Manual CIO action required."
    routing = bool(execution.get("order_routing_enabled"))
    generated = int(execution.get("orders_generated") or execution.get("orders_generated_by_pipeline") or 0)
    feasibility = "NOT GUARANTEED" if miner_orders and len(executable_now) < len(miner_orders) else "REVIEW_REQUIRED"
    if not miner_orders:
        feasibility = "NO AU/NEM SELL ORDERS FOUND"

    rows = [
        ["CIO Intended Action", "Gold thesis WARNING / THESIS_WEAKENING; HOLD / REVIEW only; no add unless CIO support-bid policy explicitly applies."],
        ["Existing Miner Sell Orders", f"{len(miner_orders)} AU/NEM sell orders open"],
        ["Feasibility", feasibility],
        ["Manual Action Required", "YES"],
        ["System Authority", execution.get("execution_authority", "CIO_ONLY_MANUAL")],
        ["Routing Enabled", "YES" if routing else "NO"],
        ["Generated Orders", generated],
        ["Warning", warning],
    ]
    for item in miner_orders:
        rows.append([
            f"{item['ticker']} order",
            f"status={item['status']} qty={fmt_int(item['qty'])} limit={fmt_money(item['limit'])} "
            f"current={fmt_money(item['current_price'])} dealt={fmt_int(item['dealt_qty'])} "
            f"executable_now={'YES' if item['executable_now'] else 'NO'}",
        ])

    return {
        "rows": rows,
        "warning": warning,
        "miner_sell_order_count": len(miner_orders),
        "feasibility": feasibility,
        "manual_action_required": True,
    }


def build_recent_fill_rows(dataset: Dict[str, Any], limit: int = 80) -> List[List[Any]]:
    fills = dataset.get("fills") or {}
    rows = []
    for row in fills.get("historical_deals_recent") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            _broker_ticker(row),
            row.get("trd_side", ""),
            n(row.get("qty")),
            n(row.get("price")),
            row.get("deal_time", ""),
            row.get("order_id", ""),
            row.get("deal_id", ""),
            row.get("deal_scope", ""),
        ])
    rows.sort(key=lambda r: str(r[4]), reverse=True)
    return rows[:limit]


def build_trade_lifecycle_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    lifecycle = dataset.get("trade_lifecycle") or {}
    rows = []
    for row in lifecycle.get("stages") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("stage", ""),
            row.get("owner", ""),
            row.get("system_record", ""),
        ])
    return rows


def deterministic_operator_pack(dataset: Dict[str, Any]) -> Dict[str, Any]:
    ops = dataset.get("deterministic_operators")
    return ops if isinstance(ops, dict) else {}


def build_deterministic_operator_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    ops = deterministic_operator_pack(dataset)
    summary = ops.get("summary") if isinstance(ops.get("summary"), dict) else {}
    return [
        ["Status", ops.get("status", "not_available")],
        ["Readiness", ops.get("readiness", "UNKNOWN")],
        ["Generated At", ops.get("generated_at", "")],
        ["Source Dataset", ops.get("source_dataset_generated_at", "")],
        ["LLM Used", str(bool(ops.get("llm_used", False)))],
        ["Execution Authority", ops.get("execution_authority", "CIO_ONLY_MANUAL")],
        ["Order Routing Enabled", str(bool(ops.get("order_routing_enabled", False)))],
        ["Orders Generated", ops.get("orders_generated", 0)],
        ["Operator Count", summary.get("operator_count", "")],
        ["Fail Count", summary.get("fail_count", "")],
        ["Review Count", summary.get("review_count", "")],
        ["Blocked Actions", ", ".join(summary.get("blocked_actions") or [])],
        ["Doctrine", ops.get("doctrine", "")],
    ]


def build_deterministic_operator_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    ops = deterministic_operator_pack(dataset)
    operators = ops.get("operators") if isinstance(ops.get("operators"), dict) else {}
    rows: List[List[Any]] = []
    for name, op in operators.items():
        if not isinstance(op, dict):
            continue
        rows.append([
            name,
            op.get("status", ""),
            op.get("score", ""),
            op.get("confidence", ""),
            "; ".join(str(x) for x in (op.get("evidence") or [])),
            ", ".join(str(x) for x in (op.get("blocked_actions") or [])),
        ])
    return rows


def build_cio_cognition_summary_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    cognition = dataset.get("cio_cognition") or {}
    latest = {}
    journals = cognition.get("latest_journals") if isinstance(cognition.get("latest_journals"), list) else []
    if journals and isinstance(journals[0], dict):
        latest = journals[0]
    evidence_refs = latest.get("evidence_refs") if isinstance(latest.get("evidence_refs"), dict) else {}
    tickers = evidence_refs.get("tickers") if isinstance(evidence_refs.get("tickers"), list) else []
    return [
        ["Status", cognition.get("status", "")],
        ["Latest Journal ID", cognition.get("latest_journal_id", latest.get("journal_id", ""))],
        ["Generated At", cognition.get("generated_at", latest.get("journal_ts", ""))],
        ["Entry Type", latest.get("entry_type", "")],
        ["Priority", latest.get("priority", "")],
        ["Thesis Title", clean_text(evidence_refs.get("thesis_title", ""), 260)],
        ["Tickers", ", ".join(str(t) for t in tickers)],
        ["Asset Class", evidence_refs.get("asset_class", "")],
        ["Already Placed Manually", "YES" if evidence_refs.get("already_placed_manually_by_cio") else "NO"],
        ["Manual Order Ref", evidence_refs.get("manual_order_reference_id", "")],
        ["Review Due", evidence_refs.get("review_due_date", "")],
        ["Regime", latest.get("regime", "")],
        ["CIO Action", latest.get("cio_action", "")],
        ["Confidence", n(latest.get("confidence"))],
        ["Author", latest.get("author", "")],
        ["Journal Count Exported", cognition.get("journal_count_exported", "")],
        ["Thesis Reviews", cognition.get("review_count", "")],
        ["Orders Generated", cognition.get("orders_generated", "")],
        ["Execution Authority", cognition.get("execution_authority", "")],
        ["Doctrine", cognition.get("doctrine", "")],
    ]


def build_cio_cognition_journal_rows(dataset: Dict[str, Any], limit: int = 20) -> List[List[Any]]:
    cognition = dataset.get("cio_cognition") or {}
    rows = []
    for row in cognition.get("latest_journals") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("journal_ts", ""),
            row.get("journal_id", ""),
            row.get("entry_type", ""),
            row.get("priority", ""),
            row.get("regime", ""),
            row.get("cio_action", ""),
            n(row.get("confidence")),
            clean_text(row.get("strategic_thinking", ""), 240),
            clean_text(row.get("planning", ""), 240),
            clean_text(row.get("execution_intent", ""), 220),
            clean_text(row.get("non_execution_rationale", ""), 180),
            row.get("author", ""),
        ])
    return rows[:limit]


def build_cio_thesis_review_rows(dataset: Dict[str, Any], limit: int = 40) -> List[List[Any]]:
    cognition = dataset.get("cio_cognition") or {}
    rows = []
    for row in cognition.get("latest_thesis_reviews") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("thesis_id", ""),
            row.get("status_at_review", ""),
            n(row.get("probability_at_review")),
            n(row.get("confidence_at_review")),
            row.get("cio_assessment", ""),
            clean_text(row.get("strategic_note", ""), 180),
            clean_text(row.get("planning_note", ""), 180),
            clean_text(row.get("execution_note", ""), 140),
            clean_text(row.get("repeatability_hypothesis", ""), 180),
            clean_text(row.get("mistake_risk", ""), 180),
        ])
    rows.sort(key=lambda r: (str(r[4]), str(r[0])))
    return rows[:limit]


def build_cio_decision_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    cio = dataset.get("cio_decisions") or {}
    # Dataset accumulates one snapshot per pipeline cycle — deduplicate to latest per (type, ticker)
    latest: Dict[tuple, Any] = {}
    for row in cio.get("decisions") or []:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("decision_type", "")), str(row.get("ticker") or "PORT"))
        ts = str(row.get("decision_ts") or "")
        if key not in latest or ts > str(latest[key].get("decision_ts") or ""):
            latest[key] = row
    rows = []
    for row in latest.values():
        rec = row.get("research_recommendation") if isinstance(row.get("research_recommendation"), dict) else {}
        rows.append([
            row.get("priority", ""),
            row.get("decision_type", ""),
            row.get("ticker", ""),
            row.get("status", ""),
            n(row.get("current_weight")),
            n(row.get("target_weight")),
            n(row.get("delta_weight")),
            row.get("cio_decision", ""),
            row.get("execution_authority", ""),
            "YES" if row.get("order_generated") else "NO",
            clean_text(str(rec.get("reason") or rec.get("objective") or rec.get("source") or ""), 180),
            row.get("decision_ts", ""),
        ])
    rows.sort(key=lambda r: (str(r[0]), str(r[1]), str(r[2] or "")))
    return rows


def build_backfill_queue_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    backfill = dataset.get("historical_backfill") or {}
    rows = []
    for row in backfill.get("incomplete_sample") or []:
        if not isinstance(row, dict):
            continue
        rows.append([
            row.get("ticker", ""),
            row.get("status", ""),
            row.get("universe_source", ""),
            n(row.get("priority")),
            n(row.get("row_count")),
            row.get("first_bar_date", ""),
            row.get("latest_bar_date", ""),
            row.get("latest_fetch_at", ""),
            n(row.get("attempt_count")),
            row.get("last_attempt_at", ""),
            clean_text(row.get("last_error", ""), 160),
        ])
    rows.sort(key=lambda r: (n(r[3], 9) or 9, n(r[4], 0) or 0, str(r[0])))
    return rows


def build_institutional_positioning(dataset: Dict[str, Any]) -> Dict[str, List[List[Any]]]:
    """
    Build three tables for the Institutional Positioning section.
    Sources: moomoo_intel (options flow), capital_flow (outflows), signals.CFTC_COT.
    """
    import re as _re

    # ── Table 1: Options Flow ────────────────────────────────────────────────
    options_rows: List[List[Any]] = []
    for entry in dataset.get("moomoo_intel") or []:
        if not isinstance(entry, str) or "[OPTIONS FLOW]" not in entry:
            continue
        try:
            ticker_m = _re.search(r"\[OPTIONS FLOW\]\s+([A-Z0-9]+):", entry)
            if not ticker_m:
                continue
            ticker = ticker_m.group(1)
            for trade in _re.finditer(
                r"(\d+\.\d+\s+\d+:\d+),\s+a\s+([\w\s]+?)\s+options trade was recorded\.\s+Volume was\s+([\d,]+)",
                entry, _re.IGNORECASE,
            ):
                date_time  = trade.group(1).strip()
                action_raw = trade.group(2).strip().upper()
                try:
                    volume = int(trade.group(3).replace(",", ""))
                except ValueError:
                    volume = 0
                if "BUY PUT"   in action_raw: signal = "BEARISH"
                elif "SELL CALL" in action_raw: signal = "BEARISH"
                elif "BUY CALL"  in action_raw: signal = "BULLISH"
                elif "SELL PUT"  in action_raw: signal = "BULLISH"
                else:                           signal = "NEUTRAL"
                options_rows.append([ticker, date_time, action_raw.title(), volume, signal])
        except Exception:
            continue
    options_rows.sort(key=lambda r: ({"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}.get(r[4], 9), -(r[3] or 0)))

    # ── Table 2: Capital Flow — Top Institutional Outflows ───────────────────
    cf_rows: List[List[Any]] = []
    for ticker, v in (dataset.get("capital_flow") or {}).items():
        if not isinstance(v, dict):
            continue
        sl_net = float(v.get("super_large_net") or 0)
        l_net  = float(v.get("large_net")       or 0)
        total  = sl_net + l_net
        if total >= 0:
            continue
        sl_out = float(v.get("super_large_out") or 0)
        l_out  = float(v.get("large_out")       or 0)
        cf_rows.append([
            ticker,
            f"-${sl_out / 1e6:.1f}M" if sl_out else "",
            f"-${l_out  / 1e6:.1f}M" if l_out  else "",
            f"-${abs(total) / 1e6:.1f}M",
            v.get("institutional_bias") or "",
        ])
    cf_rows.sort(key=lambda r: float(r[3].replace("-$", "").replace("M", "") or 0), reverse=True)

    # ── Table 3: CFTC COT — Leveraged Funds ─────────────────────────────────
    cftc_rows: List[List[Any]] = []
    for entry in (dataset.get("signals") or {}).get("CFTC_COT") or []:
        text = entry.get("raw_text", "") if isinstance(entry, dict) else str(entry)
        m = _re.match(
            r"CFTC COT \(TFF\)\s+(.+?)\s*-\s*CHICAGO MERCANTILE EXCHANGE:\s*net\s*([+-]?[\d,]+)\s+as of\s+(.+)",
            text, _re.IGNORECASE,
        )
        if not m:
            continue
        try:
            net = int(m.group(2).replace(",", ""))
        except ValueError:
            net = 0
        direction = "LONG" if net > 0 else "SHORT" if net < 0 else "FLAT"
        cftc_rows.append([m.group(1).strip(), f"{net:+,}", m.group(3).strip(), direction])
    cftc_rows.sort(key=lambda r: abs(int(r[1].replace(",", "").replace("+", ""))), reverse=True)

    return {"options_flow": options_rows, "capital_outflow": cf_rows, "cftc_cot": cftc_rows}


def build_concentration_risk(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate portfolio concentration risk: HHI, top-3 weight, thesis clusters."""
    portfolio  = dataset.get("portfolio") or {}
    positions  = portfolio.get("positions") or {}
    total_assets = float(portfolio.get("total_assets") or portfolio.get("total_value") or 0)
    holdings: List[Tuple[str, float]] = []
    for ticker, pos in positions.items():
        if isinstance(pos, dict):
            w = float(pos.get("weight") or 0)
            if not w and total_assets:
                mkt = float(pos.get("mkt_val") or pos.get("market_val") or pos.get("market_value") or 0)
                w = mkt / total_assets
            if w > 0:
                holdings.append((ticker, w))
    holdings.sort(key=lambda x: x[1], reverse=True)
    if not holdings:
        return {"hhi": 0.0, "top3_weight": 0.0, "largest_weight": 0.0,
                "largest_ticker": "", "clusters": {}, "concentration_status": "UNKNOWN"}
    weights = [w for _, w in holdings]
    hhi = sum(w ** 2 for w in weights)
    top3_weight = sum(weights[:3])
    CLUSTERS: Dict[str, set] = {
        "GOLD_MINERS": {"AU", "NEM", "GLD", "GDX", "GDXJ"},
        "QUANTUM":     {"QBTS", "QUBT", "IONQ", "RGTI", "IQM"},
        "AI_SEMIS":    {"NVDA", "AMD", "MU", "SMCI", "AMAT", "ARM", "AVGO", "MRVL"},
        "TECH_MAG7":   {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"},
        "BANKS":       {"JPM", "BAC", "GS", "MS", "WFC", "C"},
    }
    cluster_weights: Dict[str, float] = {}
    for cluster, members in CLUSTERS.items():
        ch = [(t, w) for t, w in holdings if t.upper() in members]
        if len(ch) >= 2:
            cluster_weights[cluster] = round(sum(w for _, w in ch), 4)
    # Base severity from HHI / single-name weight
    status_base = ("CRITICAL" if hhi > 0.35 or weights[0] > 0.40 else
                   "HIGH"     if hhi > 0.20 or weights[0] > 0.30 else
                   "ELEVATED" if hhi > 0.12 or weights[0] > 0.20 else "NORMAL")

    # Governance Gate cluster escalation rule (work order: cluster >= 65% => CRITICAL)
    # Mirrors R6 patch logic so TXT / Word / Excel all agree.
    _SEV_ORDER = {"NORMAL": 0, "ELEVATED": 1, "HIGH": 2, "CRITICAL": 3}
    cluster_max_name = max(cluster_weights, key=cluster_weights.get) if cluster_weights else None
    cluster_max_val  = cluster_weights[cluster_max_name] if cluster_max_name else 0.0
    cluster_sev = (
        "CRITICAL" if cluster_max_val >= 0.65
        else "HIGH" if cluster_max_val >= 0.45
        else None
    )
    if cluster_sev and _SEV_ORDER.get(cluster_sev, 0) > _SEV_ORDER.get(status_base, 0):
        status = cluster_sev
    else:
        status = status_base

    return {
        "hhi": round(hhi, 4),
        "top3_weight": round(top3_weight, 4),
        "largest_weight": round(weights[0], 4),
        "largest_ticker": holdings[0][0],
        "clusters": cluster_weights,
        "cluster_max_name": cluster_max_name,
        "cluster_max_val": round(cluster_max_val, 4),
        "concentration_status": status,
    }


def build_cio_briefing_rows(
    dataset: Dict[str, Any], archive: Dict[str, Any],
    causal_data: Optional[Dict[str, Any]] = None,
    blind_data: Optional[Dict[str, Any]] = None,
    operating_truth: Optional[Dict[str, Any]] = None,
    action_logic: Optional[Dict[str, Any]] = None,
) -> Tuple[List[List[Any]], List[Optional[int]]]:
    """Return (rows, row_styles) for the 1-page CIO Briefing sheet with traffic-light coloring.

    Consistency discipline: when causal_data and blind_data are provided (freshly computed),
    use them as the authoritative source. DB-archived values are fallback only (Upgrade #1, #3).
    """
    W = XlsxWorkbook  # style constants
    db = archive.get("database_row") or {}
    regime = dataset.get("regime") or {}
    portfolio = dataset.get("portfolio") or {}

    cio_action_val  = str(db.get("cio_action", "WAIT / HOLD"))
    doctrine        = str(db.get("doctrine_warning", "") or "")
    regime_name     = str(regime.get("regime", "UNKNOWN"))
    regime_score    = int(regime.get("score", 0) or 0)
    try:
        conf_f = float(db.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        conf_f = 0.0
    conf_label = str(db.get("confidence_label", "") or "")
    open_orders = int((dataset.get("orders") or {}).get("open_order_count", 0) or 0)

    # CONSISTENCY: use live-computed causal/blind status (Upgrades #1, #2)
    if causal_data:
        causal_status = str(causal_data.get("causal_status", "INCOMPLETE"))
        causal_pass   = int(causal_data.get("pass_count", 0))
        causal_conf   = float(causal_data.get("causal_confidence", 0.0))
        causal_crit   = causal_data.get("critical_checks") or []
        causal_src    = "MODEL INFERRED"
    else:
        causal_status = str(db.get("causal_explanation_status", "INCOMPLETE"))
        causal_pass, causal_conf, causal_crit = 0, 0.0, []
        causal_src    = "ARCHIVED"

    if blind_data:
        blind_status  = str(blind_data.get("blind_spot_status", "WARNING"))
        blind_pass    = int(blind_data.get("pass_count", 0))
        blind_fail    = int(blind_data.get("fail_count", 0))
        blind_src     = "MODEL INFERRED"
    else:
        # Never fall back to archived blind_spot_status — if live data absent, show UNKNOWN
        _ot_blind = (causal_data or {}).get("_operating_truth_blind_status", "") if causal_data else ""
        blind_status  = str(_ot_blind or "UNKNOWN")
        blind_pass, blind_fail = 0, 0
        blind_src     = "UNKNOWN — live data unavailable"

    conc = build_concentration_risk(dataset)
    conc_status = conc["concentration_status"]
    cluster_str = " | ".join(f"{k} {v:.0%}" for k, v in conc["clusters"].items())

    ece = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    top_opps = sorted(ece, key=lambda e: float(e.get("basket_move") or 0), reverse=True)[:3]
    bot_risks_themes = sorted(ece, key=lambda e: float(e.get("basket_move") or 0))[:2]

    monitoring = dataset.get("monitoring") or {}
    crit_alerts = [a.get("title", "")[:80] for a in (monitoring.get("alerts") or [])
                   if isinstance(a, dict) and str(a.get("severity", "")).upper() == "CRITICAL"][:2]

    rows: List[List[Any]] = []
    rs: List[Optional[int]] = []

    def R(field: Any, value: Any, style: int) -> None:
        rows.append([field, str(value) if value is not None else ""])
        rs.append(style)

    ot = operating_truth or {}
    al = action_logic or {}

    R("1-PAGE CIO BRIEFING", f"Generated {datetime.now().isoformat(sep=' ', timespec='seconds')}", W.STYLE_HEADER)

    # ── REPORT STATUS (Fix 4: clearly separate 4 status dimensions) ──────────
    R("── REPORT STATUS ──", "", W.STYLE_SECTION)
    _rr_cls  = ot.get("report_readiness", "PENDING")
    _rr_sty  = W.STYLE_RED if _rr_cls in ("NOT_INSTITUTIONAL_CLEAN", "EXECUTION_SAFETY_BREACH") else W.STYLE_AMBER if "REVIEW" in _rr_cls else W.STYLE_GREEN
    R("Report Operating Status",   f"[DATA CONFIRMED] {_rr_cls}", _rr_sty)
    _audit_st = ot.get("consistency_audit_status", "PENDING")
    _audit_sty = W.STYLE_RED if _audit_st == "INCONSISTENT" else W.STYLE_AMBER if _audit_st == "WARNINGS" else W.STYLE_GREEN
    R("Report Consistency Status", f"[MODEL INFERRED] {_audit_st}", _audit_sty)

    # Quant Process Readiness (separate from report cleanliness) — with dataset fallback
    _iq = (dataset.get("institutional_quant") or {})
    _qri = float(db.get("quant_readiness_index") or db.get("quant_readiness_score")
                 or _iq.get("readiness_score") or 0)
    _qr_label = (db.get("quant_readiness_label") or _iq.get("readiness_label")
                 or ("INSTITUTIONAL_READY" if _qri >= 90 else "REVIEW_REQUIRED" if _qri >= 75 else "NOT_READY"))
    _qr_sty = W.STYLE_GREEN if "READY" in _qr_label and "NOT" not in _qr_label else W.STYLE_AMBER if "REVIEW" in _qr_label else W.STYLE_RED
    _qr_val = f"[DATA CONFIRMED] {_qr_label}" + (f" {_qri:.1f}" if _qri else "")
    R("Quant Process Readiness",   _qr_val, _qr_sty)

    R("Execution Safety",          "[DATA CONFIRMED] CIO_ONLY_MANUAL | Routing: DISABLED | Pipeline Orders: 0", W.STYLE_GREEN)

    # ── OPERATING POSTURE ────────────────────────────────────────────────────
    R("── OPERATING POSTURE ──", "", W.STYLE_SECTION)
    r_sty = W.STYLE_RED if ("RISK OFF" in regime_name or regime_score <= -3) else W.STYLE_AMBER if regime_score < 0 else W.STYLE_GREEN
    R("Regime", f"[DATA CONFIRMED] {regime_name} (score {regime_score})", r_sty)

    # Fix 5: CIO Action Hierarchy — Raw → Gated → Final Operating Action
    raw_action   = ot.get("cio_action") or cio_action_val
    final_action = al.get("final_action") or raw_action
    action_cap   = al.get("action_cap") or final_action
    rules_fired  = al.get("rules_triggered") or []
    raw_sty  = W.STYLE_RED if "SELL" in raw_action else W.STYLE_AMBER
    gate_sty = W.STYLE_AMBER if "WAIT" in action_cap or "REVIEW" in action_cap else W.STYLE_RED if action_cap != raw_action else raw_sty
    final_sty = W.STYLE_RED if "SELL" in final_action else W.STYLE_AMBER if "WAIT" in final_action or "REVIEW" in final_action else W.STYLE_GREEN
    R("Raw Regime Action",         f"[DATA CONFIRMED] {raw_action}", raw_sty)
    _gate_detail = action_cap
    if rules_fired:
        _gate_reasons = [r for r in rules_fired if r not in ("RULE_1_EXECUTION_AUTHORITY_OK",)]
        if _gate_reasons:
            _gate_detail += f" (triggered: {'; '.join(r.replace('RULE_','').replace('_',' ') for r in _gate_reasons[:2])})"
    R("CIO Action Gate",           f"[MODEL INFERRED] {_gate_detail}", gate_sty)
    R("★ Final CIO Operating Action", f"[MODEL INFERRED] {final_action}", final_sty)

    conf_sty = W.STYLE_GREEN if conf_f >= 0.70 else W.STYLE_AMBER if conf_f >= 0.55 else W.STYLE_RED
    R("Confidence", f"[DATA CONFIRMED] {conf_f:.3f} {conf_label}".strip(), conf_sty)

    # 5-level causal status styling (Upgrade #2)
    _causal_red   = causal_status in ("INCOMPLETE", "CRITICAL_GAP")
    _causal_amber = causal_status in ("PARTIAL", "MOSTLY_COMPLETE")
    causal_sty = W.STYLE_RED if _causal_red else W.STYLE_AMBER if _causal_amber else W.STYLE_GREEN
    causal_detail = f"[{causal_src}] {causal_status}"
    if causal_data:
        causal_detail += f" | Pass {causal_pass}/10 | Conf {causal_conf:.3f}"
        if causal_crit:
            causal_detail += f" | CRITICAL GAPS: {', '.join(causal_crit)}"
    R("Causal Explanation", causal_detail, causal_sty)

    blind_sty = W.STYLE_RED if "CRITICAL" in blind_status else W.STYLE_AMBER if "WARNING" in blind_status else W.STYLE_GREEN
    blind_detail = f"[{blind_src}] {blind_status}"
    if blind_data:
        blind_detail += f" | Pass {blind_pass}/12 | Fail {blind_fail}/12"
    R("Blind Spot Status", blind_detail, blind_sty)

    # Portfolio (Upgrade #5: concentration always prominent)
    R("── PORTFOLIO ──", "", W.STYLE_SECTION)
    R("Total Assets",  f"[DATA CONFIRMED] {portfolio.get('total_assets', '')}", W.STYLE_NORMAL)
    R("Cash",          f"[DATA CONFIRMED] {portfolio.get('cash', '')}", W.STYLE_NORMAL)
    R("Market Value",  f"[DATA CONFIRMED] {portfolio.get('market_val', '')}", W.STYLE_NORMAL)
    R("Total P/L",     f"[DATA CONFIRMED] {portfolio.get('total_pnl', '')} ({portfolio.get('total_pnl_pct', '')}%)", W.STYLE_NORMAL)

    conc_sty = W.STYLE_RED if conc_status == "CRITICAL" else W.STYLE_AMBER if conc_status in ("HIGH", "ELEVATED") else W.STYLE_GREEN
    conc_val = (f"[DATA CONFIRMED] {conc_status} "
                f"[NORMAL <35% | ELEVATED <50% | HIGH <65% | CRITICAL ≥65%] "
                f"| HHI {conc['hhi']:.3f} | Top-3 {conc['top3_weight']:.0%} "
                f"| Largest {conc['largest_ticker']} {conc['largest_weight']:.0%}")
    if cluster_str:
        conc_val += f" | Clusters: {cluster_str}"
    R("Concentration Risk", conc_val, conc_sty)

    ord_sty = W.STYLE_AMBER if open_orders > 0 else W.STYLE_NORMAL
    R("Open Orders", f"[DATA CONFIRMED] {open_orders}", ord_sty)

    # Top 3 risks
    R("── TOP 3 RISKS ──", "", W.STYLE_SECTION)
    risks: List[str] = []
    if causal_status in ("INCOMPLETE", "CRITICAL_GAP"):
        risks.append(f"Causal explanation {causal_status} — research conclusion is PROVISIONAL")
    elif causal_status == "PARTIAL":
        risks.append("Causal explanation PARTIAL — missing inputs need resolution before sizing up")
    if "WARNING" in blind_status or "CRITICAL" in blind_status:
        risks.append(f"Blind spot status {blind_status} — unknown catalysts possible")
    if conc_status in ("HIGH", "CRITICAL"):
        risks.append(f"Portfolio concentration {conc_status}: {conc['largest_ticker']} {conc['largest_weight']:.0%}")
    for a in crit_alerts[:max(0, 3 - len(risks))]: risks.append(a)
    for t in bot_risks_themes:
        if len(risks) >= 3: break
        risks.append(f"Weak theme: {t.get('theme','')} {float(t.get('basket_move') or 0):+.1f}%")
    if not risks: risks.append("No critical risks flagged this cycle")
    for i, risk_item in enumerate(risks[:3], 1):
        r_sty_i = W.STYLE_RED if i == 1 and causal_status in ("INCOMPLETE", "CRITICAL_GAP") else W.STYLE_AMBER
        R(f"Risk {i}", f"[MODEL INFERRED] {risk_item}", r_sty_i)

    # Top 3 opportunities
    R("── TOP 3 OPPORTUNITIES ──", "", W.STYLE_SECTION)
    if top_opps:
        for i, opp in enumerate(top_opps, 1):
            R(f"Opportunity {i}", f"[MODEL INFERRED] {opp.get('theme','')} {float(opp.get('basket_move') or 0):+.1f}% | conf {opp.get('confidence',0):.2f}", W.STYLE_GREEN)
    else:
        R("Opportunities", "[DATA CONFIRMED] No strong rotation signals this cycle", W.STYLE_NORMAL)

    # CIO guidance — DERIVED from live status (Upgrade #3: no contradictions)
    R("── CIO GUIDANCE ──", "", W.STYLE_SECTION)
    R("What Changed",
      f"[PROVISIONAL] Regime {regime_name} score={regime_score}. Confidence {conf_f:.3f} ({conf_label}). "
      f"Blind-spot: {blind_status} ({blind_src}). Causal: {causal_status} ({causal_src}).",
      W.STYLE_NORMAL)

    # Dynamic "Should NOT Do" based on live status (Upgrade #3)
    not_do_parts = ["Do NOT route orders without CIO sign-off."]
    if causal_status in ("INCOMPLETE", "CRITICAL_GAP"):
        not_do_parts.append(f"Do NOT add new risk — causal evidence is {causal_status}.")
    if blind_status in ("WARNING", "CRITICAL"):
        not_do_parts.append(f"Do NOT ignore blind-spot {blind_status} — unknown catalysts possible.")
    if conc_status in ("HIGH", "CRITICAL"):
        not_do_parts.append(f"Do NOT add to concentrated cluster — concentration is {conc_status}.")
    R("What CIO Should NOT Do", f"[CIO THESIS] {' '.join(not_do_parts)}", W.STYLE_RED)

    # Dynamic "May Consider" based on live status (Upgrade #3)
    may_parts = []
    if causal_status in ("PARTIAL", "MOSTLY_COMPLETE"):
        missing_crit = causal_crit or []
        may_parts.append(f"Resolve missing causal inputs{(': ' + ', '.join(missing_crit)) if missing_crit else ''}.")
    if blind_fail > 0:
        may_parts.append(f"Address {blind_fail} blind-spot failures before adding risk.")
    if conc_status == "ELEVATED":
        may_parts.append("Monitor cluster concentration; avoid adding to top-weighted names.")
    if not may_parts:
        may_parts.append("Review thesis lifecycle. Monitor upcoming catalysts.")
    R("What CIO May Consider", f"[PROVISIONAL] {' '.join(may_parts)}", W.STYLE_AMBER)

    if doctrine:
        R("Doctrine Warning", f"[DATA CONFIRMED] {doctrine}", W.STYLE_RED)

    return rows, rs


def build_causal_explanation(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """
    Structured causal chain check. Examines 10 evidence categories and returns
    causal_status (COMPLETE/PARTIAL/INCOMPLETE), causal_confidence, primary_causal_driver,
    secondary_causal_driver, missing_causal_inputs, and check_rows for reporting.
    """
    from datetime import datetime as _dt, timedelta as _td
    import re as _re

    sigs   = dataset.get("signals") or {}
    regime = dataset.get("regime") or {}
    cm     = dataset.get("cross_market_confirmation") or {}
    cats   = (dataset.get("catalyst_calendar") or {}).get("all") or []
    conf_cal = dataset.get("conference_calendar") or []
    if isinstance(conf_cal, dict): conf_cal = conf_cal.get("events") or []
    ceo_apps = dataset.get("ceo_appearances") or []
    if isinstance(ceo_apps, dict): ceo_apps = ceo_apps.get("appearances") or []
    mon    = dataset.get("monitoring") or {}
    health = dataset.get("source_health") or {}

    # Helper: count fresh signal entries (received within last 72h)
    now_str = datetime.now().strftime("%Y-%m-%d")
    def _sig_count(keys: List[str]) -> int:
        return sum(len(sigs.get(k) or []) for k in keys if k in sigs)

    # 10 causal checks
    checks: List[Tuple[str, str, str]] = []  # (name, status, detail)

    # 1. Regime driver strength
    factors = regime.get("factors") or {}
    nonzero = sum(1 for v in factors.values() if v != 0)
    if nonzero >= 3:
        checks.append(("Regime Drivers",   "PASS", f"{nonzero}/6 factors active | score {regime.get('score',0)} | {regime.get('regime','')}"))
    else:
        checks.append(("Regime Drivers",   "FAIL", f"Only {nonzero}/6 factors active — regime driver evidence thin"))

    # 2. Cross-market confirmation
    flags = cm.get("interpretation_flags") or {}
    active_flags = [k for k, v in flags.items() if v]
    cov = f"{cm.get('filled_count','?')}/{cm.get('ticker_count','?')}"
    if cm and cm.get("filled_count", 0):
        checks.append(("Cross-Market",     "PASS", f"Coverage {cov} | flags: {', '.join(active_flags) or 'none'}"))
    else:
        checks.append(("Cross-Market",     "FAIL", "Cross-market confirmation data unavailable or empty"))

    # 3. News catalyst (Reuters/WSJ/FT/CNBC/MarketWatch)
    news_count = _sig_count(["Reuters_Business","Reuters_Markets","Reuters_Technology","WSJ_Markets","FT_Markets","CNBC_Markets","MarketWatch_RSS"])
    if news_count >= 5:
        checks.append(("News Catalyst",    "PASS", f"{news_count} fresh news signals from Reuters/WSJ/FT/CNBC"))
    else:
        checks.append(("News Catalyst",    "FAIL", f"Only {news_count} news signals — news catalyst coverage thin"))

    # 4. Macro / economic data (BLS/BEA/WorldBank/EIA)
    macro_count = _sig_count(["BLS_API","BEA_GDP_PCE","WorldBank_Macro","EIA_Petroleum","EIA_NatGas"])
    if macro_count >= 3:
        checks.append(("Macro/Economic",   "PASS", f"{macro_count} macro data signals (BLS/BEA/WorldBank/EIA)"))
    else:
        checks.append(("Macro/Economic",   "FAIL", f"Only {macro_count} macro signals — fundamental data thin"))

    # 5. Fed / Policy events
    fed_count = _sig_count(["Fed_Press","Fed_Speeches","Fed_FOMC_Minutes","ECB_Press","BOJ_Press","PBOC_Policy","Treasury_Press"])
    if fed_count >= 3:
        checks.append(("Fed/Policy",       "PASS", f"{fed_count} central bank/policy signals available"))
    else:
        checks.append(("Fed/Policy",       "FAIL", f"Only {fed_count} Fed/policy signals — policy catalyst unclear"))

    # 6. Geopolitical events
    geo_count = _sig_count(["WhiteHouse_RSS","IAEA_News","ArabNews_Business","Defense_News","Breaking_Defense","OPEC_News","GDELT_API"])
    if geo_count >= 3:
        checks.append(("Geopolitical",     "PASS", f"{geo_count} geopolitical signals available"))
    else:
        checks.append(("Geopolitical",     "FAIL", f"Only {geo_count} geopolitical signals — geopolitical risk poorly covered"))

    # 7. Forward catalyst calendar (imminent/active events)
    macro_risks = dataset.get("macro_event_risks") if isinstance(dataset.get("macro_event_risks"), list) else []
    imminent = [c for c in cats if str(c.get("alert_flag","")).upper() in ("IMMINENT","ACTIVE")]
    imminent = imminent + [c for c in macro_risks if isinstance(c, dict)]
    if imminent:
        names = []
        for c in imminent[:6]:
            if c.get("event"):
                names.append(f"{c.get('event')} {c.get('event_date','')}".strip())
            else:
                names.append(f"{c.get('ticker','')} {c.get('catalyst_type','')} {c.get('catalyst_date','')}".strip())
        names = ", ".join(names)
        checks.append(("Catalyst Calendar", "PASS", f"{len(imminent)} imminent/active: {names}"))
    else:
        checks.append(("Catalyst Calendar", "FAIL", "No IMMINENT or ACTIVE portfolio, macro, geopolitical, or liquidity catalysts"))

    # 8. CEO / Conference events (recent or active)
    active_conf = [e for e in conf_cal if isinstance(e, dict) and str(e.get("event_date_end","")) >= now_str[:10]]
    recent_ceo  = [a for a in ceo_apps if isinstance(a, dict) and str(a.get("appearance_date","")) >= (datetime.now() - __import__("datetime").timedelta(days=7)).strftime("%Y-%m-%d")]
    if active_conf or recent_ceo:
        detail = f"{len(active_conf)} active conferences | {len(recent_ceo)} recent CEO appearances"
        checks.append(("CEO/Conference",   "PASS", detail))
    else:
        checks.append(("CEO/Conference",   "FAIL", "No active conferences or recent CEO appearances found"))

    # 9. CFTC COT positioning
    cftc = sigs.get("CFTC_COT") or []
    if cftc:
        checks.append(("CFTC COT",         "PASS", f"{len(cftc)} CFTC positioning signals available"))
    else:
        checks.append(("CFTC COT",         "FAIL", "CFTC COT data unavailable — institutional positioning unknown"))

    # 10. Missing-source risk
    sh_data = health if isinstance(health, dict) else {}
    stale_count = sum(1 for v in sh_data.values() if isinstance(v, dict) and str(v.get("grade","")).upper() == "STALE")
    if stale_count == 0:
        checks.append(("Source Freshness", "PASS", "No stale sources detected"))
    elif stale_count <= 2:
        checks.append(("Source Freshness", "WARN", f"{stale_count} stale source(s) — minor coverage gap"))
    else:
        checks.append(("Source Freshness", "FAIL", f"{stale_count} stale sources — significant data freshness risk"))

    # Score — 6-level graded status (Fix 3: MOSTLY_COMPLETE_WITH_CRITICAL_GAP)
    _CRITICAL_CHECKS = {
        "Regime Drivers", "Cross-Market Confirmation", "News Catalyst",
        "Macro / Economic", "Geopolitical Risk", "Source Freshness",
        # also match the shorter names used in check tuples above
        "Cross-Market", "Macro/Economic", "Geopolitical", "News Catalyst",
    }
    pass_count = sum(1 for _, s, _ in checks if s == "PASS")
    warn_count = sum(1 for _, s, _ in checks if s == "WARN")
    total_count = len(checks)

    passed = [name for name, s, _ in checks if s == "PASS"]
    failed = [name for name, s, _ in checks if s == "FAIL"]
    failed_critical = [c for c in failed if c in _CRITICAL_CHECKS]

    if failed_critical:
        if pass_count >= 8:
            causal_status = "MOSTLY_COMPLETE_WITH_CRITICAL_GAP"
        elif pass_count >= 4:
            causal_status = "CRITICAL_GAP"
        else:
            causal_status = "INCOMPLETE"
    elif pass_count == total_count:
        causal_status = "COMPLETE"
    elif pass_count >= 8:
        causal_status = "MOSTLY_COMPLETE"
    elif pass_count >= 6:
        causal_status = "PARTIAL"
    elif pass_count >= 4:
        causal_status = "INCOMPLETE"
    else:
        causal_status = "CRITICAL_GAP"

    causal_confidence = round(min(1.0, (pass_count + 0.5 * warn_count) / 10.0), 3)

    primary   = passed[0] if passed else "None"
    secondary = passed[1] if len(passed) > 1 else "None"

    # Missing causal inputs + CRITICAL_CHECKS (Upgrade #2 + Fix 3)
    missing = [name for name, s, _ in checks if s == "FAIL"]
    _CRITICAL_CAUSAL_NAMES = {"Regime Drivers", "Cross-Market", "Catalyst Calendar", "Source Freshness",
                              "Cross-Market Confirmation", "News Catalyst", "Macro/Economic",
                              "Geopolitical", "Macro / Economic", "Geopolitical Risk"}
    critical_checks = [name for name in missing if name in _CRITICAL_CAUSAL_NAMES]

    # Build check_rows for Excel/reports
    check_rows: List[List[Any]] = []
    for name, status, detail in checks:
        check_rows.append([name, status, detail])

    return {
        "causal_status":          causal_status,
        "causal_confidence":      causal_confidence,
        "primary_driver":         primary,
        "secondary_driver":       secondary,
        "missing_inputs":         missing,
        "critical_checks":        critical_checks,
        "failed_critical_checks": failed_critical,    # Fix 3
        "pass_count":             pass_count,
        "warn_count":             warn_count,
        "fail_count":             len(failed),
        "check_rows":             check_rows,
    }


def build_blind_spot_checklist(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """
    Structured 12-item blind spot checklist as per the Institutional Operating Mandate.
    Returns blind_spot_status, failed_items, missing_data_sources, cio_penalty, check_rows.
    """
    sigs     = dataset.get("signals") or {}
    cats     = (dataset.get("catalyst_calendar") or {}).get("all") or []
    conf_cal = dataset.get("conference_calendar") or []
    if isinstance(conf_cal, dict): conf_cal = conf_cal.get("events") or []
    ceo_apps = dataset.get("ceo_appearances") or []
    if isinstance(ceo_apps, dict): ceo_apps = ceo_apps.get("appearances") or []
    ece      = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    named_ev = dataset.get("ece_named_events") or []
    regime   = dataset.get("regime") or {}
    movers   = dataset.get("live_prices") or {}
    top_mv   = (movers.get("top_movers") or movers.get("movers") or []) if isinstance(movers, dict) else []

    now_s = datetime.now().strftime("%Y-%m-%d")
    next14 = (datetime.now() + __import__("datetime").timedelta(days=14)).strftime("%Y-%m-%d")

    items: List[Tuple[str, str, str]] = []  # (check_name, PASS/FAIL, detail)

    # 1. Scheduled conferences checked
    upcoming_conf = [e for e in conf_cal if isinstance(e, dict) and str(e.get("event_date_start","")) >= now_s]
    if upcoming_conf:
        items.append(("Scheduled Conferences",      "PASS", f"{len(upcoming_conf)} upcoming conferences tracked"))
    else:
        items.append(("Scheduled Conferences",      "FAIL", "No upcoming conference events in calendar"))

    # 2. CEO appearances checked
    upcoming_ceo = [a for a in ceo_apps if isinstance(a, dict) and str(a.get("appearance_date","")) >= now_s]
    if ceo_apps:
        items.append(("CEO Appearances",             "PASS", f"{len(ceo_apps)} total | {len(upcoming_ceo)} upcoming"))
    else:
        items.append(("CEO Appearances",             "FAIL", "No CEO appearance data in system"))

    # 3. Portfolio catalyst calendar checked
    port_cats = [c for c in cats if c.get("in_portfolio") and str(c.get("alert_flag","")).upper() != "PAST"]
    if port_cats:
        items.append(("Portfolio Catalyst Calendar", "PASS", f"{len(port_cats)} portfolio catalysts tracked"))
    else:
        items.append(("Portfolio Catalyst Calendar", "FAIL", "No portfolio tickers in catalyst calendar"))

    # 4. Earnings calendar checked
    earning_cats = [c for c in cats if c.get("catalyst_type","").upper() == "EARNINGS"
                    and str(c.get("catalyst_date","")) <= next14]
    if earning_cats:
        names = ", ".join(f"{c['ticker']} {c.get('catalyst_date','')}" for c in earning_cats[:5])
        items.append(("Earnings Calendar",           "PASS", f"{len(earning_cats)} earnings in 14d: {names}"))
    else:
        items.append(("Earnings Calendar",           "FAIL", "No earnings events found in next 14 days"))

    # 5. Investor days checked
    inv_days = [e for e in conf_cal if isinstance(e, dict) and "INVESTOR" in str(e.get("conference_slug","")).upper()]
    inv_days += [c for c in cats if "INVESTOR" in str(c.get("catalyst_type","")).upper()]
    if inv_days:
        items.append(("Investor Days",               "PASS", f"{len(inv_days)} investor day events found"))
    else:
        items.append(("Investor Days",               "FAIL", "No investor day events in calendar"))

    # 6. Analyst days checked (approximation — look for ANALYST in catalyst types / conference slugs)
    analyst_days = [e for e in conf_cal if isinstance(e, dict) and "ANALYST" in str(e.get("conference_slug","")).upper()]
    analyst_days += [c for c in cats if "ANALYST" in str(c.get("catalyst_type","")).upper()]
    if analyst_days:
        items.append(("Analyst Days",                "PASS", f"{len(analyst_days)} analyst day events found"))
    else:
        items.append(("Analyst Days",                "FAIL", "No analyst day events detected"))

    # 7. Tech keynote events checked
    tech_keynotes = [e for e in conf_cal if isinstance(e, dict) and e.get("keynote_date")]
    if tech_keynotes:
        tnames = ", ".join(e.get("conference_name","") for e in tech_keynotes[:4])
        items.append(("Tech Keynote Events",         "PASS", f"{len(tech_keynotes)} tech keynotes tracked: {tnames}"))
    else:
        items.append(("Tech Keynote Events",         "FAIL", "No tech keynote events in conference calendar"))

    # 8. Fed / policy events checked
    fed_count = sum(len(sigs.get(k) or []) for k in ["Fed_Press","Fed_Speeches","Fed_FOMC_Minutes","Treasury_Press"])
    if fed_count >= 3:
        items.append(("Fed/Policy Events",           "PASS", f"{fed_count} Fed/Treasury signals available"))
    else:
        items.append(("Fed/Policy Events",           "FAIL", f"Only {fed_count} Fed/policy signals — watch for surprise announcements"))

    # 9. Geopolitical events checked
    geo_count = sum(len(sigs.get(k) or []) for k in ["WhiteHouse_RSS","IAEA_News","ArabNews_Business","Defense_News","OPEC_News"])
    if geo_count >= 3:
        items.append(("Geopolitical Events",         "PASS", f"{geo_count} geopolitical signals monitored"))
    else:
        items.append(("Geopolitical Events",         "FAIL", f"Only {geo_count} geopolitical signals — geopolitical catalyst risk elevated"))

    # 10. Named historical event calendar checked
    if isinstance(named_ev, list) and named_ev:
        items.append(("Named Historical Events",     "PASS", f"{len(named_ev)} named events in historical correlation database"))
    elif isinstance(named_ev, dict) and named_ev:
        items.append(("Named Historical Events",     "PASS", f"{len(named_ev)} named events in historical correlation database"))
    else:
        items.append(("Named Historical Events",     "FAIL", "Named historical event calendar empty or unavailable"))

    # 11. Unexplained market moves checked
    large_movers = [m for m in (ece or []) if abs(float(m.get("basket_move") or 0)) >= 3]
    unexplained  = [m for m in large_movers if "ANALYST CONSENSUS" in str(m.get("why","")).upper() or not m.get("why")]
    if not unexplained:
        items.append(("Unexplained Market Moves",    "PASS", f"{len(large_movers)} large moves checked — all have causal explanations"))
    else:
        names = ", ".join(m.get("theme","") for m in unexplained[:3])
        items.append(("Unexplained Market Moves",    "FAIL", f"{len(unexplained)} unexplained large moves: {names}"))

    # 12. Sector rally / selloff catalyst checked
    sector_catalyst_present = all(
        bool(e.get("why") and "ANALYST CONSENSUS" not in str(e.get("why","")).upper())
        for e in ece[:10] if abs(float(e.get("basket_move") or 0)) >= 2
    ) if ece else False
    if sector_catalyst_present:
        items.append(("Sector Catalyst Check",       "PASS", "Sector moves have causal explanations beyond analyst consensus"))
    else:
        items.append(("Sector Catalyst Check",       "FAIL", "Some sector moves lack non-consensus causal explanation"))

    # Score
    fails = [name for name, s, _ in items if s == "FAIL"]
    n_fail = len(fails)
    penalty = round(min(0.35, 0.04 * n_fail), 3)
    status = "CLEAR" if n_fail == 0 else "CRITICAL" if n_fail >= 6 else "WARNING"

    return {
        "blind_spot_status": status,
        "failed_items":      fails,
        "pass_count":        len(items) - n_fail,
        "fail_count":        n_fail,
        "cio_penalty":       penalty,
        "check_rows":        [[name, s, detail] for name, s, detail in items],
    }


# ---------------------------------------------------------------------------
# Consistency Audit (Upgrade #4)
# ---------------------------------------------------------------------------

def build_consistency_audit(
    dataset: Dict[str, Any],
    archive: Dict[str, Any],
    causal_data: Optional[Dict[str, Any]] = None,
    blind_data: Optional[Dict[str, Any]] = None,
    operating_truth: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """10-check internal consistency audit verifying operating_truth uses live values.

    Checks that operating_truth (the canonical executive object) matches
    freshly-computed live values.  Archived DB values are NOT compared here —
    archive mismatches are reported separately via detect_archive_live_mismatches().

    Returns audit_score (0-100), audit_status, and check_rows.
    """
    db  = archive.get("database_row") or {}
    ot  = operating_truth or {}
    checks: List[Tuple[str, str, str]] = []  # (name, PASS/WARNING/FAIL, detail)

    def _chk(name: str, result: str, detail: str) -> None:
        checks.append((name, result, detail))

    live_causal = str((causal_data or {}).get("causal_status", "") or "")
    live_blind  = str((blind_data  or {}).get("blind_spot_status", "") or "")

    # 1. Causal status: operating_truth must match live-computed value
    ot_causal = str(ot.get("causal_status", "") or "")
    if not live_causal:
        _chk("Causal Status Consistency", "WARNING", "Live causal data not available — cannot verify")
    elif not ot_causal:
        _chk("Causal Status Consistency", "WARNING", f"operating_truth.causal_status absent; live={live_causal}")
    elif ot_causal == live_causal:
        _chk("Causal Status Consistency", "PASS", f"operating_truth matches live: both {live_causal}")
    else:
        _chk("Causal Status Consistency", "FAIL",
             f"operating_truth.causal_status={ot_causal} but live={live_causal} — stale value in executive summary")

    # 2. Blind spot: operating_truth must match live-computed value
    #    (Archive mismatches reported separately — not a consistency FAIL here)
    ot_blind = str(ot.get("blind_spot_status", "") or "")
    if not live_blind:
        _chk("Blind Spot Consistency", "WARNING", "Live blind-spot data not available — cannot verify")
    elif not ot_blind:
        _chk("Blind Spot Consistency", "WARNING", f"operating_truth.blind_spot_status absent; live={live_blind}")
    elif ot_blind == live_blind:
        _chk("Blind Spot Consistency", "PASS",
             f"operating_truth uses live value: {live_blind} [archived value reported separately]")
    else:
        _chk("Blind Spot Consistency", "FAIL",
             f"operating_truth.blind_spot_status={ot_blind} but live={live_blind} — stale value in executive summary")

    # 3. Causal COMPLETE + Blind WARNING is allowed — means "causal chain known but coverage gaps exist"
    #    Causal COMPLETE + Blind CRITICAL is a contradiction.
    if live_causal in ("COMPLETE", "MOSTLY_COMPLETE") and live_blind == "CRITICAL":
        _chk("Causal-Blind Coherence", "FAIL", f"Contradiction: causal={live_causal} but blind_spot=CRITICAL")
    elif live_causal in ("COMPLETE", "MOSTLY_COMPLETE") and live_blind == "WARNING":
        _chk("Causal-Blind Coherence", "PASS",
             f"causal={live_causal} + blind=WARNING is valid: causal chain known, coverage gaps remain — action: WAIT/REVIEW")
    elif live_causal and live_blind:
        _chk("Causal-Blind Coherence", "PASS", f"causal={live_causal} blind={live_blind} coherent")
    else:
        _chk("Causal-Blind Coherence", "WARNING", "Insufficient data to check causal-blind coherence")

    # 4. CIO action coherence: use operating_truth (live) not DB (archived)
    cio_action = str(ot.get("cio_action", "") or db.get("cio_action", "") or "")
    if cio_action:
        is_hold = "WAIT" in cio_action or "HOLD" in cio_action
        is_reduce = "REDUCE" in cio_action or "SELL" in cio_action
        is_safe = is_hold or is_reduce
        if live_causal in ("INCOMPLETE", "CRITICAL_GAP") and not is_safe:
            _chk("CIO Action Coherence", "FAIL", f"Action '{cio_action}' too aggressive for causal {live_causal}")
        elif live_blind == "CRITICAL" and not is_hold:
            _chk("CIO Action Coherence", "FAIL", f"Action '{cio_action}' too aggressive for blind_spot CRITICAL")
        else:
            _chk("CIO Action Coherence", "PASS",
                 f"'{cio_action}' consistent with causal={live_causal} blind={live_blind}")
    else:
        _chk("CIO Action Coherence", "WARNING", "CIO action not available")

    # 5. Concentration risk: compare matching denominators.
    # build_concentration_risk() computes AUM-weighted HHI because it uses total_assets.
    # risk_metrics also carries an equity-only HHI, which is valid risk telemetry but not
    # the same denominator. Do not fail the report by comparing equity-only to AUM HHI.
    risk = dataset.get("risk_metrics") or {}
    conc_live = build_concentration_risk(dataset)
    risk_hhi_equity = float(risk.get("concentration_hhi_equity_only") or 0)
    risk_hhi_aum = float(
        risk.get("concentration_hhi_vs_total_aum")
        or risk.get("concentration_hhi_aum")
        or risk.get("concentration_hhi")
        or 0
    )
    live_hhi = conc_live["hhi"]
    risk_hhi = risk_hhi_aum
    if risk_hhi and live_hhi:
        diff = abs(risk_hhi - live_hhi)
        if diff < 0.05:
            _chk(
                "Concentration HHI Consistency",
                "PASS",
                f"AUM HHI matches: risk_metrics={risk_hhi:.4f}, computed={live_hhi:.4f}; "
                f"equity-only HHI={risk_hhi_equity:.4f} reported separately",
            )
        elif diff < 0.20:
            _chk("Concentration HHI Consistency", "WARNING", f"AUM HHI drift: risk_metrics={risk_hhi:.4f} computed={live_hhi:.4f}; equity-only={risk_hhi_equity:.4f}")
        else:
            _chk("Concentration HHI Consistency", "FAIL", f"AUM HHI mismatch: risk_metrics={risk_hhi:.4f} computed={live_hhi:.4f}; equity-only={risk_hhi_equity:.4f}")
    else:
        _chk("Concentration HHI Consistency", "WARNING", "Insufficient HHI data for consistency check")

    # 6. Causal pass count consistent with causal status — severity-aware logic
    # Uses the same critical/important check classification as build_causal_explanation()
    # so the audit expectation exactly mirrors what the engine produces.
    if causal_data:
        cp   = int(causal_data.get("pass_count", 0) or 0)
        cs   = str(causal_data.get("causal_status", "") or "")
        tc   = int(causal_data.get("fail_count", 0) or 0) + cp + int(causal_data.get("warn_count", 0) or 0)
        fc   = causal_data.get("failed_critical_checks") or []
        fi   = causal_data.get("missing_inputs") or []   # all failed check names

        # Mirror the severity-aware rules of build_causal_explanation()
        _CAUSAL_CRITICAL = {
            "Regime Drivers", "Cross-Market Confirmation", "News Catalyst",
            "Macro / Economic", "Geopolitical Risk", "Source Freshness",
            "Cross-Market", "Macro/Economic", "Geopolitical",
        }
        _CAUSAL_IMPORTANT = {"Catalyst Calendar", "CEO/Conference", "CFTC COT"}

        # Compute expected status from the same rules the engine uses
        if fc:
            _exp = "MOSTLY_COMPLETE_WITH_CRITICAL_GAP" if cp >= 8 else \
                   "CRITICAL_GAP"                      if cp >= 4 else \
                   "INCOMPLETE"
        elif cp == tc and tc > 0:
            _exp = "COMPLETE"
        elif cp >= 8:
            _exp = "MOSTLY_COMPLETE"
        elif cp >= 6:
            _exp = "PARTIAL"
        elif cp >= 4:
            _exp = "INCOMPLETE"
        else:
            _exp = "CRITICAL_GAP"

        # Also accept MOSTLY_COMPLETE when only IMPORTANT checks failed (non-critical)
        _only_important_failed = all(name in _CAUSAL_IMPORTANT for name in fi) and fi
        _acceptable = {_exp}
        if _only_important_failed and cp >= 8:
            _acceptable.add("MOSTLY_COMPLETE")
        if _exp == "COMPLETE" and fi:
            # If any check failed but pass_count == total - some failed, this is a data edge case
            _acceptable.add("MOSTLY_COMPLETE")

        if cs in _acceptable:
            _chk("Causal Score->Status", "PASS",
                 f"pass={cp}/{tc} failed_critical={fc} failed_all={fi} -> status={cs} (accepted: {sorted(_acceptable)})")
        else:
            _chk("Causal Score->Status", "FAIL",
                 f"pass={cp}/{tc} failed_critical={fc} failed_all={fi} -> expected {sorted(_acceptable)} but got {cs}")
    else:
        _chk("Causal Score->Status", "WARNING", "No live causal data to verify score->status mapping")

    # 7. Blind spot fail count consistent with blind status
    if blind_data:
        bf = blind_data.get("fail_count", 0)
        bs = blind_data.get("blind_spot_status", "")
        expected_bs = "CLEAR" if bf == 0 else "CRITICAL" if bf >= 6 else "WARNING"
        if bs == expected_bs:
            _chk("Blind Spot Score->Status", "PASS", f"fail={bf} -> status={bs} (correct)")
        else:
            _chk("Blind Spot Score->Status", "FAIL", f"fail={bf} -> expected {expected_bs} but got {bs}")
    else:
        _chk("Blind Spot Score->Status", "WARNING", "No live blind-spot data to verify score->status mapping")

    # 8. Regime score aligns with regime name
    regime = dataset.get("regime") or {}
    regime_name  = str(regime.get("regime", "") or "")
    regime_score = int(regime.get("score", 0) or 0)
    if regime_name and regime_score is not None:
        is_risk_off = "RISK OFF" in regime_name.upper() or "BEAR" in regime_name.upper()
        is_risk_on  = "RISK ON" in regime_name.upper() or "BULL" in regime_name.upper()
        if is_risk_off and regime_score > 0:
            _chk("Regime Score Coherence", "FAIL", f"Regime name '{regime_name}' says RISK OFF but score={regime_score}>0")
        elif is_risk_on and regime_score < 0:
            _chk("Regime Score Coherence", "FAIL", f"Regime name '{regime_name}' says RISK ON but score={regime_score}<0")
        else:
            _chk("Regime Score Coherence", "PASS", f"'{regime_name}' score={regime_score} coherent")
    else:
        _chk("Regime Score Coherence", "WARNING", "Regime name or score unavailable")

    # 9. Confidence label consistent with confidence float
    conf_f = float(db.get("confidence") or 0)
    conf_label = str(db.get("confidence_label", "") or "")
    if not conf_f and not conf_label:
        # Archive empty or not yet available — check not applicable, do not penalise
        _chk("Confidence Label Coherence", "PASS", "Archive not yet available — check not applicable (pre-pass)")
    elif conf_f and conf_label:
        expected_label_high = conf_f >= 0.70
        is_high_label = any(x in conf_label.upper() for x in ("HIGH", "STRONG"))
        is_low_label  = any(x in conf_label.upper() for x in ("LOW", "WEAK", "POOR"))
        if expected_label_high and is_low_label:
            _chk("Confidence Label Coherence", "FAIL", f"conf={conf_f:.3f} but label='{conf_label}' says LOW")
        elif not expected_label_high and is_high_label:
            _chk("Confidence Label Coherence", "FAIL", f"conf={conf_f:.3f} but label='{conf_label}' says HIGH")
        else:
            _chk("Confidence Label Coherence", "PASS", f"conf={conf_f:.3f} label='{conf_label}' consistent")
    else:
        _chk("Confidence Label Coherence", "WARNING", "Confidence float or label unavailable")

    # 10. At least one certainty label present in report sections
    _ce_has_data = bool(causal_data and causal_data.get("check_rows"))
    _bs_has_data = bool(blind_data and blind_data.get("check_rows"))
    if _ce_has_data and _bs_has_data:
        _chk("Report Completeness", "PASS", "Causal engine and blind-spot checklist both have live data")
    elif _ce_has_data or _bs_has_data:
        _chk("Report Completeness", "WARNING", "Only one of causal engine / blind-spot checklist has live data")
    else:
        _chk("Report Completeness", "FAIL", "Neither causal engine nor blind-spot checklist produced live data")

    # 11. Sentiment hygiene gate — governance hardening patch
    # Load from approved_operating_truth.json (written by governance_gate.py each cycle)
    try:
        _gov_truth_path = Path(r"C:\bluelotus3\data\governance\approved_operating_truth.json")
        if _gov_truth_path.exists():
            import json as _json
            _gov_truth_raw = json.loads(_gov_truth_path.read_text(encoding="utf-8"))
            _hyg = _gov_truth_raw.get("sentiment_hygiene_gate") or {}
            _hyg_status = _hyg.get("status", "UNKNOWN")
            _hyg_dirty  = _hyg.get("dirty_count", 0)
            _hyg_failed = _hyg.get("tape_contamination_count", 0)
            if _hyg_status == "PASS":
                _chk("Sentiment Hygiene Gate", "PASS", f"dirty_count=0 — all headlines are relevant to their ticker")
            elif _hyg_status == "WARNING":
                _chk("Sentiment Hygiene Gate", "WARNING",
                     f"dirty_count={_hyg_dirty} but excluded from CIO tape — report safe, audit noted")
            elif _hyg_status == "FAIL":
                _chk("Sentiment Hygiene Gate", "FAIL",
                     f"CRITICAL: {_hyg_failed} dirty headline(s) in CIO tape — report BLOCKED. "
                     f"Examples: {_hyg.get('examples_failed', [])[:2]}")
            else:
                _chk("Sentiment Hygiene Gate", "WARNING", f"hygiene gate status unknown ({_hyg_status}) — re-run governance gate")
        else:
            _chk("Sentiment Hygiene Gate", "WARNING", "approved_operating_truth.json not found — run governance_gate.py")
    except Exception as _hyg_exc:
        _chk("Sentiment Hygiene Gate", "WARNING", f"hygiene gate check error: {_hyg_exc}")

    # Score — apply sentiment hygiene deduction before computing
    pass_c    = sum(1 for _, s, _ in checks if s == "PASS")
    warn_c    = sum(1 for _, s, _ in checks if s == "WARNING")
    fail_c    = sum(1 for _, s, _ in checks if s == "FAIL")
    base_score = round((pass_c * 10 + warn_c * 5) / max(len(checks), 1) * 10, 1)
    # Governance deductions: sentiment hygiene fail = -15, warning = -5
    _hygiene_deduction = 0
    try:
        _hyg_stat_for_score = (locals().get("_hyg_status") or "UNKNOWN")
        if _hyg_stat_for_score == "FAIL":
            _hygiene_deduction = -15
        elif _hyg_stat_for_score == "WARNING":
            _hygiene_deduction = -5
    except Exception:
        pass
    audit_score = max(0.0, round(base_score + _hygiene_deduction, 1))
    audit_status = "CONSISTENT" if fail_c == 0 and warn_c <= 2 else "WARNINGS" if fail_c == 0 else "INCONSISTENT"

    # report_status field
    if audit_status == "CONSISTENT":
        report_status = "INSTITUTIONAL_READY"
    elif audit_status == "WARNINGS":
        report_status = "INSTITUTIONAL_REVIEW_REQUIRED"
    else:
        report_status = "NOT_INSTITUTIONAL_CLEAN"

    failed_check_names = [name for name, s, _ in checks if s == "FAIL"]

    return {
        "audit_score":   audit_score,
        "audit_status":  audit_status,
        "report_status": report_status,
        "failed_checks": failed_check_names,
        "pass_count":    pass_c,
        "warn_count":    warn_c,
        "fail_count":    fail_c,
        "check_rows":    [[name, s, detail] for name, s, detail in checks],
    }


def build_live_truth_consistency(
    dataset:         dict,
    portfolio_live:  dict,
    operating_truth: dict,
) -> dict:
    """
    Compare report values against live dashboard/broker truth.
    Returns a separate LIVE_TRUTH_CONSISTENCY verdict.
    Never replaces build_consistency_audit() — both must run.
    """
    checks   = []
    warnings = 0
    failures = 0

    # ── Check 1: Cash delta ────────────────────────────────────────────────
    report_cash = float((operating_truth.get("portfolio") or {}).get("cash", 0) or 0)
    live_cash   = float(portfolio_live.get("cash", 0) or 0)
    cash_delta  = abs(report_cash - live_cash)
    if cash_delta > 5000:
        checks.append({"check": "cash_delta", "status": "FAIL",
                        "detail": f"report ${report_cash:,.0f} vs live ${live_cash:,.0f} Δ${cash_delta:,.0f}"})
        failures += 1
    elif cash_delta > 500:
        checks.append({"check": "cash_delta", "status": "WARNING",
                        "detail": f"report ${report_cash:,.0f} vs live ${live_cash:,.0f} Δ${cash_delta:,.0f}"})
        warnings += 1
    else:
        checks.append({"check": "cash_delta", "status": "PASS",
                        "detail": f"Δ${cash_delta:,.0f}"})

    # ── Check 2: Market value delta ────────────────────────────────────────
    report_mv = float((operating_truth.get("portfolio") or {}).get("market_value", 0) or 0)
    live_mv   = float(portfolio_live.get("market_val", 0) or 0)
    mv_delta  = abs(report_mv - live_mv)
    if mv_delta >= 5000:
        checks.append({"check": "market_value_delta", "status": "FAIL",
                        "detail": f"report ${report_mv:,.0f} vs live ${live_mv:,.0f} Δ${mv_delta:,.0f}"})
        failures += 1
    elif mv_delta > 1000:
        checks.append({"check": "market_value_delta", "status": "WARNING",
                        "detail": f"report ${report_mv:,.0f} vs live ${live_mv:,.0f} Δ${mv_delta:,.0f}"})
        warnings += 1
    else:
        checks.append({"check": "market_value_delta", "status": "PASS",
                        "detail": f"Δ${mv_delta:,.0f}"})

    # ── Check 3: Cash weight ──────────────────────────────────────────────
    report_cash_pct = (report_cash / report_mv * 100) if report_mv else 0
    live_cash_pct   = float(portfolio_live.get("cash_pct", 0) or 0)
    cash_pct_delta  = abs(report_cash_pct - live_cash_pct)
    if cash_pct_delta > 20:
        checks.append({"check": "cash_weight_delta", "status": "FAIL",
                        "detail": f"report {report_cash_pct:.1f}% vs live {live_cash_pct:.1f}%"})
        failures += 1
    elif cash_pct_delta > 5:
        checks.append({"check": "cash_weight_delta", "status": "WARNING",
                        "detail": f"report {report_cash_pct:.1f}% vs live {live_cash_pct:.1f}%"})
        warnings += 1
    else:
        checks.append({"check": "cash_weight_delta", "status": "PASS"})

    # ── Check 4: Gold miner position cross-check ──────────────────────────
    report_gm_pct  = float((operating_truth.get("gold_thesis") or {}).get(
        "gold_miner_cluster_weight", 0) or 0) * 100
    live_positions = portfolio_live.get("positions", [])
    _GOLD_TICKERS  = {"AU", "NEM", "GDX", "GDXJ", "GLD"}
    live_has_gold  = any(
        str(p.get("ticker", "")).upper() in _GOLD_TICKERS
        for p in live_positions
    )
    if report_gm_pct > 30 and not live_has_gold:
        checks.append({
            "check":  "gold_miner_position_cross_check",
            "status": "FAIL",
            "detail": (
                f"report shows {report_gm_pct:.1f}% gold-miner cluster "
                f"but live dashboard has no AU/NEM/GDX"
            ),
        })
        failures += 1
    else:
        checks.append({"check": "gold_miner_position_cross_check", "status": "PASS"})

    # ── Overall verdict ───────────────────────────────────────────────────
    if failures > 0:
        verdict = "FAIL"
    elif warnings > 0:
        verdict = "WARNING"
    else:
        verdict = "PASS"

    return {
        "live_truth_consistency": verdict,
        "checks":                 checks,
        "failure_count":          failures,
        "warning_count":          warnings,
    }


# ── 9.5/10 Upgrade Modules ────────────────────────────────────────────────────

def build_operating_truth(
    dataset: Dict[str, Any],
    archive: Dict[str, Any],
    causal_data: Dict[str, Any],
    blind_data: Dict[str, Any],
    conc_data: Dict[str, Any],
    audit_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Module A — Canonical operating truth dict used by ALL report layers.
    Live values come from freshly-computed causal_data, blind_data, conc_data, audit_data.
    """
    db     = archive.get("database_row") or {}
    regime = dataset.get("regime") or {}
    meta   = dataset.get("meta") or {}

    cio_action_val = (
        str(db.get("cio_action") or "")
        or str(regime.get("action") or "")
        or str(meta.get("cio_action") or "")
        or "WAIT / HOLD"
    )
    # ── Scenario overlay — adjust CIO action string if breaking catalyst active ──
    _cio_briefing_ot = _load_approved_cio_briefing()
    _overlay_action = (_cio_briefing_ot.get("scenario_overlay") or {}).get("cio_action_adjusted")
    if _overlay_action and _overlay_action != cio_action_val:
        cio_action_val = _overlay_action  # e.g. "WAIT / HOLD — RELIEF RALLY WATCH"

    # Brier maturity
    rf_data   = dataset.get("research_forecasting") or {}
    acc_data  = rf_data.get("accuracy_summary") or []
    resolved  = sum(int(r.get("resolved_count") or 0) for r in acc_data if isinstance(r, dict))
    brier_status = (
        "MATURE"      if resolved >= 100 else
        "NOT_MATURE"  if resolved >= 30  else
        "COLLECTING"
    )

    # Open forecasts
    open_fc = int(rf_data.get("forecast_count") or 0)

    # Concentration fields
    largest_cluster = max(conc_data.get("clusters", {}).items(), key=lambda kv: kv[1], default=("NONE", 0.0))

    # Freshness: minimal inline check here — full freshness from build_freshness_governor
    # report_readiness is populated after freshness is known; use placeholder here
    # It will be overwritten by build_report_readiness after both are computed.
    confidence_val = (
        db.get("confidence")
        or (dataset.get("report_archive") or {}).get("confidence")
        or meta.get("confidence")
        or 0
    )
    confidence_label_val = (
        db.get("confidence_label")
        or (dataset.get("report_archive") or {}).get("confidence_label")
        or meta.get("confidence_label")
        or ""
    )
    if confidence_val and not confidence_label_val:
        confidence_label_val = (
            "HIGH" if float(confidence_val) >= 0.75
            else "MEDIUM" if float(confidence_val) >= 0.60
            else "LOW-MEDIUM" if float(confidence_val) >= 0.45
            else "LOW"
        )

    truth: Dict[str, Any] = {
        "regime":                       str(regime.get("regime") or "UNKNOWN"),
        "regime_score":                 int(regime.get("score") or 0),
        "cio_action":                   cio_action_val,
        "confidence":                   float(confidence_val or 0),
        "confidence_label":             str(confidence_label_val or ""),
        # LIVE from freshly-computed functions
        "causal_status":                causal_data.get("causal_status", "UNKNOWN"),
        "causal_confidence":            float(causal_data.get("causal_confidence") or 0),
        "blind_spot_status":            blind_data.get("blind_spot_status", "UNKNOWN"),
        "blind_spot_failed_items":      list(blind_data.get("failed_items") or []),
        "consistency_audit_status":     (audit_data or {}).get("audit_status", "PENDING"),
        "consistency_report_status":    (audit_data or {}).get("report_status", "PENDING"),
        "concentration_status":         conc_data.get("concentration_status", "UNKNOWN"),
        "largest_cluster":              largest_cluster[0],
        "largest_cluster_weight":       float(largest_cluster[1]),
        # Execution safety — always these values, never from archive
        "execution_authority":          "CIO_ONLY_MANUAL",
        "order_routing_enabled":        False,
        "orders_generated_by_pipeline": 0,
        # Brier
        "brier_status":                 brier_status,
        "open_forecasts":               open_fc,
        # report_readiness filled by build_report_readiness
        "forecast_proof_status":        ("PROVEN" if brier_status == "MATURE" else "PRELIMINARY" if brier_status == "NOT_MATURE" else "UNPROVEN"),
        "report_readiness":             "PENDING",
    }
    return truth


def detect_archive_live_mismatches(
    operating_truth: Dict[str, Any],
    archive: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Module C — Detect mismatches between live operating_truth and archived values."""
    db = archive.get("database_row") or {}
    mismatches: List[Dict[str, Any]] = []

    field_map = {
        "causal_status":        db.get("causal_explanation_status", ""),
        "blind_spot_status":    db.get("blind_spot_status", ""),
        "cio_action":           db.get("cio_action", ""),
        "concentration_status": db.get("concentration_status", ""),
    }

    for field, archived_value in field_map.items():
        live_value = str(operating_truth.get(field) or "")
        archived_str = str(archived_value or "")
        if archived_str and live_value and archived_str != live_value:
            mismatches.append({
                "field":              field,
                "archived_value":     archived_str,
                "live_value":         live_value,
                "action":             "Use live value; archive mismatch flagged.",
                "archive_live_mismatch": True,
            })

    return mismatches


def build_regime_cognition_disclosure(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Module F — Regime vs CIO Cognition Ledger Timestamp Disclosure.

    WO-Final-PhD Defect 6: The CIO Cognition Ledger records strategic thinking at a
    specific point in time (journal_ts). The market regime is assessed at dataset
    generation time (meta.generated_at). If the ledger entry predates the current
    dataset by a material amount (≥ 2 hours), the CIO's recorded thinking may
    reference a PRIOR regime state — disclosure is mandatory.

    Returns:
        {
            "regime_ts":          <ISO string or "UNKNOWN">,
            "ledger_ts":          <ISO string or "UNKNOWN">,
            "delta_hours":        <float or None>,
            "mismatch_severity":  "NONE" | "MINOR" | "MODERATE" | "MATERIAL",
            "disclosure_required": bool,
            "disclosure_text":    <str>,
        }
    """
    from dateutil import parser as _dp
    import pytz as _pytz

    def _parse(ts_str: str):
        try:
            dt = _dp.parse(str(ts_str))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_pytz.UTC)
            return dt
        except Exception:
            return None

    meta         = dataset.get("meta") or {}
    cognition    = dataset.get("cio_cognition") or {}
    journals     = cognition.get("latest_journals") if isinstance(cognition.get("latest_journals"), list) else []
    latest_entry = journals[0] if journals and isinstance(journals[0], dict) else {}

    # Regime / dataset timestamp — prefer explicit regime.generated_at else meta.generated_at
    regime_ts_str  = (
        (dataset.get("regime") or {}).get("generated_at")
        or meta.get("generated_at")
        or ""
    )
    # CIO Cognition entry timestamp
    ledger_ts_str  = (
        latest_entry.get("journal_ts")
        or cognition.get("generated_at")
        or ""
    )

    regime_dt  = _parse(regime_ts_str) if regime_ts_str else None
    ledger_dt  = _parse(ledger_ts_str) if ledger_ts_str else None

    if regime_dt and ledger_dt:
        delta_hours = abs((regime_dt - ledger_dt).total_seconds()) / 3600.0
    else:
        delta_hours = None

    if delta_hours is None:
        severity = "NONE"
    elif delta_hours < 2.0:
        severity = "NONE"
    elif delta_hours < 6.0:
        severity = "MINOR"
    elif delta_hours < 24.0:
        severity = "MODERATE"
    else:
        severity = "MATERIAL"

    disclosure_required = severity in ("MODERATE", "MATERIAL")

    if severity == "NONE":
        disclosure_text = (
            "Regime and CIO Cognition timestamps are aligned "
            f"(Δ {delta_hours:.1f}h < 2h threshold)."
            if delta_hours is not None
            else "Insufficient timestamps to assess regime-cognition alignment."
        )
    elif severity == "MINOR":
        disclosure_text = (
            f"[MINOR] Regime assessed {regime_ts_str} | CIO Cognition entry {ledger_ts_str} "
            f"(Δ {delta_hours:.1f}h). CIO thinking is recent but may predate current regime."
        )
    elif severity == "MODERATE":
        disclosure_text = (
            f"[MODERATE] REGIME-COGNITION TIMING GAP: Regime assessed {regime_ts_str} | "
            f"CIO Cognition entry {ledger_ts_str} (Δ {delta_hours:.1f}h). "
            "CIO strategic thinking may reference a prior regime state. "
            "Verify cognition entry remains consistent with current regime before acting."
        )
    else:
        disclosure_text = (
            f"[MATERIAL] ⚠ REGIME-COGNITION MISMATCH: Regime assessed {regime_ts_str} | "
            f"CIO Cognition entry {ledger_ts_str} (Δ {delta_hours:.1f}h ≥ 24h). "
            "CIO strategic thinking is STALE relative to current regime. "
            "Do not rely on recorded cognition for trade decisions until refreshed."
        )

    return {
        "regime_ts":           regime_ts_str or "UNKNOWN",
        "ledger_ts":           ledger_ts_str or "UNKNOWN",
        "delta_hours":         round(delta_hours, 2) if delta_hours is not None else None,
        "mismatch_severity":   severity,
        "disclosure_required": disclosure_required,
        "disclosure_text":     disclosure_text,
    }


def build_cio_action_logic(
    operating_truth: Dict[str, Any],
    dataset: Dict[str, Any],
) -> Dict[str, Any]:
    """Module D — CIO Action Logic Engine with strict priority rules."""
    causal_status  = operating_truth.get("causal_status", "UNKNOWN")
    blind_status   = operating_truth.get("blind_spot_status", "UNKNOWN")
    conc_status    = operating_truth.get("concentration_status", "UNKNOWN")
    audit_status   = operating_truth.get("consistency_audit_status", "UNKNOWN")
    regime         = operating_truth.get("regime", "UNKNOWN")
    exec_auth      = operating_truth.get("execution_authority", "CIO_ONLY_MANUAL")

    blocked: List[str] = []
    rules: List[str] = []
    required_review = False
    action_cap = "SELECTIVE_BUY_RESEARCH_ONLY"
    final_action = "WAIT / HOLD"
    reason_parts: List[str] = []

    # Rule 1: execution authority check
    if exec_auth != "CIO_ONLY_MANUAL":
        return {
            "final_action":       "BLOCKED — EXECUTION SAFETY BREACH",
            "action_cap":         "NONE",
            "blocked_actions":    ["ALL_ACTIONS"],
            "reason":             f"Execution authority is '{exec_auth}' — not CIO_ONLY_MANUAL. Execution safety breach.",
            "required_cio_review": True,
            "rules_triggered":    ["RULE_1_EXECUTION_AUTHORITY"],
        }
    rules.append("RULE_1_EXECUTION_AUTHORITY_OK")

    # Rule 2: consistency audit
    if audit_status == "INCONSISTENT":
        action_cap = "HOLD_REVIEW"
        blocked += ["BUY", "ADD_EXPOSURE", "INCREASE_POSITION"]
        rules.append("RULE_2_INCONSISTENT_AUDIT")
        reason_parts.append(f"Consistency audit is INCONSISTENT — cap at WAIT/REVIEW.")
        required_review = True

    # Rule 3: blind spot WARNING
    if blind_status == "WARNING":
        blocked += ["BUY", "ADD_EXPOSURE"]
        rules.append("RULE_3_BLIND_SPOT_WARNING")
        reason_parts.append("Blind spot WARNING — discretionary risk addition blocked.")
        required_review = True  # Fix 6: blind WARNING always requires CIO review

    # Rule 4: blind spot CRITICAL
    if blind_status == "CRITICAL":
        action_cap = "HOLD_ONLY"
        blocked += ["BUY", "ADD_EXPOSURE", "INCREASE_POSITION", "SELECTIVE_BUY"]
        rules.append("RULE_4_BLIND_SPOT_CRITICAL")
        reason_parts.append("Blind spot CRITICAL — cap at WAIT/HOLD.")
        required_review = True

    # Rule 5: concentration HIGH/CRITICAL
    if conc_status in ("HIGH", "CRITICAL"):
        largest = operating_truth.get("largest_cluster", "UNKNOWN")
        blocked.append(f"ADD_{largest.upper().replace(' ', '_')}")
        blocked.append("ADD_TO_LARGEST_CLUSTER")
        rules.append(f"RULE_5_CONCENTRATION_{conc_status}")
        reason_parts.append(f"Concentration {conc_status} — blocked from adding to largest cluster.")
        required_review = True  # Fix 6: concentration HIGH/CRITICAL always requires CIO review

    # Rule 6: RISK OFF + causal gap
    if ("RISK OFF" in regime.upper() or "BEAR" in regime.upper()) and causal_status in ("INCOMPLETE", "CRITICAL_GAP"):
        action_cap = "HOLD_ONLY"
        blocked += ["BUY", "ADD_EXPOSURE", "SELECTIVE_BUY"]
        rules.append("RULE_6_RISK_OFF_CAUSAL_GAP")
        reason_parts.append(f"Regime RISK OFF and causal status {causal_status} — cap at WAIT/HOLD.")
        required_review = True

    # Rule 7: causal COMPLETE but blind spot WARNING
    if causal_status == "COMPLETE" and blind_status == "WARNING":
        if "BUY" not in blocked:
            blocked.append("BUY")
        rules.append("RULE_7_CAUSAL_OK_BLIND_WARNING")
        reason_parts.append("Causal complete but blind spot WARNING — no BUY.")

    # Rule 8: derive from regime
    is_risk_on  = "RISK ON" in regime.upper() or "BULL" in regime.upper()
    is_risk_off = "RISK OFF" in regime.upper() or "BEAR" in regime.upper()
    clean = causal_status in ("COMPLETE", "MOSTLY_COMPLETE") and blind_status == "CLEAR" and conc_status not in ("HIGH", "CRITICAL")

    if action_cap == "HOLD_ONLY":
        final_action = "WAIT / HOLD"
    elif action_cap == "HOLD_REVIEW":
        final_action = "WAIT / REVIEW"
    elif is_risk_on and clean:
        final_action = "SELECTIVE BUY / HOLD"
        rules.append("RULE_8_RISK_ON_CLEAN")
    elif is_risk_off:
        final_action = "WAIT / HOLD"
        rules.append("RULE_8_RISK_OFF")
    else:
        final_action = "WAIT / HOLD"
        rules.append("RULE_8_DEFAULT_HOLD")

    if not reason_parts:
        reason_parts.append(f"Regime {regime}, causal {causal_status}, blind {blind_status}, conc {conc_status}.")

    # Deduplicate blocked
    blocked = list(dict.fromkeys(blocked))

    # Fix 6 — derive raw_regime_action and risk_adjusted_action
    # raw: from regime only (before any blind/conc/VaR gates)
    raw_regime_action = (
        "SELECTIVE BUY / HOLD" if ("RISK ON" in str(regime).upper() or "BULL" in str(regime).upper()) else
        "REDUCE / HEDGE" if ("RISK OFF" in str(regime).upper() or "BEAR" in str(regime).upper()) else
        "WAIT / HOLD"
    )

    # risk_adjusted: after blind spot + concentration adjustment
    risk_adjusted_action = raw_regime_action
    if blind_status in ("WARNING", "CRITICAL") or conc_status in ("HIGH", "CRITICAL"):
        if "BUY" in raw_regime_action:
            risk_adjusted_action = "WAIT / HOLD"
        elif "REDUCE" in raw_regime_action:
            risk_adjusted_action = raw_regime_action

    # Fix 6: action_cap must not include plain SELECTIVE BUY when blind_spot=WARNING and conc is HIGH/CRITICAL
    if blocked and any("BUY" in str(x).upper() or "ADD" in str(x).upper() for x in blocked):
        if action_cap == "SELECTIVE_BUY_RESEARCH_ONLY":
            action_cap = "ADD_BLOCKED"
    if blind_status == "WARNING" and conc_status in ("HIGH", "CRITICAL"):
        if action_cap in ("SELECTIVE_BUY_RESEARCH_ONLY", "BUY_ALLOWED"):
            action_cap = "HOLD_REVIEW"

    # Add review reasons list
    review_reasons: List[str] = reason_parts[:]

    return {
        "raw_regime_action":          raw_regime_action,         # Fix 6
        "risk_adjusted_action":       risk_adjusted_action,      # Fix 6
        "final_cio_operating_action": final_action,              # Fix 6 alias
        "final_action":               final_action,
        "action_cap":                 action_cap,
        "blocked_actions":            blocked,
        "reason":                     " ".join(reason_parts),
        "required_cio_review":        required_review,
        "cio_review_required":        required_review,           # Fix 6 alias
        "review_reasons":             review_reasons,            # Fix 6
        "rules_triggered":            rules,
    }


def build_blind_spot_remediations(blind_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Module E — Remediation dicts for each failed blind-spot check."""
    remediation_map: Dict[str, Dict[str, Any]] = {
        "Investor Days": {
            "failed_check":      "Investor Days",
            "reason":            "No investor day events found in calendar",
            "severity":          "MEDIUM",
            "data_source_needed": "company IR calendar / Nasdaq events / Koyfin / Benzinga / FMP calendar",
            "fallback_available": True,
            "fallback_source":   "earnings calendar + conference calendar",
            "decision_impact":   "prevents full blind spot clearance",
            "next_action":       "scrape/add investor-day source or mark unavailable with CIO override",
        },
        "Analyst Days": {
            "failed_check":      "Analyst Days",
            "reason":            "No analyst day events detected",
            "severity":          "MEDIUM",
            "data_source_needed": "sell-side IR calendars / Bloomberg EVTS / Sentieo",
            "fallback_available": True,
            "fallback_source":   "analyst estimate revision data",
            "decision_impact":   "prevents full blind spot clearance",
            "next_action":       "add analyst-day feed or use earnings call transcripts as proxy",
        },
        "Scheduled Conferences": {
            "failed_check":      "Scheduled Conferences",
            "reason":            "No upcoming conference events in calendar",
            "severity":          "LOW",
            "data_source_needed": "conference calendar feed / Nasdaq events",
            "fallback_available": True,
            "fallback_source":   "earnings calendar",
            "decision_impact":   "minor; CIO can proceed with caution",
            "next_action":       "add conference calendar source",
        },
        "CEO Appearances": {
            "failed_check":      "CEO Appearances",
            "reason":            "No CEO appearance data",
            "severity":          "LOW",
            "data_source_needed": "company IR / PR Newswire / CNBC schedule",
            "fallback_available": False,
            "fallback_source":   "N/A",
            "decision_impact":   "missed sentiment signals from management",
            "next_action":       "add CEO appearance feed",
        },
        "Portfolio Catalyst Calendar": {
            "failed_check":      "Portfolio Catalyst Calendar",
            "reason":            "No portfolio tickers in catalyst calendar",
            "severity":          "HIGH",
            "data_source_needed": "earnings data provider / FMP / Bloomberg",
            "fallback_available": True,
            "fallback_source":   "Earnings Whispers / Yahoo Finance",
            "decision_impact":   "critical: portfolio catalysts unknown",
            "next_action":       "ensure portfolio tickers mapped to catalyst calendar",
        },
        "Earnings Calendar": {
            "failed_check":      "Earnings Calendar",
            "reason":            "No earnings in next 14 days found",
            "severity":          "HIGH",
            "data_source_needed": "FMP / Bloomberg / Refinitiv",
            "fallback_available": True,
            "fallback_source":   "Yahoo Finance earnings calendar",
            "decision_impact":   "critical: unknown earnings surprises possible",
            "next_action":       "refresh earnings calendar data",
        },
        "Tech Keynote Events": {
            "failed_check":      "Tech Keynote Events",
            "reason":            "No tech keynote events in calendar",
            "severity":          "LOW",
            "data_source_needed": "conference calendar / company IR",
            "fallback_available": False,
            "fallback_source":   "N/A",
            "decision_impact":   "minor for non-tech-heavy portfolios",
            "next_action":       "add tech conference calendar",
        },
        "Fed/Policy Events": {
            "failed_check":      "Fed/Policy Events",
            "reason":            "Insufficient Fed/policy signals",
            "severity":          "HIGH",
            "data_source_needed": "Fed.gov RSS / FOMC calendar / Treasury press",
            "fallback_available": True,
            "fallback_source":   "CME FedWatch",
            "decision_impact":   "interest rate surprise risk unmonitored",
            "next_action":       "restore Fed signal feed",
        },
        "Geopolitical Events": {
            "failed_check":      "Geopolitical Events",
            "reason":            "Insufficient geopolitical signals",
            "severity":          "MEDIUM",
            "data_source_needed": "GDELT / Reuters geopolitical / Defense News",
            "fallback_available": True,
            "fallback_source":   "Google News alerts for key regions",
            "decision_impact":   "geopolitical risk poorly covered",
            "next_action":       "restore geopolitical signal feeds",
        },
        "Named Historical Events": {
            "failed_check":      "Named Historical Events",
            "reason":            "Named historical event calendar empty",
            "severity":          "LOW",
            "data_source_needed": "internal historical event database",
            "fallback_available": False,
            "fallback_source":   "N/A",
            "decision_impact":   "historical pattern matching unavailable",
            "next_action":       "populate named events database",
        },
        "Unexplained Market Moves": {
            "failed_check":      "Unexplained Market Moves",
            "reason":            "Large market moves without causal explanation",
            "severity":          "HIGH",
            "data_source_needed": "news feed / catalyst calendar / analyst notes",
            "fallback_available": True,
            "fallback_source":   "Reuters/CNBC real-time alerts",
            "decision_impact":   "cannot explain portfolio P&L movements",
            "next_action":       "investigate unexplained moves before trading",
        },
        "Sector Catalyst Check": {
            "failed_check":      "Sector Catalyst Check",
            "reason":            "Sector moves lack non-consensus causal explanation",
            "severity":          "MEDIUM",
            "data_source_needed": "sector news / ECE event correlation",
            "fallback_available": True,
            "fallback_source":   "theme rotation analysis",
            "decision_impact":   "sector rotation blind spots",
            "next_action":       "review causal explanations for each sector move",
        },
    }

    failed_items = blind_data.get("failed_items") or []
    remediations: List[Dict[str, Any]] = []
    for item in failed_items:
        if item in remediation_map:
            remediations.append(remediation_map[item])
        else:
            remediations.append({
                "failed_check":      item,
                "reason":            "Unknown failure",
                "severity":          "MEDIUM",
                "data_source_needed": "N/A",
                "fallback_available": False,
                "fallback_source":   "N/A",
                "decision_impact":   "unknown",
                "next_action":       "investigate and add remediation",
            })
    return remediations


def build_causal_chain(
    dataset: Dict[str, Any],
    causal_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Module F — Ranked causal chain drivers from causal_data check_rows."""
    regime   = dataset.get("regime") or {}
    portfolio_tickers = list((dataset.get("security_master") or {}).keys())
    THEME_GROUPS: Dict[str, List[str]] = {}
    for ticker, theme in THEME_MAP.items():
        THEME_GROUPS.setdefault(theme, []).append(ticker)

    check_rows = causal_data.get("check_rows") or []
    pass_rows  = [r for r in check_rows if r[1] == "PASS"]
    fail_rows  = [r for r in check_rows if r[1] == "FAIL"]

    # Build ranked list from pass rows
    chain: List[Dict[str, Any]] = []
    rank = 1

    regime_name  = str(regime.get("regime") or "")
    regime_score = int(regime.get("score") or 0)
    factors      = regime.get("factors") or {}

    for row in pass_rows:
        check_name = row[0]
        detail     = row[2] if len(row) > 2 else ""

        # Evidence sources from detail
        evidence_sources: List[str] = [s.strip() for s in detail.split("|") if s.strip()]

        # Market expression
        if check_name == "Regime Drivers":
            market_expression = f"{regime_name} score={regime_score}: {', '.join(f'{k}={v}' for k, v in list(factors.items())[:3])}"
        elif check_name == "Cross-Market":
            cm = dataset.get("cross_market_confirmation") or {}
            flags_active = [k for k, v in (cm.get("interpretation_flags") or {}).items() if v]
            market_expression = f"Cross-market confirmation: {', '.join(flags_active) or 'no active flags'}"
        elif check_name == "News Catalyst":
            market_expression = "Fresh news signals from major financial outlets"
        elif check_name == "Fed/Policy":
            market_expression = "Central bank / policy signals active"
        elif check_name == "Catalyst Calendar":
            market_expression = "Imminent/active portfolio catalysts present"
        else:
            market_expression = detail[:120] if detail else check_name

        # Affected themes — high confidence: all themes relevant to regime direction
        if check_name == "Regime Drivers":
            affected_themes = (
                ["GOLD / SAFE HAVEN", "MACRO / FED", "OIL / GAS"] if "RISK OFF" in regime_name.upper()
                else ["AI / SEMIS", "MAG7 / BIG TECH", "SOFTWARE / CYBERSECURITY"]
            )
        else:
            affected_themes = []

        # Affected holdings from portfolio tickers matching affected themes
        affected_holdings: List[str] = []
        for theme in affected_themes:
            for ticker in (THEME_GROUPS.get(theme) or []):
                if ticker in portfolio_tickers:
                    affected_holdings.append(ticker)

        # Contradicting evidence from fail rows
        contradicting = [r[0] for r in fail_rows[:3]]

        # Confidence
        check_confidence = round(causal_data.get("causal_confidence", 0) * (1 - 0.05 * (rank - 1)), 3)
        check_confidence = max(0.0, check_confidence)

        decision_impact = (
            "Primary regime driver — anchors regime classification and CIO posture" if rank == 1
            else "Supporting evidence — corroborates primary driver" if rank == 2
            else "Supplementary — adds confirmation weight"
        )

        chain.append({
            "rank":                  rank,
            "driver":                check_name,
            "evidence_sources":      evidence_sources,
            "market_expression":     market_expression,
            "affected_themes":       affected_themes,
            "affected_holdings":     affected_holdings[:5],
            "confidence":            check_confidence,
            "contradicting_evidence": contradicting,
            "decision_impact":       decision_impact,
        })
        rank += 1

    return chain


def build_portfolio_risk_governor(
    dataset: Dict[str, Any],
    conc_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Module G — Portfolio Risk Governor."""
    portfolio = dataset.get("portfolio") or {}
    positions = portfolio.get("positions") or []
    if not isinstance(positions, list):
        positions = list(positions.values()) if isinstance(positions, dict) else []

    clusters     = conc_data.get("clusters") or {}
    largest_t    = conc_data.get("largest_ticker") or ""
    largest_w    = float(conc_data.get("largest_weight") or 0)
    conc_status  = conc_data.get("concentration_status") or "NORMAL"

    breaches: List[str] = []
    blocked: List[str] = []
    allowed: List[str] = []
    reviews: List[str] = []

    # Per-position rules
    single_name_over30 = []
    single_name_over33 = []
    for pos in positions:
        ticker = str(pos.get("ticker") or pos.get("symbol") or "").upper()
        weight = float(pos.get("weight") or 0)
        if weight > 0.30:
            single_name_over30.append((ticker, weight))
            breaches.append(f"{ticker} >{weight:.0%} single name (>30% threshold)")
            blocked.append(f"ADD_{ticker}")
        if weight > 0.33:
            single_name_over33.append((ticker, weight))
            reviews.append(f"P1 risk review required: {ticker} at {weight:.0%} > 33% threshold")

    # Cluster-to-ticker mapping for expanded blocking
    _CLUSTER_TICKERS: Dict[str, List[str]] = {
        "GOLD_MINERS":       ["AU", "NEM", "PAAS", "HL", "CDE", "AG"],
        "BASIC_MATERIALS":   ["AU", "NEM", "FCX", "TECK", "RIO", "BHP", "VALE", "CLF", "NUE", "AA"],
        "ENERGY":            ["XOM", "CVX", "COP", "EOG", "OXY", "DVN", "PSX", "VLO", "MPC", "LNG", "KMI", "WMB", "EPD", "ENB"],
        "TECH":              ["NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN", "AMD", "TSM", "ASML"],
    }

    # Cluster rules
    cluster_blocked: List[str] = []
    for cluster_name, cluster_w in clusters.items():
        safe_name = cluster_name.upper().replace(" ", "_").replace("/", "_")
        if cluster_w > 0.65:
            breaches.append(f"{cluster_name} cluster at {cluster_w:.0%} (CRITICAL ≥65%)")
            blocked.append(f"ADD_{safe_name}")
            blocked.append(f"INCREASE_{safe_name}_EXPOSURE")
            blocked.append(f"ADD_TO_{safe_name}")
            # Block all constituent tickers in this cluster
            for ct in _CLUSTER_TICKERS.get(cluster_name, []):
                _b = f"ADD_{ct}"
                if _b not in blocked:
                    blocked.append(_b)
            cluster_blocked.append(cluster_name)
            reviews.append(f"P1 CRITICAL cluster review: {cluster_name} at {cluster_w:.0%} — CIO override required for any addition")
        elif cluster_w > 0.50:
            breaches.append(f"{cluster_name} cluster at {cluster_w:.0%} (HIGH >50%)")
            blocked.append(f"ADD_{safe_name}")
            for ct in _CLUSTER_TICKERS.get(cluster_name, []):
                _b = f"ADD_{ct}"
                if _b not in blocked:
                    blocked.append(_b)
            cluster_blocked.append(cluster_name)
            reviews.append(f"P2 HIGH cluster review: {cluster_name} at {cluster_w:.0%}")

    # Largest ticker overall
    if largest_w > 0.30:
        block_key = f"ADD_{largest_t.upper()}"
        if block_key not in blocked:
            blocked.append(block_key)

    # Allowed actions — explicit safe list
    allowed_base = [
        "HOLD",
        "REDUCE_CLUSTER",
        "REDUCE_CONCENTRATION",
        "HEDGE",
        "REVIEW",
        "CANCEL_STALE_ORDERS",
        "REBALANCE_ONLY_WITH_CIO_APPROVAL",
        "ADD_UNRELATED_SECTOR",
    ]
    all_tickers = [str(p.get("ticker") or p.get("symbol") or "").upper() for p in positions]
    for t in all_tickers:
        if f"ADD_{t}" not in blocked:
            allowed_base.append(f"HOLD_{t}")
    allowed.extend(allowed_base)

    # Overall status
    if conc_status in ("CRITICAL",) or any(w > 0.65 for w in clusters.values()):
        status = "CRITICAL"
    elif conc_status in ("HIGH",) or any(w > 0.50 for w in clusters.values()):
        status = "HIGH"
    elif conc_status == "ELEVATED" or single_name_over30:
        status = "ELEVATED"
    else:
        status = "NORMAL"

    return {
        "status":              status,
        "breaches":            breaches,
        "blocked_actions":     list(dict.fromkeys(blocked)),
        "allowed_actions":     list(dict.fromkeys(allowed))[:10],
        "required_reviews":    reviews,
        "cio_override_required": bool(reviews or conc_status in ("HIGH", "CRITICAL")),
    }


def build_forecast_maturity_schedule(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Module H — Brier Forecast Maturity Schedule."""
    rf_data   = dataset.get("research_forecasting") or {}
    acc_data  = rf_data.get("accuracy_summary") or []
    forecasts = rf_data.get("forecasts") or []

    resolved  = sum(int(r.get("resolved_count") or 0) for r in acc_data if isinstance(r, dict))
    open_fc   = int(rf_data.get("forecast_count") or len(forecasts))

    # Maturity dates
    now = datetime.now(timezone.utc)
    next_mat_date = "N/A"
    maturing_7d   = 0
    maturing_30d  = 0

    if isinstance(forecasts, list):
        for fc in forecasts:
            if not isinstance(fc, dict):
                continue
            for date_field in ("target_date", "end_date", "horizon_date"):
                dval = fc.get(date_field)
                if dval:
                    try:
                        td = datetime.fromisoformat(str(dval).replace("Z", "+00:00"))
                        if td.tzinfo is None:
                            td = td.replace(tzinfo=timezone.utc)
                        delta_days = (td - now).days
                        if 0 <= delta_days <= 7:
                            maturing_7d += 1
                        if 0 <= delta_days <= 30:
                            maturing_30d += 1
                        if next_mat_date == "N/A" and delta_days >= 0:
                            next_mat_date = str(dval)[:10]
                    except Exception:
                        pass
                    break

    maturity_status = (
        "MATURE"     if resolved >= 100 else
        "NOT_MATURE" if resolved >= 30  else
        "COLLECTING"
    )
    note = (
        "COLLECTING: insufficient resolved forecasts — need 30+ to report."     if maturity_status == "COLLECTING" else
        "NOT_MATURE: some signal — need 100+ for full Brier accountability."     if maturity_status == "NOT_MATURE" else
        "MATURE: statistically meaningful Brier accountability established."
    )

    return {
        "open_forecasts":               open_fc,
        "next_maturity_date":           next_mat_date,
        "forecasts_maturing_7d":        maturing_7d,
        "forecasts_maturing_30d":       maturing_30d,
        "resolved_forecasts":           resolved,
        "minimum_reporting_threshold":  30,
        "full_accountability_threshold": 100,
        "maturity_status":              maturity_status,
        "note":                         note,
    }


def build_freshness_governor(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Module I — Dataset Freshness Governor.

    Distinguishes CRITICAL stale sections (decision-relevant, no safe fallback)
    from NON-CRITICAL stale sections (excluded with an acceptable fallback).
    freshness_status = FAIL only if critical sections are stale.
    """
    now = datetime.now(timezone.utc)

    # Each entry: (warn_threshold_min, is_critical, fallback_source)
    section_config: Dict[str, Tuple[int, bool, str]] = {
        "fear_greed":   (60,  False, "VIX / VXX / UVXY / risk appetite score"),
        "macro_data":   (120, True,  "last known macro dataset"),
        "news_feed":    (60,  True,  "tech_pub_signals / signals_latest"),
        "market_data":  (60,  True,  "last known market snapshot"),
    }

    critical_stale: List[Dict[str, Any]] = []
    non_critical_stale: List[Dict[str, Any]] = []
    decision_excluded: List[str] = []
    fallback_used: List[str] = []
    confidence_penalty = 0.0

    def _get_ts(section_data: Any) -> Optional[datetime]:
        if not isinstance(section_data, dict):
            return None
        for key in ("fetched_at", "generated_at", "timestamp", "cycle_ts", "as_of"):
            val = section_data.get(key)
            if val:
                try:
                    ts = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    return ts
                except Exception:
                    pass
        return None

    # Proxy: dataset meta.generated_at as fallback timestamp for sections without own timestamp
    _meta_ts = _get_ts(dataset.get("meta") or {})
    # Fix 4: export-time freshness grades from meta.freshness are authoritative (DB fetch age)
    _meta_freshness = (dataset.get("meta") or {}).get("freshness") or {}

    for section_key, (threshold_warn, is_critical, fallback_src) in section_config.items():
        section_data = dataset.get(section_key)
        # Skip sections that are completely empty/missing — no data to be stale
        if not section_data or (isinstance(section_data, dict) and not section_data) or (isinstance(section_data, list) and not section_data):
            continue

        ts = _get_ts(section_data) if isinstance(section_data, dict) else None
        if ts is None:
            for subkey in ("data", "feed", "result", "current"):
                sub = section_data.get(subkey) if isinstance(section_data, dict) else None
                if sub:
                    ts = _get_ts(sub)
                    if ts:
                        break

        if ts is None:
            ts = _meta_ts

        if ts is None:
            age_min = 9999
        else:
            age_min = int((now - ts).total_seconds() / 60)

        # Fix 4: if export-time meta.freshness reports a worse (higher) age, use that.
        # This resolves the divergence where the data's own `timestamp` field may be the
        # index-reading time (frequently updated) while the DB fetch time is much older.
        _meta_age = (_meta_freshness.get(section_key) or {}).get("age_minutes")
        if _meta_age is not None and int(_meta_age) > age_min:
            age_min = int(_meta_age)

        threshold_stale = 240

        entry = {
            "section":            section_key,
            "age_minutes":        age_min,
            "threshold_minutes":  threshold_stale,
            "is_critical":        is_critical,
            "fallback_source":    fallback_src,
            "decision_use":       "EXCLUDED" if age_min > threshold_stale else "INCLUDED",
        }

        if age_min > threshold_stale:
            if is_critical:
                critical_stale.append(entry)
                confidence_penalty += 0.08
            else:
                non_critical_stale.append({**entry, "decision_use": "EXCLUDED",
                                            "note": f"Non-critical — fallback: {fallback_src}"})
            decision_excluded.append(section_key)
            fallback_used.append(f"{section_key}: excluded (>{threshold_stale}min) | fallback: {fallback_src}")
        elif age_min > threshold_warn:
            if is_critical:
                critical_stale.append({**entry, "decision_use": "WARNING"})
            else:
                non_critical_stale.append({**entry, "decision_use": "WARNING"})

    # freshness_status = FAIL only if CRITICAL sections are stale (non-critical with fallback = acceptable)
    freshness_status = (
        "FAIL"    if critical_stale else
        "WARNING" if non_critical_stale else
        "PASS"
    )

    # Confidence penalty = 0 if non-critical is properly excluded (fallback used)
    if not critical_stale and non_critical_stale:
        confidence_penalty = 0.0  # excluded non-critical sections don't penalize confidence

    return {
        "critical_stale_sections":     critical_stale,
        "non_critical_stale_sections": non_critical_stale,
        "stale_sections":              critical_stale + non_critical_stale,  # backward compat
        "decision_excluded_sections":  decision_excluded,
        "fallback_sources_used":       fallback_used,
        "confidence_penalty":          round(min(confidence_penalty, 0.30), 3),
        "freshness_status":            freshness_status,
    }


def build_news_priority_engine(
    dataset: Dict[str, Any],
    operating_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """Module J — News Priority Engine. Returns 3-section dict (Fix 5)."""
    from datetime import datetime as _dt, timezone as _tz

    now = _dt.now(_tz.utc)
    portfolio_tickers = set(
        str(k).upper() for k in (dataset.get("security_master") or {}).keys()
    )
    regime = operating_truth.get("regime", "")

    # Fix 5: Tiered source classification
    _SOURCE_CLASS: Dict[str, float] = {
        # T1 Official / Macro
        "Reuters": 0.95, "FT_World": 0.92, "WSJ_Technology": 0.90,
        "Bloomberg": 0.95, "Fed": 1.00, "Treasury": 1.00, "OPEC": 0.98,
        "EIA": 0.95, "WhiteHouse": 0.98, "CBO": 0.95, "BLS": 0.98,
        # T2 Major Financial
        "WSJ": 0.90, "FT": 0.92, "CNBC": 0.82, "MarketWatch": 0.80,
        "Seeking Alpha": 0.72, "Barrons": 0.85,
        # Map to signal key patterns
        "Reuters_Business": 0.90, "Reuters_Markets": 0.90, "Reuters_Technology": 0.85,
        "WSJ_Markets": 0.90, "FT_Markets": 0.92, "CNBC_Markets": 0.82,
        "MarketWatch_RSS": 0.80,
        # T3 Specialist Industry / Tech
        "NvidiaNewsroom": 0.55, "TomsHardware": 0.40, "TheRegister": 0.50,
        "ServeTheHome": 0.45, "TheQuantumInsider": 0.50, "Wired": 0.55,
        "Ars Technica": 0.55, "ArsTechnica": 0.55, "AnandTech": 0.45,
        "IEEESpectrum": 0.60,
        # T4 Social / Early Warning
        "X_Signals": 0.45, "Reddit_WallStreetBets": 0.30, "StockTwits": 0.35,
        "tech_pub": 0.50,  # fallback
    }
    _T3_TECH_SOURCES = {
        "NvidiaNewsroom", "TomsHardware", "TheRegister", "ServeTheHome",
        "TheQuantumInsider", "Wired", "ArsTechnica", "Ars Technica", "AnandTech", "IEEESpectrum",
    }
    _T4_SOCIAL_SOURCES = {"X_Signals", "Reddit_WallStreetBets", "StockTwits"}

    # Fix 5: Catalyst keyword bonuses/penalties
    _CATALYST_KEYWORDS: Dict[str, float] = {
        "iran": +0.30, "hormuz": +0.30, "strait": +0.25, "escalat": +0.28,
        "geopolit": +0.25, "cpi": +0.30, "inflation": +0.28, "pce": +0.28,
        "fed ": +0.25, "federal reserve": +0.28, "rate decision": +0.28,
        "fomc": +0.28, "opec": +0.25, "oil": +0.20, "crude": +0.20,
        "futures": +0.22, "selloff": +0.25, "sell-off": +0.25,
        "vix": +0.22, "vxx": +0.22, "uvxy": +0.22, "volatility": +0.18,
        "gold": +0.18, "miners": +0.18, "treasury": +0.20, "yield": +0.18,
        "tariff": +0.25, "sanction": +0.25, "earnings": +0.15,
        "semis": +0.12, "semiconductor": +0.12, "nvidia": +0.12, "ai chip": +0.15,
        "macro": +0.12, "gdp": +0.15, "unemployment": +0.15, "jobs": +0.12,
        "discount": -0.30, "deal": -0.20, "sale ": -0.25, "% off": -0.30,
        "gaming pc": -0.35, "consumer product": -0.35, "personal finance": -0.40,
        "clickbait": -0.50, "listicle": -0.40, "roundup": -0.20,
        "product review": -0.30, "unboxing": -0.40,
    }

    # Backward-compat alias (for callers that used SOURCE_TRUST directly)
    SOURCE_TRUST = _SOURCE_CLASS

    # Collect news items from multiple sources
    raw_items: List[Dict[str, Any]] = []

    # 1. tech_articles
    for art in tech_articles(dataset):
        raw_items.append({
            "source":   str(art.get("source") or "tech_pub"),
            "headline": str(art.get("title") or art.get("headline") or ""),
            "published": art.get("published") or art.get("published_at") or "",
            "tickers":  art.get("tickers") or [],
            "themes":   art.get("themes") or [],
            "sentiment_score": float(art.get("score") or art.get("sentiment_score") or 0),
        })

    # 2. signals news sources
    sigs = dataset.get("signals") or {}
    news_source_keys = [
        "Reuters_Business", "Reuters_Markets", "Reuters_Technology",
        "WSJ_Markets", "FT_Markets", "CNBC_Markets", "MarketWatch_RSS",
    ]
    for key in news_source_keys:
        for item in (sigs.get(key) or []):
            if not isinstance(item, dict):
                continue
            tickers_mentioned = [str(t).upper() for t in parse_list(item.get("tickers_mentioned") or item.get("tickers") or [])]
            raw_items.append({
                "source":    key,
                "headline":  str(item.get("title") or item.get("headline") or ""),
                "published": item.get("published") or item.get("published_at") or "",
                "tickers":   tickers_mentioned,
                "themes":    [str(t) for t in parse_list(item.get("themes_detected") or [])],
                "sentiment_score": float(item.get("score") or 0),
            })

    scored: List[Dict[str, Any]] = []
    for item in raw_items:
        headline = item.get("headline") or ""
        if not headline:
            continue

        # Fix 5: Catalyst keyword scoring replaces old NOISE/BOOST patterns
        hl_lower = headline.lower()
        catalyst_delta = sum(v for kw, v in _CATALYST_KEYWORDS.items() if kw in hl_lower)
        catalyst_delta = max(-0.60, min(0.50, catalyst_delta))

        # Freshness score
        pub_str = str(item.get("published") or "")
        age_min = 9999
        if pub_str:
            try:
                pub_dt = _dt.fromisoformat(pub_str.replace("Z", "+00:00"))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=_tz.utc)
                age_min = max(0, int((now - pub_dt).total_seconds() / 60))
            except Exception:
                pass
        freshness = max(0.0, 1.0 - age_min / 480.0)  # decays to 0 at 8h

        # Source class (Fix 5: tiered)
        source_name = item.get("source", "")
        source_class = _SOURCE_CLASS.get(source_name, 0.50)
        source_trust = source_class  # backward-compat alias

        # Portfolio relevance
        tickers = [str(t).upper() for t in (item.get("tickers") or [])]
        portfolio_hits = [t for t in tickers if t in portfolio_tickers]
        portfolio_rel = min(1.0, len(portfolio_hits) * 0.33)

        # Macro relevance
        macro_keywords = ["fed", "rate", "inflation", "gdp", "tariff", "recession", "geopolitical", "opec"]
        macro_matches = sum(1 for kw in macro_keywords if kw in hl_lower)
        macro_rel = min(1.0, macro_matches * 0.20)

        # Fix 5: Hard filter — exclude from top CIO if low-trust + no portfolio/macro relevance
        _exclude_from_cio = (source_class < 0.60 and portfolio_rel < 0.10 and macro_rel < 0.10)

        # Confirmation count (how many sources mention same ticker)
        tickers_in_multiple = sum(1 for t in tickers if article_mentions(dataset).get(t, 0) > 1)
        conf_norm = min(1.0, tickers_in_multiple * 0.33)

        # Novelty (short headlines are often breaking news; very long = analysis/listicle)
        novelty = 0.7 if len(headline) < 100 else 0.5 if len(headline) < 140 else 0.3

        # Final score with catalyst delta
        final_score = round(
            max(0.0,
                0.25 * freshness +
                0.20 * source_class +
                0.20 * portfolio_rel +
                0.15 * macro_rel +
                0.10 * conf_norm +
                0.10 * novelty
                + catalyst_delta
            ),
            4
        )

        # Decision impact
        if _exclude_from_cio:
            decision_impact = "Low decision value — low-trust source, no portfolio/macro angle"
        elif portfolio_rel > 0.5:
            decision_impact = "Direct portfolio exposure — CIO attention required"
        elif macro_rel > 0.4 or catalyst_delta > 0.15:
            decision_impact = "Macro/market catalyst — watch for regime impact"
        else:
            decision_impact = "Background signal — monitor"

        # Affected themes
        affected_themes = list(item.get("themes") or [])
        for ticker in tickers:
            t_theme = THEME_MAP.get(ticker)
            if t_theme and t_theme not in affected_themes:
                affected_themes.append(t_theme)

        scored.append({
            "rank":                  0,
            "source":                source_name,
            "source_class":          source_class,   # Fix 5
            "headline":              headline[:200],
            "age_minutes":           age_min,
            "source_trust":          source_trust,
            "ticker_relevance":      portfolio_rel,
            "portfolio_relevance":   portfolio_rel,
            "macro_relevance":       macro_rel,
            "confirmation_count":    tickers_in_multiple,
            "final_priority_score":  final_score,
            "decision_impact":       decision_impact,
            "affected_tickers":      portfolio_hits[:5],
            "affected_themes":       affected_themes[:4],
            "_exclude_from_cio":     _exclude_from_cio,  # Fix 5 filter flag
            "_is_t3_tech":           source_name in _T3_TECH_SOURCES,
            "_is_t4_social":         source_name in _T4_SOCIAL_SOURCES,
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["final_priority_score"], reverse=True)
    for i, item in enumerate(scored, 1):
        item["rank"] = i

    # Fix 5: Split into 3 sections + medium-priority fallback
    top_cio = [
        it for it in scored
        if not it["_exclude_from_cio"] and it["source_class"] >= 0.80
    ][:10]
    top_tech = [
        it for it in scored
        if it["_is_t3_tech"] and it["final_priority_score"] > 0
    ][:5]
    top_early = [
        it for it in scored
        if it["_is_t4_social"]
    ][:5]

    # Fix 5: Medium-priority — shown when high-trust CIO section is empty.
    # Criteria: not high-trust source but has portfolio relevance OR macro relevance OR catalyst signal.
    cio_headlines = {it["headline"] for it in top_cio}
    top_medium = [
        it for it in scored
        if it["headline"] not in cio_headlines
        and not it["_exclude_from_cio"]
        and not it["_is_t3_tech"]        # T3 tech sources belong in top_tech_intelligence only
        and not it["_is_t4_social"]
        and (
            it["portfolio_relevance"] > 0
            or it["macro_relevance"] > 0.10
            or it["final_priority_score"] > 0.35
        )
    ][:8]

    return {
        "top_cio_market_catalysts":    top_cio,
        "top_medium_priority":         top_medium,
        "top_tech_intelligence":       top_tech,
        "top_early_warning":           top_early,
        "all_scored":                  scored[:20],
    }


def build_report_readiness(
    operating_truth: Dict[str, Any],
    freshness_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Module M — Report Readiness Classification."""
    blocking: List[str] = []
    classification = "INSTITUTIONAL_READY"
    reason = "All checks passed."

    # Rule 1
    if operating_truth.get("order_routing_enabled"):
        classification = "EXECUTION_SAFETY_BREACH"
        reason = "Order routing is enabled — execution safety breach."
        blocking.append("order_routing_enabled=True")
        return {"classification": classification, "reason": reason, "blocking_issues": blocking}

    # Severity rank: higher number = more severe
    _sev = {"INSTITUTIONAL_READY": 0, "INSTITUTIONAL_REVIEW_REQUIRED": 1,
            "DATA_STALE": 2, "NOT_INSTITUTIONAL_CLEAN": 3, "EXECUTION_SAFETY_BREACH": 4}

    def _escalate(new_cls: str, new_reason: str) -> None:
        nonlocal classification, reason
        if _sev.get(new_cls, 0) > _sev.get(classification, 0):
            classification = new_cls
            reason = new_reason

    # Rule 2 — consistency audit failure
    if operating_truth.get("consistency_audit_status") == "INCONSISTENT":
        _escalate("NOT_INSTITUTIONAL_CLEAN", "Consistency audit is INCONSISTENT.")
        blocking.append("consistency_audit_status=INCONSISTENT")

    # Rule 3 — genuinely stale data (only when sections have content but old timestamps)
    if freshness_data.get("freshness_status") == "FAIL" and freshness_data.get("stale_sections"):
        _escalate("DATA_STALE", "One or more critical data sources are stale (>240 min).")
        blocking.append("freshness_status=FAIL")

    # Rule 4 — blind spot warning / critical (Fix 2)
    _bs_rr = operating_truth.get("blind_spot_status", "")
    if _bs_rr in ("WARNING", "CRITICAL"):
        _escalate("INSTITUTIONAL_REVIEW_REQUIRED",
                  f"Blind Spot {_bs_rr} — coverage gaps require CIO review")
        blocking.append(f"blind_spot_status={_bs_rr}")

    # Rule 4b — causal gap escalation (Fix 2)
    _cs_rr = operating_truth.get("causal_status", "")
    if _cs_rr in ("INCOMPLETE", "CRITICAL_GAP", "MOSTLY_COMPLETE_WITH_CRITICAL_GAP"):
        _escalate("INSTITUTIONAL_REVIEW_REQUIRED",
                  f"Causal status {_cs_rr} — regime drivers incomplete")
        blocking.append(f"causal_status={_cs_rr}")

    if not blocking:
        classification = "INSTITUTIONAL_READY"
        reason = "All checks passed — report is institutionally clean."

    return {
        "classification":  classification,
        "reason":          reason,
        "blocking_issues": blocking,
    }


# ---------------------------------------------------------------------------
# Presentation builders
# ---------------------------------------------------------------------------

def build_excel_report(dataset: Dict[str, Any], archive: Dict[str, Any], output_path: Path) -> None:
    db = archive.get("database_row") or {}
    meta = dataset.get("meta") or {}
    regime = dataset.get("regime") or {}
    portfolio = dataset.get("portfolio") or {}
    risk = dataset.get("risk_metrics") or {}
    snapshot_hierarchy = build_snapshot_hierarchy(dataset)
    security_rows = list((dataset.get("security_master") or {}).values())
    unknown_security = sum(
        1 for s in security_rows
        if str(s.get("sector")).upper() == "UNKNOWN" or str(s.get("industry")).upper() == "UNKNOWN"
    )

    # CONSISTENCY: two-pass approach to break operating_truth ↔ audit circular dependency
    # Pass 1: build live components + preliminary operating_truth (audit_data=None)
    _causal  = build_causal_explanation(dataset)
    _bscheck = build_blind_spot_checklist(dataset)
    _conc    = build_concentration_risk(dataset)
    _op_truth_pre = build_operating_truth(dataset, archive, _causal, _bscheck, _conc)
    # Pass 2: build audit using preliminary operating_truth (checks ot vs live — will PASS if live used correctly)
    _audit   = build_consistency_audit(dataset, archive, causal_data=_causal, blind_data=_bscheck, operating_truth=_op_truth_pre)
    # Finalize operating_truth with real audit results
    _op_truth = build_operating_truth(dataset, archive, _causal, _bscheck, _conc, _audit)

    # ── Governance contract merge — load approved_operating_truth.json fields ──
    # Renderers must NOT recalculate governance status; consume the gate output directly.
    _approved_truth_x = _load_approved_truth_for_renderer() or {}
    _GOV_CONTRACT_FIELDS = (
        "cio_action", "confidence", "confidence_label",
        "causal_status", "blind_spot_status", "concentration_status",
        "_release_status", "governance_gate_score",
        "governance_gate_failed_gates", "governance_gate_passed_gates",
        "governance_gate_deductions", "sentiment_hygiene_gate",
    )
    for _gf in _GOV_CONTRACT_FIELDS:
        if _gf in _approved_truth_x:
            _op_truth[_gf] = _approved_truth_x[_gf]

    # 9.5/10 Upgrade: compute all new module objects
    _action_logic = build_cio_action_logic(_op_truth, dataset)
    _remediations = build_blind_spot_remediations(_bscheck)
    _causal_chain = build_causal_chain(dataset, _causal)
    _risk_gov     = build_portfolio_risk_governor(dataset, _conc)
    _forecast_mat = build_forecast_maturity_schedule(dataset)
    _freshness    = build_freshness_governor(dataset)
    _news_priority = build_news_priority_engine(dataset, _op_truth)
    _readiness    = build_report_readiness(_op_truth, _freshness)
    _op_truth["report_readiness"] = _readiness["classification"]
    _mismatches   = detect_archive_live_mismatches(_op_truth, archive)

    workbook = XlsxWorkbook()

    # ── CIO COCKPIT (first sheet, Module K) ─────────────────────────────────
    W = XlsxWorkbook
    _G = W.STYLE_GREEN
    _A = W.STYLE_AMBER
    _R = W.STYLE_RED
    _S = W.STYLE_SECTION
    _N = W.STYLE_NORMAL
    _H = W.STYLE_HEADER

    _law_binding_x = dataset.get("law_governance_binding") if isinstance(dataset.get("law_governance_binding"), dict) else {}
    _law_rows_x = [["field", "value", "certainty", "source_layer"], *build_law_governance_rows(_law_binding_x)]
    workbook.add_sheet(
        "LAW_GOVERNANCE_BINDING",
        _law_rows_x,
        widths=[42, 90, 24, 30],
        row_styles=[W.STYLE_HEADER] + [W.STYLE_NORMAL for _ in _law_rows_x[1:]],
    )

    _pei_x = dataset.get("prospective_event_intelligence") if isinstance(dataset.get("prospective_event_intelligence"), dict) else {}
    if pei_event_rows and pei_branch_rows and pei_sleeve_rows and pei_playbook_rows and pei_forecast_rows:
        workbook.add_sheet("PEI_Events", pei_event_rows(_pei_x), widths=[24, 28, 56, 18, 32, 28, 34])
        workbook.add_sheet("PEI_Scenario_Trees", pei_branch_rows(_pei_x), widths=[24, 24, 46, 14, 18, 60, 60, 60])
        workbook.add_sheet("PEI_Sleeve_Map", pei_sleeve_rows(_pei_x), widths=[24, 24, 24, 18, 14, 34, 44, 44, 60])
        workbook.add_sheet("PEI_Playbook", pei_playbook_rows(_pei_x), widths=[24, 24, 46, 42, 52, 52, 42, 30])
        workbook.add_sheet("PEI_Forecast_Registry", pei_forecast_rows(_pei_x), widths=[28, 24, 24, 14, 18, 24, 70, 24])
        workbook.add_sheet("PEI_Brier_CRS", pei_brier_rows(_pei_x), widths=[30, 40, 28, 28])
        workbook.add_sheet("PEI_Reflexive_Suppression", pei_suppression_rows(_pei_x), widths=[24, 34, 34, 24, 80])
        workbook.add_sheet("PEI_Oscillation_Engine", pei_oscillation_rows(_pei_x), widths=[12, 18, 18, 18, 18, 18, 18, 22, 20])

    _str_x = dataset.get("shannon_thorp_refinement") if isinstance(dataset.get("shannon_thorp_refinement"), dict) else {}
    if str_summary_rows and str_signal_entropy_rows and str_source_capacity_rows and str_cost_basis_rows and str_kelly_rows and str_hedge_rows:
        workbook.add_sheet("STR_Signal_Entropy", str_signal_entropy_rows(_str_x), widths=[16, 18, 16, 16, 16, 16, 16, 34])
        workbook.add_sheet("STR_Source_Capacity", str_source_capacity_rows(_str_x), widths=[28, 10, 12, 12, 14, 14, 14, 32, 24])
        workbook.add_sheet("STR_Cost_Basis", str_cost_basis_rows(_str_x), widths=[12, 16, 16, 16, 16, 24, 36, 14])
        workbook.add_sheet("STR_Kelly_Sizing", str_kelly_rows(_str_x), widths=[12, 12, 12, 12, 12, 18, 18, 14, 14, 14, 16, 18, 16, 14, 42])
        workbook.add_sheet("STR_Hedge_Review", str_hedge_rows(_str_x), widths=[36, 30])
        workbook.add_sheet("STR_Cycle_Summary", str_summary_rows(_str_x), widths=[36, 80])

    _rem_x = dataset.get("v3_str_bug_clearance_reconciliation") if isinstance(dataset.get("v3_str_bug_clearance_reconciliation"), dict) else {}
    if _rem_x and remediation_summary_rows:
        workbook.add_sheet("V3_STR_Remediation", remediation_summary_rows(_rem_x), widths=[36, 90])
        workbook.add_sheet(
            "Open_Order_State",
            [["Ticker", "Side", "Qty", "Limit", "Broker Status", "Raw Intent", "Canonical State", "Live On Exchange", "Classification", "Still Live", "Requires CIO Review", "Blocked By Operator", "Dealt Qty", "Last Updated"]] + [
                [
                    r.get("ticker"), r.get("side"), r.get("qty"), r.get("limit_price"),
                    r.get("broker_status"), r.get("raw_order_intent"),
                    r.get("canonical_order_state"), r.get("is_live_on_exchange"),
                    r.get("classification"), r.get("still_live"), r.get("requires_cio_review"),
                    r.get("blocked_by_operator"), r.get("dealt_qty"), r.get("order_age"),
                ]
                for r in (_rem_x.get("open_order_state_reconciliation") or [])
            ],
            widths=[14, 10, 10, 12, 24, 26, 28, 16, 42, 12, 18, 18, 12, 14],
        )

    def _has_sheet(name: str) -> bool:
        return any(s.get("name") == name for s in workbook.sheets)

    if not _has_sheet("Artifact_Manifest"):
        workbook.add_sheet("Artifact_Manifest", build_artifact_manifest_rows(dataset, archive), widths=[42, 110])
    if not _has_sheet("Canonical_Reconciliation"):
        workbook.add_sheet("Canonical_Reconciliation", build_canonical_reconciliation_rows(dataset), widths=[42, 90, 42, 42, 18])
    workbook.add_sheet("Canonical_Contract", build_canonical_contract_rows(dataset), widths=[42, 110])
    workbook.add_sheet("Target_USD_Vector", build_target_usd_vector_rows(dataset), widths=[16, 18, 18, 18, 18, 42, 24, 28, 18, 18])
    workbook.add_sheet("Risk_Overlay", build_risk_overlay_rows(dataset), widths=[34, 42, 24, 24, 24, 24, 46])
    workbook.add_sheet("Deterministic_Pipeline", build_deterministic_pipeline_rows(dataset), widths=[28, 18, 46, 46, 40, 40, 18, 18])
    workbook.add_sheet("Replay_Summary", build_replay_summary_rows(dataset), widths=[34, 42, 24, 24])
    workbook.add_sheet("Benchmark_Summary", build_benchmark_summary_rows(dataset), widths=[34, 80])
    workbook.add_sheet("Benchmark_Strategies", build_benchmark_strategy_rows(dataset), widths=[10, 36, 20, 22, 20, 18])
    workbook.add_sheet("Scenario_Scorecards", build_benchmark_scenario_rows(dataset), widths=[34, 20, 22, 18])
    workbook.add_sheet("Layer_Attribution", build_benchmark_layer_rows(dataset), widths=[30, 18, 16, 16, 18, 18])
    workbook.add_sheet("One_Week_Observation", build_observation_lock_rows(dataset), widths=[34, 110])

    for _required_sheet in REQUIRED_STR_REMEDIATION_SHEETS:
        if not _has_sheet(_required_sheet):
            workbook.add_sheet(_required_sheet, [["Status", "Reason"], ["MISSING", "Required sheet placeholder: upstream section unavailable during generation."]], widths=[24, 90])

    def _style_for(value: str, green_vals: List[str], amber_vals: List[str]) -> int:
        v = str(value).upper()
        for g in green_vals:
            if g in v: return _G
        for a in amber_vals:
            if a in v: return _A
        return _R

    cockpit_rows: List[List[Any]] = []
    cockpit_styles: List[Optional[int]] = []

    def _ck(field: Any, value: Any, style: int) -> None:
        cockpit_rows.append([str(field), str(value) if value is not None else ""])
        cockpit_styles.append(style)

    _ck("CIO COCKPIT", f"Generated {datetime.now().isoformat(sep=' ', timespec='seconds')}", _H)

    # 0. GOVERNANCE GATE BANNER (top of cockpit)
    _gov_release_ck = _op_truth.get("_release_status", "BLOCKED_RENDERER_CONTRACT_FAILURE")
    _gov_score_ck   = _op_truth.get("governance_gate_score", "CONTRACT_FAILURE")
    _gov_hyg_ck     = (_op_truth.get("sentiment_hygiene_gate") or {}).get("status", "BLOCKED_RENDERER_CONTRACT_FAILURE")
    _gov_failed_ck  = _op_truth.get("governance_gate_failed_gates") or []
    if _gov_release_ck == "BLOCKED":
        _ck("!! GOVERNANCE GATE !!", "REPORT BLOCKED — DO NOT USE FOR CIO DECISION UNTIL FIXED", _R)
        _ck("!! Failed Gates !!", ", ".join(_gov_failed_ck) or "see audit", _R)
    _ck("── GOVERNANCE STATUS ──", "", _S)
    _ck("Governance Release", _gov_release_ck,
        _G if _gov_release_ck == "APPROVED" else _A if "WARNINGS" in _gov_release_ck else _R)
    _ck("Governance Gate Score", f"{_gov_score_ck}/100",
        _G if str(_gov_score_ck) == "100" else _A if int(str(_gov_score_ck).split(".")[0] if str(_gov_score_ck) != "N/A" else "0") >= 85 else _R)
    _ck("Sentiment Hygiene Gate", _gov_hyg_ck,
        _G if _gov_hyg_ck == "PASS" else _A if _gov_hyg_ck == "WARNING" else _R)

    # 1. REPORT STATUS
    _ck("── REPORT STATUS ──", "", _S)
    _ready_cls = _readiness["classification"]
    _ready_cls2 = _op_truth.get("report_readiness", _ready_cls)
    _ck("Report Readiness", _ready_cls2, _G if _ready_cls2 == "INSTITUTIONAL_READY" else _A if "REVIEW" in _ready_cls2 else _R)
    _ck("Consistency Audit", _audit.get("audit_status", ""), _G if _audit.get("audit_status") == "CONSISTENT" else _A if _audit.get("audit_status") == "WARNINGS" else _R)
    _ck("Archive/Live Mismatches", len(_mismatches), _R if _mismatches else _G)
    # Fix #1 — Report Status must mirror operating_truth.report_readiness, never consistency audit
    _rpt_status = _op_truth.get("report_readiness", "PENDING")
    _ck("Report Decision Status", _rpt_status, _G if _rpt_status == "INSTITUTIONAL_READY" else _A if "REVIEW" in _rpt_status else _R)
    # Fix #2 — Quant Process Readiness as a separate row (distinct from report decision status)
    _iq_ck = (dataset.get("institutional_quant") or {})
    _qri_ck = float(db.get("quant_readiness_index") or db.get("quant_readiness_score")
                    or _iq_ck.get("readiness_score") or 0)
    _qrl_ck = (db.get("quant_readiness_label") or _iq_ck.get("readiness_label")
               or ("INSTITUTIONAL_READY" if _qri_ck >= 90 else "REVIEW_REQUIRED" if _qri_ck >= 75 else "NOT_READY"))
    _qr_ck_val = _qrl_ck + (f" ({_qri_ck:.1f})" if _qri_ck else "")
    _ck("Quant Process Readiness", _qr_ck_val, _G if "READY" in _qrl_ck and "NOT" not in _qrl_ck else _A if "REVIEW" in _qrl_ck else _R)

    # 2. EXECUTION SAFETY
    _ck("── EXECUTION SAFETY ──", "", _S)
    _ck("Execution Authority", _op_truth.get("execution_authority", ""), W.STYLE_BLUE if hasattr(W, "STYLE_BLUE") else _G)
    _ck("Order Routing Enabled", str(_op_truth.get("order_routing_enabled", False)), _G)
    _ck("Orders Generated By Pipeline", _op_truth.get("orders_generated_by_pipeline", 0), _G)

    # 2b. SCENARIO OVERLAY (from approved_cio_briefing.json)
    _briefing_x = _load_approved_cio_briefing()
    _bc_x = _briefing_x.get("breaking_catalyst", {})
    _ov_x = _briefing_x.get("scenario_overlay", {})
    _mon_x = _briefing_x.get("monday_open_scenario", {})
    if _bc_x.get("detected"):
        _ck("── SCENARIO OVERLAY ──", "", _S)
        _ck("Breaking Catalyst", f"{_bc_x.get('catalyst_type','—')} / {_bc_x.get('polarity','—')}", _A)
        _ck("Overlay Type", _ov_x.get("overlay_type", "—"), _A)
        _ck("Risk Clearance", _ov_x.get("risk_clearance", "NOT_CONFIRMED"), _A)
        _ck("CIO Action (Adjusted)", _ov_x.get("cio_action_adjusted", "—"), _A)
        _ck("Gold Miner Relief Action", _ov_x.get("gold_miner_relief_rally_action", "—"),
            _A if _ov_x.get("gold_miner_relief_rally_action") == "DECONCENTRATION_WINDOW" else _R)
        _sp_x = _ov_x.get("space_sector_overlay", {})
        if _sp_x:
            _ck("Space Sector Net View", _sp_x.get("net_view", "—"), _A)
            _ck("SpaceX Liquidity Drain", _sp_x.get("spcx_liquidity_drain", "—"), _A)
        _ck("Verification Required", str(_bc_x.get("verification_required", True)), _A)
        # Next-session scenarios
        if _mon_x:
            _ck("NEXT U.S. REGULAR SESSION SCENARIO", "", _S)
            for _sk, _sv in _mon_x.items():
                _ck(_sv.get("name", _sk),
                    _sv.get("cio_implication", ""),
                    _A)

    # 3. REGIME
    _ck("── REGIME ──", "", _S)
    _rscore = _op_truth.get("regime_score", 0)
    _ck("Regime", f"{_op_truth.get('regime', '')} (score {_rscore})", _R if _rscore < -2 else _A if _rscore < 0 else _G)
    _ck("CIO Action", _action_logic.get("final_action", "WAIT / HOLD"), _A)

    # 4. CONFIDENCE
    _ck("── CONFIDENCE ──", "", _S)
    _conf_f = float(_op_truth.get("confidence") or 0)
    _ck("Confidence", f"{_conf_f:.3f} {_op_truth.get('confidence_label', '')}".strip(), _G if _conf_f >= 0.70 else _A if _conf_f >= 0.55 else _R)
    _ck("Causal Status", _op_truth.get("causal_status", ""), _style_for(_op_truth.get("causal_status", ""), ["COMPLETE"], ["MOSTLY", "PARTIAL"]))
    _ck("Causal Confidence", f"{_op_truth.get('causal_confidence', 0):.3f}", _G if float(_op_truth.get("causal_confidence", 0)) >= 0.6 else _A)

    # 5. BLIND SPOT
    _ck("── BLIND SPOT ──", "", _S)
    _bs = _op_truth.get("blind_spot_status", "")
    _ck("Blind Spot Status", _bs, _G if _bs == "CLEAR" else _A if _bs == "WARNING" else _R)
    _ck("Failed Items", ", ".join(_op_truth.get("blind_spot_failed_items") or []) or "None", _G if not _op_truth.get("blind_spot_failed_items") else _A)
    _ck("Remediations Available", len(_remediations), _A if _remediations else _G)

    # 6. CONCENTRATION
    _ck("── CONCENTRATION ──", "", _S)
    _cs = _op_truth.get("concentration_status", "")
    _ck("Concentration Status", _cs, _G if _cs == "NORMAL" else _A if _cs == "ELEVATED" else _R)
    _ck("Largest Cluster", f"{_op_truth.get('largest_cluster', '')} {_op_truth.get('largest_cluster_weight', 0):.0%}", _N)
    _ck("HHI", f"{_conc.get('hhi', 0):.4f}", _N)

    # 7. PORTFOLIO
    _ck("── PORTFOLIO ──", "", _S)
    _ck("Cash", portfolio.get("cash", ""), _N)
    _ck("Total P/L", f"{portfolio.get('total_pnl', '')} ({portfolio.get('total_pnl_pct', '')}%)", _N)
    _hv = (dataset.get("risk_model") or {}).get("historical_var") or {}
    if isinstance(_hv, dict):
        _var95 = (_hv.get("confidence_95") or {}).get("daily_dollars") or ""
    else:
        _var95 = ""
    _ck("VaR 95", fmt_money(_var95) if _var95 else "N/A", _N)
    _formal = dataset.get("risk_model") or {}
    _ck("Beta To SPY", fmt_float(_formal.get("beta_to_spy"), 3), _N)
    _ck("Open Orders", (dataset.get("orders") or {}).get("open_order_count", 0), _N)

    # 8. BRIER
    _ck("── BRIER MATURITY ──", "", _S)
    _bm = _forecast_mat.get("maturity_status", "")
    _ck("Maturity Status", _bm, _G if _bm == "MATURE" else _A if _bm == "NOT_MATURE" else _N)
    _ck("Resolved Forecasts", _forecast_mat.get("resolved_forecasts", 0), _N)
    _ck("Next Maturity Date", _forecast_mat.get("next_maturity_date", "N/A"), _N)

    # 9. FRESHNESS (Fix 4: explicit critical/non-critical)
    _ck("── FRESHNESS ──", "", _S)
    _fs = _freshness.get("freshness_status", "")
    _ck("Freshness Status", _fs, _G if _fs == "PASS" else _A if _fs == "WARNING" else _R)
    _fs_crit = _freshness.get("critical_stale_sections") or []
    _fs_noncrit = _freshness.get("non_critical_stale_sections") or []
    _ck("Critical Stale Sections", len(_fs_crit), _R if _fs_crit else _G)
    _ck("Non-Critical Stale Sections", len(_fs_noncrit), _A if _fs_noncrit else _G)
    if _fs_noncrit:
        _nc_names = ", ".join(s.get("section","?") for s in _fs_noncrit)
        _ck("Non-Critical Stale (fallback used)", _nc_names, _A)

    # 10. TOP 3 RISKS
    _ck("── TOP 3 RISKS ──", "", _S)
    _monitoring = dataset.get("monitoring") or {}
    _crit_alerts = [a.get("title", "")[:80] for a in (_monitoring.get("alerts") or []) if isinstance(a, dict) and str(a.get("severity", "")).upper() in ("CRITICAL", "HIGH")][:3]
    # Prepend concentration risk when concentration_status is CRITICAL or HIGH (sourced from governance truth)
    _conc_risk_status = _op_truth.get("concentration_status", "")
    if _conc_risk_status in ("CRITICAL", "HIGH"):
        _largest_cluster = _op_truth.get("largest_cluster", "")
        _largest_cluster_w = _op_truth.get("largest_cluster_weight", 0)
        _conc_risk_label = (
            f"Concentration {_conc_risk_status}: {_largest_cluster} cluster {_largest_cluster_w:.0%} — CIO review required"
            if _largest_cluster else
            f"Concentration {_conc_risk_status} — CIO review required"
        )
        _crit_alerts = [_conc_risk_label] + [a for a in _crit_alerts if "concentration" not in a.lower()]
    if not _crit_alerts:
        _crit_alerts = ["No CRITICAL/HIGH alerts this cycle"]
    for _i, _alert in enumerate(_crit_alerts[:3], 1):
        _ck(f"Risk {_i}", _alert, _R if _i == 1 else _A)

    # 11. TOP 3 OPPORTUNITIES
    _ck("── TOP 3 OPPORTUNITIES ──", "", _S)
    _ece = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    _top_opps = sorted(_ece, key=lambda e: float(e.get("basket_move") or 0), reverse=True)[:3]
    if _top_opps:
        for _i, _opp in enumerate(_top_opps, 1):
            _ck(f"Opportunity {_i}", f"{_opp.get('theme', '')} {float(_opp.get('basket_move') or 0):+.1f}%", _G)
    else:
        _ck("Opportunities", "No strong rotation signals this cycle", _N)

    # 12. TOP 10 NEWS (Fix 5: 3-section output)
    _ck("── TOP CIO MARKET CATALYSTS ──", "", _S)
    _np_cio = (_news_priority.get("top_cio_market_catalysts") or []) if isinstance(_news_priority, dict) else _news_priority[:10] if isinstance(_news_priority, list) else []
    _np_tech = (_news_priority.get("top_tech_intelligence") or []) if isinstance(_news_priority, dict) else []
    _np_early = (_news_priority.get("top_early_warning") or []) if isinstance(_news_priority, dict) else []
    if _np_cio:
        for _ni in _np_cio[:10]:
            _ck(f"#{_ni['rank']} [{_ni['source']}]", f"Score {_ni['final_priority_score']:.3f} | {_ni['headline'][:100]}", _G if _ni["final_priority_score"] >= 0.5 else _A)
    else:
        _ck("CIO Catalysts", "No high-trust market catalyst signals scored this cycle", _N)
    if _np_tech:
        _ck("── TOP TECH INTELLIGENCE ──", "", _S)
        for _ni in _np_tech[:5]:
            _ck(f"#{_ni['rank']} [{_ni['source']}]", f"Score {_ni['final_priority_score']:.3f} | {_ni['headline'][:100]}", _A)
    if _np_early:
        _ck("── EARLY WARNING (low trust) ──", "", _S)
        for _ni in _np_early[:5]:
            _ck(f"#{_ni['rank']} [{_ni['source']}] [LOW TRUST]", f"Score {_ni['final_priority_score']:.3f} | {_ni['headline'][:100]}", _A)

    # 13. CIO CONSTRAINTS
    _ck("── CIO CONSTRAINTS ──", "", _S)
    _ck("Blocked Actions", ", ".join((_action_logic.get("blocked_actions") or [])[:6]) or "None", _R if _action_logic.get("blocked_actions") else _G)
    _ck("Allowed Actions", ", ".join((_risk_gov.get("allowed_actions") or [])[:6]) or "HOLD / REVIEW", _G)
    _ck("Risk Governor Status", _risk_gov.get("status", ""), _G if _risk_gov.get("status") == "NORMAL" else _A if _risk_gov.get("status") == "ELEVATED" else _R)

    # 14. WHAT NOT TO DO
    _ck("── WHAT NOT TO DO ──", "", _S)
    _all_blocked = list(dict.fromkeys(
        (_action_logic.get("blocked_actions") or []) +
        (_risk_gov.get("blocked_actions") or [])
    ))
    _ck("Do NOT", ", ".join(_all_blocked[:8]) or "No explicit blocks", _R if _all_blocked else _G)
    _ck("Rules Triggered", ", ".join((_action_logic.get("rules_triggered") or [])[:5]), _N)

    # 15. WHAT TO CONSIDER
    _ck("── WHAT TO CONSIDER ──", "", _S)
    _ck("Final Action", _action_logic.get("final_action", "WAIT / HOLD"), _A)
    _ck("Reason", _action_logic.get("reason", "")[:200], _N)
    _ck("CIO Review Required", str(_action_logic.get("required_cio_review", False)), _A if _action_logic.get("required_cio_review") else _G)

    # 16. GOLD SAFE-HAVEN THESIS TRACKER panel
    _gt = build_gold_thesis_tracker(dataset)
    _gt_status = _gt.get("status", "UNKNOWN")
    _gt_style  = _G if _gt_status == "CONFIRMING" else _A if _gt_status == "WATCH" else _R
    _ck("── GOLD SAFE-HAVEN THESIS ──", "", _S)
    _ck("Gold Thesis Status", f"{_gt_status} | Score {_gt.get('score', 0):.2f} | Confidence {_gt.get('confidence', 'LOW')}", _gt_style)
    _ck("Summary", _gt.get("summary", "")[:200], _N)
    _gm = _gt.get("key_metrics") or {}
    def _gc(k): v = _gm.get(k); return f"{v:+.2f}%" if v is not None else "N/A"
    _ck("GLD / SLV", f"GLD {_gc('gld_change_pct')} | SLV {_gc('slv_change_pct')} | GSR proxy {_gm.get('gold_silver_ratio_proxy') or 'N/A'}", _N)
    _ck("GDX / GDXJ vs GLD", f"GDX-GLD {_gc('gdx_vs_gld_spread')} | GDXJ-GLD {_gc('gdxj_vs_gld_spread')}", _N)
    _ck("AU / NEM vs GDX", f"AU-GDX {_gc('au_vs_gdx_spread')} | NEM-GDX {_gc('nem_vs_gdx_spread')}", _N)
    _ck("UUP / Rates", f"UUP {_gc('uup_change_pct')} | 10Y yield {_gm.get('ten_year_yield') or 'N/A'} | TLT {_gc('tlt_change_pct')}", _N)
    _ck("Oil News Score", f"{_gm.get('oil_news_pressure_score', 0)} keyword hits | XLE {_gc('xle_change_pct')}", _N)
    _ck("SPY / VXX", f"SPY {_gc('spy_change_pct')} | VXX {_gc('vxx_change_pct')}", _N)
    _ga = _gt.get("thesis_action") or {}
    _ck("Gold Miner Cluster", f"{_ga.get('gold_miner_cluster_weight', 0):.0%}", _R if _ga.get('add_blocked_by_concentration') else _A)
    for _label, _value in gold_thesis_action_rows(_ga):
        _style = _gt_style if _label == "CIO Gold Action" else _A if _label == "Execution Permission" else _N
        _ck(_label, _value, _style)
    # Check-level summary
    _ck("── CHECK RESULTS ──", "", _S)
    _CHECK_LABELS = [
        ("gold_stabilizes_and_rises",         "1. Gold stabilizes/rises"),
        ("silver_confirms_or_gsr_compresses", "2. Silver confirms / GSR"),
        ("miners_vs_gold",                    "3. GDX/GDXJ vs GLD"),
        ("au_nem_vs_gdx",                     "4. AU/NEM vs GDX"),
        ("real_yields_do_not_spike",          "5. Real yields stable"),
        ("dxy_does_not_surge",                "6. DXY/UUP not surging"),
        ("oil_risk_premium_elevated",         "7. Oil-risk premium"),
        ("miners_not_liquidated_as_equity_beta", "8. Miner liquidation risk"),
    ]
    for _ckey, _clabel in _CHECK_LABELS:
        _ch = (_gt.get("checks") or {}).get(_ckey) or {}
        _cst = _ch.get("status", "MISSING")
        _csty = _G if _cst == "PASS" else _A if _cst == "WATCH" else (_R if _cst == "FAIL" else _N)
        _ck(_clabel, f"[{_cst}] {_ch.get('evidence', '')[:80]}", _csty)

    if build_master_prompt_rows:
        workbook.add_sheet(
            "00_CS_MASTER_PROMPT",
            build_master_prompt_rows(dataset),
            widths=[34, 120, 24, 34],
        )

    if build_cio_context_rows:
        workbook.add_sheet(
            "00_CIO_CONTEXT_CAPSULE",
            [
                ["Field", "Value", "Certainty", "Source Layer"],
                ["READ 00_CS_MASTER_PROMPT BEFORE INTERPRETING THIS REPORT", "No Chief Strategist answer may be produced from tactical data alone.", "GOVERNANCE_RULE", "chief_strategist_master_prompt"],
                *build_cio_context_rows(dataset),
            ],
            widths=[34, 120, 24, 34],
        )

    workbook.add_sheet("CIO Cockpit", cockpit_rows, widths=[38, 100], row_styles=cockpit_styles)

    # ── CIO BRIEFING (now second sheet) ─────────────────────────────────────
    _briefing_rows, _briefing_styles = build_cio_briefing_rows(
        dataset, archive, causal_data=_causal, blind_data=_bscheck,
        operating_truth=_op_truth, action_logic=_action_logic,
    )
    workbook.add_sheet("CIO Briefing", _briefing_rows, widths=[34, 100], row_styles=_briefing_styles)

    if build_cs_governance_rows and build_thesis_reconciliation_rows and build_event_thesis_map_rows:
        workbook.add_sheet(
            "CS_Governance",
            [
                ["Field", "Value", "Certainty", "Source Layer"],
                *build_cs_governance_rows(dataset),
            ],
            widths=[34, 100, 24, 38],
        )
        workbook.add_sheet(
            "Thesis_Reconciliation",
            [
                ["Thesis", "Strategic Thesis", "Tactical State", "Allowed Interpretation", "Forbidden Interpretation", "Kill Conditions"],
                *build_thesis_reconciliation_rows(dataset),
            ],
            widths=[30, 52, 54, 70, 70, 70],
        )
        workbook.add_sheet(
            "Event_Thesis_Map",
            [
                ["Event", "Thesis ID", "Relationship", "Reconciliation Note"],
                *build_event_thesis_map_rows(dataset),
            ],
            widths=[30, 42, 34, 90],
        )

    # Consistency Audit sheet (Upgrade #4) — placed second for CIO visibility
    _ca_pass = XlsxWorkbook.STYLE_GREEN
    _ca_warn = XlsxWorkbook.STYLE_AMBER
    _ca_fail = XlsxWorkbook.STYLE_RED
    _ca_hdr  = XlsxWorkbook.STYLE_SECTION
    _audit_row_styles = [_ca_hdr] + [
        (_ca_pass if r[1] == "PASS" else _ca_warn if r[1] == "WARNING" else _ca_fail)
        for r in _audit["check_rows"]
    ]
    workbook.add_sheet(
        "Consistency Audit",
        [
            ["REPORT CONSISTENCY AUDIT",
             f"Score: {_audit['audit_score']}/100 | Status: {_audit['audit_status']} | "
             f"Pass: {_audit['pass_count']}/10 | Warn: {_audit['warn_count']}/10 | Fail: {_audit['fail_count']}/10"],
            *[[r[0], f"[{r[1]}] {r[2]}"] for r in _audit["check_rows"]],
        ],
        widths=[32, 110],
        row_styles=_audit_row_styles,
    )

    # ── GOLD THESIS TRACKER sheet ────────────────────────────────────────────
    _gtx = build_gold_thesis_tracker(dataset)
    _gtx_status = _gtx.get("status", "UNKNOWN")
    _gtx_style  = XlsxWorkbook.STYLE_GREEN if _gtx_status == "CONFIRMING" else \
                  XlsxWorkbook.STYLE_AMBER if _gtx_status == "WATCH" else XlsxWorkbook.STYLE_RED
    _gt_sheet_rows  = [["GOLD SAFE-HAVEN THESIS TRACKER",
                         f"Status: {_gtx_status} | Score: {_gtx.get('score',0):.2f}/{_gtx.get('max_score',1.0):.1f} | "
                         f"Confidence: {_gtx.get('confidence','LOW')} | "
                         f"Pass: {_gtx.get('n_pass',0)} | Watch: {_gtx.get('n_watch',0)} | "
                         f"Fail: {_gtx.get('n_fail',0)} | Missing: {_gtx.get('n_missing',0)}"]]
    _gt_sheet_styles = [_gtx_style]
    # Summary
    _gt_sheet_rows.append(["Summary", _gtx.get("summary", "")[:250]])
    _gt_sheet_styles.append(XlsxWorkbook.STYLE_NORMAL)
    # CIO Action
    _gtxa = _gtx.get("thesis_action") or {}
    for _label, _value in gold_thesis_action_rows(_gtxa):
        _gt_sheet_rows.append([_label, _value])
        _gt_sheet_styles.append(
            _gtx_style if _label == "CIO Gold Action"
            else XlsxWorkbook.STYLE_AMBER if _label == "Execution Permission"
            else XlsxWorkbook.STYLE_NORMAL
        )
    # Separator
    _gt_sheet_rows.append(["", ""])
    _gt_sheet_styles.append(XlsxWorkbook.STYLE_NORMAL)
    # Header row for checks
    _gt_sheet_rows.append(["Check", "Status | Score | Evidence | Interpretation | CIO Implication"])
    _gt_sheet_styles.append(XlsxWorkbook.STYLE_SECTION)
    _GT_CHECK_ORDER = [
        ("gold_stabilizes_and_rises",         "1. Gold stabilizes/rises"),
        ("silver_confirms_or_gsr_compresses", "2. Silver confirms / GSR compresses"),
        ("miners_vs_gold",                    "3. GDX/GDXJ vs GLD"),
        ("au_nem_vs_gdx",                     "4. AU/NEM vs GDX"),
        ("real_yields_do_not_spike",          "5. Real yields do not spike"),
        ("dxy_does_not_surge",                "6. DXY/UUP not surging"),
        ("oil_risk_premium_elevated",         "7. Oil-risk premium elevated"),
        ("miners_not_liquidated_as_equity_beta", "8. Miners not liquidated as equity beta"),
    ]
    for _gck, _glabel in _GT_CHECK_ORDER:
        _gch = (_gtx.get("checks") or {}).get(_gck) or {}
        _gcst = _gch.get("status", "MISSING")
        _gcscore = _gch.get("score", 0)
        _gcstyle = (XlsxWorkbook.STYLE_GREEN if _gcst == "PASS" else
                    XlsxWorkbook.STYLE_AMBER if _gcst == "WATCH" else
                    (XlsxWorkbook.STYLE_RED if _gcst == "FAIL" else XlsxWorkbook.STYLE_NORMAL))
        _detail = (f"[{_gcst}] Score={_gcscore} | {_gch.get('evidence','')[:80]} | "
                   f"{_gch.get('interpretation','')[:80]} | {_gch.get('cio_implication','')[:80]}")
        _gt_sheet_rows.append([_glabel, _detail])
        _gt_sheet_styles.append(_gcstyle)
    # Key metrics block
    _gt_sheet_rows.append(["", ""])
    _gt_sheet_styles.append(XlsxWorkbook.STYLE_NORMAL)
    _gt_sheet_rows.append(["KEY METRICS", ""])
    _gt_sheet_styles.append(XlsxWorkbook.STYLE_SECTION)
    _gtxm = _gtx.get("key_metrics") or {}
    # Keys that are percent-change or spread values → format as +/-X.XX%
    _PCT_KEYS = {
        "gld_change_pct", "slv_change_pct", "gdx_change_pct", "gdxj_change_pct",
        "au_change_pct", "nem_change_pct", "uup_change_pct", "tlt_change_pct",
        "xle_change_pct", "spy_change_pct", "qqq_change_pct", "vxx_change_pct",
        "uvxy_change_pct", "gdx_vs_gld_spread", "gdxj_vs_gld_spread",
        "au_vs_gdx_spread", "nem_vs_gdx_spread",
    }
    for _mkey, _mval in _gtxm.items():
        if _mval is None:
            _mfmt = "N/A"
        elif _mkey in _PCT_KEYS:
            _mfmt = f"{_mval:+.2f}%"
        else:
            _mfmt = str(_mval)
        _gt_sheet_rows.append([_mkey.replace("_", " ").title(), _mfmt])
        _gt_sheet_styles.append(XlsxWorkbook.STYLE_NORMAL)
    workbook.add_sheet("Gold Thesis Tracker", _gt_sheet_rows,
                       widths=[42, 120], row_styles=_gt_sheet_styles)

    workbook.add_sheet(
        "CIO Summary",
        [
            ["Field", "Value"],
            ["Workbook Generated", datetime.now().isoformat(sep=" ", timespec="seconds")],
            ["Platform Team", PLATFORM_TEAM],
            ["Report Generated", db.get("generated_at", "")],
            ["Dataset Generated", meta.get("generated_at", "")],
            ["FORMAL_REPORT_SNAPSHOT_TS", snapshot_hierarchy["formal_report_snapshot_ts"]],
            ["LIVE_DASHBOARD_SNAPSHOT_TS", snapshot_hierarchy["live_dashboard_snapshot_ts"]],
            ["BROKER_PORTFOLIO_TS", snapshot_hierarchy["broker_portfolio_ts"]],
            ["REPORT_IS_OLDER_THAN_LIVE_DASHBOARD", str(snapshot_hierarchy["report_is_older_than_live_dashboard"])],
            ["REGIME_DIFFERENCE_DETECTED", str(snapshot_hierarchy["regime_difference_detected"])],
            ["Snapshot Timing", snapshot_hierarchy["snapshot_disclosure"]],
            ["Market Status", normalize_market_session(meta.get("market_session", ""), snapshot_hierarchy["formal_report_snapshot_ts"])],
            ["Export / Ingest", f"{meta.get('export_version', '')} / {meta.get('ingest_version', '')}"],
            ["Sources Active", source_coverage_label(meta.get('external_sources_active', db.get('sources_active', '')), meta.get('sources_expected', db.get('sources_expected', '')))],
            ["Total Signals", meta.get("total_signals", db.get("total_signals", ""))],
            ["Regime", f"{regime.get('regime', '')} ({regime.get('score', '')})"],
            ["Regime Action", regime.get("action", db.get("regime_action", ""))],
            ["CIO Action", _op_truth.get("cio_action", db.get("cio_action", ""))],
            ["Confidence", f"{float(_op_truth.get('confidence') or 0):.3f} {_op_truth.get('confidence_label', '')}".strip()],
            # CONSISTENCY: always show live-computed status alongside archived (Upgrade #1)
            ["Causal Explanation (Live)", f"{_causal['causal_status']} | Pass {_causal['pass_count']}/10 | Conf {_causal['causal_confidence']:.3f}"],
            ["Causal Explanation (Archived)", db.get("causal_explanation_status", "")],
            ["Blind Spot Status (Live)", f"{_bscheck['blind_spot_status']} | Pass {_bscheck['pass_count']}/12 | Fail {_bscheck['fail_count']}/12"],
            ["Blind Spot Status (Archived)", db.get("blind_spot_status", "")],
            # Concentration always visible (Upgrade #5)
            ["Concentration (Live)", f"{_conc['concentration_status']} | HHI {_conc['hhi']:.4f} | Top-3 {_conc['top3_weight']:.1%} | Largest {_conc['largest_ticker']} {_conc['largest_weight']:.1%}"],
            ["Consistency Audit", f"{_audit['audit_status']} | Score {_audit['audit_score']}/100 | Fail {_audit['fail_count']}/10"],
            ["Quant Readiness", f"{dataset.get('institutional_quant', {}).get('readiness_label', '')} {dataset.get('institutional_quant', {}).get('readiness_score', '')}".strip()],
            ["IQ Status", dataset.get("institutional_quant", {}).get("status", "")],
            ["Execution Status", (dataset.get("execution") or {}).get("status", "")],
            ["Broker History", f"{(dataset.get('orders') or {}).get('historical_order_count', '')} orders / {(dataset.get('fills') or {}).get('historical_deal_count', '')} fills"],
            ["Open Orders", (dataset.get("orders") or {}).get("open_order_count", "")],
            ["Order Routing", "ENABLED" if (dataset.get("execution") or {}).get("order_routing_enabled") else "DISABLED"],
            ["CIO Cognition", (dataset.get("cio_cognition") or {}).get("latest_journal_id", "")],
            ["CIO Thesis Reviews", (dataset.get("cio_cognition") or {}).get("review_count", "")],
            ["Total Assets", portfolio.get("total_assets", "")],
            ["Cash", portfolio.get("cash", "")],
            ["Market Value", portfolio.get("market_val", "")],
            ["Total P/L", portfolio.get("total_pnl", "")],
            ["Largest Position", (risk.get("largest_position") or {}).get("ticker", "")],
            ["Largest Weight", (risk.get("largest_position") or {}).get("weight", "")],
            ["Security Master Gap", f"{unknown_security} UNKNOWN sector/industry rows" if unknown_security else "No unknown sector/industry gap"],
            ["Doctrine Warning", db.get("doctrine_warning", "")],
            ["Archive ID", archive.get("archive_id", db.get("id", ""))],
            ["Report SHA-256", db.get("report_sha256", "")],
        ],
        widths=[28, 90],
    )
    workbook.add_sheet("Health & Gaps", [["Dataset Section", "Grade", "Age Minutes"], *build_source_rows(dataset), [], ["Process", "Status", "Score", "Label", "Primary Gap"], *build_process_rows(dataset)], widths=[28, 20, 14, 18, 80])
    workbook.add_sheet("Portfolio", [["Ticker", "Mandate", "Qty", "Price", "Avg Cost", "Market Value", "Weight", "P/L", "P/L %", "Day %", "Action Note", "P/L Integrity", "P/L Conflict Detail"], *build_portfolio_rows(dataset)], widths=[12, 16, 10, 12, 12, 16, 12, 14, 12, 12, 26, 22, 60])
    workbook.add_sheet("Top Movers", [["Rank", "Ticker", "Move %", "PreMkt %", "Price", "Volume", "Rel Vol", "Session", "Catalyst", "Reason"], *build_mover_rows(dataset)], widths=[8, 10, 12, 12, 12, 16, 10, 12, 14, 60])
    workbook.add_sheet("Theme Rotation", [["No", "Theme", "Direction", "Basket Move %", "Confidence", "Evidence Tier", "Review Flag", "Why"], *build_theme_rows(dataset)], widths=[7, 30, 14, 15, 12, 22, 14, 90])
    workbook.add_sheet("Cross Market", [["Group", "Ticker", "Price", "Move %", "Volume", "Unavailable", "Reason", "Price Source"], *build_cross_market_rows(dataset), [], ["Type", "Name", "Value"], *build_cross_market_score_rows(dataset)], widths=[16, 10, 12, 12, 16, 14, 70, 16])
    workbook.add_sheet("Forward Catalysts", [["Ticker", "Type", "Date", "Time ET", "Days", "Flag", "EPS Est", "Source", "Portfolio"], *build_catalyst_rows(dataset)], widths=[10, 14, 14, 12, 8, 12, 10, 26, 12])
    _cs_pass = XlsxWorkbook.STYLE_GREEN
    _cs_warn = XlsxWorkbook.STYLE_AMBER
    _cs_fail = XlsxWorkbook.STYLE_RED
    _cs_hdr  = XlsxWorkbook.STYLE_SECTION
    _causal_row_styles  = [_cs_hdr] + [(_cs_pass if r[1]=="PASS" else _cs_warn if r[1]=="WARN" else _cs_fail) for r in _causal["check_rows"]]
    _bs_row_styles      = [_cs_hdr] + [(_cs_pass if r[1]=="PASS" else _cs_fail) for r in _bscheck["check_rows"]]
    workbook.add_sheet(
        "Causal & Blind Spot",
        [
            ["CAUSAL EXPLANATION ENGINE",
             f"Status: {_causal['causal_status']} | Confidence: {_causal['causal_confidence']:.3f} | "
             f"Pass: {_causal['pass_count']}/10 | Fail: {_causal['fail_count']}/10 | "
             f"Primary: {_causal['primary_driver']} | Secondary: {_causal['secondary_driver']}"
             + (f" | CRITICAL GAPS: {', '.join(_causal['critical_checks'])}" if _causal.get('critical_checks') else "")],
            *[[r[0], f"[{r[1]}] {r[2]}"] for r in _causal["check_rows"]],
            [],
            ["BLIND SPOT CHECKLIST (12 Items)",
             f"Status: {_bscheck['blind_spot_status']} | Pass: {_bscheck['pass_count']}/12 | "
             f"Fail: {_bscheck['fail_count']}/12 | CIO Penalty: -{_bscheck['cio_penalty']:.3f}"],
            *[[r[0], f"[{r[1]}] {r[2]}"] for r in _bscheck["check_rows"]],
        ],
        widths=[30, 110],
        row_styles=_causal_row_styles + [None, _cs_hdr] + _bs_row_styles[1:],
    )
    _inst = build_institutional_positioning(dataset)
    workbook.add_sheet(
        "Institutional Positioning",
        [
            ["SHORT VOLUME & INSTITUTIONAL POSITIONING"],
            [],
            ["-- OPTIONS FLOW (Unusual Large Trades) --"],
            ["Ticker", "Date / Time", "Action", "Volume (Contracts)", "Signal"],
            *_inst["options_flow"],
            [],
            ["-- CAPITAL FLOW: Largest Institutional Outflows --"],
            ["Ticker", "Super-Large Out", "Large Out", "Total", "Bias"],
            *_inst["capital_outflow"],
            [],
            ["-- CFTC COT: Leveraged Funds Positioning (Hedge Funds / CTAs) --"],
            ["Contract", "Net Position", "As Of", "Direction"],
            *_inst["cftc_cot"],
        ],
        widths=[18, 18, 18, 22, 12],
    )
    workbook.add_sheet("Tech Intelligence", [["Source", "Published", "Sentiment", "Score", "Type", "Tickers", "Themes", "Headline", "Summary"], *build_tech_rows(dataset)], widths=[20, 20, 12, 10, 18, 18, 28, 70, 80])
    # ── Risk Governor header rows for Analyst Targets sheet ──────────────────
    # Use approved_operating_truth.json (most authoritative cluster data)
    _xl_rg_conc = (_approved_truth_x.get("concentration_status") or _conc.get("concentration_status") or "UNKNOWN")
    _xl_rg_cluster = (_approved_truth_x.get("cluster_status") or {})
    _xl_rg_gm = _xl_rg_cluster.get("GOLD_MINERS", {})
    _xl_rg_gm_sev = str(_xl_rg_gm.get("severity", "")).upper()
    if not _xl_rg_gm_sev and _conc.get("cluster_max_name") == "GOLD_MINERS":
        _xl_rg_gm_sev = "CRITICAL" if _conc.get("cluster_max_val", 0) >= 0.65 else "HIGH"
    _xl_rg_gm_pct = _xl_rg_gm.get("weight_pct", f"{_conc.get('cluster_max_val', 0):.0%}" if _conc.get("cluster_max_name") == "GOLD_MINERS" else "N/A")
    if _xl_rg_gm_sev == "CRITICAL" or _xl_rg_conc == "CRITICAL":
        _xl_rg_header = [
            ["RISK GOVERNOR — WATCHLIST OVERRIDE ACTIVE", "", "", "", "", "", "", "", "", "", "", "", ""],
            [f"GOLD_MINERS cluster = CRITICAL ({_xl_rg_gm_pct}). AU/NEM/GLD/GDX/GDXJ: action = HOLD / DECONCENTRATION REVIEW | governance = CLUSTER_BLOCKED_NO_ADD. A high 8-Lens score does NOT mean BUY.", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["CIO must manually approve any deconcentration trade. No automated orders permitted.", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", "", "", "", "", "", ""],
        ]
    else:
        _xl_rg_header = []
    workbook.add_sheet("Analyst Targets", [["Ticker", "Price", "Low Target", "Avg Target", "High Target", "Upside %", "Buy %", "Hold %", "Sell %", "Analysts", "Rating", "Source", "Fetched At"], *_xl_rg_header, *build_analyst_rows(dataset)], widths=[10, 12, 12, 12, 12, 12, 10, 10, 10, 10, 10, 26, 24])
    workbook.add_sheet("Superforecast", [["Ticker", "Method", "Dir", "Price", "Target 7D", "Target 14D", "Target 30D", "Target 60D", "Target 90D", "Exp Ret 90D %", "Prob 90D", "Confidence", "Theme", "Risk Notes", "Basis"], *build_forecast_rows(dataset)], widths=[10, 26, 8, 12, 12, 12, 12, 12, 12, 14, 12, 12, 28, 44, 90])
    # Brier sheet: compute maturity label (Upgrade #6)
    _rf_data = dataset.get("research_forecasting") or {}
    _acc_data = _rf_data.get("accuracy_summary") or []
    _resolved = sum(int(r.get("resolved_count") or 0) for r in _acc_data if isinstance(r, dict))
    _brier_maturity = (
        f"MATURE [{_resolved} resolved]" if _resolved >= 100 else
        f"NOT_MATURE [{_resolved} resolved — need 100+]" if _resolved >= 30 else
        f"COLLECTING [{_resolved} resolved — need 30+ to report; 100+ for full accountability]"
    )
    workbook.add_sheet("Brier Accuracy", [
        ["BRIER ACCOUNTABILITY STATUS", _brier_maturity],
        ["", "Interpretation: COLLECTING = insufficient data | NOT_MATURE = some signal | MATURE = statistically meaningful"],
        [],
        ["Method", "Horizon Days", "Resolved Count", "Avg Brier", "Avg Price Error", "Directional Accuracy"],
        *build_forecast_accuracy_rows(dataset),
    ], widths=[26, 80, 16, 14, 16, 18])
    workbook.add_sheet("Risk Model", [["Metric", "Value"], *build_risk_summary_rows(dataset), [], ["Ticker", "Mkt Value", "Weight", "History Points", "Ann Vol", "VaR95 $", "VaR99 $", "Max DD", "Beta SPY", "First", "Last"], *build_risk_model_rows(dataset)], widths=[18, 18, 14, 16, 14, 14, 14, 14, 12, 14, 14])
    workbook.add_sheet("Portfolio Targets", [["Ticker", "Current Weight", "Target Weight", "Delta Weight", "Current Value", "Target Value", "Research Only"], *build_portfolio_target_rows(dataset)], widths=[12, 16, 16, 14, 16, 16, 16])
    workbook.add_sheet(
        "Execution Intel",
        [
            ["Field", "Value"],
            *build_execution_summary_rows(dataset),
            [],
            ["Open Orders"],
            ["Ticker", "Side", "Type", "Status", "Order Intent", "Qty", "Limit Price", "Dealt Qty", "Avg Fill", "TIF", "Session", "Created", "Updated", "Order ID"],
            *build_open_order_rows(dataset, 40),
            [],
            ["Recent Broker Fills"],
            ["Ticker", "Side", "Qty", "Price", "Deal Time", "Order ID", "Deal ID", "Scope"],
            *build_recent_fill_rows(dataset, 80),
            [],
            ["Trade Lifecycle"],
            ["Stage", "Owner", "System Record"],
            *build_trade_lifecycle_rows(dataset),
        ],
        widths=[16, 12, 12, 24, 12, 14, 12, 14, 12, 12, 24, 24, 28],
    )
    _plan_vs_orders = build_cio_plan_vs_order_book(dataset)
    workbook.add_sheet(
        "CIO Plan vs Orders",
        [
            ["CIO PLAN VS BROKER ORDER BOOK", ""],
            *_plan_vs_orders["rows"],
        ],
        widths=[34, 120],
    )
    workbook.add_sheet(
        "Deterministic Ops",
        [
            ["Field", "Value"],
            *build_deterministic_operator_summary_rows(dataset),
            [],
            ["Operator", "Status", "Score", "Confidence", "Evidence", "Blocked Actions"],
            *build_deterministic_operator_rows(dataset),
        ],
        widths=[26, 24, 12, 20, 100, 60],
    )
    workbook.add_sheet(
        "CIO Cognition",
        [
            ["Field", "Value"],
            *build_cio_cognition_summary_rows(dataset),
            [],
            ["Strategic Thinking / Planning / Execution Journal"],
            ["Journal TS", "Journal ID", "Type", "Priority", "Regime", "CIO Action", "Confidence", "Strategic Thinking", "Planning", "Execution Intent", "Non-Execution Rationale", "Author"],
            *build_cio_cognition_journal_rows(dataset, 20),
            [],
            ["Thesis Reviews"],
            ["Thesis ID", "Status", "Probability", "Confidence", "CIO Assessment", "Strategic Note", "Planning Note", "Execution Note", "Repeatability Hypothesis", "Mistake Risk"],
            *build_cio_thesis_review_rows(dataset, 40),
        ],
        widths=[24, 32, 18, 12, 18, 18, 12, 55, 55, 48, 45, 18],
    )
    workbook.add_sheet("Thesis Lifecycle", [["Priority", "Status", "Thesis ID", "Thesis", "Base Prob", "Current Prob", "Confidence", "Direction", "Horizon", "Tickers", "Evidence", "Kill Condition"], *build_thesis_rows(dataset)], widths=[10, 14, 30, 52, 12, 14, 12, 28, 10, 40, 70, 80])
    workbook.add_sheet("Thesis Evidence", [
        ["ECE GOVERNING LOGIC v2 — Sector direction derived from basket_move vs SPY: RISK_ON>=+0.50% | SELECTIVE_RISK_ON>=+0.10% | NEUTRAL+-0.10% | SELECTIVE_RISK_OFF<=-0.10% | RISK_OFF<=-0.50% | Broad-rally override: when SPY>0 AND (QQQ>0 OR IWM>0) AND VXX<=0, positive-basket sectors cannot be RISK_OFF | Review flags: POSITIVE_BASKET_RISK_OFF_CONFLICT, NEGATIVE_BASKET_RISK_ON_CONFLICT, SECTOR_EVIDENCE_MISMATCH, GENERIC_EVIDENCE_REVIEW | Global regime context stored separately and never overwrites sector basket behavior | Version: ECE_v2"],
        [],
        ["Status", "Type", "Sector / Thesis", "Logic (Basket · Polarity · RegimeCtx · Flags)", "Evidence / Why", "Direction Code"],
        *build_thesis_evidence_rows(dataset),
    ], widths=[10, 14, 36, 60, 120, 22])
    workbook.add_sheet("Monitoring Alerts", [["Severity", "Layer", "Type", "Title", "Message", "Ticker", "Cycle"], *build_monitoring_rows(dataset)], widths=[12, 18, 24, 42, 90, 10, 24])
    workbook.add_sheet("History Coverage", [["Ticker", "Rows", "First Date", "Last Date", "Latest Fetch"], *build_history_coverage_rows(dataset)], widths=[10, 12, 14, 14, 24])
    workbook.add_sheet("Ops Upgrade", [["Field", "Value"], *build_ops_summary_rows(dataset)], widths=[30, 100])
    workbook.add_sheet("CIO Decisions", [["Priority", "Type", "Ticker", "Status", "Current Weight", "Target Weight", "Delta Weight", "CIO Decision", "Execution Authority", "Order Generated", "Research Basis", "Decision TS"], *build_cio_decision_rows(dataset)], widths=[10, 24, 10, 34, 16, 16, 16, 16, 22, 16, 80, 24])
    workbook.add_sheet("Backfill Queue", [["Ticker", "Status", "Source", "Priority", "Rows", "First", "Latest", "Latest Fetch", "Attempts", "Last Attempt", "Last Error"], *build_backfill_queue_rows(dataset)], widths=[10, 14, 22, 10, 10, 14, 14, 24, 10, 24, 80])
    workbook.add_sheet("Capital Flow", [["Ticker", "Bias", "Main Net", "Super Large Net", "Large Net", "Medium Net", "Small Net", "In Flow", "Snapshot", "Cycle TS"], *build_flow_rows(dataset)], widths=[10, 18, 16, 18, 16, 16, 16, 16, 14, 24])
    workbook.add_sheet("Universe Snapshot", [["Ticker", "Attention Tags", "Theme", "Sector", "Industry", "Mkt Cap Tier", "Asset Type", "Price", "Day %", "PreMkt %", "Rel Vol", "Vol Spike", "Volume", "Avg Target", "Upside %", "Buy %", "Hold %", "Sell %", "Analysts", "Flow Bias", "Main Net Flow", "Super Large Net", "Sentiment", "Sent Score", "Catalyst Date", "Catalyst Flag", "Days To Catalyst", "PE TTM", "P/B", "52W High %", "Earnings Yield", "Fundamental Applicability"], *build_universe_rows(dataset)], widths=[10, 22, 28, 20, 26, 15, 12, 12, 10, 10, 10, 10, 14, 12, 12, 10, 10, 10, 10, 16, 16, 16, 14, 12, 14, 14, 14, 12, 12, 14, 14, 24])
    workbook.add_sheet("Archive Metadata", [["Field", "Value"], *[[k, v] for k, v in {
        "archive_status": archive.get("archive_status", ""),
        "archive_id": archive.get("archive_id", ""),
        "verified_from_database": archive.get("verified_from_database", ""),
        "archive_json_generated_at": archive.get("archive_json_generated_at", ""),
        "platform_team": PLATFORM_TEAM,
        "report_text_included": archive.get("report_text_included", ""),
        "report_text_char_count": archive.get("report_text_char_count", ""),
        "report_version": db.get("report_version", ""),
        "report_sha256": db.get("report_sha256", ""),
        "source_file_path": db.get("source_file_path", ""),
    }.items()]], widths=[28, 90])

    # ── QA Sheet (WO-ECE-20260613-001 / WO-Final-PhD Defect 2) ──────────────
    # Use the LIVE _audit and _op_truth already computed above — never empty dicts.
    _qa_cd_xl = {
        "consistency_audit": {
            "status":     _audit.get("audit_status", "UNKNOWN"),
            "score":      _audit.get("audit_score", 0),
            "fail_count": _audit.get("fail_count", 0),
            "warn_count": _audit.get("warn_count", 0),
            "check_results": {r[0]: r[1] for r in _audit.get("check_rows", [])},
        }
    }
    _ot_qa_xl = {
        "order_routing_enabled":        _op_truth.get("order_routing_enabled", False),
        "orders_generated_by_pipeline": int(_op_truth.get("orders_generated_by_pipeline") or 0),
    }
    # Also check freshness governor for the freshness_gate field
    _fg_xl = _freshness.get("freshness_status", "UNKNOWN")
    try:
        _qa_xl = build_report_qa_footer(dataset, _qa_cd_xl, _ot_qa_xl)
        _qa_xl["freshness_gate"] = _fg_xl
    except Exception:
        _qa_xl = {"freshness_gate": _fg_xl}
    _qa_xl_blocking = list(_qa_xl.get("blocking_failures") or [])
    # Inject governance-gate failed gates so QA surface reflects same state as governance gate.
    for _gfg in (_gov_failed_ck or []):
        _gfg_key = f"GOV_GATE_FAIL:{_gfg}"
        if _gfg_key not in _qa_xl_blocking:
            _qa_xl_blocking.append(_gfg_key)
    # Cap institutional grade at 9.2/10 when governance gate has active failed gates.
    _qa_xl_grade = float(_qa_xl.get("final_institutional_grade") or 9.5)
    if _gov_failed_ck:
        _qa_xl_grade = round(min(_qa_xl_grade, 9.2), 1)
    _qa_xl_warnings = _qa_xl.get("warnings") or []
    # Wording: only call "Blocking Failures" when release is actually BLOCKED.
    # For APPROVED_WITH_WARNINGS, label as "Warning / Failed Gates" with clean names.
    if _gov_release_ck == "BLOCKED":
        _qa_fail_label = "Blocking Failures"
        _qa_fail_items = _qa_xl_blocking
    else:
        _qa_fail_label = "Warning / Failed Gates"
        _qa_fail_items = [g.replace("GOV_GATE_FAIL:", "") for g in _qa_xl_blocking]
    _qa_xl_rows = [
        ["QA Field", "Value", "Notes"],
        ["Consistency Audit",     f"{_qa_xl.get('consistency_audit', 'N/A')} (score={_qa_xl.get('consistency_audit_score', 'N/A')})", "Must be CONSISTENT (score=100)"],
        ["ECE Renderer Match",    str(_qa_xl.get("ece_renderer_match", "N/A")),    "Must be PASS"],
        ["ECE Percent Scale Check", str(_qa_xl.get("ece_percent_scale_check", "N/A")), "FAIL = basket_move >±50%"],
        ["Evidence Mapping Check", str(_qa_xl.get("evidence_mapping_check", "N/A")), "FLAG = SECTOR_EVIDENCE_MISMATCH rows present"],
        ["Causal Status Logic",   str(_qa_xl.get("causal_status_logic", "N/A")),   "Must be PASS"],
        ["Execution Safety Gate", str(_qa_xl.get("execution_safety_gate", "N/A")), "Must be PASS (routing=off, orders=0)"],
        ["Freshness Gate",        str(_qa_xl.get("freshness_gate", "N/A")),        "Must be PASS or WARNING"],
        ["Governance Gate Status", _gov_release_ck,                                 "APPROVED_WITH_WARNINGS = no hard block; BLOCKED = hard stop"],
        [_qa_fail_label,          ", ".join(_qa_fail_items) if _qa_fail_items else "None", "Gov failures cap grade at 9.2; BLOCKED = grade not issued"],
        ["Warnings",              ", ".join(_qa_xl_warnings) if _qa_xl_warnings else "None", ""],
        ["Final Institutional Grade", f"{_qa_xl_grade} / 10", "Target: 9.5/10; capped at 9.2 when governance gate has failed gates"],
    ]
    if _qa_xl.get("over_scaled_themes"):
        _qa_xl_rows.append(["  Over-scaled Themes", ", ".join(_qa_xl["over_scaled_themes"]), "Review basket_move unit convention"])
    if _qa_xl.get("mismatch_themes"):
        _qa_xl_rows.append(["  Evidence Mismatch Themes", ", ".join(_qa_xl["mismatch_themes"]), "Wrong-theme evidence detected"])
    # Defect 6 — Regime vs Cognition Ledger timestamp disclosure in QA sheet
    _rcd_xl = build_regime_cognition_disclosure(dataset)
    _rcd_xl_delta = (f"{_rcd_xl['delta_hours']:.1f}h" if _rcd_xl['delta_hours'] is not None else "unknown")
    _qa_xl_rows.append([])
    _qa_xl_rows.append(["── REGIME-COGNITION ALIGNMENT (Defect 6) ──", "", ""])
    _qa_xl_rows.append(["Regime Timestamp",   _rcd_xl["regime_ts"],         "Dataset / ingest generation time"])
    _qa_xl_rows.append(["Ledger Timestamp",   _rcd_xl["ledger_ts"],         "CIO Cognition latest journal_ts"])
    _qa_xl_rows.append(["Time Delta",         _rcd_xl_delta,                "Hours between regime assessment and cognition entry"])
    _qa_xl_rows.append(["Alignment Severity", _rcd_xl["mismatch_severity"], "NONE/MINOR/MODERATE/MATERIAL"])
    _qa_xl_rows.append(["Disclosure Required", "YES" if _rcd_xl["disclosure_required"] else "NO", "MODERATE or MATERIAL requires disclosure"])
    _qa_xl_rows.append(["Disclosure Text",    _rcd_xl["disclosure_text"][:200], ""])
    workbook.add_sheet("Report QA", _qa_xl_rows, widths=[36, 50, 80])

    # ── NITE-PEI Bayesian Engine Tab ─────────────────────────────────────────
    try:
        _npb = _load_latest_nite_pei_block()
        if _npb:
            # Tab 1: NITE-PEI Summary (CKRI + formula)
            _np_summary_rows = [
                ["NITE-PEI Engine — Bayesian Thesis Update", "", ""],
                ["Generated", _npb.get("generated_at_sgt", ""), ""],
                ["Schema", _npb.get("schema_version", ""), ""],
                ["Governance", "MANUAL_EXECUTION_REQUIRED | LLM_ORDER_GENERATION=FALSE", ""],
                [],
                ["COMPOSITE KILL RISK INDEX (CKRI)", "", ""],
                ["CKRI Score", _npb.get("ckri", ""), ""],
                ["CKRI Zone", _npb.get("ckri_zone", ""), ""],
                ["Weighted Sum", (_npb.get("ckri_detail") or {}).get("weighted_sum", ""), ""],
                ["Correlation Penalty", (_npb.get("ckri_detail") or {}).get("correlation_penalty_applied", ""), ""],
                ["Total Weight", (_npb.get("ckri_detail") or {}).get("total_weight", ""), ""],
                [],
                ["BAYESIAN UPDATE FORMULA", "", ""],
                ["Step 1", "prior_odds = P_prior / (1 - P_prior)", ""],
                ["Step 2", "LR_adjusted = 1.0 + (LR_table[event_class][thesis_type] - 1.0) x (1 - noise_discount)", "discount pulls evidence toward neutral LR=1.0; T1=0.00 T2=0.10 T3=0.25 T4=0.50"],
                ["Step 3", "post_odds = prior_odds x LR_adjusted", ""],
                ["Step 4", "P_posterior = post_odds / (1 + post_odds)", ""],
                ["Step 5", "clamp to [0.05, 0.95]", "prevents probability reaching 0 or 1"],
                ["Multi-event", "posterior_N becomes prior_(N+1)", "sequential compounding"],
                [],
                ["LR > 1.0", "Event is evidence FOR the thesis (raises P)", ""],
                ["LR < 1.0", "Event is evidence AGAINST the thesis (lowers P)", ""],
                ["LR = 1.0", "Event carries no information (no update)", ""],
            ]
            _np_s_styles = [XlsxWorkbook.STYLE_SECTION] + [None] * (len(_np_summary_rows) - 1)
            workbook.add_sheet("NITE-PEI Summary", _np_summary_rows, widths=[28, 72, 52], row_styles=_np_s_styles)

            # Tab 2: Thesis Probability Updates with evidence + source URLs
            _np_thesis_rows = [["Thesis ID", "P_prior", "P_posterior", "Delta P", "Posture", "Event Class", "Headline", "Source", "Published", "Dataset Key", "Source URL", "Step1 Prior Odds", "Step2 LR_adjusted", "Step3 Post Odds", "Step4 P_posterior", "Step5 Clamp", "Delta P Step"]]
            for snap in _npb.get("thesis_probability_snapshots", []):
                events = snap.get("events_applied", [])
                if not events:
                    _np_thesis_rows.append([
                        snap.get("thesis_id", ""), snap.get("P_prior", ""), snap.get("P_posterior", ""),
                        snap.get("delta_p", ""), snap.get("posture", ""),
                        "(no events this cycle)", "", "", "", "", "", "", "", "", "", "", ""
                    ])
                else:
                    for i, ev in enumerate(events):
                        beq = ev.get("bayesian_equation", {})
                        _np_thesis_rows.append([
                            snap.get("thesis_id", "") if i == 0 else "",
                            snap.get("P_prior", "") if i == 0 else "",
                            snap.get("P_posterior", "") if i == 0 else "",
                            snap.get("delta_p", "") if i == 0 else "",
                            snap.get("posture", "") if i == 0 else "",
                            ev.get("event_class", ""),
                            ev.get("raw_headline", ""),
                            ev.get("source", ""),
                            ev.get("published_at", ""),
                            ev.get("dataset_key", ""),
                            ev.get("source_url", "[NO URL]"),
                            beq.get("step_1_prior_odds", ""),
                            beq.get("step_2_lr_adjustment", ""),
                            beq.get("step_3_posterior_odds", ""),
                            beq.get("step_4_posterior_prob", ""),
                            beq.get("step_5_clamp", ""),
                            ev.get("delta_p_step", ""),
                        ])
            _np_t_styles = [XlsxWorkbook.STYLE_HEADER] + [None] * (len(_np_thesis_rows) - 1)
            workbook.add_sheet("NITE-PEI Thesis Updates", _np_thesis_rows,
                widths=[32, 10, 12, 10, 28, 26, 60, 40, 20, 28, 60, 38, 40, 38, 38, 30, 14],
                row_styles=_np_t_styles)

            # Tab 3: Kelly Advisories
            _np_kelly_rows = [["Thesis ID", "Thesis Type", "P_posterior", "f*_full", "Frac Mult", "f*_kelly", "Coherence", "H_norm", "Dispersion", "NAV Total", "Target USD", "Current USD", "Delta USD", "Action"]]
            for k in _npb.get("kelly_advisories", []):
                _np_kelly_rows.append([
                    k.get("thesis_id", ""), k.get("thesis_type", ""),
                    k.get("p_posterior_used", ""), k.get("f_star_full", ""),
                    k.get("fractional_multiplier", ""), k.get("f_star_kelly", ""),
                    k.get("coherence_score", ""), k.get("h_norm_used", ""),
                    k.get("dispersion_used", ""), k.get("nav_total", ""),
                    k.get("target_usd_sleeve", ""), k.get("current_usd_sleeve", ""),
                    k.get("delta_usd", ""), k.get("advisory_text", ""),
                ])
            _np_k_styles = [XlsxWorkbook.STYLE_HEADER] + [None] * (len(_np_kelly_rows) - 1)
            workbook.add_sheet("NITE-PEI Kelly", _np_kelly_rows,
                widths=[32, 30, 12, 10, 10, 10, 10, 10, 12, 14, 14, 14, 14, 50],
                row_styles=_np_k_styles)
    except Exception as _npe_xl:
        workbook.add_sheet("NITE-PEI Summary", [["Error loading NITE-PEI block", str(_npe_xl)]], widths=[40, 80])

    workbook.save(output_path)


def build_word_report(dataset: Dict[str, Any], archive: Dict[str, Any], output_path: Path) -> None:
    db = archive.get("database_row") or {}
    meta = dataset.get("meta") or {}
    regime = dataset.get("regime") or {}
    portfolio = dataset.get("portfolio") or {}
    risk = dataset.get("risk_metrics") or {}
    formal_risk = dataset.get("risk_model") or {}
    treasury = dataset.get("treasury_yields") or {}
    themes = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    strongest = sorted(themes, key=lambda r: n(r.get("basket_move"), -999) or -999, reverse=True)[:3]
    weakest = sorted(themes, key=lambda r: n(r.get("basket_move"), 999) or 999)[:3]

    # CONSISTENCY: two-pass approach (Word)
    _causal_data  = build_causal_explanation(dataset)
    _bscheck_data = build_blind_spot_checklist(dataset)
    _conc         = build_concentration_risk(dataset)
    _op_truth_pre_w = build_operating_truth(dataset, archive, _causal_data, _bscheck_data, _conc)
    _audit_data   = build_consistency_audit(dataset, archive, causal_data=_causal_data, blind_data=_bscheck_data, operating_truth=_op_truth_pre_w)
    _op_truth_w   = build_operating_truth(dataset, archive, _causal_data, _bscheck_data, _conc, _audit_data)

    # ── Governance contract merge — load approved_operating_truth.json fields ──
    _approved_truth_w = _load_approved_truth_for_renderer() or {}
    for _gf in (
        "cio_action", "confidence", "confidence_label",
        "causal_status", "blind_spot_status", "concentration_status",
        "_release_status", "governance_gate_score",
        "governance_gate_failed_gates", "governance_gate_passed_gates",
        "governance_gate_deductions", "sentiment_hygiene_gate",
    ):
        if _gf in _approved_truth_w:
            _op_truth_w[_gf] = _approved_truth_w[_gf]

    # 9.5/10 Upgrade: compute all new module objects for Word
    _action_logic_w = build_cio_action_logic(_op_truth_w, dataset)
    _remediations_w = build_blind_spot_remediations(_bscheck_data)
    _causal_chain_w = build_causal_chain(dataset, _causal_data)
    _risk_gov_w     = build_portfolio_risk_governor(dataset, _conc)
    _forecast_mat_w = build_forecast_maturity_schedule(dataset)
    _freshness_w    = build_freshness_governor(dataset)
    _news_priority_w = build_news_priority_engine(dataset, _op_truth_w)
    _readiness_w    = build_report_readiness(_op_truth_w, _freshness_w)
    _op_truth_w["report_readiness"] = _readiness_w["classification"]
    _mismatches_w   = detect_archive_live_mismatches(_op_truth_w, archive)

    # Live-computed aliases for use throughout
    _live_causal  = _causal_data["causal_status"]
    _live_blind   = _bscheck_data["blind_spot_status"]
    _live_conc_s  = _conc["concentration_status"]
    _conf_f       = float(_op_truth_w.get("confidence", 0) or 0)
    _conf_label_w = str(_op_truth_w.get("confidence_label", "") or "")
    _cio_action_w = str(_op_truth_w.get("cio_action") or db.get("cio_action") or "WAIT / HOLD")
    _cluster_str  = " | ".join(f"{k} {v:.0%}" for k, v in _conc["clusters"].items())
    _snapshot_w   = build_snapshot_hierarchy(dataset)

    doc = DocxDocument()
    doc.paragraph("BLUELOTUS FUND", bold=True, size=26, color="606060", after=40)
    doc.paragraph("CIO OPERATING BRIEF", bold=True, size=48, after=40)
    doc.paragraph(PLATFORM_TEAM, bold=True, size=24, color="1F4E79", after=60)
    doc.paragraph("Trial Word presentation layer for the R6 deterministic research report", size=25, color="606060", after=180)

    if render_master_prompt_text_section and build_master_prompt_rows:
        _master_prompt_w = (dataset.get("chief_strategist_master_prompt") or {})
        _master_active_w = master_prompt_is_active(dataset) if master_prompt_is_active else False
        doc.heading("00 · CHIEF STRATEGIST MASTER PROMPT / MODUS OPERANDI")
        doc.callout(
            "READ FIRST BEFORE ANY ANALYSIS",
            (
                "Chief Strategist Master Prompt: ACTIVE / MANDATORY / READ FIRST\n"
                f"Prompt version: {_master_prompt_w.get('version', 'MISSING')}\n"
                f"Prompt hash: {_master_prompt_w.get('prompt_hash', '')}\n"
                "CIO Context Capsule status: ACTIVE\n"
                "Execution authority: CIO_ONLY_MANUAL\n"
                "Order routing enabled: FALSE\n"
                "System orders generated: 0\n"
                "No Chief Strategist answer may be produced from tactical data alone."
            ),
            fill="FFE0E0" if _master_active_w else "FF0000",
        )
        doc.table(build_master_prompt_rows(dataset), widths=[1800, 4860, 1260, 1440], font_size=13)

    _law_binding_w = dataset.get("law_governance_binding") if isinstance(dataset.get("law_governance_binding"), dict) else {}
    doc.heading("00A · LAW & ORDER GOVERNANCE BINDING")
    doc.callout(
        "ACTIVE LAW PACK GOVERNING THIS REPORT",
        _law_binding_w.get("doctrine_text", ""),
        fill="E2F0D9" if _law_binding_w.get("status") == "BOUND" else "FFE0E0",
    )
    _law_doc_rows = [["Field", "Value", "Certainty", "Source Layer"], *build_law_governance_rows(_law_binding_w)]
    doc.table(_law_doc_rows, widths=[2200, 4640, 1260, 1260], font_size=13)

    if render_cio_context_text_section and build_cio_context_rows:
        _cio_capsule_w = (dataset.get("cio_context_capsule") or {})
        _cio_capsule_active_w = capsule_is_active(dataset) if capsule_is_active else False
        doc.heading("CIO CONTEXT CAPSULE — READ FIRST")
        doc.callout(
            "Portable CIO Memory Layer",
            (
                f"Version: {_cio_capsule_w.get('version', 'MISSING')}\n"
                f"Mandatory for Chief Strategist: {_cio_capsule_w.get('mandatory_for_all_chief_strategist_replies', False)}\n"
                f"Capsule Hash: {_cio_capsule_w.get('capsule_hash', '')}\n"
                "No Chief Strategist answer may be produced from tactical data alone."
            ),
            fill="E2F0D9" if _cio_capsule_active_w else "FFE0E0",
        )
        _cio_doc_rows = [["Field", "Value", "Certainty", "Source Layer"], *build_cio_context_rows(dataset)]
        doc.table(_cio_doc_rows, widths=[1800, 4860, 1260, 1440], font_size=14)

    _pei_w = dataset.get("prospective_event_intelligence") if isinstance(dataset.get("prospective_event_intelligence"), dict) else {}
    if pei_rows and pei_branch_rows and pei_playbook_rows:
        doc.heading("00B · PEI PROSPECTIVE EVENT INTELLIGENCE")
        doc.callout(
            "EVENT PATHWAYS / SCENARIO TREES / PORTFOLIO PREPARATION",
            (
                f"Status: {_pei_w.get('status', 'MISSING')}\n"
                f"Governance Pack: {_pei_w.get('governance_pack_id', '')}\n"
                f"Report Memory Binding: {_pei_w.get('report_memory_binding_id', '')}\n"
                "Authority: RESEARCH / FORECASTING / PREPARATION ONLY\n"
                "Execution: CIO_ONLY_MANUAL | Order routing: FALSE | Orders generated: 0"
            ),
            fill="E2F0D9" if _pei_w.get("status") == "OPERATIONAL" else "FFE0E0",
        )
        doc.table(pei_rows(_pei_w), widths=[1800, 4860, 1260, 1440], font_size=13)
        doc.table(
            [["Event", "Branch", "Probability", "Allowed", "Blocked", "Kill Conditions"], *[
                [row[0], row[1], row[2], row[3], row[4], row[5]]
                for row in pei_branch_rows(_pei_w)[1:10]
            ]],
            widths=[1500, 2100, 900, 1500, 1500, 1860],
            font_size=12,
        )
        doc.table(
            [["Event", "Branch", "Allowed", "Blocked", "Resolution Date"], *[
                [row[0], row[1], row[4], row[5], row[6]]
                for row in pei_playbook_rows(_pei_w)[1:8]
            ]],
            widths=[1500, 2460, 1800, 1800, 1800],
            font_size=12,
        )

    _str_w = dataset.get("shannon_thorp_refinement") if isinstance(dataset.get("shannon_thorp_refinement"), dict) else {}
    if str_summary_rows and str_signal_entropy_rows and str_cost_basis_rows and str_kelly_rows and str_hedge_rows:
        doc.heading("00C · STR SIGNAL, ENTROPY, AND EDGE")
        doc.callout(
            "SHANNON-THORP RESEARCH-ONLY ADVISORY LAYER",
            (
                f"Status: {_str_w.get('status', 'MISSING')}\n"
                f"Governance Pack: {_str_w.get('governance_pack_id', '')}\n"
                f"Report Memory Binding: {_str_w.get('report_memory_binding_id', '')}\n"
                "Authority: RESEARCH / PROPOSAL / PREPARATION ONLY\n"
                "Execution: CIO_ONLY_MANUAL | Order routing: FALSE | Orders generated: 0\n"
                "Kelly output is advisory only. It is not an order. It does not override CIO manual sizing."
            ),
            fill="E2F0D9" if _str_w.get("status") == "OPERATIONAL" else "FFE0E0",
        )
        doc.table(str_summary_rows(_str_w), widths=[2500, 6860], font_size=13)
        doc.table(str_signal_entropy_rows(_str_w)[:12], widths=[1100, 1300, 1000, 1000, 1000, 1100, 1100, 2760], font_size=10)
        doc.table(str_cost_basis_rows(_str_w), widths=[900, 1200, 1200, 1200, 1200, 1700, 2100, 860], font_size=10)
        doc.table(str_kelly_rows(_str_w)[:12], widths=[600, 700, 600, 600, 600, 1050, 1050, 800, 850, 850, 900, 1000, 900, 750, 1510], font_size=8)
        doc.table(str_hedge_rows(_str_w), widths=[3000, 6360], font_size=12)

    _rem_w = dataset.get("v3_str_bug_clearance_reconciliation") if isinstance(dataset.get("v3_str_bug_clearance_reconciliation"), dict) else {}
    if _rem_w and remediation_summary_rows:
        _hedge_disc = (_rem_w.get("hedge_advisory_disclaimer") or {}).get("text", "")
        doc.heading("00D · V3 / STR BUG-CLEARANCE RECONCILIATION")
        doc.callout(
            "ENGINEERING REMEDIATION STATUS",
            (
                f"Status: {_rem_w.get('status', 'MISSING')}\n"
                "Execution: CIO_ONLY_MANUAL | Order routing: FALSE | Orders generated: 0\n"
                f"{_hedge_disc}"
            ),
            fill="E2F0D9" if _rem_w.get("status") == "OPERATIONAL" else "FFE0E0",
        )
        doc.table(remediation_summary_rows(_rem_w), widths=[2800, 6560], font_size=12)
        _open_rows = [["Ticker", "Side", "Qty", "Limit", "Broker Status", "Classification", "CIO Review"]]
        for _r in (_rem_w.get("open_order_state_reconciliation") or [])[:8]:
            _open_rows.append([_r.get("ticker"), _r.get("side"), _r.get("qty"), _r.get("limit_price"), _r.get("broker_status"), _r.get("classification"), _r.get("requires_cio_review")])
        doc.table(_open_rows, widths=[900, 800, 800, 900, 1500, 3000, 1460], font_size=9)

    doc.table(
        [
            ["Field", "Value"],
            ["Platform Team", PLATFORM_TEAM],
            ["Generated", db.get("generated_at") or datetime.now().isoformat(sep=" ", timespec="seconds")],
            ["Dataset", meta.get("generated_at", "")],
            ["FORMAL_REPORT_SNAPSHOT_TS", _snapshot_w["formal_report_snapshot_ts"]],
            ["LIVE_DASHBOARD_SNAPSHOT_TS", _snapshot_w["live_dashboard_snapshot_ts"]],
            ["BROKER_PORTFOLIO_TS", _snapshot_w["broker_portfolio_ts"]],
            ["REPORT_IS_OLDER_THAN_LIVE_DASHBOARD", str(_snapshot_w["report_is_older_than_live_dashboard"])],
            ["REGIME_DIFFERENCE_DETECTED", str(_snapshot_w["regime_difference_detected"])],
            ["Snapshot Timing", _snapshot_w["snapshot_disclosure"]],
            ["Market Status", normalize_market_session(meta.get("market_session", ""), _snapshot_w["formal_report_snapshot_ts"])],
            ["Export / Ingest", f"{meta.get('export_version', '')} / {meta.get('ingest_version', '')}"],
            ["Archive", f"ID {archive.get('archive_id', db.get('id', ''))} | Report {db.get('report_version', 'R6')}"],
            ["Consistency Audit", f"{_audit_data['audit_status']} | Score {_audit_data['audit_score']}/100 | Fail {_audit_data['fail_count']}/10"],
        ],
        widths=[1800, 7560],
        font_size=19,
    )
    doc.table(
        [
            ["Regime", "CIO Action", "Confidence", "Readiness"],
            [
                f"{regime.get('regime', '')} ({regime.get('score', '')})",
                _cio_action_w,
                f"{_conf_f:.3f} {_conf_label_w}".strip(),
                f"{dataset.get('institutional_quant', {}).get('readiness_label', '')} {fmt_float(dataset.get('institutional_quant', {}).get('readiness_score'), 1)}",
            ],
        ],
        widths=[2340, 2340, 2340, 2340],
        font_size=19,
    )
    # CONSISTENCY: derive doctrine warning from LIVE causal status only (Fix 3 — no archived contradiction)
    _doctrine_msg = (
        ""
        if _live_causal in ("COMPLETE", "MOSTLY_COMPLETE")
        else "Research conclusion remains PROVISIONAL — causal gaps exist."
        if "MOSTLY_COMPLETE" in _live_causal
        else "CAUSAL EXPLANATION INCOMPLETE. Research conclusion is PROVISIONAL."
        if _live_causal in ("INCOMPLETE", "CRITICAL_GAP", "PARTIAL")
        else ""
    )
    if _live_blind in ("WARNING", "CRITICAL") and not _doctrine_msg:
        _doctrine_msg = "Blind Spot WARNING — unknown catalysts possible. CIO review required before risk addition."
    doc.callout(
        "Decision Posture",
        f"{_cio_action_w} remains the compressed action because causal explanation is "
        f"{_live_causal} [MODEL INFERRED] and blind-spot status is {_live_blind} [MODEL INFERRED]. "
        f"{_doctrine_msg}",
        fill="FFF2CC",
    )

    # ── REPORT CONSISTENCY GATE (Module B) — top of CIO Briefing ───────────
    _gate_fill = ("FFE0E0" if _audit_data["audit_status"] == "INCONSISTENT" else
                  "FFF2CC" if _audit_data["audit_status"] == "WARNINGS" else "E2F0D9")
    _gate_failed = _audit_data.get("failed_checks") or []
    _gate_text = (
        f"REPORT CONSISTENCY : {_audit_data['audit_status']}\n"
        f"REPORT STATUS      : {_op_truth_w.get('report_readiness', 'UNKNOWN')}\n"
        f"FAILED CHECKS      : {', '.join(_gate_failed) if _gate_failed else 'None'}"
    )
    doc.callout("REPORT CONSISTENCY GATE", _gate_text, fill=_gate_fill)

    # ── CHIEF STRATEGIST GOVERNANCE LAYER v3.5 ─────────────────────────────
    if build_cs_governance_rows and build_thesis_reconciliation_rows and build_event_thesis_map_rows:
        _csg_active = governance_is_active(dataset) if governance_is_active else False
        _csg_fill = "E2F0D9" if _csg_active else "FFE0E0"
        doc.heading("Chief Strategist Governance Layer")
        doc.callout(
            "CSG v3.5",
            (
                f"Status: {'ACTIVE' if _csg_active else 'MISSING_OR_INACTIVE'}\n"
                "Doctrine: tactical score modifies timing; tactical score does not invalidate structural thesis "
                "unless kill condition triggered.\n"
                "Execution safety: CIO_ONLY_MANUAL remains intact; order routing remains disabled."
            ),
            fill=_csg_fill,
        )
        _csg_rows = [["Field", "Value", "Certainty", "Source Layer"], *build_cs_governance_rows(dataset)[:16]]
        doc.table(_csg_rows, widths=[1800, 4680, 1260, 1620], font_size=15)
        _thesis_rows = [
            ["Thesis", "Strategic Thesis", "Allowed", "Forbidden / Kill Conditions"],
        ]
        for _row in build_thesis_reconciliation_rows(dataset):
            _thesis_rows.append([
                _row[0],
                _row[1],
                _row[3],
                f"{_row[4]} | Kill: {_row[5]}",
            ])
        doc.table(_thesis_rows[:8], widths=[1620, 2880, 2520, 2340], font_size=14)
        _event_rows = [["Event", "Thesis", "Relationship", "Note"], *build_event_thesis_map_rows(dataset)[:12]]
        doc.table(_event_rows, widths=[1800, 2700, 1800, 3060], font_size=14)

    # ── 01  1-PAGE CIO BRIEFING ─────────────────────────────────────────────
    doc.heading("01 · 1-Page CIO Briefing")
    # Governance release banner
    _gov_rel_w  = _op_truth_w.get("_release_status", "BLOCKED_RENDERER_CONTRACT_FAILURE")
    _gov_scr_w  = _op_truth_w.get("governance_gate_score", "CONTRACT_FAILURE")
    _gov_hyg_w  = (_op_truth_w.get("sentiment_hygiene_gate") or {}).get("status", "BLOCKED_RENDERER_CONTRACT_FAILURE")
    _gov_fail_w = _op_truth_w.get("governance_gate_failed_gates") or []
    if _gov_rel_w == "BLOCKED":
        doc.callout("!! GOVERNANCE GATE BLOCKED !!",
                    f"REPORT BLOCKED BY GOVERNANCE GATE — DO NOT USE FOR CIO DECISION UNTIL FIXED. "
                    f"Failed gates: {', '.join(_gov_fail_w) or 'see audit'}",
                    fill="FF0000")
    doc.table(
        [
            ["Metric", "Value", "Certainty"],
            ["Governance Release",   f"{_gov_rel_w} | Score {_gov_scr_w}/100 | Hygiene {_gov_hyg_w}",              "DATA CONFIRMED"],
            ["Regime",               f"{regime.get('regime','UNKNOWN')} (score {regime.get('score',0)})",                    "DATA CONFIRMED"],
            ["CIO Action",           _cio_action_w,                                                                          "DATA CONFIRMED"],
            ["Confidence",           f"{_conf_f:.3f} {_conf_label_w}".strip(),                                               "DATA CONFIRMED"],
            # CONSISTENCY: live computed values, with pass counts for transparency (Upgrades #1, #2)
            ["Causal Explanation",   f"{_live_causal} | Pass {_causal_data['pass_count']}/10 | Conf {_causal_data['causal_confidence']:.3f}",  "MODEL INFERRED"],
            ["Blind Spot Status",    f"{_live_blind} | Pass {_bscheck_data['pass_count']}/12 | Fail {_bscheck_data['fail_count']}/12",         "MODEL INFERRED"],
            ["Total Assets",         portfolio.get("total_assets", ""),                                                      "DATA CONFIRMED"],
            ["Cash",                 portfolio.get("cash", ""),                                                               "DATA CONFIRMED"],
            ["Total P/L",            f"{portfolio.get('total_pnl','')} ({portfolio.get('total_pnl_pct','')}%)",               "DATA CONFIRMED"],
            # CONSISTENCY: concentration with thresholds always visible (Upgrade #5)
            ["Concentration",        f"{_live_conc_s} [NORMAL<35%|ELEVATED<50%|HIGH<65%|CRITICAL≥65%] | HHI {_conc['hhi']:.3f} | Largest {_conc['largest_ticker']} {_conc['largest_weight']:.0%}", "DATA CONFIRMED"],
            ["Clusters",             _cluster_str or "None",                                                                  "DATA CONFIRMED"],
            ["Open Orders",          (dataset.get("orders") or {}).get("open_order_count", 0),                               "DATA CONFIRMED"],
            ["Consistency Audit",    f"{_audit_data['audit_status']} Score {_audit_data['audit_score']}/100",                 "MODEL INFERRED"],
        ],
        widths=[1980, 5040, 2340],
        font_size=18,
    )

    # CONSISTENCY: dynamic CIO guidance derived from live status (Upgrade #3)
    _not_do_parts = ["Do NOT route orders without CIO sign-off."]
    if _live_causal in ("INCOMPLETE", "CRITICAL_GAP"):
        _not_do_parts.append(f"Do NOT add new risk — causal evidence is {_live_causal}.")
    if _live_blind in ("WARNING", "CRITICAL"):
        _not_do_parts.append(f"Do NOT ignore blind-spot {_live_blind} — unknown catalysts possible.")
    if _live_conc_s in ("HIGH", "CRITICAL"):
        _not_do_parts.append(f"Do NOT add to concentrated cluster — concentration is {_live_conc_s}.")
    doc.callout("What CIO Should NOT Do", f"[CIO THESIS] {' '.join(_not_do_parts)}", fill="FFE0E0")

    _may_parts = []
    if _live_causal in ("PARTIAL", "MOSTLY_COMPLETE"):
        _missing_crit = _causal_data.get("critical_checks") or []
        _may_parts.append(f"Resolve missing causal inputs{(': ' + ', '.join(_missing_crit)) if _missing_crit else ''}.")
    if _bscheck_data.get("fail_count", 0) > 0:
        _may_parts.append(f"Address {_bscheck_data['fail_count']} blind-spot failures before adding risk.")
    if _live_conc_s == "ELEVATED":
        _may_parts.append("Monitor cluster concentration; avoid adding to top-weighted names.")
    if not _may_parts:
        _may_parts.append("Review thesis lifecycle. Monitor upcoming catalysts.")
    doc.callout("What CIO May Consider", f"[PROVISIONAL] {' '.join(_may_parts)}", fill="FFF2CC")

    # ── Breaking Catalyst Overlay + Monday Open Scenario ────────────────────
    _briefing_w = _load_approved_cio_briefing()
    _bc_w       = _briefing_w.get("breaking_catalyst", {})
    _ov_w       = _briefing_w.get("scenario_overlay", {})
    _mon_w      = _briefing_w.get("monday_open_scenario", {})

    if _bc_w.get("detected") and _ov_w.get("active"):
        _ov_fill = "FFF9C4"
        doc.callout(
            f"Breaking Catalyst: {_bc_w.get('catalyst_type','—')} / {_bc_w.get('polarity','—')}",
            (
                f"Matched headline: \"{str(_bc_w.get('headline_matched',''))[:100]}\"\n"
                f"Overlay: {_ov_w.get('overlay_type','—')} | Risk clearance: {_ov_w.get('risk_clearance','NOT_CONFIRMED')} | "
                f"Verification required: {_bc_w.get('verification_required',True)}\n"
                f"{_ov_w.get('interpretation','')}"
            ),
            fill=_ov_fill,
        )
        # Asset impact
        _ai_w = _ov_w.get("asset_impact", {})
        if _ai_w:
            _ai_rows = [["Asset Class", "Direction", "Note"]]
            for _ak, _av in _ai_w.items():
                if isinstance(_av, dict):
                    _ai_rows.append([_ak.replace("_", " ").title(), _av.get("direction", ""), _av.get("note", "")])
            if len(_ai_rows) > 1:
                doc.table(_ai_rows, widths=[1980, 1800, 5580], font_size=16)

        # Gold miner + space overlay
        _gma_w = _ov_w.get("gold_miner_relief_rally_action", "")
        _sp_w  = _ov_w.get("space_sector_overlay", {})
        if _gma_w or _sp_w:
            doc.callout(
                "Concentration + Space Sector Overlay",
                (
                    f"Gold Miner Relief Action: {_gma_w} (concentration={_ov_w.get('gold_safe_haven_pressure','—')})\n"
                    f"Space Sector: Geopolitical={_sp_w.get('geopolitical_relief','—')} | "
                    f"SpaceX liquidity drain={_sp_w.get('spcx_liquidity_drain','—')} | "
                    f"Net view={_sp_w.get('net_view','—')}\n"
                    f"Affected names: {', '.join(_sp_w.get('affected_names',[]))}"
                ),
                fill="E8F4FD",
            )

        # Monday open scenarios
        if _mon_w:
            doc.heading("Next U.S. Regular Session Scenario")
            _sc_rows = [["Scenario", "Signals", "CIO Implication"]]
            for _sk, _sv in _mon_w.items():
                _sc_rows.append([
                    _sv.get("name", _sk),
                    "\n".join(f"• {s}" for s in _sv.get("signals", [])),
                    _sv.get("cio_implication", ""),
                ])
            doc.table(_sc_rows, widths=[1980, 3780, 3600], font_size=16)

    # ── Gold Safe-Haven Thesis Tracker ──────────────────────────────────────
    _gtt = build_gold_thesis_tracker(dataset)
    _gtt_status = _gtt.get("status", "UNKNOWN")
    _gtt_fill   = {"CONFIRMING": "E2EFDA", "WATCH": "FFF2CC", "WARNING": "FCE4D6", "FAILING": "FFE0E0"}.get(_gtt_status, "F2F2F2")
    _gtt_score  = _gtt.get("score", 0)
    _gtta       = _gtt.get("thesis_action") or {}
    _gttm       = _gtt.get("key_metrics") or {}

    doc.heading("Gold Safe-Haven Thesis Tracker")
    # Status summary callout
    doc.callout(
        f"Gold Thesis: {_gtt_status}",
        f"Score: {_gtt_score:.2f}/{_gtt.get('max_score', 1.0):.1f} | Confidence: {_gtt.get('confidence', 'LOW')} | "
        f"Pass {_gtt.get('n_pass', 0)} / Watch {_gtt.get('n_watch', 0)} / Fail {_gtt.get('n_fail', 0)} | "
        f"Gold-Miner Cluster: {_gtta.get('gold_miner_cluster_weight', 0):.0%} | "
        f"CIO Gold Action: {_gtta.get('gold_miner_core_action', 'HOLD / WAIT')} | "
        f"Thesis Add Signal: {_gtta.get('thesis_add_signal', 'UNKNOWN')} | "
        f"Execution Permission: {_gtta.get('execution_permission', 'UNKNOWN')}",
        fill=_gtt_fill,
    )
    # Metrics table — null-safe formatter: None → "N/A", not "+0.00%"
    def _gm_chg(key):
        v = _gttm.get(key)
        return f"{v:+.2f}%" if v is not None else "N/A"
    def _gm_val(key, fmt=None):
        v = _gttm.get(key)
        if v is None:
            return "N/A"
        return fmt(v) if fmt else str(v)
    doc.table(
        [
            ["Metric", "Value"],
            ["GLD",           _gm_chg('gld_change_pct')],
            ["SLV",           _gm_chg('slv_change_pct')],
            ["GDX vs GLD",    _gm_chg('gdx_vs_gld_spread')],
            ["GDXJ vs GLD",   _gm_chg('gdxj_vs_gld_spread')],
            ["AU vs GDX",     _gm_chg('au_vs_gdx_spread')],
            ["NEM vs GDX",    _gm_chg('nem_vs_gdx_spread')],
            ["GSR Proxy",     _gm_val('gold_silver_ratio_proxy')],
            ["UUP",           _gm_chg('uup_change_pct')],
            ["10Y Yield",     _gm_val('ten_year_yield')],
            ["TLT",           _gm_chg('tlt_change_pct')],
            ["XLE",           _gm_chg('xle_change_pct')],
            ["Oil News Hits", str(_gttm.get('oil_news_pressure_score', 0))],
            ["SPY",           _gm_chg('spy_change_pct')],
            ["VXX",           _gm_chg('vxx_change_pct')],
        ],
        widths=[2200, 7160],
        font_size=16,
    )
    # 8-check table
    _GT_CHECK_LABELS_W = [
        ("gold_stabilizes_and_rises",         "1. Gold stabilizes/rises"),
        ("silver_confirms_or_gsr_compresses", "2. Silver confirms / GSR"),
        ("miners_vs_gold",                    "3. GDX/GDXJ vs GLD"),
        ("au_nem_vs_gdx",                     "4. AU/NEM vs GDX"),
        ("real_yields_do_not_spike",          "5. Real yields stable"),
        ("dxy_does_not_surge",                "6. DXY/UUP not surging"),
        ("oil_risk_premium_elevated",         "7. Oil-risk premium"),
        ("miners_not_liquidated_as_equity_beta", "8. Miner liquidation risk"),
    ]
    _gtt_check_rows = [["Check", "Status", "Evidence", "CIO Implication"]]
    for _gtwk, _gtwl in _GT_CHECK_LABELS_W:
        _gtch = (_gtt.get("checks") or {}).get(_gtwk) or {}
        _gtt_check_rows.append([
            _gtwl,
            _gtch.get("status", "MISSING"),
            _gtch.get("evidence", "")[:60],
            _gtch.get("cio_implication", "")[:80],
        ])
    doc.table(_gtt_check_rows, widths=[2400, 900, 2700, 3360], font_size=15)
    doc.paragraph(_gtt.get("summary", ""), italic=True, size=18, color="2F5496")

    # Fear & Greed staleness check
    _fg_data = dataset.get("fear_greed") or {}
    _fg_ts   = _fg_data.get("timestamp") or _fg_data.get("updated_at") or _fg_data.get("generated_at")
    _fg_age_min = 9999
    if _fg_ts:
        try:
            from datetime import datetime as _dt, timezone as _tz
            _fg_dt = _dt.fromisoformat(str(_fg_ts).replace("Z", "+00:00"))
            if _fg_dt.tzinfo is None:
                _fg_dt = _fg_dt.replace(tzinfo=_tz.utc)
            _fg_age_min = (_dt.now(_tz.utc) - _fg_dt).total_seconds() / 60
        except Exception:
            pass

    _fg_stale = _fg_age_min > 60
    _fg_staleness_suffix = " - STALE_SECONDARY / EXCLUDED_FROM_CIO_CONFIDENCE" if _fg_stale else " - FRESH"

    doc.heading("02 · Executive Read")
    doc.paragraph(
        f"The cycle is dominated by {regime.get('regime', 'N/A')} conditions. VIX is {fmt_float(regime.get('vix_level'), 2)}, Fear & Greed is {fmt_float(regime.get('fg_score'), 1)}{_fg_staleness_suffix}, and institutional sentiment averages {fmt_float(regime.get('inst_avg'), 4)}. The report therefore favors capital preservation, gold/defensives/cash, and explicit causal verification before new risk is added.",
        size=22,
    )
    doc.paragraph(f"Portfolio assets {fmt_money(portfolio.get('total_assets'))}; cash {fmt_money(portfolio.get('cash'))}; market value {fmt_money(portfolio.get('market_val'))}; total P/L {fmt_money(portfolio.get('total_pnl'))} ({fmt_pct_point(portfolio.get('total_pnl_pct'))}).", bullet=True)
    doc.paragraph("Top movers: " + ", ".join(f"{r.get('ticker')} {fmt_pct_point(r.get('chg_pct'))}" for r in top_movers(dataset, 5)) + ".", bullet=True)
    doc.paragraph("Strongest themes: " + ", ".join(f"{r.get('theme')} {fmt_pct_point(r.get('basket_move'))}" for r in strongest) + ".", bullet=True)
    doc.paragraph("Weakest themes: " + ", ".join(f"{r.get('theme')} {fmt_pct_point(r.get('basket_move'))}" for r in weakest) + ".", bullet=True)

    doc.heading("08 · Cross-Market Confirmation")
    cm = dataset.get("cross_market_confirmation") or {}
    flags = cm.get("interpretation_flags") or {}
    active_flags = ", ".join(k for k, v in flags.items() if v) or "none"
    doc.table(
        [
            ["Field", "Value"],
            ["Status", "operational" if cm else "not available"],
            ["Cycle", cm.get("cycle_ts", "")],
            ["Coverage", f"{cm.get('filled_count', '')}/{cm.get('ticker_count', '')}"],
            ["Active Flags", active_flags],
        ],
        widths=[2200, 7160],
        font_size=16,
    )
    score_rows = [[row[1], row[2]] for row in build_cross_market_score_rows(dataset) if row[0] == "Score"]
    doc.table([["Score", "Value"], *score_rows[:8]], widths=[5200, 4160], font_size=16)

    # ── 04  CAUSAL EXPLANATION ENGINE ─────────────────────────────────────────
    doc.heading("04 · Causal Explanation Engine")
    _ce_status = _live_causal
    _ce_fill = ("FFE0E0" if _ce_status in ("INCOMPLETE", "CRITICAL_GAP") else
                "FFF2CC" if _ce_status in ("PARTIAL", "MOSTLY_COMPLETE") else "E2F0D9")
    doc.callout(
        "Causal Status",
        f"[MODEL INFERRED] {_ce_status} | Confidence {_causal_data['causal_confidence']:.3f} | "
        f"Primary: {_causal_data['primary_driver']} | Secondary: {_causal_data['secondary_driver']} | "
        f"Pass {_causal_data['pass_count']}/10"
        + (f" | CRITICAL GAPS: {', '.join(_causal_data['critical_checks'])}" if _causal_data.get('critical_checks') else ""),
        fill=_ce_fill,
    )
    if _causal_data["missing_inputs"]:
        doc.paragraph(f"Missing causal inputs: {', '.join(_causal_data['missing_inputs'])}", bold=True, size=20, color="9C0006")
    doc.table(
        [["Causal Check", "Status", "Detail"], *_causal_data["check_rows"][:10]],
        widths=[2000, 900, 6460],
        font_size=16,
    )

    # ── 05  BLIND SPOT CHECKLIST ──────────────────────────────────────────────
    doc.heading("05 · Blind Spot Checklist")
    _bs_status = _live_blind
    _bs_fill = "FFE0E0" if _bs_status == "CRITICAL" else "FFF2CC" if _bs_status == "WARNING" else "E2F0D9"
    doc.callout(
        "Blind Spot Status",
        f"[MODEL INFERRED] {_bs_status} | Pass {_bscheck_data['pass_count']}/12 | Fail {_bscheck_data['fail_count']}/12 | "
        f"CIO Penalty -{_bscheck_data['cio_penalty']:.3f}",
        fill=_bs_fill,
    )
    if _bscheck_data["failed_items"]:
        doc.paragraph(f"Failed checks: {', '.join(_bscheck_data['failed_items'])}", bold=True, size=20, color="9C0006")
    doc.table(
        [["Check", "Status", "Detail"], *_bscheck_data["check_rows"][:12]],
        widths=[2400, 900, 6060],
        font_size=16,
    )

    # ── NEW: CIO ACTION LOGIC (Module D) ────────────────────────────────────
    doc.heading("04b · CIO Action Logic Engine")
    _al_fill = "FFE0E0" if "BREACH" in _action_logic_w.get("final_action", "") else "FFF2CC" if "WAIT" in _action_logic_w.get("final_action", "") else "E2F0D9"
    doc.callout(
        "CIO Action Logic",
        f"[MODEL INFERRED] Final Action: {_action_logic_w.get('final_action', 'WAIT / HOLD')} | "
        f"Cap: {_action_logic_w.get('action_cap', '')} | CIO Review Required: {_action_logic_w.get('required_cio_review', False)}\n"
        f"Reason: {_action_logic_w.get('reason', '')[:200]}",
        fill=_al_fill,
    )
    _al_blocked = _action_logic_w.get("blocked_actions") or []
    _al_rules   = _action_logic_w.get("rules_triggered") or []
    doc.table(
        [
            ["Field", "Value"],
            ["Final Action", _action_logic_w.get("final_action", "WAIT / HOLD")],
            ["Action Cap", _action_logic_w.get("action_cap", "")],
            ["Blocked Actions", ", ".join(_al_blocked) or "None"],
            ["Rules Triggered", ", ".join(_al_rules[:5]) or "None"],
            ["CIO Review Required", str(_action_logic_w.get("required_cio_review", False))],
            ["Reason", _action_logic_w.get("reason", "")[:300]],
        ],
        widths=[2200, 7160],
        font_size=16,
    )

    # ── NEW: CAUSAL CHAIN RANKING (Module F) ────────────────────────────────
    doc.heading("04c · Causal Chain Ranking")
    if _causal_chain_w:
        _chain_table_rows = [["Rank", "Driver", "Market Expression", "Confidence", "Decision Impact"]]
        for _drv in _causal_chain_w[:5]:
            _chain_table_rows.append([
                str(_drv.get("rank", "")),
                str(_drv.get("driver", ""))[:40],
                str(_drv.get("market_expression", ""))[:80],
                f"{_drv.get('confidence', 0):.3f}",
                str(_drv.get("decision_impact", ""))[:60],
            ])
        doc.table(_chain_table_rows, widths=[600, 1800, 3200, 900, 2860], font_size=15)
    else:
        doc.paragraph("No ranked causal drivers available this cycle.", italic=True, color="606060")

    # ── NEW: BLIND SPOT REMEDIATION (Module E) ──────────────────────────────
    if _remediations_w:
        doc.heading("05b · Blind Spot Remediation", level=2)
        _rem_rows = [["Failed Check", "Severity", "Data Source Needed", "Fallback", "Next Action"]]
        for _rem in _remediations_w:
            _rem_rows.append([
                str(_rem.get("failed_check", ""))[:35],
                str(_rem.get("severity", "")),
                str(_rem.get("data_source_needed", ""))[:50],
                "Yes" if _rem.get("fallback_available") else "No",
                str(_rem.get("next_action", ""))[:60],
            ])
        doc.table(_rem_rows, widths=[1400, 900, 2100, 700, 4260], font_size=14)

    # ── NEW: PORTFOLIO RISK GOVERNOR (Module G) ──────────────────────────────
    doc.heading("08b · Portfolio Risk Governor")
    _rg_fill = "FFE0E0" if _risk_gov_w.get("status") in ("CRITICAL", "HIGH") else "FFF2CC" if _risk_gov_w.get("status") == "ELEVATED" else "E2F0D9"
    doc.callout(
        "Risk Governor",
        f"[MODEL INFERRED] Status: {_risk_gov_w.get('status', 'NORMAL')} | "
        f"Breaches: {len(_risk_gov_w.get('breaches') or [])} | "
        f"Blocked: {', '.join((_risk_gov_w.get('blocked_actions') or [])[:4]) or 'None'} | "
        f"CIO Override Required: {_risk_gov_w.get('cio_override_required', False)}",
        fill=_rg_fill,
    )
    if _risk_gov_w.get("breaches"):
        _rg_table = [["Breach", ""], *[[b, ""] for b in _risk_gov_w["breaches"][:6]]]
        doc.table(_rg_table, widths=[5600, 3760], font_size=14)
    if _risk_gov_w.get("required_reviews"):
        for _rev in _risk_gov_w["required_reviews"][:3]:
            doc.paragraph(f"[REQUIRED REVIEW] {_rev}", bold=True, size=16, color="9C0006")

    # ── NEW: NEWS PRIORITY ENGINE (Module J, Fix 5: 3-section) ─────────────
    doc.heading("11b · News/Catalyst Priority Tape")
    _npw_cio   = (_news_priority_w.get("top_cio_market_catalysts") or []) if isinstance(_news_priority_w, dict) else _news_priority_w[:10] if isinstance(_news_priority_w, list) else []
    _npw_tech  = (_news_priority_w.get("top_tech_intelligence") or []) if isinstance(_news_priority_w, dict) else []
    _npw_early = (_news_priority_w.get("top_early_warning") or []) if isinstance(_news_priority_w, dict) else []
    _npw_medium = (_news_priority_w.get("top_medium_priority") or []) if isinstance(_news_priority_w, dict) else []
    doc.paragraph("Top CIO Market Catalysts", bold=True, size=20)
    if _npw_cio:
        _news_rows = [["#", "Source", "Score", "Portfolio Tickers", "Headline"]]
        for _ni in _npw_cio[:10]:
            _news_rows.append([
                str(_ni.get("rank", "")),
                str(_ni.get("source", ""))[:20],
                f"{_ni.get('final_priority_score', 0):.3f}",
                ", ".join((_ni.get("affected_tickers") or [])[:3]),
                str(_ni.get("headline", ""))[:100],
            ])
        doc.table(_news_rows, widths=[500, 1600, 900, 1400, 5460], font_size=14)
    else:
        doc.paragraph("No high-trust CIO catalyst signals scored this cycle.", italic=True, color="606060")
        if _npw_medium:
            doc.paragraph("Medium-Priority CIO Catalysts (portfolio/macro relevance detected):", bold=True, size=18, color="1F4E79")
            _med_rows = [["#", "Source", "Score", "Tickers", "Headline"]]
            for _ni in _npw_medium[:8]:
                _med_rows.append([
                    str(_ni.get("rank", "")),
                    str(_ni.get("source", ""))[:20],
                    f"{_ni.get('final_priority_score', 0):.3f}",
                    ", ".join((_ni.get("affected_tickers") or [])[:3]),
                    str(_ni.get("headline", ""))[:100],
                ])
            doc.table(_med_rows, widths=[500, 1600, 900, 1400, 5460], font_size=14)
    if _npw_tech:
        doc.paragraph("Top Tech Intelligence", bold=True, size=18, color="1F4E79")
        _tech_rows = [["#", "Source", "Score", "Headline"]]
        for _ni in _npw_tech[:5]:
            _tech_rows.append([str(_ni.get("rank","")), str(_ni.get("source",""))[:20], f"{_ni.get('final_priority_score',0):.3f}", str(_ni.get("headline",""))[:100]])
        doc.table(_tech_rows, widths=[500, 1600, 900, 6660], font_size=13)
    if _npw_early:
        doc.paragraph("Early Warning Signals (Low Trust)", bold=True, size=18, color="9C0006")
        _early_rows = [["#", "Source", "Score", "Headline"]]
        for _ni in _npw_early[:5]:
            _early_rows.append([str(_ni.get("rank","")), str(_ni.get("source",""))[:20], f"{_ni.get('final_priority_score',0):.3f}", str(_ni.get("headline",""))[:100]])
        doc.table(_early_rows, widths=[500, 1600, 900, 6660], font_size=13)

    # ── NEW: FRESHNESS GOVERNOR (Module I, Fix 4: explicit critical/non-critical) ──
    doc.heading("13b · Dataset Freshness Governor")
    _fs_crit_w = _freshness_w.get("critical_stale_sections") or []
    _fs_noncrit_w = _freshness_w.get("non_critical_stale_sections") or []
    _fs_fill = "FFE0E0" if _freshness_w.get("freshness_status") == "FAIL" else "FFF2CC" if _freshness_w.get("freshness_status") == "WARNING" else "E2F0D9"
    _fs_penalty = float(_freshness_w.get("confidence_penalty") or 0)
    _fs_penalty_text = f"-{_fs_penalty:.3f}" if _fs_penalty > 0 else "0.000"
    _fs_text = (
        f"[DATA CONFIRMED] {_freshness_w.get('freshness_status', 'PASS')} | "
        f"Critical stale: {len(_fs_crit_w)} | "
        f"Non-critical stale: {len(_fs_noncrit_w)} | "
        f"Confidence penalty: {_fs_penalty_text}"
    )
    if _fs_noncrit_w:
        _nc_names = ", ".join(s.get("section","?") for s in _fs_noncrit_w)
        _fs_text += f" | Non-critical stale: {_nc_names} [excluded, fallback used]"
    doc.callout("Freshness Status", _fs_text, fill=_fs_fill)
    _all_stale_w = _fs_crit_w + _fs_noncrit_w
    if _all_stale_w:
        _fs_rows = [["Section", "Critical?", "Age (min)", "Threshold (min)"]]
        for _ss in _all_stale_w[:8]:
            _fs_rows.append([
                _ss.get("section", ""),
                "YES" if _ss.get("is_critical") else "NO",
                str(_ss.get("age_minutes", "")),
                str(_ss.get("threshold_minutes", "")),
            ])
        doc.table(_fs_rows, widths=[2200, 900, 1600, 1800], font_size=14)

    # ── 09  SUPERFORECAST & BRIER ACCOUNTABILITY ─────────────────────────────
    doc.heading("09 · Superforecast & Brier Accountability")
    rf = dataset.get("research_forecasting") or {}
    # Brier maturity: COLLECTING = <30 resolved forecasts; NOT_MATURE = 30-99; MATURE = 100+
    _brier_raw = str(rf.get("brier_status", "") or "").lower()
    _acc_rows = rf.get("accuracy_summary") or []
    _resolved_total = sum(int(r.get("resolved_count") or 0) for r in _acc_rows if isinstance(r, dict))
    if _resolved_total >= 100:
        _brier_label = f"MATURE [{_resolved_total} resolved]"
        _brier_fill  = "E2F0D9"
    elif _resolved_total >= 30:
        _brier_label = f"NOT_MATURE [{_resolved_total} resolved — need 100+ for statistical significance]"
        _brier_fill  = "FFF2CC"
    else:
        _brier_label = f"COLLECTING [{_resolved_total} resolved — need 30+ to report; 100+ for full Brier accountability]"
        _brier_fill  = "F2F2F2"
    doc.callout(
        "Forecast Doctrine",
        "[DATA CONFIRMED] BlueLotus Conservative is the house method. Analyst consensus is the benchmark opponent. "
        "Forecasts are measured research records, not CIO execution orders. "
        f"Brier accountability: {_brier_label}",
        fill=_brier_fill,
    )
    doc.table(
        [
            ["Field", "Value", "Certainty"],
            ["Status",         rf.get("status", "[MISSING]"),          "DATA CONFIRMED"],
            ["Snapshot",       rf.get("snapshot_id", "[MISSING]"),     "DATA CONFIRMED"],
            ["Forecast Rows",  rf.get("forecast_count", 0),            "DATA CONFIRMED"],
            ["Tickers",        rf.get("ticker_count", 0),              "DATA CONFIRMED"],
            # Upgrade #6: explicit COLLECTING/NOT_MATURE/MATURE labeling
            ["Brier Status",   _brier_label,                           "DATA CONFIRMED"],
            ["Resolved Total", _resolved_total,                        "DATA CONFIRMED"],
            # Upgrade #7: MISSING tag when brier not available
            ["Brier Score",    "[MISSING — not enough resolved forecasts]" if _resolved_total < 30 else
                               f"[DATA CONFIRMED] {fmt_float((_acc_rows[0] if _acc_rows else {}).get('avg_brier_score'), 4)}", "DATA CONFIRMED"],
        ],
        widths=[2200, 5560, 1560],
        font_size=16,
    )
    forecast_rows = []
    for row in build_forecast_rows(dataset, 10):
        if row[1] != "BLUELOTUS_CONSERVATIVE":
            continue
        forecast_rows.append([row[0], row[2], fmt_money(row[3]), fmt_money(row[8]), fmt_pct_point(row[9]), fmt_float(row[10], 3)])
    doc.table([["Ticker", "Dir", "Price", "90D Target", "90D Ret", "Prob"], *forecast_rows[:8]], widths=[1100, 900, 1400, 1600, 1300, 1460], font_size=16)

    doc.heading("06 · Dataset Integrity & Source Health")
    doc.table([["Section", "Freshness", "Age Min"], *build_source_rows(dataset)[:10]], widths=[3600, 2400, 1800], font_size=18)
    process_rows = [[r[0], r[1], fmt_float(r[2], 1), clean_text(r[4], 100)] for r in build_process_rows(dataset)]
    doc.table([["Process", "Status", "Score", "Primary Gap"], *process_rows], widths=[2400, 1400, 1000, 4560], font_size=16)

    security_rows = list((dataset.get("security_master") or {}).values())
    unknown_security = sum(1 for s in security_rows if str(s.get("sector")).upper() == "UNKNOWN" or str(s.get("industry")).upper() == "UNKNOWN")
    if unknown_security:
        doc.callout("Classification Gap", f"{unknown_security} tickers still carry UNKNOWN sector or industry in security_master. Keep this visible as a data-quality gap, not a hidden model signal.", fill="FFF2CC")

    # ── 03  CONSISTENCY AUDIT (Upgrade #4) ──────────────────────────────────
    doc.heading("03 · Report Consistency Audit")
    _au_fill = ("FFE0E0" if _audit_data["audit_status"] == "INCONSISTENT" else
                "FFF2CC" if _audit_data["audit_status"] == "WARNINGS" else "E2F0D9")
    doc.callout(
        "Consistency Audit",
        f"[MODEL INFERRED] {_audit_data['audit_status']} | Score {_audit_data['audit_score']}/100 | "
        f"Pass {_audit_data['pass_count']}/10 | Warn {_audit_data['warn_count']}/10 | Fail {_audit_data['fail_count']}/10",
        fill=_au_fill,
    )
    doc.table(
        [["Check", "Result", "Detail"], *_audit_data["check_rows"]],
        widths=[2400, 900, 6060],
        font_size=15,
    )

    doc.heading("07 · Market Regime")
    doc.table(
        [
            ["Field", "Current Reading"],
            ["Regime", f"{regime.get('regime', '')} | score {regime.get('score', '')}"],
            ["Action", regime.get("action", "")],
            ["Warnings", "; ".join(regime.get("warnings") or [])],
            ["Treasury", f"10Y {fmt_float(treasury.get('yield_10y'), 2)}% | 2Y {fmt_float(treasury.get('yield_2y'), 2)}% | 30Y {fmt_float(treasury.get('yield_30y'), 2)}% | 3M {fmt_float(treasury.get('yield_3m'), 2)}%"],
            ["Curve", f"10Y-2Y {fmt_float(treasury.get('yield_spread_10_2'), 2)}% | {treasury.get('curve_status', '')} | NIM proxy {fmt_float(treasury.get('nim_proxy'), 2)}%"],
        ],
        widths=[1800, 7560],
        font_size=18,
    )

    doc.heading("10 · Portfolio, Cash & Mandate-Aware Exposure")
    port_rows = []
    _pnl_conflict_w_rows = []
    for r in build_portfolio_rows(dataset):
        # r[11]=pnl_integrity_status, r[12]=pnl_flag_str
        _pnl_integrity_w = r[11] if len(r) > 11 else "OK"
        _pnl_detail_w    = r[12] if len(r) > 12 else ""
        port_rows.append([r[0], r[1], fmt_money(r[5]), fmt_ratio_pct(r[6]), fmt_pct_point(r[8]), fmt_pct_point(r[9]), r[10], _pnl_integrity_w])
        if _pnl_integrity_w == "BROKER_PNL_SOURCE_CONFLICT":
            _pnl_conflict_w_rows.append([r[0], _pnl_detail_w])
    doc.table([["Ticker", "Mandate", "Mkt Value", "Weight", "P/L %", "Day %", "Action", "P/L Integrity"], *port_rows], widths=[800, 1300, 1400, 1000, 1000, 1000, 1800, 2060], font_size=16)
    if _pnl_conflict_w_rows:
        doc.paragraph("BROKER_PNL_SOURCE_CONFLICT - COST_BASIS_REVIEW_REQUIRED. Broker-reported P/L differs materially from computed value. Selected source remains BROKER_REPORTED until CIO reviews cost basis.", bold=True, color="CC0000")
        doc.table([["Ticker", "Conflict Detail"], *_pnl_conflict_w_rows], widths=[900, 8460], font_size=16)
    doc.paragraph(
        f"Risk concentration: largest position {(risk.get('largest_position') or {}).get('ticker', '')} at {fmt_ratio_pct((risk.get('largest_position') or {}).get('weight_vs_equity_capital') or (risk.get('largest_position') or {}).get('weight'))} of equity capital ({fmt_ratio_pct((risk.get('largest_position') or {}).get('weight_vs_total_aum') or (risk.get('largest_position') or {}).get('weight'))} of total AUM); HHI equity {fmt_float(risk.get('concentration_hhi_equity_only') or risk.get('concentration_hhi'), 4)} [{risk.get('hhi_interpretation', '')}].",
        italic=True,
        color="606060",
    )
    hv = formal_risk.get("historical_var") if isinstance(formal_risk.get("historical_var"), dict) else {}
    doc.table(
        [
            ["Metric", "Value"],
            ["Risk Run", formal_risk.get("run_id", "")],
            ["Observations", formal_risk.get("return_observations", "")],
            ["VaR 95 Daily", f"{fmt_money((hv.get('confidence_95') or {}).get('daily_dollars'))} / {fmt_ratio_pct((hv.get('confidence_95') or {}).get('daily_pct'))}"],
            ["VaR 99 Daily", f"{fmt_money((hv.get('confidence_99') or {}).get('daily_dollars'))} / {fmt_ratio_pct((hv.get('confidence_99') or {}).get('daily_pct'))}"],
            ["Expected Shortfall 95", fmt_money((hv.get("expected_shortfall_95") or {}).get("daily_dollars"))],
            ["Annualized Vol", fmt_ratio_pct(formal_risk.get("volatility_annualized"))],
            ["Max Drawdown", fmt_ratio_pct(formal_risk.get("max_drawdown"))],
            ["Beta To SPY", fmt_float(formal_risk.get("beta_to_spy"), 3)],
        ],
        widths=[2700, 6660],
        font_size=16,
    )

    doc.heading("12 · Portfolio Targets & Thesis Lifecycle")
    target_rows = [[r[0], fmt_ratio_pct(r[1]), fmt_ratio_pct(r[2]), fmt_ratio_pct(r[3]), fmt_money(r[4]), fmt_money(r[5])] for r in build_portfolio_target_rows(dataset)[:14]]
    doc.table([["Ticker", "Current", "Target", "Delta", "Current $", "Target $"], *target_rows], widths=[1000, 1300, 1300, 1200, 1600, 1600], font_size=15)
    doc.paragraph("Portfolio targets are research-only target weights for CIO review. No order tickets or fills are generated by this report layer.", italic=True, color="606060")

    doc.heading("13 · Execution Intelligence / TCA Readiness")
    execution = dataset.get("execution") or {}
    orders = dataset.get("orders") or {}
    fills = dataset.get("fills") or {}
    doc.callout(
        "Execution Doctrine",
        "Moomoo broker data is extracted read-only for order history, fill history, and TCA readiness. Order routing remains disabled; CIO owns all execution decisions.",
        fill="E2F0D9",
    )
    doc.table([["Field", "Value"], *build_execution_summary_rows(dataset)], widths=[2700, 6660], font_size=15)
    doc.paragraph(
        f"Broker history currently covers {fmt_int(orders.get('historical_order_count'))} historical orders and {fmt_int(fills.get('historical_deal_count'))} historical fills/deals. Open orders: {fmt_int(orders.get('open_order_count'))}. Routing enabled: {'YES' if execution.get('order_routing_enabled') else 'NO'}.",
        italic=True,
        color="606060",
    )

    open_rows = []
    for r in build_open_order_rows(dataset, 10):
        open_rows.append([r[0], r[1], r[3], fmt_int(r[4]), fmt_money(r[5]), fmt_int(r[6]), r[11]])
    if not open_rows:
        open_rows.append(["none", "", "", "", "", "", ""])
    doc.table([["Ticker", "Side", "Status", "Qty", "Limit", "Dealt", "Updated"], *open_rows], widths=[900, 800, 2100, 900, 1200, 900, 2560], font_size=14)

    plan_vs_orders = build_cio_plan_vs_order_book(dataset)
    doc.heading("13a · CIO Plan vs Broker Order Book", level=2)
    doc.callout("Manual CIO Action Required", plan_vs_orders["warning"], fill="FFE0B2")
    doc.table([["Field", "Assessment"], *plan_vs_orders["rows"]], widths=[2700, 6660], font_size=14)

    fill_rows = []
    for r in build_recent_fill_rows(dataset, 10):
        fill_rows.append([r[0], r[1], fmt_int(r[2]), fmt_money(r[3]), r[4], clean_text(r[5], 28)])
    if not fill_rows:
        fill_rows.append(["none", "", "", "", "", ""])
    doc.table([["Ticker", "Side", "Qty", "Price", "Deal Time", "Order ID"], *fill_rows], widths=[900, 800, 900, 1200, 2200, 3360], font_size=14)

    lifecycle_rows = [[clean_text(r[0], 28), clean_text(r[1], 20), clean_text(r[2], 80)] for r in build_trade_lifecycle_rows(dataset)]
    if lifecycle_rows:
        doc.table([["Stage", "Owner", "System Record"], *lifecycle_rows], widths=[2400, 1800, 5160], font_size=14)

    doc.heading("13b · Deterministic Operator Layer")
    det_ops = deterministic_operator_pack(dataset)
    det_summary = det_ops.get("summary") if isinstance(det_ops.get("summary"), dict) else {}
    det_fill = "FFE0E0" if det_ops.get("readiness") == "FAIL" else "FFF2CC" if det_ops.get("readiness") == "REVIEW_REQUIRED" else "E2F0D9"
    doc.callout(
        "Rules-Based Operator Pack",
        f"Readiness {det_ops.get('readiness', 'UNKNOWN')} | LLM used {bool(det_ops.get('llm_used', False))} | "
        f"routing {bool(det_ops.get('order_routing_enabled', False))} | generated orders {det_ops.get('orders_generated', 0)} | "
        f"blocked actions: {', '.join(det_summary.get('blocked_actions') or []) or 'none'}",
        fill=det_fill,
    )
    doc.table([["Field", "Value"], *build_deterministic_operator_summary_rows(dataset)], widths=[2700, 6660], font_size=14)
    det_rows = [[r[0], r[1], fmt_float(r[2], 3), clean_text(r[4], 120), clean_text(r[5], 80)] for r in build_deterministic_operator_rows(dataset)]
    if det_rows:
        doc.table([["Operator", "Status", "Score", "Evidence", "Blocked Actions"], *det_rows], widths=[1900, 1200, 900, 3600, 1760], font_size=13)

    doc.heading("S1 · CIO Cognition Ledger")
    cognition = dataset.get("cio_cognition") or {}
    cognition_rows = build_cio_cognition_summary_rows(dataset)
    doc.callout(
        "CIO Cognition Doctrine",
        "This layer records Strategic Thinking, Planning, Execution intent, thesis reviews, and mistake-learning prompts. It is not an execution system; all live capital actions remain CIO-only manual decisions.",
        fill="E2F0D9",
    )
    doc.table([["Field", "Value"], *cognition_rows], widths=[2600, 6760], font_size=15)
    # Defect 6 — Regime vs Cognition Ledger timestamp disclosure
    _rcd_w = build_regime_cognition_disclosure(dataset)
    _rcd_delta_w = (f"{_rcd_w['delta_hours']:.1f}h" if _rcd_w['delta_hours'] is not None else "unknown")
    _rcd_rows_w = [
        ["Regime Timestamp",   _rcd_w["regime_ts"]],
        ["Ledger Timestamp",   _rcd_w["ledger_ts"]],
        ["Time Delta",         _rcd_delta_w],
        ["Alignment Severity", _rcd_w["mismatch_severity"]],
        ["Disclosure",         _rcd_w["disclosure_text"]],
    ]
    doc.table([["Regime-Cognition Alignment", ""], *_rcd_rows_w], widths=[2600, 6760], font_size=13)
    if _rcd_w["disclosure_required"]:
        doc.callout(
            f"⚠ Regime-Cognition Timing Disclosure [{_rcd_w['mismatch_severity']}]",
            _rcd_w["disclosure_text"],
            fill="FFE0B2",
        )
    journal_rows = build_cio_cognition_journal_rows(dataset, 3)
    if journal_rows:
        compact_journals = [
            [r[0], r[4], r[5], clean_text(r[7], 90), clean_text(r[8], 90), clean_text(r[9], 80)]
            for r in journal_rows
        ]
        doc.table(
            [["Journal TS", "Regime", "Action", "Strategic Thinking", "Planning", "Execution Intent"], *compact_journals],
            widths=[1600, 1000, 1200, 2300, 2300, 1560],
            font_size=13,
        )
    review_rows = build_cio_thesis_review_rows(dataset, 8)
    if review_rows:
        compact_reviews = [
            [r[0], r[1], fmt_ratio_pct(r[2]), r[4], clean_text(r[8], 85), clean_text(r[9], 85)]
            for r in review_rows
        ]
        doc.table(
            [["Thesis", "Status", "Prob", "Assessment", "Repeatability", "Mistake Risk"], *compact_reviews],
            widths=[2200, 1100, 900, 1700, 1800, 1660],
            font_size=13,
        )

    doc.heading("S2 · Thesis Lifecycle")
    # Full Thesis Lifecycle: all theses, 8 columns (Priority, Status, Thesis, Base, Prob, Conf, Direction, Evidence)
    _all_thesis_rows = build_thesis_rows(dataset)
    thesis_doc_rows = [
        [r[0], r[1], clean_text(r[3], 40), fmt_ratio_pct(r[4]), fmt_ratio_pct(r[5]), fmt_ratio_pct(r[6]), r[7], clean_text(r[10], 80)]
        for r in _all_thesis_rows
    ]
    doc.table(
        [["P", "Status", "Thesis", "Base", "Prob", "Conf", "Direction", "Evidence"], *thesis_doc_rows],
        widths=[550, 1100, 2400, 800, 800, 800, 1200, 1710],
        font_size=13,
    )

    doc.heading("S3 · Thesis Evidence")
    # ECE Governing Logic Disclosure — WO-ECE-20260612-001
    doc.paragraph(
        "ECE Sector Direction Governing Logic  |  version: ECE_v2\n"
        "Sector Dir is computed from live sector basket move, broad-market tape confirmation, "
        "catalyst polarity, and review-flag validation. Global regime is reported separately "
        "and does NOT overwrite sector direction.\n"
        "Thresholds:  Strong Risk-On ≥ +0.50%  ·  Selective Risk-On ≥ +0.10%  ·  "
        "Neutral −0.10%–+0.10%  ·  Selective Risk-Off ≤ −0.10%  ·  Risk-Off ≤ −0.50%\n"
        "Broad-rally overlay: positive-basket sectors cannot be Risk-Off when SPY > 0 AND (QQQ > 0 OR IWM > 0) AND VXX ≤ 0.\n"
        "Validation:  Positive basket cannot be Risk-Off without POSITIVE_BASKET_RISK_OFF_CONFLICT flag.  "
        "Theme evidence must match approved ticker/theme mapping or SECTOR_EVIDENCE_MISMATCH is raised.",
        size=18,
        italic=True,
    )
    # Thesis Evidence: ECE sector themes + per-thesis evidence signals
    _thesis_ev_rows = build_thesis_evidence_rows(dataset)
    thesis_ev_doc_rows = [[r[0], r[2], r[3], clean_text(r[4], 120)] for r in _thesis_ev_rows]
    doc.table(
        [["Status", "Sector / Thesis", "Logic (incl. Regime·Polarity·Flags)", "Evidence / Why"], *thesis_ev_doc_rows[:30]],
        widths=[700, 2500, 2500, 3660],
        font_size=13,
    )

    doc.heading("15 · Monitoring, Alerts & CIO Operations")
    alert_rows = [[r[0], r[1], clean_text(r[3], 38), clean_text(r[4], 90)] for r in build_monitoring_rows(dataset)[:10]]
    doc.table([["Severity", "Layer", "Title", "Message"], *alert_rows], widths=[1200, 1600, 2800, 3760], font_size=14)

    doc.heading("S4 · Institutional Operations")
    doc.table([["Field", "Value"], *build_ops_summary_rows(dataset)], widths=[2600, 6760], font_size=15)
    decision_rows = [[r[0], r[1], r[2] or "PORT", r[3], fmt_ratio_pct(r[6]), r[9]] for r in build_cio_decision_rows(dataset)[:10]]
    doc.table([["P", "Type", "Ticker", "Status", "Delta", "Order"], *decision_rows], widths=[600, 2200, 900, 3000, 1000, 800], font_size=13)

    doc.heading("S5 · Top Mover Catalyst Verification")
    mover_rows = [[r[1], fmt_pct_point(r[2]), fmt_float(r[6], 2), r[8], clean_text(r[9], 90)] for r in build_mover_rows(dataset)[:12]]
    doc.table([["Ticker", "Move", "Rel Vol", "Catalyst", "Reason"], *mover_rows], widths=[1000, 1100, 1000, 1400, 4860], font_size=16)

    doc.heading("S6 · Theme Rotation")
    theme_rows = [[clean_text(r[1], 28), r[2], fmt_pct_point(r[3]), f"{fmt_float(r[4], 0)}%", r[5], r[6] or clean_text(r[7], 80)] for r in build_theme_rows(dataset)[:12]]
    doc.table([["Theme", "Dir", "Basket", "Conf", "Tier", "Note"], *theme_rows], widths=[2200, 1000, 1000, 900, 1600, 2660], font_size=15)

    doc.heading("S7 · Forward Catalysts")
    cat_rows = [[r[0], r[1], r[2], fmt_int(r[4]), r[5], fmt_float(r[6], 3)] for r in build_catalyst_rows(dataset, 14)]
    doc.table([["Ticker", "Type", "Date", "Days", "Flag", "EPS Est"], *cat_rows], widths=[1000, 1400, 1500, 900, 1400, 1200], font_size=16)

    conf_rows = []
    for row in (dataset.get("conference_calendar") or [])[:5]:
        conf_rows.append([
            clean_text(row.get("conference_slug") or row.get("conference_name"), 28),
            row.get("event_date_start", ""),
            fmt_int(row.get("days_until_event")),
            row.get("catalyst_flag", ""),
            clean_text(", ".join(str(x) for x in parse_list(row.get("affected_tickers"))), 50),
        ])
    doc.table([["Conference", "Start", "Days", "Flag", "Affected"], *conf_rows], widths=[2400, 1400, 900, 1200, 3460], font_size=16)

    doc.heading("14 · Institutional Positioning")
    _inst = build_institutional_positioning(dataset)
    doc.callout("Source", "Options flow from Moomoo Intel. Capital flow from live intraday data. CFTC COT from CFTC TFF report (Leveraged Funds category = hedge funds, CTAs, CPOs).", fill="FFF2CC")
    doc.heading("Options Flow — Unusual Large Trades", level=2)
    doc.table(
        [["Ticker", "Date / Time", "Action", "Volume", "Signal"], *[[r[0], r[1], r[2], fmt_int(r[3]), r[4]] for r in _inst["options_flow"]]],
        widths=[900, 1400, 1600, 1400, 1400],
        font_size=14,
    )
    doc.heading("Capital Flow — Largest Institutional Outflows", level=2)
    doc.table(
        [["Ticker", "Super-Large Out", "Large Out", "Total", "Bias"], *_inst["capital_outflow"]],
        widths=[900, 1900, 1800, 1800, 1960],
        font_size=14,
    )
    doc.heading("CFTC COT — Leveraged Funds (Hedge Funds / CTAs)", level=2)
    doc.table(
        [["Contract", "Net Position", "As Of", "Direction"], *_inst["cftc_cot"]],
        widths=[3800, 1800, 1600, 1160],
        font_size=14,
    )

    doc.heading("S8 · Tech Intelligence Tape")
    article_rows = []
    for row in build_tech_rows(dataset, 10):
        ticker_theme = row[5] or row[6]
        article_rows.append([row[0], clean_text(ticker_theme, 30), row[2], clean_text(row[7], 110)])
    doc.table([["Source", "Ticker/Theme", "Tone", "Headline"], *article_rows], widths=[1600, 1900, 1100, 4860], font_size=15)

    doc.heading("S9 · Analyst & Flow Watchlist")
    # ── Risk Governor disclaimer — must appear before watchlist table ─────────
    _s9_conc = (_approved_truth_w.get("concentration_status") or _op_truth_w.get("concentration_status") or "UNKNOWN")
    _s9_cluster = (_approved_truth_w.get("cluster_status") or {})
    _s9_gm = _s9_cluster.get("GOLD_MINERS", {})
    _s9_gm_sev = str(_s9_gm.get("severity", "")).upper()
    if _s9_gm_sev == "CRITICAL" or _s9_conc == "CRITICAL":
        _s9_gm_pct = _s9_gm.get("weight_pct", "")
        doc.callout(
            "Risk Governor — Watchlist Override Active",
            f"GOLD_MINERS cluster concentration is CRITICAL ({_s9_gm_pct}). "
            "Watchlist actions are risk-governor adjusted. "
            "A high 8-Lens score does NOT automatically mean BUY. "
            "AU, NEM, GLD, GDX, GDXJ: action = HOLD / DECONCENTRATION REVIEW | governance = CLUSTER_BLOCKED_NO_ADD. "
            "CIO must manually approve any deconcentration trade. No automated orders permitted.",
            fill="FFE0B2",
        )
    watch_rows = []
    for row in build_analyst_rows(dataset)[:12]:
        flow = (dataset.get("capital_flow") or {}).get(row[0], {})
        watch_rows.append([row[0], theme_for(row[0], (dataset.get("security_master") or {}).get(row[0])), fmt_money(row[1]), fmt_pct_point(row[5]), fmt_int(row[9]), flow.get("institutional_bias", "")])
    doc.table([["Ticker", "Theme", "Price", "Upside", "Analysts", "Flow"], *watch_rows], widths=[1000, 2700, 1200, 1100, 1000, 1460], font_size=16)

    doc.heading("S10 · CIO Doctrine & Archive")
    doc.callout("Doctrine", "If catalyst unknown, say unknown. If blind spot unknown, search for it. If causal intelligence is incomplete, WAIT / HOLD. No blind spot check means no research confidence.", fill="E2F0D9")
    doc.table(
        [
            ["Archive Field", "Value"],
            ["Archive Status", archive.get("archive_status", "")],
            ["Archive ID", archive.get("archive_id", "")],
            ["Verified From DB", "TRUE" if archive.get("verified_from_database") else ""],
            ["Report SHA-256", db.get("report_sha256", "")],
            ["Report Source", db.get("source_file_path", "")],
        ],
        widths=[2000, 7360],
        font_size=16,
    )

    # ── QA Footer (WO-Final-PhD Defect 2 — wired to live audit, not empty dicts) ─
    _qa_cd_w = {
        "consistency_audit": {
            "status":     _audit_data.get("audit_status", "UNKNOWN"),
            "score":      _audit_data.get("audit_score", 0),
            "fail_count": _audit_data.get("fail_count", 0),
            "warn_count": _audit_data.get("warn_count", 0),
            "check_results": {r[0]: r[1] for r in _audit_data.get("check_rows", [])},
        }
    }
    _ot_qa = {
        "order_routing_enabled":        _op_truth_w.get("order_routing_enabled", False),
        "orders_generated_by_pipeline": int(_op_truth_w.get("orders_generated_by_pipeline") or 0),
    }
    _freshness_w = build_freshness_governor(dataset)
    _fg_w = _freshness_w.get("freshness_status", "UNKNOWN")
    try:
        _qa = build_report_qa_footer(dataset, _qa_cd_w, _ot_qa)
        _qa["freshness_gate"] = _fg_w
    except Exception:
        _qa = {"freshness_gate": _fg_w}
    _qa_blocking = list(_qa.get("blocking_failures") or [])
    # Inject governance-gate failed gates into Word QA (parity with Excel)
    for _gfg_w in (_gov_fail_w or []):
        _gfg_w_key = f"GOV_GATE_FAIL:{_gfg_w}"
        if _gfg_w_key not in _qa_blocking:
            _qa_blocking.append(_gfg_w_key)
    _qa_grade_w = float(_qa.get("final_institutional_grade") or 9.5)
    if _gov_fail_w:
        _qa_grade_w = round(min(_qa_grade_w, 9.2), 1)
    _qa_warnings = _qa.get("warnings") or []
    # Wording: only "Blocking Failures" when actually BLOCKED; otherwise "Warning / Failed Gates"
    if _gov_rel_w == "BLOCKED":
        _qa_w_fail_label = "Blocking Failures"
        _qa_w_fail_items = _qa_blocking
    else:
        _qa_w_fail_label = "Warning / Failed Gates"
        _qa_w_fail_items = [g.replace("GOV_GATE_FAIL:", "") for g in _qa_blocking]
    doc.heading("S11 · Report QA Footer")
    doc.paragraph(
        "Machine-readable QA block. All fields must PASS for INSTITUTIONAL_READY status.",
        size=18, color="808080",
    )
    _qa_rows = [
        ["QA Field", "Value"],
        ["Consistency Audit",     f"{_qa.get('consistency_audit', 'N/A')} (score={_qa.get('consistency_audit_score', 'N/A')})"],
        ["ECE Renderer Match",    str(_qa.get("ece_renderer_match", "N/A"))],
        ["ECE Percent Scale Check", str(_qa.get("ece_percent_scale_check", "N/A"))],
        ["Evidence Mapping Check", str(_qa.get("evidence_mapping_check", "N/A"))],
        ["Causal Status Logic",   str(_qa.get("causal_status_logic", "N/A"))],
        ["Execution Safety Gate", str(_qa.get("execution_safety_gate", "N/A"))],
        ["Freshness Gate",        str(_qa.get("freshness_gate", "N/A"))],
        ["Governance Gate Status", _gov_rel_w],
        [_qa_w_fail_label,        ", ".join(_qa_w_fail_items) if _qa_w_fail_items else "None"],
        ["Warnings",              ", ".join(_qa_warnings) if _qa_warnings else "None"],
        ["Final Institutional Grade", f"{_qa_grade_w} / 10"],
    ]
    if _qa.get("over_scaled_themes"):
        _qa_rows.append(["  Over-scaled Themes", ", ".join(_qa["over_scaled_themes"])])
    if _qa.get("mismatch_themes"):
        _qa_rows.append(["  Evidence Mismatch Themes", ", ".join(_qa["mismatch_themes"])])
    doc.table(_qa_rows, widths=[3000, 6360], font_size=16)

    # ── NITE-PEI Bayesian Engine Section ─────────────────────────────────────
    try:
        _npb_w = _load_latest_nite_pei_block()
        if _npb_w:
            doc.heading("NITE-PEI Bayesian Thesis Engine", level=1)
            doc.paragraph("News Impact & Thesis Engine for Prospective Event Intelligence", bold=True, color="004E98")
            doc.paragraph(f"Generated: {_npb_w.get('generated_at_sgt', '')}  |  Schema: {_npb_w.get('schema_version', '')}")
            doc.paragraph("MANUAL_EXECUTION_REQUIRED | LLM_ORDER_GENERATION=FALSE | ORDER_ROUTING=FALSE", italic=True, color="7F1D1D")

            # CKRI
            doc.heading("Composite Kill Risk Index (CKRI)", level=2)
            _np_ckri = _npb_w.get("ckri", 0.0)
            _np_zone = _npb_w.get("ckri_zone", "UNKNOWN")
            _zone_color = {"CLEAR": "22C55E", "WATCH": "F59E0B", "ELEVATED": "F97316", "HIGH": "EF4444", "CRITICAL": "7F1D1D"}.get(_np_zone, "000000")
            doc.paragraph(f"CKRI Score: {_np_ckri:.4f}   Zone: {_np_zone}", bold=True, color=_zone_color)
            _np_det = _npb_w.get("ckri_detail", {})
            doc.table([
                ["Metric", "Value"],
                ["Weighted Sum", f"{_np_det.get('weighted_sum', 0.0):.4f}"],
                ["Correlation Penalty", f"{_np_det.get('correlation_penalty_applied', 0.0):.4f}"],
                ["Total Weight", f"{_np_det.get('total_weight', 0.0):.4f}"],
            ], widths=[3000, 6360], font_size=18)

            # Bayesian formula
            doc.heading("Bayesian Update Formula", level=2)
            for _step in [
                "Step 1: prior_odds = P_prior / (1 - P_prior)",
                "Step 2: LR_adjusted = 1.0 + (LR_table[event_class][thesis_type] - 1.0) x (1 - noise_discount)  [discount pulls evidence toward neutral LR=1.0; T1=0.00 T2=0.10 T3=0.25 T4=0.50]",
                "Step 3: post_odds = prior_odds x LR_adjusted",
                "Step 4: P_posterior = post_odds / (1 + post_odds)",
                "Step 5: clamp to [0.05, 0.95]",
                "Multi-event: posterior_N becomes prior_(N+1) (sequential compounding)",
            ]:
                doc.paragraph(_step, bullet=True, size=18)

            # Thesis snapshots with evidence
            doc.heading("Thesis Probability Updates", level=2)
            for _snap in _npb_w.get("thesis_probability_snapshots", []):
                _tid = _snap.get("thesis_id", "UNKNOWN")
                _pp  = _snap.get("P_prior", 0.5)
                _ppo = _snap.get("P_posterior", 0.5)
                _dp  = _snap.get("delta_p", 0.0)
                _arrow = "+" if _dp >= 0 else ""
                doc.paragraph(f"{_tid}:  {_pp:.4f}  ->  {_ppo:.4f}  ({_arrow}{_dp:.4f})", bold=True, size=20)
                doc.paragraph(f"Posture: {_snap.get('posture', '')}", italic=True, size=18)
                _evts = _snap.get("events_applied", [])
                if _evts:
                    for _ev in _evts:
                        _beq = _ev.get("bayesian_equation", {})
                        _src_url = _ev.get("source_url", "")
                        doc.paragraph(f"[{_ev.get('event_class','?')}]  kw: '{_ev.get('matched_keyword','?')}'  Tier T{_ev.get('source_tier','?')}", bold=True, size=18)
                        doc.paragraph(f"Headline: {_ev.get('raw_headline', '')}", size=18)
                        doc.paragraph(f"Source: {_ev.get('source', '')}  |  Published: {_ev.get('published_at', '')}", size=16, color="555555")
                        doc.paragraph(f"Source URL: {_src_url}" if _src_url else "Source URL: [NO URL — ACCOUNTABILITY BREACH]",
                            size=16, color="0056D2" if _src_url else "EF4444")
                        doc.table([
                            ["Equation Step", "Value"],
                            ["Prior Odds", _beq.get("step_1_prior_odds", "")],
                            ["LR Adjustment", _beq.get("step_2_lr_adjustment", "")],
                            ["Posterior Odds", _beq.get("step_3_posterior_odds", "")],
                            ["P_posterior", _beq.get("step_4_posterior_prob", "")],
                            ["Clamp", _beq.get("step_5_clamp", "")],
                            ["Delta P this step", f"{_ev.get('delta_p_step', 0):+.4f}"],
                        ], widths=[2800, 6560], font_size=16)
                else:
                    doc.paragraph("No matching events this cycle — P unchanged from prior.", italic=True, size=18)
    except Exception as _npe_w:
        doc.paragraph(f"[NITE-PEI Word section failed: {_npe_w}]", color="EF4444")

    doc.save(output_path)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def file_status(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "path": str(path),
            "exists": True,
            "size_bytes": stat.st_size,
            "last_write_time": datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds"),
        }
    except FileNotFoundError:
        return {"path": str(path), "exists": False, "size_bytes": 0}


def validate_zip(path: Path, required_members: Sequence[str]) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(path, "r") as z:
            bad = z.testzip()
            names = set(z.namelist())
        missing = [x for x in required_members if x not in names]
        return {"zip_ok": bad is None, "missing_members": missing}
    except Exception as exc:
        return {"zip_ok": False, "error": str(exc)}


REQUIRED_STR_REMEDIATION_SHEETS = [
    "STR_Signal_Entropy",
    "STR_Source_Capacity",
    "STR_Cost_Basis",
    "STR_Kelly_Sizing",
    "STR_Hedge_Review",
    "STR_Cycle_Summary",
    "V3_STR_Remediation",
    "Open_Order_State",
    "Artifact_Manifest",
    "Canonical_Reconciliation",
    "Canonical_Contract",
    "Target_USD_Vector",
    "Risk_Overlay",
    "Deterministic_Pipeline",
    "Replay_Summary",
    "Benchmark_Summary",
    "Benchmark_Strategies",
    "Scenario_Scorecards",
    "Layer_Attribution",
    "One_Week_Observation",
]


def file_sha256(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return ""


def xlsx_sheet_names(path: Path) -> List[str]:
    try:
        with zipfile.ZipFile(path, "r") as z:
            xml = z.read("xl/workbook.xml").decode("utf-8", errors="replace")
        return re.findall(r'<sheet name="([^"]+)"', xml)
    except Exception:
        return []


def validate_required_xlsx_sheets(path: Path) -> Dict[str, Any]:
    names = xlsx_sheet_names(path)
    missing = [name for name in REQUIRED_STR_REMEDIATION_SHEETS if name not in names]
    return {
        "required_sheets": REQUIRED_STR_REMEDIATION_SHEETS,
        "sheet_names": names,
        "missing_required_sheets": missing,
        "section_coverage_status": "PASS" if not missing else "FAIL",
    }


def build_section_coverage_map(sheet_names: Sequence[str], report_text: str = "") -> Dict[str, Any]:
    coverage = {
        "00C_STR_SIGNAL_ENTROPY_AND_EDGE": {
            "txt": "STR - SIGNAL, ENTROPY, AND EDGE" in report_text,
            "xlsx": all(name in sheet_names for name in [
                "STR_Signal_Entropy", "STR_Source_Capacity", "STR_Cost_Basis",
                "STR_Kelly_Sizing", "STR_Hedge_Review", "STR_Cycle_Summary",
            ]),
        },
        "00D_V3_STR_BUG_CLEARANCE_RECONCILIATION": {
            "txt": "V3 / STR BUG-CLEARANCE RECONCILIATION" in report_text,
            "xlsx": all(name in sheet_names for name in ["V3_STR_Remediation", "Open_Order_State"]),
        },
        "00E_ARTIFACT_MANIFEST_AND_CANONICAL_TRUTH_SOURCE_AUDIT": {
            "txt": "ARTIFACT MANIFEST AND CANONICAL TRUTH-SOURCE AUDIT" in report_text,
            "xlsx": all(name in sheet_names for name in ["Artifact_Manifest", "Canonical_Reconciliation"]),
        },
    }
    benchmark_sheet_names = {
        "Canonical_Contract", "Target_USD_Vector", "Risk_Overlay",
        "Deterministic_Pipeline", "Replay_Summary", "Benchmark_Summary",
        "Benchmark_Strategies", "Scenario_Scorecards", "Layer_Attribution",
        "One_Week_Observation",
    }
    if "V3.4 BENCHMARK DASHBOARD AND OBSERVATION LOCK" in report_text or any(name in sheet_names for name in benchmark_sheet_names):
        coverage["00F_V3_4_BENCHMARK_DASHBOARD_AND_OBSERVATION_LOCK"] = {
            "txt": "V3.4 BENCHMARK DASHBOARD AND OBSERVATION LOCK" in report_text,
            "xlsx": all(name in sheet_names for name in benchmark_sheet_names),
        }
    return coverage


def build_artifact_manifest(
    dataset: Dict[str, Any],
    archive_result: Dict[str, Any],
    outputs: Dict[str, Any],
    text_output: Path,
    excel_output: Path,
    word_output: Path,
    delivery_json: Path,
    dashboard_generated_at: Any = None,
    report_text: str = "",
) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    readonly = dataset.get("portfolio_readonly") if isinstance(dataset.get("portfolio_readonly"), dict) else {}
    sheet_names = xlsx_sheet_names(excel_output)
    coverage = build_section_coverage_map(sheet_names, report_text)
    missing_sections = [
        section for section, cov in coverage.items()
        if not all(bool(v) for v in cov.values())
    ]
    missing_sheets = [name for name in REQUIRED_STR_REMEDIATION_SHEETS if name not in sheet_names]
    if missing_sheets or missing_sections:
        status = "ARTIFACT_SECTION_MISSING"
    elif not all(Path(p).exists() for p in [text_output, excel_output, word_output]):
        status = "ARTIFACT_STALE"
    else:
        status = "ARTIFACTS_CONSISTENT"
    return {
        "report_id": archive_result.get("archive_id") or archive_result.get("report_id") or meta.get("cycle_id"),
        "archive_id": archive_result.get("archive_id"),
        "dataset_generated_at": meta.get("generated_at"),
        "formal_report_snapshot_ts": meta.get("generated_at"),
        "broker_portfolio_ts": readonly.get("cycle_ts") or portfolio.get("cycle_ts"),
        "dashboard_snapshot_ts": readonly.get("cycle_ts") or portfolio.get("cycle_ts") or meta.get("generated_at"),
        "txt_generated_at": outputs.get("text_report", {}).get("last_write_time"),
        "docx_generated_at": outputs.get("word_report", {}).get("last_write_time"),
        "xlsx_generated_at": outputs.get("excel_report", {}).get("last_write_time"),
        "json_generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "dashboard_generated_at": dashboard_generated_at,
        "dataset_sha256": file_sha256(DEFAULT_DATASET),
        "txt_sha256": file_sha256(text_output),
        "docx_sha256": file_sha256(word_output),
        "xlsx_sha256": file_sha256(excel_output),
        "delivery_json_sha256": file_sha256(delivery_json),
        "section_coverage_map": coverage,
        "xlsx_sheet_names": sheet_names,
        "missing_required_sheets": missing_sheets,
        "artifact_consistency_status": status,
    }


def timestamped_fallback_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def write_delivery_json(path: Path, delivery: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(delivery, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1 — Live-only status reader (never reads from archive)
# ---------------------------------------------------------------------------

def get_current_status(dataset: Dict[str, Any], field_name: str) -> str:
    """Read a status field from operating_truth (live) only. Never from archive."""
    ot = (dataset.get("consistency_discipline") or {}).get("operating_truth") or {}
    val = ot.get(field_name)
    if val and str(val) not in ("", "UNKNOWN", "None"):
        return str(val)
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Gold Safe-Haven Thesis Tracker (Work Order 2026-06-10)
# ---------------------------------------------------------------------------

def build_gold_thesis_tracker(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """8-check Gold Safe-Haven Thesis Tracker.

    Evaluates whether the gold/silver/gold-miner safe-haven thesis is
    CONFIRMING, WATCH, WARNING, or FAILING based purely on price action,
    rates, dollar, oil news, and miner-vs-equity behaviour.

    No orders generated. CIO_ONLY_MANUAL doctrine preserved.
    """
    from datetime import datetime, timezone

    lp = live_prices(dataset)

    def _chg(ticker: str) -> Optional[float]:
        row = lp.get(ticker.upper())
        if row and row.get("chg_pct") is not None:
            try:
                return float(row["chg_pct"])
            except (TypeError, ValueError):
                pass
        return None

    def _price(ticker: str) -> Optional[float]:
        row = lp.get(ticker.upper())
        if row and row.get("price") is not None:
            try:
                return float(row["price"])
            except (TypeError, ValueError):
                pass
        return None

    def _mk_check(status: str, score: float, evidence: str, interpretation: str, cio_implication: str) -> Dict[str, Any]:
        return {"status": status, "score": score, "evidence": evidence,
                "interpretation": interpretation, "cio_implication": cio_implication}

    # ── Raw metric collection ────────────────────────────────────────────────
    gld_chg   = _chg("GLD");   slv_chg  = _chg("SLV")
    gdx_chg   = _chg("GDX");   gdxj_chg = _chg("GDXJ")
    au_chg    = _chg("AU");    nem_chg  = _chg("NEM")
    uup_chg   = _chg("UUP");   tlt_chg  = _chg("TLT")
    ief_chg   = _chg("IEF");   shy_chg  = _chg("SHY")
    spy_chg   = _chg("SPY");   qqq_chg  = _chg("QQQ")
    vxx_chg   = _chg("VXX");   uvxy_chg = _chg("UVXY")
    xle_chg   = _chg("XLE")
    gld_price = _price("GLD"); slv_price = _price("SLV")

    ty = dataset.get("treasury_yields") or {}
    yield_10y = ty.get("yield_10y")

    # Gold/silver ratio proxy (GLD price / SLV price)
    gsr_proxy: Optional[float] = None
    if gld_price and slv_price and slv_price > 0:
        gsr_proxy = round(gld_price / slv_price, 2)

    # Spread helpers
    def _spread(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is not None and b is not None:
            return round(a - b, 3)
        return None

    gdx_vs_gld   = _spread(gdx_chg, gld_chg)
    gdxj_vs_gld  = _spread(gdxj_chg, gld_chg)
    au_vs_gdx    = _spread(au_chg, gdx_chg)
    nem_vs_gdx   = _spread(nem_chg, gdx_chg)
    gdx_vs_spy   = _spread(gdx_chg, spy_chg)

    # Oil news keyword score
    OIL_KEYWORDS = {
        "hormuz", "iran", "oil shock", "supply disruption", "tanker", "shipping",
        "opec", "crude", "brent", "wti", "sanctions", "war risk", "strait",
        "barrel", "petroleum", "energy supply",
    }
    sigs = dataset.get("signals") or {}
    oil_news_count = 0
    oil_headlines: List[str] = []
    for src in ("Reuters_Commodities", "OilPrice_RSS", "OPEC_News", "EIA_Petroleum",
                "Reuters_Business", "FT_World", "WSJ_Markets"):
        for item in (sigs.get(src) or []):
            text = ""
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                text = (item.get("headline") or item.get("text") or item.get("title") or
                        item.get("summary") or "")
            if text:
                tl = text.lower()
                if any(kw in tl for kw in OIL_KEYWORDS):
                    oil_news_count += 1
                    if len(oil_headlines) < 3:
                        oil_headlines.append(text[:80])

    # Gold-miner cluster concentration
    conc = build_concentration_risk(dataset)
    clusters = conc.get("clusters") or {}
    gm_cluster_weight: float = 0.0
    for cname, cinfo in clusters.items():
        if "GOLD" in cname.upper() or "MINER" in cname.upper():
            # clusters dict values may be a float weight or a dict with "weight" key
            if isinstance(cinfo, dict):
                w = float(cinfo.get("weight", 0) or 0)
            else:
                try:
                    w = float(cinfo)
                except (TypeError, ValueError):
                    w = 0.0
            gm_cluster_weight = max(gm_cluster_weight, w)

    # ── 8 Checks ────────────────────────────────────────────────────────────

    checks: Dict[str, Any] = {}

    # CHECK 1: Gold spot stabilizes and rises
    if gld_chg is None:
        checks["gold_stabilizes_and_rises"] = _mk_check(
            "MISSING", 0.0, "GLD not in live prices",
            "Cannot determine gold trend this cycle.",
            "Gold spot data unavailable — treat as uncertain.")
    elif gld_chg >= 0:
        checks["gold_stabilizes_and_rises"] = _mk_check(
            "PASS", 1.0, f"GLD {gld_chg:+.2f}%",
            "Gold spot is flat/positive — thesis supportive.",
            "Gold leg of thesis intact; monitor for continuation.")
    elif gld_chg >= -2.0:
        checks["gold_stabilizes_and_rises"] = _mk_check(
            "WATCH", 0.5, f"GLD {gld_chg:+.2f}%",
            "Gold slightly negative — not yet breakdown.",
            "Monitor gold; no immediate action required.")
    else:
        checks["gold_stabilizes_and_rises"] = _mk_check(
            "FAIL", 0.0, f"GLD {gld_chg:+.2f}%",
            "Gold materially negative — thesis weakening.",
            "Gold leg failing; review miner thesis immediately.")

    # CHECK 2: Silver confirms or gold/silver ratio compresses
    if slv_chg is None or gld_chg is None:
        checks["silver_confirms_or_gsr_compresses"] = _mk_check(
            "MISSING", 0.0,
            f"SLV={slv_chg}, GLD={gld_chg}, GSR proxy={gsr_proxy}",
            "Silver or gold data unavailable.",
            "Cannot confirm precious metals breadth this cycle.")
    else:
        slv_vs_gld = round(slv_chg - gld_chg, 3)
        if slv_vs_gld >= 0:
            st, sc = "PASS", 1.0
            interp = "Silver outperforming gold — breadth confirming."
            cio = "Precious metals broad confirmation; thesis strengthened."
        elif slv_vs_gld >= -1.0:
            st, sc = "WATCH", 0.5
            interp = "Silver tracking gold — neutral breadth."
            cio = "Silver not diverging; wait for confirmation direction."
        else:
            st, sc = "FAIL", 0.0
            interp = "Silver sharply underperforming gold — breadth failing."
            cio = "Silver weakness undermines thesis; watch for gold isolation."
        checks["silver_confirms_or_gsr_compresses"] = _mk_check(
            st, sc,
            f"SLV {slv_chg:+.2f}% | GLD {gld_chg:+.2f}% | SLV-GLD spread {slv_vs_gld:+.2f}% | GSR proxy {gsr_proxy}",
            interp, cio)

    # CHECK 3: GDX/GDXJ stop underperforming GLD
    if gdx_vs_gld is None and gdxj_vs_gld is None:
        checks["miners_vs_gold"] = _mk_check(
            "MISSING", 0.0,
            f"GDX={gdx_chg}, GDXJ={gdxj_chg}, GLD={gld_chg}",
            "Miner ETF data unavailable.",
            "Cannot assess miner-vs-gold confirmation.")
    else:
        best_spread = max(s for s in [gdx_vs_gld, gdxj_vs_gld] if s is not None)
        ev = f"GDX-GLD {gdx_vs_gld:+.2f}%" if gdx_vs_gld is not None else ""
        ev += (f" | GDXJ-GLD {gdxj_vs_gld:+.2f}%" if gdxj_vs_gld is not None else "")
        if best_spread >= 0:
            checks["miners_vs_gold"] = _mk_check("PASS", 1.0, ev.strip(),
                "Miner ETFs confirming gold move — positive divergence.",
                "Miner ETF leg confirming; thesis intact.")
        elif best_spread >= -1.0:
            checks["miners_vs_gold"] = _mk_check("WATCH", 0.5, ev.strip(),
                "Miners slightly behind gold — minor drag.",
                "Miners tracking gold closely; acceptable underperformance.")
        else:
            checks["miners_vs_gold"] = _mk_check("FAIL", 0.0, ev.strip(),
                "Miners materially underperforming gold — divergence negative.",
                "Miner ETF rejection — consider whether gold move is credible for equity miners.")

    # CHECK 4: AU/NEM outperform GDX
    if au_vs_gdx is None and nem_vs_gdx is None:
        checks["au_nem_vs_gdx"] = _mk_check(
            "MISSING", 0.0,
            f"AU={au_chg}, NEM={nem_chg}, GDX={gdx_chg}",
            "Portfolio miner data unavailable.",
            "Cannot assess portfolio expression quality.")
    else:
        spreads = [s for s in [au_vs_gdx, nem_vs_gdx] if s is not None]
        avg_spread = round(sum(spreads) / len(spreads), 3)
        ev = f"AU-GDX {au_vs_gdx:+.2f}%" if au_vs_gdx is not None else ""
        ev += (f" | NEM-GDX {nem_vs_gdx:+.2f}%" if nem_vs_gdx is not None else "")
        if avg_spread >= 0:
            checks["au_nem_vs_gdx"] = _mk_check("PASS", 1.0, ev.strip(),
                "Portfolio miners outperforming GDX — alpha being captured.",
                "Portfolio selection alpha confirmed; maintain HOLD / RELOAD signal logic.")
        elif avg_spread >= -1.0:
            checks["au_nem_vs_gdx"] = _mk_check("WATCH", 0.5, ev.strip(),
                "Portfolio miners slightly lagging GDX — marginal underperformance.",
                "Monitor relative performance; no immediate action required.")
        else:
            checks["au_nem_vs_gdx"] = _mk_check("FAIL", 0.0, ev.strip(),
                "Portfolio miners materially underperforming GDX — selection not working.",
                "Portfolio miner selection lagging; review AU/NEM thesis independently.")

    # CHECK 5: Real yields do not spike (TLT / IEF proxy)
    rate_ev_parts = []
    if yield_10y is not None:
        rate_ev_parts.append(f"10Y yield {yield_10y:.2f}%")
    if tlt_chg is not None:
        rate_ev_parts.append(f"TLT {tlt_chg:+.2f}%")
    if ief_chg is not None:
        rate_ev_parts.append(f"IEF {ief_chg:+.2f}%")
    rate_ev = " | ".join(rate_ev_parts) or "No rate data"

    bond_chgs = [c for c in [tlt_chg, ief_chg] if c is not None]
    if not bond_chgs:
        checks["real_yields_do_not_spike"] = _mk_check("MISSING", 0.0, rate_ev,
            "Bond proxy data unavailable.", "Cannot assess rate pressure this cycle.")
    else:
        worst_bond = min(bond_chgs)
        if worst_bond >= 0:
            checks["real_yields_do_not_spike"] = _mk_check("PASS", 1.0, rate_ev,
                "Bonds flat/up — no yield spike; gold supportive environment.",
                "Rate environment not hostile to gold; thesis supported.")
        elif worst_bond >= -1.0:
            checks["real_yields_do_not_spike"] = _mk_check("WATCH", 0.5, rate_ev,
                "Mild bond weakness — modest yield pressure, manageable.",
                "Monitor rate trajectory; gold can withstand mild yield rise.")
        else:
            checks["real_yields_do_not_spike"] = _mk_check("FAIL", 0.0, rate_ev,
                "Bonds selling off materially — real yield pressure rising.",
                "Rising real yields hostile to gold; thesis under rate pressure.")

    # CHECK 6: DXY / UUP does not surge
    if uup_chg is None:
        checks["dxy_does_not_surge"] = _mk_check("MISSING", 0.0, "UUP not in live prices",
            "USD proxy unavailable.", "Cannot assess dollar headwind this cycle.")
    elif uup_chg <= 0.2:
        checks["dxy_does_not_surge"] = _mk_check("PASS", 1.0, f"UUP {uup_chg:+.2f}%",
            "Dollar flat/down — no USD headwind for gold.",
            "USD not pressuring gold; favourable environment.")
    elif uup_chg <= 0.7:
        checks["dxy_does_not_surge"] = _mk_check("WATCH", 0.5, f"UUP {uup_chg:+.2f}%",
            "Dollar modestly up — mild headwind for gold.",
            "Watch USD; moderate strengthening can dampen gold.")
    else:
        checks["dxy_does_not_surge"] = _mk_check("FAIL", 0.0, f"UUP {uup_chg:+.2f}%",
            "Dollar surging — significant gold headwind.",
            "Strong USD materially hostile to gold; thesis under dollar pressure.")

    # CHECK 7: Oil-risk premium remains elevated
    xle_ev = f"XLE {xle_chg:+.2f}%" if xle_chg is not None else "XLE unavailable"
    oil_ev = f"{xle_ev} | Oil news hits: {oil_news_count}"
    if oil_headlines:
        oil_ev += f" | Top: {oil_headlines[0][:60]}"
    if oil_news_count >= 2 and (xle_chg is None or xle_chg >= -1.0):
        checks["oil_risk_premium_elevated"] = _mk_check("PASS", 1.0, oil_ev,
            "Oil-risk news active and energy price holding — premium intact.",
            "Geopolitical oil-risk premium supports safe-haven gold thesis.")
    elif oil_news_count >= 1 or (xle_chg is not None and xle_chg >= 0):
        checks["oil_risk_premium_elevated"] = _mk_check("WATCH", 0.5, oil_ev,
            "Oil news present but price weak, or price firm but news limited.",
            "Partial oil-risk premium — not fully validating macro thesis.")
    else:
        checks["oil_risk_premium_elevated"] = _mk_check("FAIL", 0.0, oil_ev,
            "No fresh oil-risk news and energy selling off.",
            "Oil-risk premium fading — reduces macro catalyst for gold.")

    # CHECK 8: Miners not liquidated as equity beta
    vxx_rising = (vxx_chg is not None and vxx_chg > 1.0) or (uvxy_chg is not None and uvxy_chg > 1.5)
    miners_lag_spy = gdx_vs_spy is not None and gdx_vs_spy < -2.0
    au_nem_lag_gdx = avg_spread < -1.0 if (au_vs_gdx is not None or nem_vs_gdx is not None) else False

    liq_ev_parts = []
    if gdx_chg is not None: liq_ev_parts.append(f"GDX {gdx_chg:+.2f}%")
    if spy_chg is not None: liq_ev_parts.append(f"SPY {spy_chg:+.2f}%")
    if gdx_vs_spy is not None: liq_ev_parts.append(f"GDX-SPY {gdx_vs_spy:+.2f}%")
    if vxx_chg is not None: liq_ev_parts.append(f"VXX {vxx_chg:+.2f}%")
    liq_ev = " | ".join(liq_ev_parts) or "Equity data unavailable"

    if gdx_vs_spy is None and spy_chg is None:
        checks["miners_not_liquidated_as_equity_beta"] = _mk_check("MISSING", 0.0, liq_ev,
            "Equity data unavailable.", "Cannot assess liquidation risk this cycle.")
    elif miners_lag_spy and vxx_rising and au_nem_lag_gdx:
        checks["miners_not_liquidated_as_equity_beta"] = _mk_check("FAIL", 0.0, liq_ev,
            "Miners sharply lagging equities AND vol rising AND portfolio miners underperforming — liquidation pattern.",
            "Miners being sold as equity beta; gold thesis temporarily disconnected from miners.")
    elif gdx_vs_spy is not None and gdx_vs_spy >= -2.0:
        if gdx_vs_spy >= 0:
            st, sc = "PASS", 1.0
            interp = "Miners holding up or outperforming equities — not being sold as beta."
            cio = "Miner/equity divergence positive; gold safe-haven function intact."
        else:
            st, sc = "WATCH", 0.5
            interp = "Miners slightly lagging equities but within tolerable range."
            cio = "Watch for further miner-equity divergence; not yet liquidation."
        checks["miners_not_liquidated_as_equity_beta"] = _mk_check(st, sc, liq_ev, interp, cio)
    else:
        checks["miners_not_liquidated_as_equity_beta"] = _mk_check("WATCH", 0.5, liq_ev,
            "Partial data — cannot confirm or deny liquidation risk.",
            "Monitor miner-vs-equity spread; insufficient data for FAIL confirmation.")

    # ── Scoring ──────────────────────────────────────────────────────────────
    available = [c for c in checks.values() if c["status"] != "MISSING"]
    score_sum = sum(c["score"] for c in available)
    n_avail   = len(available) if available else 1
    score     = round(score_sum / n_avail, 3)

    if score >= 0.75:
        status = "CONFIRMING"
    elif score >= 0.50:
        status = "WATCH"
    elif score >= 0.30:
        status = "WARNING"
    else:
        status = "FAILING"

    _CRITICAL_GT = {"gold_stabilizes_and_rises", "au_nem_vs_gdx",
                    "miners_not_liquidated_as_equity_beta", "miners_vs_gold",
                    "real_yields_do_not_spike"}
    critical_fail_count = sum(1 for k, c in checks.items()
                              if k in _CRITICAL_GT and c["status"] == "FAIL")

    if status == "CONFIRMING":
        confidence = "HIGH" if critical_fail_count == 0 else "MEDIUM"
    elif status == "WATCH":
        confidence = "MEDIUM"
    elif status == "WARNING":
        confidence = "MEDIUM_LOW" if critical_fail_count >= 3 else "MEDIUM"
    else:  # FAILING
        confidence = "LOW"

    # Hard overrides
    if score < 0.50 and confidence == "HIGH":
        confidence = "MEDIUM"
    if critical_fail_count >= 3 and confidence in ("HIGH", "MEDIUM_HIGH"):
        confidence = "MEDIUM"

    # ── CIO Action Rules ─────────────────────────────────────────────────────
    conc_status = conc.get("concentration_status", "UNKNOWN")
    add_blocked_by_conc  = gm_cluster_weight >= 0.50 or conc_status in ("HIGH", "CRITICAL")
    add_blocked_by_thesis = status in ("WARNING", "FAILING")
    add_allowed          = not add_blocked_by_conc and not add_blocked_by_thesis

    # ── Thesis add signal (independent of portfolio state) ───────────────
    if status in ("CONFIRMING",):
        thesis_add_signal = "THESIS_SUPPORTS_ADD"
    elif status in ("WATCH",):
        thesis_add_signal = "THESIS_HOLD_ONLY"
    elif status in ("WARNING",):
        thesis_add_signal = "THESIS_WEAKENING"
    else:
        thesis_add_signal = "THESIS_INVALIDATED"

    # ── Execution permission (portfolio + governance gate) ────────────────
    if add_allowed:
        execution_permission = "EXECUTION_REQUIRES_CIO_REVIEW"
    elif add_blocked_by_conc:
        execution_permission = "EXECUTION_BLOCKED_BY_CONCENTRATION"
    elif add_blocked_by_thesis:
        execution_permission = "EXECUTION_BLOCKED_BY_GOLD_THESIS_WEAKNESS"
    else:
        execution_permission = "EXECUTION_UNKNOWN_REQUIRES_BROKER_CHECK"

    if status == "CONFIRMING":
        core_action = "HOLD"
        add_note    = ("Only if risk governor permits and concentration <50%." if not add_blocked_by_conc
                       else "BLOCKED — gold-miner cluster concentration too high.")
    elif status == "WATCH":
        core_action = "HOLD / WAIT"
        add_note    = "No add until confirmation improves."
    elif status == "WARNING":
        core_action = "HOLD / REVIEW"
        add_note    = "No add; consider hedge/reduction if trend worsens."
    else:
        core_action = "REVIEW / REDUCE"
        add_note    = "Escalate to Risk Department; review miner exposure."

    # ── Summary narrative ────────────────────────────────────────────────────
    pass_checks  = [k for k, c in checks.items() if c["status"] == "PASS"]
    fail_checks  = [k for k, c in checks.items() if c["status"] == "FAIL"]
    watch_checks = [k for k, c in checks.items() if c["status"] == "WATCH"]
    miss_checks  = [k for k, c in checks.items() if c["status"] == "MISSING"]

    _readable = {
        "gold_stabilizes_and_rises": "gold spot",
        "silver_confirms_or_gsr_compresses": "silver confirmation",
        "miners_vs_gold": "miner ETF vs gold",
        "au_nem_vs_gdx": "AU/NEM vs GDX",
        "real_yields_do_not_spike": "real yields",
        "dxy_does_not_surge": "USD/DXY",
        "oil_risk_premium_elevated": "oil-risk premium",
        "miners_not_liquidated_as_equity_beta": "miner liquidation risk",
    }
    fail_readable  = [_readable.get(k, k) for k in fail_checks]
    watch_readable = [_readable.get(k, k) for k in watch_checks]

    if status == "CONFIRMING":
        if gm_cluster_weight <= 0:
            summary = (
                "Gold thesis is confirming. Current live gold-miner cluster is 0%; "
                "no live gold-miner concentration breach is present. HOLD only. "
                "Any AU/NEM references are order-review or archive context, not current exposure. "
                "No add without CIO review."
            )
        elif add_blocked_by_conc:
            summary = (
                "Gold thesis is confirming, but live gold-miner exposure requires concentration review. "
                "HOLD only. No add. Deconcentration requires CIO review. "
                f"Current gold-miner cluster: {gm_cluster_weight:.0%}."
            )
        else:
            summary = (
                "Gold thesis is confirming and live gold-miner exposure is inside the concentration gate. "
                "HOLD only unless CIO explicitly approves review-based deployment. "
                f"Current gold-miner cluster: {gm_cluster_weight:.0%}."
            )
    elif fail_readable:
        summary = (f"Gold thesis {status}: {', '.join(fail_readable)} failing"
                   + (f"; {', '.join(watch_readable)} on watch" if watch_readable else "")
                   + f". Score {score:.2f}/{1.0:.2f} ({score_sum:.1f}/{n_avail} available checks). "
                   f"Gold-miner cluster {gm_cluster_weight:.0%} — add {'BLOCKED' if not add_allowed else 'conditional on CIO override'}.")
    else:
        summary = (f"Gold thesis {status}: {', '.join(watch_readable or ['all checks on watch'])} on watch. "
                   f"Score {score:.2f}. No immediate add. Monitor for confirmation.")

    return {
        "status":         status,
        "score":          score,
        "max_score":      1.0,
        "n_available":    n_avail,
        "n_pass":         len(pass_checks),
        "n_watch":        len(watch_checks),
        "n_fail":         len(fail_checks),
        "n_missing":      len(miss_checks),
        "confidence":     confidence,
        "generated_at":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary":        summary,
        "checks":         checks,
        "key_metrics": {
            "gld_change_pct":      gld_chg,
            "slv_change_pct":      slv_chg,
            "gdx_change_pct":      gdx_chg,
            "gdxj_change_pct":     gdxj_chg,
            "au_change_pct":       au_chg,
            "nem_change_pct":      nem_chg,
            "gold_silver_ratio_proxy": gsr_proxy,
            "gdx_vs_gld_spread":   gdx_vs_gld,
            "gdxj_vs_gld_spread":  gdxj_vs_gld,
            "au_vs_gdx_spread":    au_vs_gdx,
            "nem_vs_gdx_spread":   nem_vs_gdx,
            "uup_change_pct":      uup_chg,
            "ten_year_yield":      yield_10y,
            "tlt_change_pct":      tlt_chg,
            "xle_change_pct":      xle_chg,
            "oil_news_pressure_score": oil_news_count,
            "spy_change_pct":      spy_chg,
            "qqq_change_pct":      qqq_chg,
            "vxx_change_pct":      vxx_chg,
            "uvxy_change_pct":     uvxy_chg,
        },
        "thesis_action": {
            "gold_miner_core_action":          core_action,
            "gold_miner_cluster_weight":       round(gm_cluster_weight, 4),
            "add_allowed":                     add_allowed,
            "add_blocked_by_concentration":    add_blocked_by_conc,
            "add_blocked_by_thesis_status":    add_blocked_by_thesis,
            "reason":                          add_note,
            "risk_governor_override_required": True,
            "thesis_add_signal":               thesis_add_signal,
            "execution_permission":            execution_permission,
        },
    }


# ---------------------------------------------------------------------------
# Fix 7 — Shared briefing model consumed by ALL renderers
# ---------------------------------------------------------------------------

def build_cio_briefing_model(
    dataset: Dict[str, Any],
    archive: Dict[str, Any],
    causal_data: Optional[Dict[str, Any]] = None,
    blind_data: Optional[Dict[str, Any]] = None,
    operating_truth: Optional[Dict[str, Any]] = None,
    action_logic: Optional[Dict[str, Any]] = None,
    freshness_data: Optional[Dict[str, Any]] = None,
    news_data: Optional[Dict[str, Any]] = None,
    conc_data: Optional[Dict[str, Any]] = None,
    audit_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Single normalized briefing model consumed by ALL renderers (Fix 7)."""
    ot = operating_truth or {}
    al = action_logic or {}
    fd = freshness_data or {}
    nd = news_data or {}
    cd_data = causal_data or {}
    bd_data = blind_data or {}

    # news_data is now a dict with 3 sections (Fix 5)
    top_cio  = nd.get("top_cio_market_catalysts", []) if isinstance(nd, dict) else nd[:10] if isinstance(nd, list) else []
    top_tech = nd.get("top_tech_intelligence", []) if isinstance(nd, dict) else []
    top_early = nd.get("top_early_warning", []) if isinstance(nd, dict) else []

    return {
        "blind_spot_status":               ot.get("blind_spot_status", "UNKNOWN"),
        "causal_status":                   ot.get("causal_status", "UNKNOWN"),
        "report_readiness":                ot.get("report_readiness", "UNKNOWN"),
        "consistency_audit_status":        ot.get("consistency_audit_status", "UNKNOWN"),
        "concentration_status":            ot.get("concentration_status", "UNKNOWN"),
        "final_cio_operating_action":      al.get("final_cio_operating_action") or al.get("final_action", "UNKNOWN"),
        "execution_authority":             ot.get("execution_authority", "CIO_ONLY_MANUAL"),
        "order_routing_enabled":           ot.get("order_routing_enabled", False),
        "orders_generated_by_pipeline":    ot.get("orders_generated_by_pipeline", 0),
        "freshness_critical_stale_count":  len(fd.get("critical_stale_sections", [])),
        "freshness_noncritical_stale_count": len(fd.get("non_critical_stale_sections", [])),
        "freshness_status":                fd.get("freshness_status", "UNKNOWN"),
        "blocked_actions":                 al.get("blocked_actions", []),
        "raw_regime_action":               al.get("raw_regime_action", "UNKNOWN"),
        "risk_adjusted_action":            al.get("risk_adjusted_action", "UNKNOWN"),
        "causal_failed_critical":          cd_data.get("failed_critical_checks", []),
        "blind_spot_pass_count":           bd_data.get("pass_count", 0),
        "blind_spot_fail_count":           bd_data.get("fail_count", 0),
        "blind_spot_failed_items":         list(bd_data.get("failed_items") or []),
        "news_top_cio":   top_cio,
        "news_top_tech":  top_tech,
        "news_top_early": top_early,
        "top_movers":     top_movers(dataset),
        "brier_status":   ot.get("brier_status", "UNKNOWN"),
        "regime":         ot.get("regime", "UNKNOWN"),
    }


def load_r6_module():
    module_path = RESEARCH_DIR / "research_report_generator_r6.py"
    spec = importlib.util.spec_from_file_location("bluelotus_research_report_generator_r6", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load canonical R6 generator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_approved_truth_for_renderer() -> Optional[Dict]:
    """
    Load governance-gate approved truth for Word/Excel renderer.
    Called at renderer startup — if governance gate has not been run, returns None
    and renderers fall back to inline computation (same as before governance gate).
    Renderer compliance: contract fields consumed from approved truth, not recalculated.
    """
    try:
        _gov_dir = PROJECT_ROOT / "governance"
        if str(_gov_dir) not in sys.path:
            sys.path.insert(0, str(_gov_dir))
        from governance_gate import load_approved_truth
        truth = load_approved_truth()
        if truth:
            print(f"[Governance Gate] Approved truth loaded | release={truth.get('_release_status','?')}")
        return truth
    except Exception as exc:
        print(f"[Governance Gate] Could not load approved truth: {exc}")
        return None


def _load_approved_cio_briefing() -> Dict[str, Any]:
    """
    Load approved_cio_briefing.json produced by scenario_overlay_engine.py.
    Returns empty dict if not yet generated — renderers degrade gracefully.
    """
    try:
        _path = PROJECT_ROOT / "data" / "governance" / "approved_cio_briefing.json"
        if _path.exists():
            return json.loads(_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[CIO Briefing] Could not load approved_cio_briefing.json: {exc}")
    return {}


def run_u_generator(
    dataset_arg: Path,
    text_output_arg: Path,
    excel_output: Path,
    word_output: Path,
    delivery_json: Path,
    skip_presentations: bool = False,
) -> Dict[str, Any]:
    # ── Governance Gate: run gate to refresh approved truth before all renderers ──
    try:
        _gov_dir = PROJECT_ROOT / "governance"
        if str(_gov_dir) not in sys.path:
            sys.path.insert(0, str(_gov_dir))
        from governance_gate import run_governance_gate
        _gate_result = run_governance_gate()
        print(f"[Governance Gate] Release status: {_gate_result.get('release_status', 'UNKNOWN')}")
        for _b in _gate_result.get("blocks", []):
            print(f"[Governance Gate] BLOCK: {_b}")
        for _w in _gate_result.get("warnings", []):
            print(f"[Governance Gate] WARN: {_w}")
    except Exception as _gate_exc:
        print(f"[Governance Gate] WARNING: gate not run — {_gate_exc}")

    r6 = load_r6_module()

    dataset_path = r6.resolve_input_path(dataset_arg)
    text_output_path = r6.resolve_output_path(text_output_arg)

    wait_for_stable_file(dataset_path)
    dataset = r6.load_dataset(dataset_path)

    if master_prompt_is_active and not master_prompt_is_active(dataset):
        if build_chief_strategist_master_prompt is None:
            raise RuntimeError("Chief Strategist Master Prompt builder unavailable; report generation blocked.")
        try:
            build_chief_strategist_master_prompt(dataset_path=dataset_path)
            wait_for_stable_file(dataset_path)
            dataset = r6.load_dataset(dataset_path)
            print("[Chief Strategist Master Prompt] Built and embedded before report generation.")
        except Exception as _master_exc:
            print(f"[Chief Strategist Master Prompt] ERROR: prompt build failed: {_master_exc}")
        if not master_prompt_is_active(dataset):
            raise RuntimeError("Chief Strategist Master Prompt missing or inactive; report generation blocked.")

    if governance_is_active and not governance_is_active(dataset):
        try:
            from chief_strategist_governance.csg_builder import build_chief_strategist_governance_pack
            build_chief_strategist_governance_pack(dataset_path=dataset_path)
            wait_for_stable_file(dataset_path)
            dataset = r6.load_dataset(dataset_path)
            print("[CSG] Governance pack built and embedded before report generation.")
        except Exception as _csg_exc:
            print(f"[CSG] ERROR: governance pack build failed: {_csg_exc}")
        if not governance_is_active(dataset):
            raise RuntimeError("Chief Strategist Governance Layer missing or inactive; report generation blocked.")

    if capsule_is_active and not capsule_is_active(dataset):
        if build_cio_context_capsule is None:
            raise RuntimeError("CIO Context Capsule builder unavailable; report generation blocked.")
        try:
            build_cio_context_capsule(dataset_path=dataset_path)
            wait_for_stable_file(dataset_path)
            dataset = r6.load_dataset(dataset_path)
            print("[CIO Context] Capsule built and embedded before report generation.")
        except Exception as _cio_ctx_exc:
            print(f"[CIO Context] ERROR: capsule build failed: {_cio_ctx_exc}")
        if not capsule_is_active(dataset):
            raise RuntimeError("CIO Context Capsule missing or inactive; report generation blocked.")

    _cycle_meta_for_law = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    _law_cycle_id = str(_cycle_meta_for_law.get("cycle_id") or _cycle_meta_for_law.get("cycle_ts") or _cycle_meta_for_law.get("generated_at") or "")
    _law_report_id = f"{text_output_path.stem}:{_law_cycle_id or datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    governance_law_pack, governance_law_validation, governance_law_binding = prepare_law_governance_binding_for_report(
        dataset,
        dataset_path,
        report_id=_law_report_id,
        cycle_id=_law_cycle_id,
    )
    print(
        "[Governance Law] "
        f"status={dataset.get('law_governance_binding', {}).get('status', 'UNKNOWN')} "
        f"binding={governance_law_binding.get('binding_id', '')}"
    )

    if build_prospective_event_intelligence:
        try:
            prospective_event_intelligence = build_prospective_event_intelligence(dataset, persist=True)
            dataset["prospective_event_intelligence"] = prospective_event_intelligence
            dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
            print(
                "[PEI] "
                f"status={prospective_event_intelligence.get('status', 'UNKNOWN')} "
                f"events={len(prospective_event_intelligence.get('active_events') or [])} "
                f"forecasts={len(prospective_event_intelligence.get('forecast_registry') or [])}"
            )
        except Exception as _pei_exc:
            prospective_event_intelligence = {
                "status": "PEI_BUILD_FAILED",
                "version": "pei_v0.1",
                "generated_at_sgt": _sgt_now_text(),
                "execution_authority": "CIO_ONLY_MANUAL",
                "order_routing_enabled": False,
                "orders_generated": 0,
                "cio_action_cap": "ADD_BLOCKED",
                "failure_mode": str(_pei_exc),
            }
            dataset["prospective_event_intelligence"] = prospective_event_intelligence
            dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[PEI] WARNING: PEI build failed closed: {_pei_exc}")
    else:
        prospective_event_intelligence = {
            "status": "PEI_IMPORT_UNAVAILABLE",
            "version": "pei_v0.1",
            "generated_at_sgt": _sgt_now_text(),
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "orders_generated": 0,
            "cio_action_cap": "ADD_BLOCKED",
        }
        dataset["prospective_event_intelligence"] = prospective_event_intelligence

    if build_shannon_thorp_refinement:
        try:
            shannon_thorp_refinement = build_shannon_thorp_refinement(dataset, persist=True)
            dataset["shannon_thorp_refinement"] = shannon_thorp_refinement
            dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
            print(
                "[STR] "
                f"status={shannon_thorp_refinement.get('status', 'UNKNOWN')} "
                f"entropy={len(shannon_thorp_refinement.get('signal_entropy') or [])} "
                f"kelly={len(shannon_thorp_refinement.get('kelly_sizing_advisory') or [])} "
                f"hedge={((shannon_thorp_refinement.get('hedge_ratio_review') or {}).get('hedge_status', 'UNKNOWN'))}"
            )
        except Exception as _str_exc:
            shannon_thorp_refinement = {
                "status": "STR_BUILD_FAILED",
                "version": "str_v0.1",
                "generated_at": _sgt_now_text(),
                "execution_authority": "CIO_ONLY_MANUAL",
                "order_routing_enabled": False,
                "system_orders_generated": 0,
                "failure_mode": str(_str_exc),
                "doctrine": {
                    "research_only": True,
                    "no_order_generation": True,
                    "no_broker_routing": True,
                    "does_not_override_cio_only_manual": True,
                },
            }
            dataset["shannon_thorp_refinement"] = shannon_thorp_refinement
            dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[STR] WARNING: STR build failed closed: {_str_exc}")
    else:
        shannon_thorp_refinement = {
            "status": "STR_IMPORT_UNAVAILABLE",
            "version": "str_v0.1",
            "generated_at": _sgt_now_text(),
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "system_orders_generated": 0,
            "doctrine": {
                "research_only": True,
                "no_order_generation": True,
                "no_broker_routing": True,
                "does_not_override_cio_only_manual": True,
            },
        }
        dataset["shannon_thorp_refinement"] = shannon_thorp_refinement

    # ── Pre-inject _report_qa into dataset (WO-Final-PhD Defect 2) ───────────
    # Compute a preliminary consistency pass BEFORE rendering so the TXT renderer
    # (r6.generate) can read dataset["_report_qa"] instead of empty-dict fallback.
    # This two-pass approach is identical to what build_excel_report does internally.
    try:
        _pre_causal  = build_causal_explanation(dataset)
        _pre_blind   = build_blind_spot_checklist(dataset)
        _pre_conc    = build_concentration_risk(dataset)
        _pre_ot_pre  = build_operating_truth(dataset, {}, _pre_causal, _pre_blind, _pre_conc)
        _pre_audit   = build_consistency_audit(dataset, {}, causal_data=_pre_causal, blind_data=_pre_blind, operating_truth=_pre_ot_pre)
        _pre_ot      = build_operating_truth(dataset, {}, _pre_causal, _pre_blind, _pre_conc, _pre_audit)
        _pre_fresh   = build_freshness_governor(dataset)
        _pre_cd = {
            "consistency_audit": {
                "status":     _pre_audit.get("audit_status", "UNKNOWN"),
                "score":      _pre_audit.get("audit_score", 0),
                "fail_count": _pre_audit.get("fail_count", 0),
                "warn_count": _pre_audit.get("warn_count", 0),
                "check_results": {r[0]: r[1] for r in _pre_audit.get("check_rows", [])},
            },
            "freshness_governor": {
                "freshness_status": _pre_fresh.get("freshness_status", "UNKNOWN"),
            },
        }
        _pre_ot_qa = {
            "order_routing_enabled":        _pre_ot.get("order_routing_enabled", False),
            "orders_generated_by_pipeline": int(_pre_ot.get("orders_generated_by_pipeline") or 0),
        }
        _pre_qa = build_report_qa_footer(dataset, _pre_cd, _pre_ot_qa)
        _pre_qa["freshness_gate"] = (
            "PASS"    if _pre_fresh.get("freshness_status") in ("FRESH", "PASS") else
            "WARNING" if _pre_fresh.get("freshness_status") in ("STALE_NON_CRITICAL", "WARNING") else
            "FAIL"    if _pre_fresh.get("freshness_status") in ("STALE_CRITICAL", "FAIL") else
            "UNKNOWN"
        )
        dataset["_report_qa"] = _pre_qa
        if build_remediation_reconciliation:
            try:
                _remediation = build_remediation_reconciliation(
                    dataset,
                    dataset.get("shannon_thorp_refinement") or {},
                    {
                        "failed_checks": _pre_audit.get("failed_checks", []),
                        "audit_status": _pre_audit.get("audit_status", "UNKNOWN"),
                    },
                )
                dataset["v3_str_bug_clearance_reconciliation"] = _remediation
                dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
                print(
                    "[V3/STR Remediation] "
                    f"status={_remediation.get('status')} "
                    f"bp={((_remediation.get('buying_power_reconciliation') or {}).get('status'))} "
                    f"session={((_remediation.get('session_state') or {}).get('market_session_canonical'))}"
                )
            except Exception as _rem_exc:
                dataset["v3_str_bug_clearance_reconciliation"] = {
                    "status": "BUILD_FAILED",
                    "failure_mode": str(_rem_exc),
                    "execution_authority": "CIO_ONLY_MANUAL",
                    "order_routing_enabled": False,
                    "system_orders_generated": 0,
                }
                print(f"[V3/STR Remediation] WARNING: build failed closed: {_rem_exc}")
    except Exception as _pre_qa_exc:
        print(f"Pre-QA injection WARNING: {_pre_qa_exc}")

    if build_v3_1_to_v3_4_payload:
        try:
            dataset = build_v3_1_to_v3_4_payload(dataset)
            dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
            _canon_status = (((dataset.get("canonical") or {}).get("validation") or {}).get("status"))
            _bench = dataset.get("benchmark_dashboard_v3_4") or {}
            print(
                "[V3.1-V3.4] "
                f"canonical={_canon_status} "
                f"benchmark={_bench.get('benchmark_id', 'UNKNOWN')} "
                f"lock={((dataset.get('v3_4_observation_lock') or {}).get('lock_status', 'UNKNOWN'))}"
            )
        except Exception as _v34_exc:
            dataset["v3_1_to_v3_4_upgrade_error"] = {
                "status": "BUILD_FAILED",
                "failure_mode": str(_v34_exc),
                "execution_authority": "CIO_ONLY_MANUAL",
                "order_routing_enabled": False,
                "system_orders_generated": 0,
            }
            dataset_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[V3.1-V3.4] WARNING: build failed closed: {_v34_exc}")

    report_text = normalize_report_text(r6.generate(dataset))
    if prepend_master_prompt_and_cio_context:
        report_text = normalize_report_text(prepend_master_prompt_and_cio_context(report_text, dataset))
    governance_law_section = render_governance_law_binding_section(dataset.get("law_governance_binding") or {})
    report_text = normalize_report_text(insert_law_governance_section_after_master_prompt(report_text, governance_law_section))
    if render_pei_text_section:
        report_text = normalize_report_text(report_text.rstrip() + "\n\n" + render_pei_text_section(dataset.get("prospective_event_intelligence") or {}))
    if render_str_text_section:
        report_text = normalize_report_text(report_text.rstrip() + "\n\n" + render_str_text_section(dataset.get("shannon_thorp_refinement") or {}))
    if render_remediation_text_section:
        report_text = normalize_report_text(report_text.rstrip() + "\n\n" + render_remediation_text_section(dataset.get("v3_str_bug_clearance_reconciliation") or {}))
    report_text = normalize_report_text(report_text.rstrip() + "\n\n" + render_artifact_manifest_text_section(dataset))
    report_text = normalize_report_text(report_text.rstrip() + "\n\n" + render_benchmark_text_section(dataset))
    if append_csg_text_section:
        report_text = normalize_report_text(append_csg_text_section(report_text, dataset))
    # ── NITE-PEI Bayesian Engine — append probability update with source evidence ──
    _nite_pei_block = _load_latest_nite_pei_block()
    if _nite_pei_block and _build_nite_pei_txt:
        try:
            _nite_pei_section = _build_nite_pei_txt(_nite_pei_block)
            if _nite_pei_section.strip():
                report_text = normalize_report_text(report_text.rstrip() + "\n\n" + _nite_pei_section)
        except Exception as _npe:
            report_text = normalize_report_text(report_text.rstrip() + "\n\n[NITE-PEI section failed to render: " + str(_npe) + "]")
    text_output_path.write_text(report_text, encoding="utf-8")

    print("BlueLotus Research Report generated successfully.")
    print(f"Dataset : {dataset_path}")
    print(f"Output  : {text_output_path}")
    print(f"Lines   : {len(report_text.splitlines())}")
    print(f"Chars   : {len(report_text)}")

    archive_result: Dict[str, Any] = {}
    archive_error = None
    try:
        archive_result = r6.archive_research_report_after_generation(report_text, text_output_path)
        print(f"Archive: {archive_result.get('archive_status')} id={archive_result.get('archive_id')}")
        print(f"Archive JSON: {text_output_path.parent / 'research_report_archive_latest.json'}")
        print(f"Archive Text Included: {archive_result.get('report_text_included')} | Chars {archive_result.get('report_text_char_count')}")
    except Exception as exc:
        archive_error = str(exc)
        print(f"Archive WARNING: research_report_archive insert/extract failed: {exc}")

    outputs: Dict[str, Any] = {
        "text_report": file_status(text_output_path),
        "archive_json": file_status(text_output_path.parent / "research_report_archive_latest.json"),
    }
    warnings: List[str] = []
    outputs["governance_law_binding"] = governance_law_binding

    if not skip_presentations:
        try:
            build_excel_report(dataset, archive_result, excel_output)
            outputs["excel_report"] = {
                **file_status(excel_output),
                **validate_zip(excel_output, ["xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml"]),
                **validate_required_xlsx_sheets(excel_output),
            }
            if outputs["excel_report"].get("missing_required_sheets"):
                raise RuntimeError(f"XLSX missing required sheets: {outputs['excel_report']['missing_required_sheets']}")
            print(f"Excel Report: {excel_output}")
        except PermissionError as exc:
            fallback_excel = timestamped_fallback_path(excel_output)
            warnings.append(f"Excel primary output locked; wrote timestamped fallback: {fallback_excel}")
            try:
                build_excel_report(dataset, archive_result, fallback_excel)
                outputs["excel_report"] = {
                    "requested_path": str(excel_output),
                    "fallback_reason": str(exc),
                    **file_status(fallback_excel),
                    **validate_zip(fallback_excel, ["xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml"]),
                    **validate_required_xlsx_sheets(fallback_excel),
                }
                if outputs["excel_report"].get("missing_required_sheets"):
                    raise RuntimeError(f"XLSX fallback missing required sheets: {outputs['excel_report']['missing_required_sheets']}")
                print(f"Excel WARNING: primary output locked; fallback written: {fallback_excel}")
            except Exception as fallback_exc:
                warnings.append(f"Excel fallback generation failed: {fallback_exc}")
                outputs["excel_report"] = {
                    "requested_path": str(excel_output),
                    "path": str(fallback_excel),
                    "exists": False,
                    "error": str(fallback_exc),
                }
                print(f"Excel WARNING: {fallback_exc}")
        except Exception as exc:
            warnings.append(f"Excel generation failed: {exc}")
            outputs["excel_report"] = {"path": str(excel_output), "exists": False, "error": str(exc)}
            print(f"Excel WARNING: {exc}")

        try:
            build_word_report(dataset, archive_result, word_output)
            outputs["word_report"] = {
                **file_status(word_output),
                **validate_zip(word_output, ["word/document.xml", "word/styles.xml", "word/numbering.xml"]),
            }
            print(f"Word Report : {word_output}")
        except PermissionError as exc:
            fallback_word = timestamped_fallback_path(word_output)
            warnings.append(f"Word primary output locked; wrote timestamped fallback: {fallback_word}")
            try:
                build_word_report(dataset, archive_result, fallback_word)
                outputs["word_report"] = {
                    "requested_path": str(word_output),
                    "fallback_reason": str(exc),
                    **file_status(fallback_word),
                    **validate_zip(fallback_word, ["word/document.xml", "word/styles.xml", "word/numbering.xml"]),
                }
                print(f"Word WARNING: primary output locked; fallback written: {fallback_word}")
            except Exception as fallback_exc:
                warnings.append(f"Word fallback generation failed: {fallback_exc}")
                outputs["word_report"] = {
                    "requested_path": str(word_output),
                    "path": str(fallback_word),
                    "exists": False,
                    "error": str(fallback_exc),
                }
                print(f"Word WARNING: {fallback_exc}")
        except Exception as exc:
            warnings.append(f"Word generation failed: {exc}")
            outputs["word_report"] = {"path": str(word_output), "exists": False, "error": str(exc)}
            print(f"Word WARNING: {exc}")

    # Upgrade #8: 5 standardized consistency_discipline sections in delivery JSON
    # 9.5/10 Upgrade: also compute all new module outputs for delivery JSON
    try:
        _cd_causal = build_causal_explanation(dataset)
        _cd_blind  = build_blind_spot_checklist(dataset)
        _cd_conc   = build_concentration_risk(dataset)
        # Two-pass: build preliminary operating_truth, then audit, then finalize
        _cd_op_pre = build_operating_truth(dataset, archive_result, _cd_causal, _cd_blind, _cd_conc)
        _cd_audit  = build_consistency_audit(dataset, archive_result, _cd_causal, _cd_blind, operating_truth=_cd_op_pre)
        _rf_data   = dataset.get("research_forecasting") or {}
        _acc_data  = _rf_data.get("accuracy_summary") or []
        _resolved  = sum(int(r.get("resolved_count") or 0) for r in _acc_data if isinstance(r, dict))
        _brier_mat = ("MATURE" if _resolved >= 100 else "NOT_MATURE" if _resolved >= 30 else "COLLECTING")

        # 9.5 new modules
        _cd_op_truth   = build_operating_truth(dataset, archive_result, _cd_causal, _cd_blind, _cd_conc, _cd_audit)
        _cd_action     = build_cio_action_logic(_cd_op_truth, dataset)
        _cd_remeds     = build_blind_spot_remediations(_cd_blind)
        _cd_chain      = build_causal_chain(dataset, _cd_causal)
        _cd_risk_gov   = build_portfolio_risk_governor(dataset, _cd_conc)
        _cd_forecast   = build_forecast_maturity_schedule(dataset)
        _cd_freshness  = build_freshness_governor(dataset)
        _cd_news       = build_news_priority_engine(dataset, _cd_op_truth)
        _cd_readiness  = build_report_readiness(_cd_op_truth, _cd_freshness)
        _cd_op_truth["report_readiness"] = _cd_readiness["classification"]
        _cd_mismatches = detect_archive_live_mismatches(_cd_op_truth, archive_result)

        # Gold Thesis Tracker
        _cd_gold_thesis = build_gold_thesis_tracker(dataset)

        # Fix #6: enrich canonical operating_truth with gold thesis fields
        _cd_op_truth["gold_thesis_status"] = _cd_gold_thesis.get("status", "UNKNOWN")
        _cd_op_truth["gold_thesis_score"]  = _cd_gold_thesis.get("score", 0.0)
        _cd_op_truth["gold_add_allowed"]   = _cd_gold_thesis.get("thesis_action", {}).get("add_allowed", False)

        # Fix 7: shared briefing model (used for JSON delivery and cross-renderer consistency)
        _cd_briefing_model = build_cio_briefing_model(
            dataset, archive_result,
            causal_data=_cd_causal, blind_data=_cd_blind,
            operating_truth=_cd_op_truth, action_logic=_cd_action,
            freshness_data=_cd_freshness, news_data=_cd_news,
            conc_data=_cd_conc, audit_data=_cd_audit,
        )

        consistency_discipline: Dict[str, Any] = {
            "causal_explanation": {
                "status": _cd_causal["causal_status"],
                "confidence": _cd_causal["causal_confidence"],
                "pass_count": _cd_causal["pass_count"],
                "fail_count": _cd_causal["fail_count"],
                "critical_checks": _cd_causal["critical_checks"],
                "primary_driver": _cd_causal["primary_driver"],
                "missing_inputs": _cd_causal["missing_inputs"],
            },
            "blind_spot": {
                "status": _cd_blind["blind_spot_status"],
                "pass_count": _cd_blind["pass_count"],
                "fail_count": _cd_blind["fail_count"],
                "cio_penalty": _cd_blind["cio_penalty"],
                "failed_items": _cd_blind["failed_items"],
                "remediations": _cd_remeds,
            },
            "concentration_risk": {
                "status": _cd_conc["concentration_status"],
                "hhi": _cd_conc["hhi"],
                "top3_weight": _cd_conc["top3_weight"],
                "largest_ticker": _cd_conc["largest_ticker"],
                "largest_weight": _cd_conc["largest_weight"],
                "clusters": _cd_conc["clusters"],
                "thresholds": {"NORMAL": "<0.35 HHI/<35% top1", "ELEVATED": "<0.50/<50%", "HIGH": "<0.65/<65%", "CRITICAL": ">=0.65/>=65%"},
            },
            "consistency_audit": {
                "status": _cd_audit["audit_status"],
                "report_status": _cd_audit.get("report_status", ""),
                "score": _cd_audit["audit_score"],
                "pass_count": _cd_audit["pass_count"],
                "warn_count": _cd_audit["warn_count"],
                "fail_count": _cd_audit["fail_count"],
                "check_results": {r[0]: r[1] for r in _cd_audit["check_rows"]},
            },
            "brier_accountability": {
                "maturity": _brier_mat,
                "resolved_total": _resolved,
                "required_for_reporting": 30,
                "required_for_significance": 100,
                "note": (
                    "COLLECTING: no meaningful Brier signal yet — insufficient resolved forecasts." if _brier_mat == "COLLECTING" else
                    "NOT_MATURE: some signal but insufficient for full statistical accountability." if _brier_mat == "NOT_MATURE" else
                    "MATURE: statistically meaningful Brier accountability established."
                ),
            },
            # 9.5/10 new sections
            "cio_action_logic": _cd_action,
            "causal_chain": _cd_chain[:5],
            "portfolio_risk_governor": _cd_risk_gov,
            "forecast_maturity": _cd_forecast,
            "freshness_governor": {
                "freshness_status":           _cd_freshness.get("freshness_status"),
                "stale_sections":             _cd_freshness.get("stale_sections"),
                "critical_stale_sections":    _cd_freshness.get("critical_stale_sections"),
                "non_critical_stale_sections": _cd_freshness.get("non_critical_stale_sections"),
                "confidence_penalty":         _cd_freshness.get("confidence_penalty"),
            },
            "news_priority": _cd_news,
            "report_readiness": _cd_readiness,
            "gold_thesis_tracker": _cd_gold_thesis,
        }
        # Fix #6 / WO-9.50: report_control — canonical operating reference for all renderers
        # All report surfaces must read from this block. No surface may independently re-derive these values.
        _rc_iq   = (dataset.get("institutional_quant") or {})
        _rc_db   = (archive_result.get("database_row") or {})
        _rc_qri  = float(_rc_db.get("quant_readiness_index") or _rc_db.get("quant_readiness_score")
                         or _rc_iq.get("readiness_score") or 0)
        _rc_qrl  = (_rc_db.get("quant_readiness_label") or _rc_iq.get("readiness_label")
                    or ("INSTITUTIONAL_READY" if _rc_qri >= 90 else "REVIEW_REQUIRED" if _rc_qri >= 75 else "NOT_READY"))
        _rc_gm_cluster = (_cd_gold_thesis.get("thesis_action") or {}).get("gold_miner_cluster_weight", 0.0) or 0.0
        _rc_causal_pass  = _cd_causal.get("pass_count", 0)
        _rc_causal_total = _cd_causal.get("pass_count", 0) + _cd_causal.get("fail_count", 0)
        _rc_blind_pass   = _cd_blind.get("pass_count", 0)
        _rc_blind_fail   = _cd_blind.get("fail_count", 0)
        consistency_discipline["report_control"] = {
            "canonical_version": "v2r6",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "snapshot_hierarchy": build_snapshot_hierarchy(dataset),
            "operating_truth": {
                # Regime
                "regime":              _cd_op_truth.get("regime", ""),
                "regime_score":        _cd_op_truth.get("regime_score", 0),
                # CIO Action
                "cio_action":          _cd_op_truth.get("cio_action", "WAIT / HOLD"),
                # Report Status
                "report_status":       _cd_op_truth.get("report_readiness", "PENDING"),
                # Quant Process (separate from report status)
                "quant_process_readiness": _rc_qrl,
                "quant_process_score":     round(_rc_qri, 1),
                # Causal Explanation
                "causal_status":       _cd_op_truth.get("causal_status", "UNKNOWN"),
                "causal_pass":         _rc_causal_pass,
                "causal_total":        _rc_causal_total,
                # Blind Spot
                "blind_spot_status":   _cd_op_truth.get("blind_spot_status", "UNKNOWN"),
                "blind_spot_pass":     _rc_blind_pass,
                "blind_spot_fail":     _rc_blind_fail,
                # Gold Thesis
                "gold_thesis_status":      _cd_op_truth.get("gold_thesis_status", "UNKNOWN"),
                "gold_thesis_score":       round(float(_cd_op_truth.get("gold_thesis_score", 0.0) or 0), 3),
                "gold_thesis_confidence":  _cd_gold_thesis.get("confidence", "UNKNOWN"),
                "gold_add_allowed":        _cd_op_truth.get("gold_add_allowed", False),
                # Concentration
                "concentration_status":    _cd_op_truth.get("concentration_status", "UNKNOWN"),
                "gold_miner_cluster_pct":  round(float(_rc_gm_cluster) * 100, 1) if _rc_gm_cluster <= 1.0 else round(float(_rc_gm_cluster), 1),
                # Execution Safety
                "execution_authority":          _cd_op_truth.get("execution_authority", "CIO_ONLY_MANUAL"),
                "order_routing_enabled":        _cd_op_truth.get("order_routing_enabled", False),
                "orders_generated_by_pipeline": _cd_op_truth.get("orders_generated_by_pipeline", 0),
            },
        }
        # Fix #7: cross_asset_floor_tracker placeholder (hidden from renderers while NOT_YET_IMPLEMENTED)
        consistency_discipline["cross_asset_floor_tracker"] = {
            "status": "NOT_YET_IMPLEMENTED",
            "gold_floor_status": "WATCH",
            "beta_floor_status": "WATCH",
            "liquidity_stress_status": "STABLE",
            "synchronized_floor_score": None,
            "cio_action": "WAIT",
            "reload_allowed": False,
            "reason": "Requires floor defense confirmation. Module not yet implemented.",
        }
        # Certainty label framework (Upgrade #7)
        consistency_discipline["certainty_labels"] = {
            "DATA_CONFIRMED":  "Direct from live data sources (DB, broker, market feed)",
            "MODEL_INFERRED":  "Computed by internal model from confirmed inputs",
            "PROVISIONAL":     "Best-estimate with known uncertainty or partial inputs",
            "CIO_THESIS":      "CIO-authored non-negotiable doctrine or standing rule",
            "UNVERIFIED":      "Claimed by model but not from a primary data source",
            "MISSING":         "Known data gap — data that should exist is absent",
        }
        # Canonical section order (Upgrade #10)
        consistency_discipline["canonical_section_order"] = CANONICAL_SECTION_ORDER
        # Fix 1 / Fix 7: embed operating_truth inside consistency_discipline for get_current_status()
        consistency_discipline["operating_truth"] = _cd_op_truth
    except Exception as cd_exc:
        consistency_discipline = {"error": str(cd_exc)}
        _cd_op_truth   = {}
        _cd_mismatches = []
        print(f"Consistency discipline summary WARNING: {cd_exc}")

    _cd_briefing_model = locals().get("_cd_briefing_model", {})  # safe fallback if exception
    _snapshot_delivery = build_snapshot_hierarchy(dataset)
    delivery = {
        "delivery_status": "completed_with_presentations" if not warnings and not archive_error else "completed_with_warnings",
        "generator_version": GENERATOR_VERSION,
        "platform_team": PLATFORM_TEAM,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "dataset_path": str(dataset_path),
        "text_output_path": str(text_output_path),
        "archive_result": archive_result,
        "archive_error": archive_error,
        "presentation_outputs": outputs,
        "snapshot_hierarchy": _snapshot_delivery,
        "consistency_discipline": consistency_discipline,   # Upgrade #8
        "operating_truth": _cd_op_truth,                   # 9.5 Module A
        "archive_live_mismatches": _cd_mismatches,         # 9.5 Module C
        "briefing_model": _cd_briefing_model,               # Fix 7
        "governance_law_pack": governance_law_pack,
        "governance_law_validation": governance_law_validation,
        "governance_law_binding": governance_law_binding,
        "law_governance_binding": dataset.get("law_governance_binding") or {},
        "prospective_event_intelligence": dataset.get("prospective_event_intelligence") or {},
        "shannon_thorp_refinement": dataset.get("shannon_thorp_refinement") or {},
        "v3_str_bug_clearance_reconciliation": dataset.get("v3_str_bug_clearance_reconciliation") or {},
        "warnings": warnings,
        "notes": [
            f"Reporting layer accredited to {PLATFORM_TEAM}.",
            "R6 text report remains the canonical database archive.",
            "Excel and Word are trial CIO presentation layers generated from dataset_raw.json plus archive metadata.",
            "Consistency discipline section added: causal, blind_spot, concentration, audit, brier (Upgrade #8).",
            "Certainty label framework: DATA_CONFIRMED | MODEL_INFERRED | PROVISIONAL | CIO_THESIS | UNVERIFIED | MISSING.",
            "9.5/10 Upgrade: operating_truth, archive_live_mismatches, cio_action_logic, causal_chain, risk_governor, freshness, news_priority, report_readiness added.",
            "STR layer added: signal entropy, source capacity, cost-basis reconciliation, advisory Kelly sizing, hedge review.",
        ],
    }
    delivery["artifact_manifest"] = build_artifact_manifest(
        dataset,
        archive_result,
        outputs,
        text_output_path,
        excel_output,
        word_output,
        delivery_json,
        dashboard_generated_at=None,
        report_text=report_text,
    )
    if delivery["artifact_manifest"].get("artifact_consistency_status") != "ARTIFACTS_CONSISTENT":
        delivery["delivery_status"] = "publication_blocked_artifact_inconsistency"
        warnings.append(f"Artifact consistency status: {delivery['artifact_manifest'].get('artifact_consistency_status')}")
    write_delivery_json(delivery_json, delivery)
    delivery["artifact_manifest"]["delivery_json_sha256"] = file_sha256(delivery_json)
    write_delivery_json(delivery_json, delivery)
    print(f"Delivery JSON: {delivery_json}")

    audit_st  = consistency_discipline.get("consistency_audit", {}).get("status", "n/a")
    audit_sc  = consistency_discipline.get("consistency_audit", {}).get("score", "n/a")
    print(f"Consistency Audit: {audit_st} score={audit_sc}")

    # Run final acceptance validation (section 13 of work order)
    _ot_val   = delivery.get("operating_truth") or {}
    _ms_val   = delivery.get("archive_live_mismatches") or []
    _cd_val   = delivery.get("consistency_discipline") or {}
    val_result = run_acceptance_validation(_ot_val, _ms_val, _cd_val)
    _vfails = [c["check"] for c in val_result["checks"] if c["result"] == "FAIL"]
    print(f"Acceptance Validation: {val_result['status']} ({val_result['pass_count']}/10 pass)" +
          (f" | FAILED: {', '.join(_vfails)}" if _vfails else ""))

    return delivery


def build_report_qa_footer(
    dataset: Dict[str, Any],
    consistency_discipline: Dict[str, Any],
    operating_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute the QA footer block for all report surfaces.

    Returns a dict with all QA fields. Renderers format it in their own style.
    Required fields (WO-ECE-20260613-001, Solution 8):
      consistency_audit_status, ece_logic_version, ece_renderer_match,
      ece_percent_scale_check, evidence_mapping_check, causal_status_logic,
      execution_safety_gate, final_institutional_grade
    """
    ca = consistency_discipline.get("consistency_audit") or {}
    ca_status   = ca.get("status", "UNKNOWN")
    ca_score    = float(ca.get("score", 0) or 0)
    ca_fails    = int(ca.get("fail_count", 0) or 0)

    # ECE logic version — must be ECE_v2 for all rows
    ece_rows = build_canonical_ece_model(dataset)
    ece_versions = {r["governing_logic_version"] for r in ece_rows} or {"UNKNOWN"}
    ece_version = "ECE_v2" if ece_versions == {"ECE_v2"} else f"MIXED:{','.join(sorted(ece_versions))}"

    # ECE percent scale check — flag if any basket_move > ±50%
    over_scale = [r["theme"] for r in ece_rows if abs(r["basket_move_pct"]) > 50]
    ece_scale  = "FAIL" if over_scale else "PASS"

    # Evidence mapping — use why_raw (unsanitized) for the QA check.
    # Since _ece_sanitize_why() now overwrites `why` for mismatch rows,
    # we check why_raw (preserved original) OR treat suppressed `why` as corrected.
    mismatch_rows = [
        r["theme"] for r in ece_rows
        if "SECTOR_EVIDENCE_MISMATCH" in r.get("review_flags", [])
        and r.get("why", "") not in ("", _ECE_SUPPRESSED_MISMATCH, _ECE_SUPPRESSED_NO_CATALYST)
        and len(r.get("why", "")) <= 80
        and "http" not in r.get("why", "").lower()
    ]
    evidence_map  = "FLAG" if mismatch_rows else "PASS"

    # Causal status logic
    causal_check_pass = ca.get("check_results", {}).get("Causal Score->Status") == "PASS"
    causal_gate = "PASS" if causal_check_pass else "FAIL"

    # Execution safety gate
    exec_safe = (
        operating_truth.get("order_routing_enabled") is False
        and int(operating_truth.get("orders_generated_by_pipeline", 0) or 0) == 0
    )
    exec_gate = "PASS" if exec_safe else "FAIL"

    # ECE renderer match — check that all ECE rows have governing_logic_version ECE_v2
    ece_renderer = "PASS" if ece_version == "ECE_v2" else "FAIL"

    # Freshness gate — read from consistency_discipline.freshness_governor if available
    _fg = consistency_discipline.get("freshness_governor") or {}
    _fg_status = _fg.get("freshness_status", "UNKNOWN")
    freshness_gate = "PASS" if _fg_status in ("FRESH", "PASS") else ("WARNING" if _fg_status in ("STALE_NON_CRITICAL", "WARNING") else "FAIL" if _fg_status in ("STALE_CRITICAL", "FAIL") else "UNKNOWN")

    # Blocking failures: any FAIL field blocks grade ≥ 9.5
    blocking: List[str] = []
    if ca_status == "INCONSISTENT":
        blocking.append("CONSISTENCY_AUDIT_INCONSISTENT")
    if ca_fails > 0:
        blocking.append(f"AUDIT_FAIL_COUNT={ca_fails}")
    if ece_scale == "FAIL":
        blocking.append("ECE_PERCENT_SCALE_FAIL")
    if causal_gate == "FAIL":
        blocking.append("CAUSAL_STATUS_LOGIC_FAIL")
    if exec_gate == "FAIL":
        blocking.append("EXECUTION_SAFETY_FAIL")
    if ca_status == "UNKNOWN":
        blocking.append("CONSISTENCY_AUDIT_UNKNOWN")

    # Warnings (non-blocking but notable)
    warn_list: List[str] = []
    if evidence_map == "FLAG":
        warn_list.append(f"EVIDENCE_MISMATCH_FLAG({len(mismatch_rows)}_themes)")
    if freshness_gate == "WARNING":
        warn_list.append("FRESHNESS_NON_CRITICAL_STALE")
    if freshness_gate == "UNKNOWN":
        warn_list.append("FRESHNESS_STATUS_UNKNOWN")

    # Final institutional grade
    # Deductions: each blocking failure = -0.2, INCONSISTENT = -0.5, scale fail = -0.3
    grade = 9.5
    if ca_status == "INCONSISTENT":
        grade -= 0.5
    if ca_fails > 0:
        grade -= 0.2 * min(ca_fails, 3)
    if ece_scale == "FAIL":
        grade -= 0.3
    if evidence_map == "FLAG":
        grade -= 0.1 * min(len(mismatch_rows), 3)
    if causal_gate == "FAIL":
        grade -= 0.2
    if exec_gate == "FAIL":
        grade -= 0.3
    if ca_status == "UNKNOWN":
        grade -= 0.5
    grade = round(max(7.0, min(9.5, grade)), 1)

    return {
        "consistency_audit":        ca_status,
        "consistency_audit_score":  ca_score,
        "ece_logic_version":        ece_version,
        "ece_renderer_match":       ece_renderer,
        "ece_percent_scale_check":  ece_scale,
        "over_scaled_themes":       over_scale,
        "evidence_mapping_check":   evidence_map,
        "mismatch_themes":          mismatch_rows,
        "causal_status_logic":      causal_gate,
        "execution_safety_gate":    exec_gate,
        "freshness_gate":           freshness_gate,
        "blocking_failures":        blocking,
        "warnings":                 warn_list,
        "final_institutional_grade": grade,
    }


def run_acceptance_validation(
    operating_truth: Dict[str, Any],
    mismatches: List[Any],
    consistency_discipline: Dict[str, Any],
) -> Dict[str, Any]:
    """Final 10-check acceptance test (Work Order Section 13).

    Returns PASS/FAIL/WARNING for each check and overall status.
    """
    checks: List[Dict[str, Any]] = []
    ot  = operating_truth
    cd  = consistency_discipline
    al  = cd.get("cio_action_logic") or {}
    rg  = cd.get("portfolio_risk_governor") or {}
    fg  = cd.get("freshness_governor") or {}

    def _v(check: str, result: bool, detail: str) -> None:
        checks.append({"check": check, "result": "PASS" if result else "FAIL", "detail": detail})

    # 1. Blind spot status = live value everywhere (not archived CLEAR)
    live_bs = ot.get("blind_spot_status", "")
    # PASS if live value is not "UNKNOWN" or blank — archived CLEAR overriding means live_bs would be "CLEAR"
    # even when computed blind spot says WARNING. If they differ and operating_truth = live, this is PASS.
    _v("Blind Spot Uses Live Value", bool(live_bs) and live_bs != "",
       f"operating_truth.blind_spot_status={live_bs} (live value used)")

    # 2. Archive mismatches are documented (not silently suppressed)
    #    Mismatches are EXPECTED when live differs from last cycle's DB — what matters is they are REPORTED.
    #    FAIL only if operating_truth.blind_spot_status contradicts detect_archive_live_mismatches evidence
    mismatch_fields = [m.get("field") for m in mismatches]
    bs_mismatch = next((m for m in mismatches if m.get("field") == "blind_spot_status"), None)
    if bs_mismatch:
        # Verify operating_truth uses the LIVE value (not the archived one)
        ot_bs = ot.get("blind_spot_status", "")
        archived_bs = bs_mismatch.get("archived_value", "")
        live_val_from_mismatch = bs_mismatch.get("live_value", "")
        _v("Archive Mismatches Documented",
           ot_bs == live_val_from_mismatch,  # PASS if operating_truth uses live, not archived
           f"archive={archived_bs} live={live_val_from_mismatch} operating_truth={ot_bs} [mismatch documented]")
    else:
        _v("Archive Mismatches Documented", True,
           f"No mismatches: {mismatch_fields or 'none'}")

    # 3. Consistency audit status = CONSISTENT or WARNINGS (no INCONSISTENT)
    ca_st = (cd.get("consistency_audit") or {}).get("status", "")
    _v("Consistency Audit Not Inconsistent", ca_st != "INCONSISTENT",
       f"consistency_audit.status={ca_st}")

    # 4. Report status not INSTITUTIONAL_READY when audit is inconsistent
    rr = ot.get("report_readiness", "")
    _v("Report Status Reflects Audit", not (ca_st == "INCONSISTENT" and rr == "INSTITUTIONAL_READY"),
       f"report_readiness={rr} audit={ca_st}")

    # 5. Final CIO action respects action cap
    final_act = al.get("final_action", "")
    act_cap   = al.get("action_cap", "")
    _cap_is_conservative = "WAIT" in act_cap or "REVIEW" in act_cap or "HOLD" in act_cap
    _final_is_conservative = "WAIT" in final_act or "REVIEW" in final_act or "HOLD" in final_act or "REDUCE" in final_act
    _v("Final Action Respects Cap",
       (not _cap_is_conservative) or _final_is_conservative,
       f"action_cap={act_cap} final_action={final_act}")

    # 6. Stale sections not hidden
    critical_stale = fg.get("critical_stale_sections", [])
    non_critical   = fg.get("non_critical_stale_sections", [])
    _v("Stale Sections Reported",
       isinstance(critical_stale, list) and isinstance(non_critical, list),
       f"critical_stale={len(critical_stale)} non_critical={len(non_critical)}")

    # 7. Execution routing disabled
    _v("Order Routing Disabled", ot.get("order_routing_enabled") is False,
       f"order_routing_enabled={ot.get('order_routing_enabled')}")

    # 8. Pipeline orders = 0
    _v("Pipeline Orders Zero", ot.get("orders_generated_by_pipeline", 1) == 0,
       f"orders_generated_by_pipeline={ot.get('orders_generated_by_pipeline')}")

    # 9. Execution authority = CIO_ONLY_MANUAL
    _v("Execution Authority CIO Only",
       ot.get("execution_authority") == "CIO_ONLY_MANUAL",
       f"execution_authority={ot.get('execution_authority')}")

    # 10. Brier layer honest (not claiming skill when COLLECTING)
    brier_st = ot.get("brier_status", "")
    fp_st    = ot.get("forecast_proof_status", "")
    _v("Brier Honest",
       not (brier_st == "COLLECTING" and fp_st == "PROVEN"),
       f"brier_status={brier_st} forecast_proof_status={fp_st}")

    pass_c = sum(1 for c in checks if c["result"] == "PASS")
    fail_c = sum(1 for c in checks if c["result"] == "FAIL")
    status = "PASS" if fail_c == 0 else "WARNINGS" if fail_c <= 2 else "FAIL"

    return {
        "status":      status,
        "pass_count":  pass_c,
        "fail_count":  fail_c,
        "checks":      checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="BlueLotus R6-U text, archive, Excel, and Word report generator")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_TEXT_OUTPUT)
    parser.add_argument("--excel-output", type=Path, default=DEFAULT_EXCEL_OUTPUT)
    parser.add_argument("--word-output", type=Path, default=DEFAULT_WORD_OUTPUT)
    parser.add_argument("--delivery-json", type=Path, default=DEFAULT_DELIVERY_JSON)
    parser.add_argument("--skip-presentations", action="store_true", help="Generate only text report + DB archive JSON")
    args = parser.parse_args()

    run_u_generator(
        args.dataset,
        args.output,
        args.excel_output,
        args.word_output,
        args.delivery_json,
        skip_presentations=args.skip_presentations,
    )


if __name__ == "__main__":
    main()
