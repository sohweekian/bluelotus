from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import load_dotenv
from llm_clients.model_router import get_default_model_role, get_model_config


def main() -> int:
    load_dotenv()
    role = get_default_model_role()
    config = get_model_config(role)
    assert config["provider"] == "ollama"
    assert config["enabled"] is True
    assert config["model_name"]
    assert int(config["timeout_seconds"]) > 0
    print("PASS model registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
