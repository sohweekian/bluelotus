from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.v3_db_healthcheck import run_v3_db_healthcheck
from db.v3_db_writers import persist_cycle_archive


def persist_cycle(cycle_dir: str | Path) -> dict:
    health = run_v3_db_healthcheck(Path(cycle_dir).name)
    return persist_cycle_archive(cycle_dir, health=health)


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "cycle archive path is required"}, indent=2))
        return 1
    result = persist_cycle(sys.argv[1])
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
