from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from acms_cop.common import compact_text, latest_v3_cycle_dir, safe_float


def extract_agent_cycles(cycle_dir: str | Path | None = None) -> List[Dict[str, Any]]:
    base = Path(cycle_dir) if cycle_dir else latest_v3_cycle_dir()
    if not base:
        return []
    reports_dir = base / "agent_reports"
    if not reports_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(reports_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        findings = data.get("key_findings") if isinstance(data.get("key_findings"), list) else []
        risk_flags = data.get("risk_flags") if isinstance(data.get("risk_flags"), list) else []
        agent_name = compact_text(data.get("agent_name") or data.get("agent_id") or path.stem, 100)
        agent_role = compact_text(data.get("agent_role") or data.get("role") or "", 100)
        rows.append({
            "agent_name": agent_name,
            "agent_role": agent_role,
            "model_version": compact_text(data.get("model_version") or data.get("model") or "Qwen3:4B", 100),
            "prompt_version": compact_text(data.get("prompt_version") or data.get("prompt_architecture_version") or "", 100),
            "recommendation": compact_text(data.get("recommendation_to_chief_strategist") or data.get("recommendation") or "", 100),
            "confidence": safe_float(data.get("confidence")),
            "acms_layer_focus": compact_text(data.get("acms_layer_focus") or "", 80),
            "acms_state_claim": compact_text(data.get("acms_state_claim") or "", 80),
            "dissent_flag": bool(data.get("requires_cio_attention") or risk_flags),
            "dissent_reason": compact_text("; ".join(str(x) for x in risk_flags), 1000),
            "accepted_by_chief_strategist": None,
            "overridden_by_chief_strategist": None,
            "outcome_correct": None,
            "agent_brier_score": None,
            "false_positive_flag": None,
            "false_negative_flag": None,
            "overclaiming_flag": None,
            "summary": compact_text("; ".join(str(x) for x in findings), 1800),
            "raw_output_path": str(path),
        })
    return rows
