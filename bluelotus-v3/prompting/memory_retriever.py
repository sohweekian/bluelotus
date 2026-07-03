"""
BlueLotus V3 — Memory Retriever
================================
Reads historical cycle archives and injects relevant memory into
agent prompts according to config/memory_retrieval_policy.yaml.

ARCHITECTURE DOCTRINE:
  - File-first principle: always read data/v3_cycles/ archive before
    attempting any database read.
  - Memory is injected as "memory_context" key — SEPARATE from desk_context.
    Never merge memory into the agent's evidence context.
  - Staleness hard skip: if the newest cycle is older than
    global.staleness_hard_skip_hours, no memory is injected.
  - change_detection_mode: skip injection if monitored field is
    identical to the previous cycle's value.

ANTI-HARDCODE RULE:
  - All lookback counts, field names, and injection modes come from the
    memory_retrieval_policy.yaml file.
  - The archive directory comes from V3_CYCLE_OUTPUT_DIR env var.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Module-level config cache
# ---------------------------------------------------------------------------

_POLICY: Optional[Dict[str, Any]] = None


def _load_policy() -> Dict[str, Any]:
    global _POLICY
    if _POLICY is not None:
        return _POLICY
    path_env = os.getenv("MEMORY_RETRIEVAL_POLICY_PATH")
    if path_env:
        path = Path(path_env)
    else:
        project_root = Path(os.getenv("BLUELOTUS_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
        path = project_root / "config" / "memory_retrieval_policy.yaml"
    if not path.exists():
        raise FileNotFoundError(f"memory_retrieval_policy.yaml not found at {path}")
    with path.open(encoding="utf-8") as f:
        _POLICY = yaml.safe_load(f)
    return _POLICY


def _archive_dir() -> Path:
    env_val = os.getenv("V3_CYCLE_OUTPUT_DIR")
    if env_val:
        return Path(env_val)
    project_root = Path(os.getenv("BLUELOTUS_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
    return project_root / "data" / "v3_cycles"


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def retrieve_memory(agent_id: str, current_cycle_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns memory_context dict for injection into agent prompt, or None
    if memory injection should be skipped (staleness, policy=never, etc.)

    Return format:
    {
        "memory_label": "recent_regime_reads",
        "source": "file_archive",
        "cycles_retrieved": 3,
        "entries": [
            {"cycle_id": "...", "generated_at": "...", <extracted fields>},
            ...
        ]
    }
    """
    policy = _load_policy()
    agent_policy = policy.get("agents", {}).get(agent_id)
    if agent_policy is None:
        return None

    injection_mode = str(agent_policy.get("injection_mode", "never"))
    if injection_mode == "never":
        return None

    global_policy = policy.get("global", {})
    hard_skip_hours = int(global_policy.get("staleness_hard_skip_hours", 72))
    max_lookback = int(global_policy.get("max_lookback_cycles", 5))
    lookback_cycles = min(int(agent_policy.get("lookback_cycles", 3)), max_lookback)
    max_chars = int(agent_policy.get("max_injection_chars", 800))
    agent_staleness_skip = int(agent_policy.get("staleness_skip_hours", 48))
    effective_staleness_skip = min(agent_staleness_skip, hard_skip_hours)

    # Determine whether to read chief_strategist briefings or agent reports
    source_file = agent_policy.get("source_file", "")  # e.g. "chief_strategist_briefing.json"

    # Find past cycles (excluding current)
    past_cycles = _discover_past_cycles(current_cycle_id, lookback_cycles)
    if not past_cycles:
        return None

    # Check staleness of the newest available cycle
    newest_cycle_dir, newest_ts = past_cycles[0]
    if newest_ts is not None:
        age_hours = _age_hours(newest_ts)
        if age_hours > effective_staleness_skip:
            return None  # Too stale — skip

    # Determine which agent reports to read
    cross_agent = agent_policy.get("cross_agent_memory", False)
    if cross_agent:
        source_agents: List[str] = agent_policy.get("cross_agent_source_agents", [agent_id])
    else:
        source_agents = [agent_id]

    extract_fields: List[str] = agent_policy.get("extract_fields", [])

    # Read entries from past cycles
    entries: List[Dict[str, Any]] = []
    for cycle_dir, _ in past_cycles:
        for src_agent in source_agents:
            if source_file:
                entry = _read_file_entry(cycle_dir, source_file, extract_fields)
            else:
                entry = _read_agent_report(cycle_dir, src_agent, extract_fields)
            if entry:
                entry["_source_agent"] = src_agent
                entry["_cycle_dir"] = cycle_dir.name
                entries.append(entry)

    if not entries:
        return None

    # change_detection check for if_changes_detected mode
    if injection_mode == "if_changes_detected":
        change_field = agent_policy.get("change_detection_field", "key_findings")
        if not _change_detected(entries, change_field):
            return None

    memory_label = str(agent_policy.get("memory_label", f"{agent_id}_history"))

    memory_block = {
        "memory_label": memory_label,
        "source": "file_archive",
        "cycles_retrieved": len(past_cycles),
        "injection_mode": injection_mode,
        "entries": entries,
    }

    # Enforce budget ceiling via truncation
    serialised = json.dumps(memory_block, ensure_ascii=False, separators=(",", ":"))
    if len(serialised) > max_chars:
        # Trim oldest entries until within budget
        while len(entries) > 1:
            entries.pop()
            memory_block["entries"] = entries
            memory_block["truncated_to_budget"] = True
            serialised = json.dumps(memory_block, ensure_ascii=False, separators=(",", ":"))
            if len(serialised) <= max_chars:
                break

    return memory_block


