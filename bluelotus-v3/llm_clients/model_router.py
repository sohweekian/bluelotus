from __future__ import annotations

from typing import Any, Dict

from .config_loader import ConfigError, env_required, load_yaml_from_env


def get_model_config(model_role: str, resolve_runtime_model: bool = True) -> Dict[str, Any]:
    registry = load_yaml_from_env("MODEL_REGISTRY_PATH")
    models = registry.get("models")
    if not isinstance(models, dict):
        raise ConfigError("Model registry is missing a models mapping.")
    config = models.get(model_role)
    if not isinstance(config, dict):
        raise ConfigError(f"Model role is not registered: {model_role}")
    if not config.get("enabled", False):
        raise ConfigError(f"Model role is disabled: {model_role}")
    for field in ["provider", "model_name", "role", "timeout_seconds"]:
        if field not in config:
            raise ConfigError(f"Model role {model_role} is missing field: {field}")
    resolved = dict(config)
    runtime_model_env = str(resolved.get("runtime_model_name_env") or "").strip()
    if resolve_runtime_model and runtime_model_env:
        resolved["model_name"] = env_required(runtime_model_env)
    return resolved


def get_default_model_role() -> str:
    return env_required("OLLAMA_MODEL_ROLE")
