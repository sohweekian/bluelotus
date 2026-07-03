"""
BlueLotus V3 — Context Builder
==============================
Builds the agent-specific desk_context payload from the cycle's raw inputs
using the whitelist defined in config/agent_context_map.yaml.

ARCHITECTURE DOCTRINE:
  - Every field injected into desk_context must appear in agent_context_map.yaml.
  - Absence from the whitelist = not injected. No fallback to "send everything."
  - The compact() budget enforces per-field char ceilings.
  - allowed_operators: all = full operator dict (Risk Challenger only).

ANTI-HARDCODE RULE:
  - Dataset key mappings live in agent_context_map.yaml, not in this file.
  - Source mappings (live_news, brier, thesis_registry) derive from the map flags,
    not from agent_id if/elif chains.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Module-level config cache (loaded once per process)
# ---------------------------------------------------------------------------

_CONTEXT_MAP: Optional[Dict[str, Any]] = None


def _load_context_map() -> Dict[str, Any]:
    global _CONTEXT_MAP
    if _CONTEXT_MAP is not None:
        return _CONTEXT_MAP
    path_env = os.getenv("AGENT_CONTEXT_MAP_PATH")
    if path_env:
        path = Path(path_env)
    else:
        project_root = Path(os.getenv("BLUELOTUS_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
        path = project_root / "config" / "agent_context_map.yaml"
    if not path.exists():
        raise FileNotFoundError(f"agent_context_map.yaml not found at {path}")
    with path.open(encoding="utf-8") as f:
        _CONTEXT_MAP = yaml.safe_load(f)
    return _CONTEXT_MAP


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def build_desk_context(agent_id: str, cycle_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the desk_context dict for agent_id from cycle_context, using the
    agent_context_map.yaml whitelist.

    Returns a dict with only the fields the agent is allowed to see,
    each compacted to its per-field budget ceiling.
    """
    context_map = _load_context_map()
    agent_map = _get_agent_map(context_map, agent_id)

    # 1. Common context (always injected for all agents)
    common = _build_common(context_map, cycle_context)

    # 2. Dataset fields (from whitelist)
    dataset_fields = _build_dataset_fields(agent_map, cycle_context)

    # 3. Operator pack (full or selective based on allowed_operators)
    operator_fields = _build_operator_fields(agent_map, cycle_context)

    # 4. Live news (if agent is allowed access)
    live_news_field = _build_live_news(agent_map, cycle_context)

    # 5. Brier summary (if agent is allowed access)
    brier_field = _build_brier(agent_map, cycle_context)

    # 6. Thesis registry (if agent is allowed access)
    thesis_field = _build_thesis_registry(agent_map, cycle_context)

    desk_context: Dict[str, Any] = {**common, **dataset_fields, **operator_fields}
    if live_news_field is not None:
        desk_context["live_news"] = live_news_field
    if brier_field is not None:
        desk_context["brier_summary"] = brier_field
    if thesis_field is not None:
        desk_context["thesis_registry"] = thesis_field

    return desk_context


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _get_agent_map(context_map: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
    agents = context_map.get("agents", {})
    agent_map = agents.get(agent_id)
    if agent_map is None:
        # Unknown agent — return common-only context (safe fallback)
        return {}
    return agent_map


def _build_common(context_map: Dict[str, Any], cycle_context: Dict[str, Any]) -> Dict[str, Any]:
    common_def = context_map.get("common_context", {})
    fields: List[Dict[str, Any]] = common_def.get("fields", [])
    operator_pack = cycle_context.get("operator_verdict_pack", {})
    result: Dict[str, Any] = {}
    for field_def in fields:
        key = field_def["key"]
        budget = int(field_def.get("budget_chars", 0))
        source = field_def.get("source", "")
        if source == "operator_verdict_pack.source_summary":
            value = _parse_excerpt(operator_pack.get("source_summary", {}))
            result[key] = compact(value.get("summary", value), budget)
        elif source == "operator_verdict_pack.blocked_actions":
            result[key] = compact(operator_pack.get("blocked_actions", []), budget)
        elif source == "operator_verdict_pack.allowed_actions":
            result[key] = compact(operator_pack.get("allowed_actions", []), budget)
    return result


def _build_dataset_fields(agent_map: Dict[str, Any], cycle_context: Dict[str, Any]) -> Dict[str, Any]:
    """Read dataset from the path in cycle_context and extract only whitelisted keys."""
    dataset_path = str(cycle_context.get("dataset_summary", {}).get("path", ""))
    dataset = _load_json_path(dataset_path)
    if not dataset:
        return {"dataset_unavailable": True}

    allowed: List[Dict[str, Any]] = agent_map.get("allowed_dataset_keys", [])
    result: Dict[str, Any] = {}
    for field_def in allowed:
        key = field_def["key"]
        budget = int(field_def.get("budget_chars", 2200))
        value = dataset.get(key)
        if value is not None:
            result[key] = compact(value, budget)
    return result


def _build_operator_fields(agent_map: Dict[str, Any], cycle_context: Dict[str, Any]) -> Dict[str, Any]:
    operator_pack = cycle_context.get("operator_verdict_pack", {})
    operator_source = _parse_excerpt(operator_pack.get("source_summary", {}))
    all_operators = operator_source.get("operators", {})

    allowed_ops = agent_map.get("allowed_operators", [])

    if allowed_ops == "all" or allowed_ops == ["all"]:
        # Risk Challenger: full operator pack
        return {"relevant_operators": compact(all_operators, 3000)}

    if not isinstance(allowed_ops, list):
        return {}

    selected = {name: all_operators[name] for name in allowed_ops if name in all_operators}
    return {"relevant_operators": compact(selected, 2200)}


def _build_live_news(agent_map: Dict[str, Any], cycle_context: Dict[str, Any]) -> Optional[Any]:
    if not agent_map.get("live_news_access", False):
        return None
    budget = int(agent_map.get("live_news_budget_chars", 1600))
    live_news_raw = cycle_context.get("live_news_summary", {})
    parsed = _parse_excerpt(live_news_raw)
    return compact(parsed, budget)


def _build_brier(agent_map: Dict[str, Any], cycle_context: Dict[str, Any]) -> Optional[Any]:
    if not agent_map.get("brier_access", False):
        return None
    budget = int(agent_map.get("brier_budget_chars", 1200))
    brier_raw = cycle_context.get("brier_summary", {})
    parsed = _parse_excerpt(brier_raw)
    return compact(parsed, budget)


def _build_thesis_registry(agent_map: Dict[str, Any], cycle_context: Dict[str, Any]) -> Optional[Any]:
    if not agent_map.get("thesis_registry_access", False):
        return None
    budget = int(agent_map.get("thesis_registry_budget_chars", 1400))
    thesis_registry = cycle_context.get("thesis_registry", {})
    return compact(thesis_registry, budget)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def compact(value: Any, max_chars: int = 2200) -> Any:
    """Serialise value to JSON and truncate if over budget. Returns original value if within budget."""
    if max_chars <= 0:
        return value  # 0 = no limit
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "excerpt": text[:max_chars], "original_chars": len(text)}


def _load_json_path(path_text: str) -> Dict[str, Any]:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_excerpt(summary: Any) -> Dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    excerpt = summary.get("excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        return {}
    try:
        parsed = json.loads(excerpt)
    except Exception:
        return {"excerpt": excerpt[:1000]}
    return parsed if isinstance(parsed, dict) else {"excerpt": excerpt[:1000]}
