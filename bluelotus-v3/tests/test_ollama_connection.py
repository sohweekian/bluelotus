from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import env_required, load_dotenv, resolve_project_path
from llm_clients.llm_healthcheck import run_healthcheck


def main() -> int:
    load_dotenv()
    run_smoke = "--smoke" in sys.argv
    result = run_healthcheck(run_model_smoke=run_smoke)
    out_dir = resolve_project_path(env_required("LLM_OUTPUT_DIR"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ollama_connection_test_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
