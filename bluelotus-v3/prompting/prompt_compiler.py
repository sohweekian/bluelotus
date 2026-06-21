"""
BlueLotus V3 — Prompt Compiler
================================
Assembles the final system prompt and user prompt for each agent
from the 5-layer prompt architecture.

LAYER ASSEMBLY ORDER:
  System Prompt:
    [1] universal/bluelotus_constitution.md
    [2] universal/safety_doctrine.md
    [3] agents/{agent_id}/role.md

  User Prompt:
    [4] universal/no_generic_output_rule.md
    [5] universal/json_only_rule.md
    [6] agents/{agent_id}/template.md  (as output format hint)
    [7] desk_context (JSON — from ContextBuilder)
    [8] memory_context (JSON — from MemoryRetriever, if any)
    [9] cycle metadata (cycle_id, must_answer questions, evidence_priority)

ANTI-HARDCODE RULE:
  - All prompt file paths come from config/prompt_registry.yaml.
  - Path resolution uses BLUELOTUS_PROJECT_ROOT env var.
  - Never hardcode a file path inside this module.

INTEGRATION:
  This module is the single assembly point. base_agent.py's system_prompt()
  and user_prompt() methods should delegate here once migrated.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------

_REGISTRY: Optional[Dict[str, Any]] = None
_PROMPT_CACHE: Dict[str, str] = {}


def _load_registry() -> Dict[str, Any]:
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    path_env = os.getenv("PROMPT_REGISTRY_PATH")
    if path_env:
        path = Path(path_env)
    else:
        project_root = Path(os.getenv("BLUELOTUS_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
        path = project_root / "config" / "prompt_registry.yaml"
    if not path.exists():
        raise FileNotFoundError(f"prompt_registry.yaml not found at {path}")
    with path.open(encoding="utf-8") as f:
        _REGISTRY = yaml.safe_load(f)
    return _REGISTRY


def _project_root() -> Path:
    return Path(os.getenv("BLUELOTUS_PROJECT_ROOT", Path(__file__).resolve().parents[1]))


def _read_prompt(registry_key: str) -> str:
    """Read a prompt file by its registry key. Caches reads."""
    if registry_key in _PROMPT_CACHE:
        return _PROMPT_CACHE[registry_key]
    registry = _load_registry()
    prompts = registry.get("prompts", {})
    entry = prompts.get(registry_key)
    if entry is None:
        raise KeyError(f"Prompt registry key not found: {registry_key}")
    rel_path = str(entry.get("path", "")).replace("\\", "/")
    required = bool(entry.get("required", True))
    full_path = _project_root() / rel_path
    if not full_path.exists():
        if required:
            raise FileNotFoundError(f"Required prompt file missing: {full_path} (key: {registry_key})")
        return ""  # Optional file — return empty string
    content = full_path.read_text(encoding="utf-8").strip()
    _PROMPT_CACHE[registry_key] = content
    return content


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def compile_prompts(
    agent_id: str,
    agent_config: Dict[str, Any],
    desk_context: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]],
    cycle_context: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Assemble (system_prompt, user_prompt) for an agent.

    Returns:
        (system_prompt: str, user_prompt: str)

    The caller (e.g. base_agent.py or orchestrator) passes these directly
    to chat_with_model(model_role, system_prompt, user_prompt, ...).
    """
    system_prompt = _build_system_prompt(agent_id, agent_config)
    user_prompt = _build_user_prompt(agent_id, agent_config, desk_context, memory_context, cycle_context)
    return system_prompt, user_prompt


def compile_system_prompt(agent_id: str, agent_config: Dict[str, Any]) -> str:
    """Build system prompt only (useful for dry-run or testing)."""
    return _build_system_prompt(agent_id, agent_config)


def compile_user_prompt(
    agent_id: str,
    agent_config: Dict[str, Any],
    desk_context: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]],
    cycle_context: Dict[str, Any],
) -> str:
    """Build user prompt only."""
    return _build_user_prompt(agent_id, agent_config, desk_context, memory_context, cycle_context)


# ---------------------------------------------------------------------------
# Internal prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(agent_id: str, agent_config: Dict[str, Any]) -> str:
    """
    Assemble system prompt:
      [1] BlueLotus Constitution (universal)
      [2] Safety Doctrine (universal)
      [3] Agent Role (agent-specific)
    """
    parts = []

    # Layer 1: Constitution
    try:
        parts.append(_read_prompt("universal_constitution"))
    except (KeyError, FileNotFoundError):
        # Fallback if file not yet migrated
        parts.append(_legacy_constitution_text(agent_config))

    # Layer 2: Safety Doctrine
    try:
        parts.append(_read_prompt("universal_safety_doctrine"))
    except (KeyError, FileNotFoundError):
        parts.append(_legacy_safety_text())

    # Layer 3: Agent Role
    role_key = f"{agent_id}_role"
    try:
        parts.append(_read_prompt(role_key))
    except (KeyError, FileNotFoundError):
        # Fallback to legacy inline role text from agent_config
        parts.append(_legacy_role_text(agent_config))

    return "\n\n---\n\n".join(p for p in parts if p)


