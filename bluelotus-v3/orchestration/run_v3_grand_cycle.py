from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.linear_agent_orchestrator import LinearAgentOrchestrator
from llm_clients.config_loader import append_log, load_main_config


def main() -> int:
    cycle_id = None
    persist_db = False
    for arg in sys.argv[1:]:
        if arg.startswith("--cycle-id="):
            cycle_id = arg.split("=", 1)[1].strip()
        if arg == "--persist-db":
            persist_db = True
    result = LinearAgentOrchestrator().run_cycle(cycle_id=cycle_id)
    if persist_db or database_persistence_default_enabled():
        try:
            from orchestration.persist_v3_cycle_to_db import persist_cycle

            result["database_persistence"] = persist_cycle(result["cycle_dir"])
        except Exception as exc:
            result["database_persistence"] = {"ok": False, "error": str(exc)}
            append_log("v3_db_persistence_errors.log", f"{result.get('cycle_id')}: {exc}")
            if database_persistence_fail_cycle_on_error():
                result["ok"] = False
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def database_persistence_default_enabled() -> bool:
    config = load_main_config()
    return config.get("database_persistence", {}).get("enabled") is True


def database_persistence_fail_cycle_on_error() -> bool:
    config = load_main_config()
    return config.get("database_persistence", {}).get("fail_cycle_on_db_error") is True


if __name__ == "__main__":
    raise SystemExit(main())
