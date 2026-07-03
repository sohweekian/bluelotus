from __future__ import annotations

from typing import Any, Dict, List


READ_FIRST_TITLE = "CIO CONTEXT CAPSULE - READ FIRST"
READ_FIRST_TITLE_UNICODE = "CIO CONTEXT CAPSULE — READ FIRST"
MASTER_PROMPT_TITLE = "CHIEF STRATEGIST MASTER PROMPT / MODUS OPERANDI - READ FIRST"
MASTER_PROMPT_TITLE_UNICODE = "CHIEF STRATEGIST MASTER PROMPT / MODUS OPERANDI — READ FIRST"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (list, tuple)):
        return "; ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_text(v)}" for k, v in value.items())
    return str(value)


def get_capsule(dataset: Dict[str, Any]) -> Dict[str, Any]:
    capsule = dataset.get("cio_context_capsule") or {}
    return capsule if isinstance(capsule, dict) else {}


def get_master_prompt(dataset: Dict[str, Any]) -> Dict[str, Any]:
    prompt = dataset.get("chief_strategist_master_prompt") or {}
    return prompt if isinstance(prompt, dict) else {}


def master_prompt_is_active(dataset: Dict[str, Any]) -> bool:
    prompt = get_master_prompt(dataset)
    return (
        prompt.get("status") == "ACTIVE"
        and prompt.get("mandatory_for_chief_strategist") is True
        and prompt.get("read_first") is True
        and int(prompt.get("priority", -1)) == 0
        and bool(prompt.get("prompt_hash"))
        and bool(prompt.get("master_prompt_text"))
    )


def capsule_is_active(dataset: Dict[str, Any]) -> bool:
    capsule = get_capsule(dataset)
    doctrine = capsule.get("core_doctrine") or {}
    return (
        capsule.get("status") == "ACTIVE"
        and capsule.get("mandatory_for_all_chief_strategist_replies") is True
        and doctrine.get("execution_authority") == "CIO_ONLY_MANUAL"
        and doctrine.get("order_routing_enabled") is False
        and int(doctrine.get("system_generated_orders") or 0) == 0
        and bool(capsule.get("capsule_hash"))
    )


def build_master_prompt_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    prompt = get_master_prompt(dataset)
    rows: List[List[Any]] = [
        ["Field", "Value", "Certainty", "Source Layer"],
        ["Version", prompt.get("version", ""), "DATA_CONFIRMED", "chief_strategist_master_prompt"],
        ["Status", prompt.get("status", ""), "DATA_CONFIRMED", "chief_strategist_master_prompt"],
        ["Mandatory for Chief Strategist", prompt.get("mandatory_for_chief_strategist", ""), "GOVERNANCE_RULE", "chief_strategist_master_prompt"],
        ["Read First", prompt.get("read_first", ""), "GOVERNANCE_RULE", "chief_strategist_master_prompt"],
        ["Priority", prompt.get("priority", ""), "GOVERNANCE_RULE", "chief_strategist_master_prompt"],
        ["Prompt Hash", prompt.get("prompt_hash", ""), "DATA_CONFIRMED", "chief_strategist_master_prompt"],
        ["Core Instruction", prompt.get("core_instruction", ""), "GOVERNANCE_RULE", "chief_strategist_master_prompt"],
        ["Source Priority", _text(prompt.get("source_priority") or []), "GOVERNANCE_RULE", "source_priority"],
        ["Required Response Sequence", _text(prompt.get("required_response_sequence") or []), "GOVERNANCE_RULE", "required_response_sequence"],
        ["Active Strategy Defaults", _text(prompt.get("active_strategy_defaults") or {}), "CIO_RULE", "active_strategy_defaults"],
        ["Sleeve Rules", _text(prompt.get("sleeve_rules") or {}), "CIO_RULE", "sleeve_rules"],
        ["Kill Conditions", _text(prompt.get("kill_conditions") or []), "GOVERNANCE_RULE", "kill_conditions"],
        ["Forbidden Behaviors", _text(prompt.get("forbidden_behaviors") or []), "GOVERNANCE_RULE", "forbidden_behaviors"],
        ["Self-Check Questions", _text(prompt.get("self_check_questions") or []), "GOVERNANCE_RULE", "self_check_questions"],
        ["Full Master Prompt Text", prompt.get("master_prompt_text", ""), "GOVERNANCE_RULE", "master_prompt_text"],
    ]
    return rows


