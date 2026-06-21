from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection
from law_governance.law_core import (
    content_hash,
    json_dumps,
    make_id,
    require_memory_type,
    require_reason_code,
    utc_now,
)
from law_governance.memory_diff import summarize_diff


def _load_content(content_json: Optional[str], content_file: Optional[Path]) -> Dict[str, Any]:
    if content_file:
        value = json.loads(content_file.read_text(encoding="utf-8"))
    elif content_json:
        value = json.loads(content_json)
    else:
        raise ValueError("Provide --content-json or --content-file")
    if not isinstance(value, dict):
        raise ValueError("Memory content must be a JSON object")
    return value


def _load_existing_content(conn, memory_id: Optional[str]) -> Dict[str, Any]:
    if not memory_id:
        return {}
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT content_json FROM institutional_memory_registry WHERE memory_id=%s", (memory_id,))
    row = cur.fetchone()
    cur.close()
    if not row:
        return {}
    return json.loads(row["content_json"])


def propose_memory_change(
    memory_type: str,
    content: Dict[str, Any],
    version: str,
    summary: str,
    reason_code: str,
    reason_text: str,
    requested_by: str = "CIO",
    supersedes_memory_id: Optional[str] = None,
    artifact_path: Optional[str] = None,
) -> Dict[str, Any]:
    mtype = require_memory_type(memory_type)
    rcode = require_reason_code(reason_code)
    if not reason_text.strip():
        raise ValueError("reason_text is mandatory for immutable memory governance")

    chash = content_hash(content)
    memory_id = make_id("MEM", mtype, chash)
    change_id = make_id("CHG", mtype, chash)
    now = utc_now()
    conn = get_v3_connection()
    try:
        existing_cur = conn.cursor(dictionary=True)
        existing_cur.execute(
            "SELECT memory_id, status, approval_status FROM institutional_memory_registry WHERE memory_type=%s AND content_hash=%s",
            (mtype, chash),
        )
        existing = existing_cur.fetchone()
        existing_cur.close()
        if existing:
            return {
                "status": "EXISTS",
                "memory_id": existing["memory_id"],
                "memory_type": mtype,
                "registry_status": existing["status"],
                "approval_status": existing["approval_status"],
                "content_hash": chash,
            }

        old_content = _load_existing_content(conn, supersedes_memory_id)
        diff_summary = summarize_diff(old_content, content)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO institutional_memory_registry (
                memory_id, memory_type, version, status, content_json, content_hash,
                summary, artifact_path, change_reason_code, change_reason_text,
                supersedes_memory_id, approval_status, requested_by, created_at
            ) VALUES (%s,%s,%s,'DRAFT',%s,%s,%s,%s,%s,%s,%s,'PENDING',%s,%s)
            """,
            (
                memory_id, mtype, version, json_dumps(content), chash,
                summary, artifact_path, rcode, reason_text,
                supersedes_memory_id, requested_by, now,
            ),
        )
        cur.execute(
            """
            INSERT INTO institutional_memory_change_log (
                change_id, memory_id, memory_type, change_type, reason_code,
                reason_text, diff_summary, evidence_refs, requested_by, created_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                change_id,
                memory_id,
                mtype,
                "SUPERSEDE_PROPOSAL" if supersedes_memory_id else "CREATE_PROPOSAL",
                rcode,
                reason_text,
                json_dumps(diff_summary),
                "[]",
                requested_by,
                now,
            ),
        )
        conn.commit()
        cur.close()
        return {
            "status": "PROPOSED",
            "memory_id": memory_id,
            "change_id": change_id,
            "memory_type": mtype,
            "content_hash": chash,
            "approval_status": "PENDING",
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose immutable institutional memory change")
    parser.add_argument("--memory-type", required=True)
    parser.add_argument("--content-json")
    parser.add_argument("--content-file", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--reason-text", required=True)
    parser.add_argument("--requested-by", default="CIO")
    parser.add_argument("--supersedes-memory-id")
    parser.add_argument("--artifact-path")
    args = parser.parse_args()
    content = _load_content(args.content_json, args.content_file)
    result = propose_memory_change(
        args.memory_type,
        content,
        args.version,
        args.summary,
        args.reason_code,
        args.reason_text,
        requested_by=args.requested_by,
        supersedes_memory_id=args.supersedes_memory_id,
        artifact_path=args.artifact_path,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
