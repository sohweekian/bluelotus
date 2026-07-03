from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from db.v3_db_connection import get_v3_connection


PROJECT_ROOT = Path(r"C:\bluelotus3")
OUTPUT_DIR = PROJECT_ROOT / "data" / "governance_law"
ACTIVE_PACK_PATH = OUTPUT_DIR / "active_governance_pack_latest.json"

VALID_MEMORY_TYPES = {
    "MASTER_PROMPT",
    "CIO_CONTEXT_CAPSULE",
    "CHIEF_STRATEGIST_GOVERNANCE",
    "STRATEGY_DOCTRINE",
    "SLEEVE_RULES",
    "KILL_CONDITION_SET",
    "EXECUTION_DOCTRINE",
    "SOURCE_PRIORITY_RULES",
}

VALID_REASON_CODES = {
    "CIO_DOCTRINE_UPDATE",
    "STRATEGY_REGIME_CHANGE",
    "KILL_CONDITION_TRIGGERED",
    "TACTICAL_PLAN_EXPIRED",
    "POSITIONING_STATE_CHANGED",
    "ERROR_CORRECTION",
    "PROMPT_CLARITY_HARDENING",
    "GOVERNANCE_FAILURE_REMEDIATION",
    "POST_MORTEM_LEARNING",
    "NEW_SLEEVE_RULE",
    "RISK_LIMIT_CHANGE",
    "FOUNDING_BASELINE",
}

TYPE_TO_PACK_KEY = {
    "MASTER_PROMPT": "master_prompt",
    "CIO_CONTEXT_CAPSULE": "cio_context_capsule",
    "CHIEF_STRATEGIST_GOVERNANCE": "chief_strategist_governance",
    "STRATEGY_DOCTRINE": "strategy_doctrine",
    "SLEEVE_RULES": "sleeve_rules",
    "KILL_CONDITION_SET": "kill_condition_set",
    "EXECUTION_DOCTRINE": "execution_doctrine",
    "SOURCE_PRIORITY_RULES": "source_priority_rules",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def json_dumps(value: Any, *, sort_keys: bool = True) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=sort_keys, separators=(",", ":"))


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def content_hash(content: Any) -> str:
    return hashlib.sha256(json_dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def binding_hash(payload: Dict[str, Any]) -> str:
    return content_hash(payload)


def load_json_path(path: Path) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON content must be an object: {path}")
    return value


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = pretty_json(payload)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as fh:
        fh.write(raw)
        fh.write("\n")
        tmp = Path(fh.name)
    tmp.replace(path)


def make_id(prefix: str, memory_type: str, hash_value: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    clean_type = "".join(ch if ch.isalnum() else "_" for ch in memory_type.upper())
    return f"{prefix}_{clean_type}_{stamp}_{hash_value[:10]}"


def dict_cursor(conn):
    return conn.cursor(dictionary=True)


def fetch_one(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    conn = get_v3_connection()
    try:
        cur = dict_cursor(conn)
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        cur.close()
        return row
    finally:
        conn.close()


def fetch_all(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    conn = get_v3_connection()
    try:
        cur = dict_cursor(conn)
        cur.execute(sql, tuple(params))
        rows = list(cur.fetchall())
        cur.close()
        return rows
    finally:
        conn.close()


def active_memory_rows() -> List[Dict[str, Any]]:
    return fetch_all(
        """
        SELECT memory_id, memory_type, version, status, content_hash, summary,
               effective_from, approval_status, approved_by, artifact_path
        FROM institutional_memory_registry
        WHERE status='ACTIVE'
        ORDER BY memory_type, effective_from
        """
    )


def normalize_dt(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value)


def memory_row_to_pack_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "memory_id": row.get("memory_id", ""),
        "version": row.get("version", ""),
        "hash": row.get("content_hash", ""),
        "effective_from": normalize_dt(row.get("effective_from")),
        "approval_status": row.get("approval_status", ""),
        "approved_by": row.get("approved_by", ""),
        "artifact_path": row.get("artifact_path", ""),
    }


def require_memory_type(memory_type: str) -> str:
    value = str(memory_type or "").upper().strip()
    if value not in VALID_MEMORY_TYPES:
        raise ValueError(f"Unsupported memory_type: {memory_type}")
    return value


def require_reason_code(reason_code: str) -> str:
    value = str(reason_code or "").upper().strip()
    if value not in VALID_REASON_CODES:
        raise ValueError(f"Unsupported reason_code: {reason_code}")
    return value

