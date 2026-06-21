import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.v3_db_config import load_v3_db_config
from db.v3_db_connection import get_v3_connection


def main() -> None:
    cfg = load_v3_db_config()
    conn = get_v3_connection()
    try:
        cursor = conn.cursor()
        for table in cfg.tables.values():
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (cfg.database, table),
            )
            assert cursor.fetchone()[0] == 1, table
        cursor.close()
    finally:
        conn.close()
    print("PASS v3 db schema")


if __name__ == "__main__":
    main()
