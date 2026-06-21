from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("Sleeve Rule", ["cio_context_capsule", "active_sleeve_rules"], ["sleeve_rule_status"])
    capsule = dataset.get("cio_context_capsule") if isinstance(dataset.get("cio_context_capsule"), dict) else {}
    rules = capsule.get("active_sleeve_rules") if isinstance(capsule.get("active_sleeve_rules"), dict) else dataset.get("active_sleeve_rules")
    rules = rules if isinstance(rules, dict) else {}
    stage["sleeve_rule_count"] = len(rules)
    stage["sleeve_rule_status"] = "AVAILABLE" if rules else "NO_ACTIVE_SLEEVE_RULES"
    if not rules:
        stage["warnings"].append("no_sleeve_rules_available")
    return stage