def render_master_prompt_text_section(dataset: Dict[str, Any], unicode_title: bool = False) -> str:
    prompt = get_master_prompt(dataset)
    title = MASTER_PROMPT_TITLE_UNICODE if unicode_title else MASTER_PROMPT_TITLE
    line = "=" * 78
    short = "=" * 60
    lines = [
        line,
        title,
        short,
        f"Version: {prompt.get('version', 'MISSING')}",
        f"Status: {prompt.get('status', 'MISSING')}",
        f"Mandatory for Chief Strategist: {_text(prompt.get('mandatory_for_chief_strategist'))}",
        f"Read First: {_text(prompt.get('read_first'))}",
        f"Priority: {prompt.get('priority', '')}",
        f"Prompt Hash: {prompt.get('prompt_hash', '')}",
        "",
        "Chief Strategist Master Prompt: ACTIVE / MANDATORY / READ FIRST",
        f"Prompt Version: {prompt.get('version', '')}",
        f"Prompt Hash: {prompt.get('prompt_hash', '')}",
        "CIO Context Capsule Status: ACTIVE",
        "Execution Authority: CIO_ONLY_MANUAL",
        "Order Routing Enabled: FALSE",
        "System Orders Generated: 0",
        "",
        "Core Instruction:",
        prompt.get("core_instruction", ""),
        "",
        "Source Priority:",
    ]
    for idx, item in enumerate(prompt.get("source_priority") or [], start=1):
        lines.append(f"{idx}. {item}")
    lines.extend(["", "Required Response Sequence:"])
    for idx, item in enumerate(prompt.get("required_response_sequence") or [], start=1):
        lines.append(f"{idx}. {item}")
    lines.extend(["", "Active Strategy Defaults:"])
    for key, value in (prompt.get("active_strategy_defaults") or {}).items():
        lines.append(f"- {key}: {_text(value)}")
    lines.extend(["", "Sleeve Rules:"])
    for key, value in (prompt.get("sleeve_rules") or {}).items():
        lines.append(f"- {key}: {_text(value)}")
    lines.extend(["", "Kill Conditions:"])
    for item in prompt.get("kill_conditions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "Forbidden Behaviors:"])
    for item in prompt.get("forbidden_behaviors") or []:
        lines.append(f"- {item}")
    lines.extend(["", "Self-Check Questions:"])
    for item in prompt.get("self_check_questions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "Full Master Prompt Text:", prompt.get("master_prompt_text", ""), line])
    return "\n".join(lines).strip() + "\n"


def build_cio_context_rows(dataset: Dict[str, Any]) -> List[List[Any]]:
    capsule = get_capsule(dataset)
    doctrine = capsule.get("core_doctrine") or {}
    decision = capsule.get("latest_cio_layer_decision") or {}
    record = capsule.get("cio_three_step_record") or {}
    sleeves = capsule.get("active_sleeve_rules") or {}
    rows: List[List[Any]] = [
        ["section_title", READ_FIRST_TITLE, "DATA_CONFIRMED", "cio_context_capsule"],
        ["version", capsule.get("version", ""), "DATA_CONFIRMED", "cio_context_capsule"],
        ["mandatory_for_chief_strategist", capsule.get("mandatory_for_all_chief_strategist_replies", ""), "DATA_CONFIRMED", "cio_context_capsule"],
        ["latest_cio_decision", _text(decision), "CIO_RECORD", "latest_cio_layer_decision"],
        ["strategic_thinking", _text(record.get("strategic_thinking")), "CIO_RECORD", "cio_three_step_record"],
        ["strategic_planning", _text(record.get("strategic_planning")), "CIO_RECORD", "cio_three_step_record"],
        ["strategic_execution", _text(record.get("strategic_execution")), "CIO_RECORD", "cio_three_step_record"],
        ["execution_authority", doctrine.get("execution_authority", ""), "GOVERNANCE_RULE", "core_doctrine"],
        ["order_routing_enabled", doctrine.get("order_routing_enabled", ""), "GOVERNANCE_RULE", "core_doctrine"],
        ["system_orders_generated", doctrine.get("system_generated_orders", ""), "GOVERNANCE_RULE", "core_doctrine"],
        ["second_tranche_authorized", "FALSE", "GOVERNANCE_RULE", "core_doctrine"],
        ["dca_rule", doctrine.get("dca_rule", ""), "GOVERNANCE_RULE", "core_doctrine"],
        ["cash_fortress", _text(sleeves.get("cash_fortress")), "CIO_RULE", "active_sleeve_rules"],
        ["gold_miners_policy", _text(sleeves.get("gold_miners")), "CIO_RULE", "active_sleeve_rules"],
        ["banks_policy", _text(sleeves.get("banks_bac_wfc")), "CIO_RULE", "active_sleeve_rules"],
        ["high_beta_policy", _text(sleeves.get("high_beta_satellites")), "CIO_RULE", "active_sleeve_rules"],
        ["pl_asts_policy", _text(sleeves.get("foundational_tactical_cash_engine")), "CIO_RULE", "active_sleeve_rules"],
        ["kill_conditions", _text(capsule.get("kill_conditions") or []), "GOVERNANCE_RULE", "kill_conditions"],
        ["bootstrap_prompt", ((capsule.get("conversation_bootstrap_prompt") or {}).get("text") or ""), "GOVERNANCE_RULE", "conversation_bootstrap_prompt"],
        ["capsule_hash", capsule.get("capsule_hash", ""), "DATA_CONFIRMED", "cio_context_capsule"],
    ]
    return rows


def render_cio_context_text_section(dataset: Dict[str, Any], unicode_title: bool = False) -> str:
    capsule = get_capsule(dataset)
    doctrine = capsule.get("core_doctrine") or {}
    decision = capsule.get("latest_cio_layer_decision") or {}
    record = capsule.get("cio_three_step_record") or {}
    thinking = record.get("strategic_thinking") or {}
    planning = record.get("strategic_planning") or {}
    execution = record.get("strategic_execution") or {}
    sleeves = capsule.get("active_sleeve_rules") or {}
    title = READ_FIRST_TITLE_UNICODE if unicode_title else READ_FIRST_TITLE
    line = "=" * 78
    lines = [
        line,
        f"  {title}",
        line,
        f"Version: {capsule.get('version', 'MISSING')}",
        f"Mandatory for Chief Strategist: {_text(capsule.get('mandatory_for_all_chief_strategist_replies'))}",
        f"Capsule Hash: {capsule.get('capsule_hash', '')}",
        "",
        "Latest CIO Decision:",
        f"CIO Manual Event-Scout Override ahead of probable peace-deal relief rally. Classification: {decision.get('classification', '')}. Not full risk-on: {_text(decision.get('not_full_risk_on'))}. Not second tranche: {_text(decision.get('not_second_tranche'))}.",
        "",
        "Strategic Thinking:",
        thinking.get("summary", ""),
        f"Core Interpretation: {thinking.get('core_interpretation', '')}",
        f"Market Read: {thinking.get('market_read', '')}",
        "",
        "Strategic Planning:",
        f"Gold miners remain at 5D support bids: {planning.get('gold_miners', '')}",
        f"Banks: {planning.get('banks', '')}",
        f"High beta satellites: {planning.get('high_beta', '')}",
        f"PL/ASTS tactical cash engine: {planning.get('foundational_tactical_cash_engine', '')}",
        f"DCA: {planning.get('dca_rule', '')}",
        "",
        "Strategic Execution:",
        f"{execution.get('positioning_status', '')} Execution mode: {execution.get('execution_mode', doctrine.get('execution_authority', ''))}. No system orders. No routing. Scout positioning only, not second tranche.",
        "",
        "Active Sleeve Rules:",
    ]
    for key, sleeve in sleeves.items():
        if isinstance(sleeve, dict):
            lines.append(f"- {key}: {sleeve.get('current_policy', '')} | {sleeve.get('allowed', '')} | Forbidden: {sleeve.get('forbidden', '')}")
    lines.extend([
        "",
        "Kill Conditions:",
        "- " + "\n- ".join(capsule.get("kill_conditions") or []),
        "",
        "Bootstrap Instruction:",
        (capsule.get("conversation_bootstrap_prompt") or {}).get("text", ""),
        "",
        "Hard Rule:",
        doctrine.get("tactical_score_rule", ""),
        line,
    ])
    return "\n".join(lines).strip() + "\n"


def prepend_cio_context_text_section(report_text: str, dataset: Dict[str, Any]) -> str:
    if READ_FIRST_TITLE in report_text or READ_FIRST_TITLE_UNICODE in report_text:
        return report_text
    return render_cio_context_text_section(dataset).rstrip() + "\n\n" + report_text.lstrip()


def prepend_master_prompt_and_cio_context(report_text: str, dataset: Dict[str, Any]) -> str:
    text = prepend_cio_context_text_section(report_text, dataset)
    if MASTER_PROMPT_TITLE in text or MASTER_PROMPT_TITLE_UNICODE in text:
        return text
    return render_master_prompt_text_section(dataset).rstrip() + "\n\n" + text.lstrip()
