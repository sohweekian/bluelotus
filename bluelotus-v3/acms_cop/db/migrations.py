from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from acms_cop.db.acms_db import create_database_if_missing, get_connection


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "acms_schema.sql"


def split_sql(script: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
    in_single = False
    in_double = False
    for ch in script:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def run_migrations(database: str) -> int:
    create_database_if_missing(database)
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = split_sql(script)
    conn = get_connection(database=database)
    try:
        cursor = conn.cursor()
        for statement in statements:
            cursor.execute(statement)
        conn.commit()
        cursor.close()
        return len(statements)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply ACMS-COP MySQL schema migrations.")
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    count = run_migrations(args.database)
    print(f"ACMS-COP migrations applied: {count} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

