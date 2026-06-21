from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.v3_db_connection import get_v3_connection

SCHEMA_PATH = Path(__file__).with_name("db_bloat_reduction_schema.sql")


def apply_schema() -> dict:
    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]
    conn = get_v3_connection()
    try:
        cursor = conn.cursor()
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
        cursor.close()
        return {"status": "applied", "statements": len(statements), "schema_path": str(SCHEMA_PATH)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    print(apply_schema())


if __name__ == "__main__":
    main()
