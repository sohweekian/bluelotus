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
from law_governance.export_active_governance_pack import export_active_governance_pack
from law_governance.law_core import make_id, utc_now


def activate_memory_version(memory_id: str, performed_by: str = "CIO") -> Dict[str, Any]:
    now = utc_now()
    conn = get_v3_connection()
    previous_id: Optional[str] = None
    event_id = ""
    mtype = ""
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM institutional_memory_registry WHERE memory_id=%s", (memory_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Unknown memory_id: {memory_id}")
        if row["approval_status"] != "APPROVED":
            raise ValueError(f"Memory must be APPROVED before activation; current={row['approval_status']}")
        mtype = row["memory_type"]
        cur.execute(
            "SELECT memory_id FROM institutional_memory_registry WHERE memory_type=%s AND status='ACTIVE' ORDER BY effective_from DESC LIMIT 1",
            (mtype,),
        )
        prev = cur.fetchone()
        previous_id = prev["memory_id"] if prev else None
        cur.close()

        event_id = make_id("ACT", mtype, row["content_hash"])
        cur2 = conn.cursor()
        if previous_id and previous_id != memory_id:
            cur2.execute(
                """
                UPDATE institutional_memory_registry
                SET status='SUPERSEDED', effective_to=%s
                WHERE memory_id=%s AND status='ACTIVE'
                """,
                (now, previous_id),
            )
        cur2.execute(
            """
            UPDATE institutional_memory_registry
            SET status='ACTIVE', effective_from=COALESCE(effective_from, %s), effective_to=NULL
            WHERE memory_id=%s
            """,
            (now, memory_id),
        )
        cur2.execute(
            """
            INSERT INTO memory_activation_event (
                event_id, memory_type, event_type, previous_active_memory_id,
                new_active_memory_id, performed_by, event_reason, event_at
            ) VALUES (%s,%s,'ACTIVATED',%s,%s,%s,%s,%s)
            """,
            (
                event_id,
                mtype,
                previous_id if previous_id != memory_id else None,
                memory_id,
                performed_by,
                row.get("change_reason_text"),
                now,
            ),
        )
        conn.commit()
        cur2.close()
    finally:
        conn.close()

    export_result = export_active_governance_pack()
    conn2 = get_v3_connection()
    try:
        cur3 = conn2.cursor()
        cur3.execute(
            "UPDATE memory_activation_event SET active_pack_hash=%s WHERE event_id=%s",
            (export_result.get("active_pack_hash"), event_id),
        )
        conn2.commit()
        cur3.close()
    finally:
        conn2.close()

    return {
        "status": "ACTIVATED",
        "memory_id": memory_id,
        "memory_type": mtype,
        "previous_active_memory_id": previous_id,
        "event_id": event_id,
        "active_pack_hash": export_result.get("active_pack_hash"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate approved institutional memory version")
    parser.add_argument("--memory-id", required=True)
    parser.add_argument("--performed-by", default="CIO")
    args = parser.parse_args()
    print(json.dumps(activate_memory_version(args.memory_id, args.performed_by), indent=2))


if __name__ == "__main__":
    main()