def _build_user_prompt(
    agent_id: str,
    agent_config: Dict[str, Any],
    desk_context: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]],
    cycle_context: Dict[str, Any],
) -> str:
    """
    Assemble user prompt:
      [4] No Generic Output Rule (universal)
      [5] JSON Only Rule (universal)
      [6] Agent Template (output format hint)
      [7] Payload JSON (desk_context + memory_context + cycle metadata)
    """
    parts = []

    # Layer 4: No Generic Output Rule
    try:
        parts.append(_read_prompt("universal_no_generic_output_rule"))
    except (KeyError, FileNotFoundError):
        pass

    # Layer 5: JSON Only Rule
    try:
        parts.append(_read_prompt("universal_json_only_rule"))
    except (KeyError, FileNotFoundError):
        pass

    # Layer 6: Agent Template (output format hint — first 1000 chars as schema hint)
    template_key = f"{agent_id}_template"
    try:
        template_text = _read_prompt(template_key)
        if template_text:
            parts.append("OUTPUT FORMAT HINT (from agent template):\n" + template_text[:1500])
    except (KeyError, FileNotFoundError):
        pass

    # Layer 7: Payload — desk_context, memory_context, and cycle metadata
    payload = _build_payload(agent_id, agent_config, desk_context, memory_context, cycle_context)
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    parts.append(
        "CYCLE CONTEXT AND EVIDENCE PACKET FOLLOWS. "
        "Your desk_context is your ONLY evidence. "
        "Do not infer from absent data. "
        "Return one JSON object matching the schema above:\n"
        + payload_json
    )
    parts.append(
        "FINAL MACHINE CHECK BEFORE YOU ANSWER:\n"
        "1. Every key_findings item MUST begin with one of: [DATASET], [OPERATOR], [NEWS], [THESIS], [BRIER], [MEMORY].\n"
        "2. Every risk_flags item MUST begin with P1, P2, or P3.\n"
        "3. summary MUST name this desk's specific lens.\n"
        "4. manual_execution_required MUST be true and llm_order_generation MUST be false.\n"
        "5. If evidence is insufficient, state the missing field in blind_spots instead of inventing certainty."
    )

    return "\n\n---\n\n".join(p for p in parts if p)


def _build_payload(
    agent_id: str,
    agent_config: Dict[str, Any],
    desk_context: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]],
    cycle_context: Dict[str, Any],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "cycle_id": cycle_context.get("cycle_id", ""),
        "agent_id": agent_id,
        "agent_name": agent_config.get("display_name", ""),
        "agent_role": agent_config.get("agent_role", ""),
        "focus_areas": agent_config.get("focus_areas", []),
        "evidence_priority": agent_config.get("evidence_priority", []),
        "must_answer": agent_config.get("must_answer", []),
        "distinctive_behavior": agent_config.get("distinctive_behavior", ""),
        "desk_context": desk_context,
        "input_refs": cycle_context.get("input_refs", {}),
    }
    if memory_context:
        payload["memory_context"] = memory_context
    return payload


# ---------------------------------------------------------------------------
# Legacy fallbacks (used until all agents have role.md files)
# ---------------------------------------------------------------------------

def _legacy_constitution_text(agent_config: Dict[str, Any]) -> str:
    role_memory = str(agent_config.get("role_memory", "")).strip()
    out_of_scope = agent_config.get("out_of_scope", [])
    out_of_scope_text = (
        "; ".join(str(i) for i in out_of_scope)
        if isinstance(out_of_scope, list)
        else str(out_of_scope)
    )
    display_name = agent_config.get("display_name", "Unknown Agent")
    agent_role = agent_config.get("agent_role", "")
    return (
        f"You are the {display_name} inside the BlueLotus V3 Qwen Agent Council. "
        "You have no memory between calls; this prompt is your complete operating memory. "
        f"Your permanent desk mandate is: {agent_role} "
        f"{role_memory} "
        "Role-play the desk deeply, but stay evidence-bound. Do not imitate other desks. "
        "Do not produce generic market commentary. Do not invent facts not present in the supplied context. "
        f"Out of scope for this desk: {out_of_scope_text or 'anything outside the desk mandate'}. "
        "Respect deterministic operator blocks. CIO manual execution is required. "
        "Never recommend, route, draft, or imply executable broker orders. "
        "Return one compact JSON object only."
    )


def _legacy_safety_text() -> str:
    return (
        "You must not generate broker orders. "
        "You must not execute trades. "
        "You must not route orders. "
        "manual_execution_required must be true. "
        "llm_order_generation must be false."
    )


def _legacy_role_text(agent_config: Dict[str, Any]) -> str:
    return ""  # Return empty — legacy role text already included in constitution fallback
