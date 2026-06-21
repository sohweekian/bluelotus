from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("PEI Event Gate", ["prospective_event_intelligence"], ["pei_gate_status"])
    pei = dataset.get("prospective_event_intelligence") if isinstance(dataset.get("prospective_event_intelligence"), dict) else {}
    text = str(pei).upper()
    blocked = any(token in text for token in ("WARSH", "BOJ", "BLOCKED", "PEACE", "EVENT_RISK"))
    stage["pei_gate_status"] = "MACRO_EVENT_REVIEW" if blocked else "CLEAR"
    stage["macro_gate_active"] = blocked
    return stage