# ---------------------------------------------------------------------------
# Archive discovery
# ---------------------------------------------------------------------------

def _discover_past_cycles(
    current_cycle_id: str,
    limit: int,
) -> List[Tuple[Path, Optional[datetime]]]:
    """
    Returns list of (cycle_dir, timestamp) sorted newest-first,
    excluding the current cycle, up to `limit` entries.
    """
    archive_root = _archive_dir()
    if not archive_root.exists():
        return []

    candidates: List[Tuple[Path, Optional[datetime]]] = []
    for d in sorted(archive_root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        if d.name == current_cycle_id:
            continue
        ts = _parse_cycle_timestamp(d.name)
        candidates.append((d, ts))

    return candidates[:limit]


def _parse_cycle_timestamp(dir_name: str) -> Optional[datetime]:
    """Extract timestamp from cycle dir name like v3_cycle_20260616_205058."""
    try:
        parts = dir_name.split("_")
        if len(parts) >= 4:
            date_str = parts[-2]
            time_str = parts[-1]
            ts_str = date_str + time_str
            dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        pass
    return None


def _age_hours(ts: datetime) -> float:
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = now - ts
    return delta.total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Report reading
# ---------------------------------------------------------------------------

def _read_agent_report(
    cycle_dir: Path,
    agent_id: str,
    extract_fields: List[str],
) -> Optional[Dict[str, Any]]:
    report_path = cycle_dir / "agent_reports" / f"{agent_id}.json"
    return _read_and_extract(report_path, extract_fields)


def _read_file_entry(
    cycle_dir: Path,
    source_file: str,
    extract_fields: List[str],
) -> Optional[Dict[str, Any]]:
    path = cycle_dir / source_file
    return _read_and_extract(path, extract_fields)


def _read_and_extract(path: Path, extract_fields: List[str]) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not extract_fields:
        return data
    extracted = {f: data[f] for f in extract_fields if f in data}
    if not extracted:
        return None
    # Preserve cycle identity fields
    for meta_field in ("cycle_id", "agent_id", "generated_at_sgt", "created_at_sgt"):
        if meta_field in data:
            extracted[meta_field] = data[meta_field]
    return extracted


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def _change_detected(entries: List[Dict[str, Any]], change_field: str) -> bool:
    """Return True if the field value differs between the two most recent entries."""
    if len(entries) < 2:
        return True  # Only one entry — treat as changed (no comparison basis)
    v1 = entries[0].get(change_field)
    v2 = entries[1].get(change_field)
    return v1 != v2
