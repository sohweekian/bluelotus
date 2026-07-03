from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from chief_strategist_governance.report_renderers import governance_is_active, render_csg_text_section
except Exception:
    governance_is_active = None
    render_csg_text_section = None

try:
    from cio_context_capsule.renderers import (
        capsule_is_active,
        master_prompt_is_active,
        render_cio_context_text_section,
        render_master_prompt_text_section,
    )
except Exception:
    capsule_is_active = None
    master_prompt_is_active = None
    render_cio_context_text_section = None
    render_master_prompt_text_section = None


def _load_acms_cop_section() -> str:
    path = PROJECT_ROOT / "reports" / "acms_cop_latest.txt"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _load_dataset() -> Dict[str, Any]:
    path = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _require_csg(dataset: Dict[str, Any]) -> None:
    if not governance_is_active or not governance_is_active(dataset):
        raise RuntimeError("Chief Strategist report blocked: CSG v3.5 missing or inactive.")


def _require_cio_context(dataset: Dict[str, Any]) -> None:
    if not capsule_is_active or not capsule_is_active(dataset):
        raise RuntimeError("Chief Strategist report blocked: CIO Context Capsule v3.5 missing or inactive.")


def _require_master_prompt(dataset: Dict[str, Any]) -> None:
    if not master_prompt_is_active or not master_prompt_is_active(dataset):
        raise RuntimeError("Chief Strategist report blocked: Master Prompt missing or inactive.")


def render_strategist_report(briefing: Dict[str, Any]) -> str:
    dataset = _load_dataset()
    _require_master_prompt(dataset)
    _require_cio_context(dataset)
    _require_csg(dataset)
    lines = [
        "BlueLotus V3 Chief Strategist Report",
        "",
        f"Cycle: {briefing.get('cycle_id')}",
        f"Posture: {briefing.get('recommended_posture')}",
        "",
        str(briefing.get("summary", "")),
        "",
        "CIO attention items:",
    ]
    items = briefing.get("cio_attention_items", [])
    lines.extend(f"- {item}" for item in items) if items else lines.append("- None")
    lines.extend([
        "",
        "Manual execution required: YES",
        "No automatic orders generated.",
    ])
    acms_section = _load_acms_cop_section()
    if acms_section:
        lines.extend(["", acms_section])
    if render_master_prompt_text_section:
        lines.extend(["", render_master_prompt_text_section(dataset).strip()])
    if render_cio_context_text_section:
        lines.extend(["", render_cio_context_text_section(dataset).strip()])
    if render_csg_text_section:
        lines.extend(["", render_csg_text_section(dataset).strip()])
    return "\n".join(lines)
