from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection
from law_governance.law_core import utc_now


def approve_memory_change(memory_id: str, approved_by: str = "CIO") -> Dict[str, Any]:
    now = utc_now()
    conn = get_v3_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM institutional_memory_registry WHERE memory_id=%s", (memory_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Unknown memory_id: {memory_id}")
        if row["status"] != "DRAFT":
            raise ValueError(f"Only DRAFT memory can be approved; current status={row['status']}")
        cur.close()

        cur2 = conn.cursor()
        cur2.execute(
            """
            UPDATE institutional_memory_registry
            SET approval_status='APPROVED', approved_by=%s, approved_at=%s
            WHERE memory_id=%s
            """,
            (approved_by, now, memory_id),
        )
        cur2.execute(
            """
            UPDATE institutional_memory_change_log
            SET approved_by=%s, approved_at=%s
            WHERE memory_id=%s
            """,
            (approved_by, now, memory_id),
        )
        conn.commit()
        cur2.close()
        return {"status": "APPROVED", "memory_id": memory_id, "approved_by": approved_by, "approved_at": now}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve proposed institutional memory")
    parser.add_argument("--memory-id", required=True)
    parser.add_argument("--approved-by", default="CIO")
    args = parser.parse_args()
    print(json.dumps(approve_memory_change(args.memory_id, args.approved_by), indent=2))


if __name__ == "__main__":
    main()
