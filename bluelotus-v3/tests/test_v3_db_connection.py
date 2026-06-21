import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.v3_db_connection import test_v3_connection


def main() -> None:
    assert test_v3_connection()
    print("PASS v3 db connection")


if __name__ == "__main__":
    main()
