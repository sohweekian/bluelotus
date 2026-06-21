from __future__ import annotations

from typing import Any, Dict

from llm_clients.config_loader import load_yaml_from_env


def load_thesis_registry() -> Dict[str, Any]:
    return load_yaml_from_env("THESIS_REGISTRY_PATH")
