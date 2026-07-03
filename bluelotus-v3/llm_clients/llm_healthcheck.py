from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import ConfigError, env_required, load_dotenv, load_main_config, project_root, resolve_project_path
from llm_clients.json_response_validator import ResponseValidationError, validate_json_response
from llm_clients.model_router import get_default_model_role, get_model_config
from llm_clients.ollama_client import chat_with_model
from llm_clients.prompt_guard import PromptRejected, guard_prompt


def run_healthcheck(run_model_smoke: bool = False) -> Dict:
    load_dotenv()
    checks: List[Dict] = []
    root = project_root()
    checks.append(check("project_root_loaded", root.exists(), str(root)))
    for env_name in [
        "MODEL_REGISTRY_PATH",
        "LLM_SAFETY_POLICY_PATH",
        "PROMPT_REGISTRY_PATH",
        "LLM_SCHEMA_DIR",
        "LLM_OUTPUT_DIR",
        "LLM_LOG_DIR",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL_ROLE",
    ]:
        checks.append(check(f"env_{env_name}", bool(os.getenv(env_name)), env_name))

    model_role = get_default_model_role()
    model_config = get_model_config(model_role)
    checks.append(check("model_registry_loaded", bool(model_config.get("model_name")), model_role))

    output_dir = resolve_project_path(env_required("LLM_OUTPUT_DIR"))
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_path = output_dir / "healthcheck_write_probe.txt"
    probe_path.write_text("ok", encoding="utf-8")
    checks.append(check("output_folder_writable", probe_path.exists(), str(output_dir)))

    try:
        guard_prompt("Analyze only.", "Please place_order now.")
        checks.append(check("prompt_guard_blocks_execution", False, "Forbidden prompt was accepted."))
    except PromptRejected:
        checks.append(check("prompt_guard_blocks_execution", True, "Forbidden prompt rejected."))

    valid = json.dumps({
        "schema_version": "bluelotus_llm_response_v1.0",
        "model_role": model_role,
        "summary": "Smoke validation.",
        "key_findings": [],
        "risk_flags": [],
        "recommended_cio_action": "WAIT",
        "manual_execution_required": True,
        "llm_order_generation": False,
    })
    validate_json_response(valid, "LLM_RESPONSE_SCHEMA_PATH")
    checks.append(check("json_validator_accepts_valid_output", True, "Valid schema output accepted."))
    try:
        validate_json_response("{bad json", "LLM_RESPONSE_SCHEMA_PATH")
        checks.append(check("json_validator_rejects_malformed_output", False, "Malformed output accepted."))
    except ResponseValidationError:
        checks.append(check("json_validator_rejects_malformed_output", True, "Malformed output rejected."))

    tags = check_ollama_tags()
    checks.append(check("ollama_api_reachable", tags["ok"], tags.get("detail", "")))
    if tags["ok"]:
        wanted = str(model_config.get("model_name"))
        reported = set(tags.get("models", []))
        available = wanted in reported or f"{wanted}:latest" in reported
        checks.append(check("configured_model_available", available, wanted))
    else:
        checks.append(check("configured_model_available", False, "Ollama API unavailable."))

    checks.append(check("no_v2_write_target", protected_root_check(root, output_dir), str(output_dir)))

    smoke_result = None
    if run_model_smoke:
        system_prompt = read_prompt("specialist_desk_system")
        user_prompt = read_prompt("qwen_smoke_test").replace("{{MODEL_ROLE}}", model_role)
        smoke_result = chat_with_model(model_role, system_prompt, user_prompt, require_json=True)
        checks.append(check("qwen_smoke_json_response", bool(smoke_result.get("ok")), smoke_result.get("error", "OK")))

    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "checks": checks,
        "smoke_result": smoke_result,
    }


def check_ollama_tags() -> Dict:
    try:
        main_config = load_main_config()
        endpoint_path = str(main_config.get("ollama", {}).get("tags_endpoint_path") or "")
        if not endpoint_path:
            raise ConfigError("Configured Ollama tags endpoint path is missing.")
        base_url = env_required("OLLAMA_BASE_URL").rstrip("/")
        with urllib.request.urlopen(base_url + endpoint_path, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        models = []
        for item in body.get("models", []):
            name = item.get("name")
            if name:
                models.append(str(name))
        return {"ok": True, "models": models, "detail": f"{len(models)} models reported."}
    except Exception as exc:
        return {"ok": False, "models": [], "detail": str(exc)}


def read_prompt(prompt_id: str) -> str:
    from llm_clients.config_loader import load_yaml_from_env

    registry = load_yaml_from_env("PROMPT_REGISTRY_PATH")
    prompts = registry.get("prompts", {})
    entry = prompts.get(prompt_id)
    if not isinstance(entry, dict):
        raise ConfigError(f"Prompt not registered: {prompt_id}")
    path = resolve_project_path(str(entry.get("path", "")))
    if not path.exists():
        raise ConfigError(f"Prompt file not found: {prompt_id}")
    return path.read_text(encoding="utf-8")


def protected_root_check(root: Path, output_dir: Path) -> bool:
    protected = os.getenv("BLUELOTUS_PROTECTED_ROOT", "").strip()
    if not protected:
        return output_dir.is_relative_to(root)
    protected_path = Path(protected).expanduser().resolve()
    return not output_dir.is_relative_to(protected_path) and output_dir.is_relative_to(root)


def check(name: str, ok: bool, detail: str) -> Dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> int:
    run_smoke = "--smoke" in sys.argv
    result = run_healthcheck(run_model_smoke=run_smoke)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
