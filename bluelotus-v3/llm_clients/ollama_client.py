from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Dict

from .config_loader import append_log, env_bool, env_int, env_required, load_dotenv, load_main_config
from .json_response_validator import ResponseValidationError, load_schema, validate_json_response
from .model_router import get_model_config
from .prompt_guard import PromptRejected, guard_prompt


def chat_with_model(
    model_role: str,
    system_prompt: str,
    user_prompt: str,
    require_json: bool = True,
    schema_env: str = "LLM_RESPONSE_SCHEMA_PATH",
) -> dict:
    load_dotenv()
    response_text = ""
    try:
        model_config = get_model_config(model_role)
        guarded = guard_prompt(system_prompt, user_prompt)
        response_text = send_chat_request(
            model_name=str(model_config["model_name"]),
            model_role=model_role,
            system_prompt=guarded.system_prompt,
            user_prompt=guarded.user_prompt,
            timeout_seconds=int(model_config.get("timeout_seconds") or env_int("OLLAMA_TIMEOUT_SECONDS")),
            require_json=require_json,
            schema_env=schema_env,
            options=model_config.get("options") if isinstance(model_config.get("options"), dict) else None,
        )
        parsed = validate_json_response(response_text, schema_env, require_json=require_json)
        if parsed.get("model_role", model_role) != model_role:
            raise ResponseValidationError("Model role does not match configured role.")
        return {
            "ok": True,
            "model_role": model_role,
            "provider": model_config["provider"],
            "response_text": response_text,
            "parsed": parsed,
        }
    except (PromptRejected, ResponseValidationError, urllib.error.URLError, TimeoutError, OSError, Exception) as exc:
        log_error(f"chat_with_model failed for role {model_role}: {exc}")
        result = {
            "ok": False,
            "model_role": model_role,
            "error": str(exc),
        }
        if response_text:
            result["response_text"] = response_text
        return result


def send_chat_request(
    model_name: str,
    model_role: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int,
    require_json: bool,
    schema_env: str,
    options: dict | None,
) -> str:
    main_config = load_main_config()
    ollama_config = main_config.get("ollama", {})
    request_mode_env = str(ollama_config.get("request_mode_env") or "")
    request_mode = env_required(request_mode_env).strip().lower() if request_mode_env else "chat"
    if request_mode == "generate":
        return send_generate_request(
            main_config=main_config,
            model_name=model_name,
            model_role=model_role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=timeout_seconds,
            require_json=require_json,
            schema_env=schema_env,
            options=options,
        )
    if request_mode != "chat":
        raise RuntimeError(f"Unsupported Ollama request mode: {request_mode}")

    endpoint_path = str(ollama_config.get("chat_endpoint_path") or "")
    if not endpoint_path:
        raise RuntimeError("Configured Ollama chat endpoint path is missing.")
    base_url = env_required("OLLAMA_BASE_URL").rstrip("/")
    payload = {
        "model": model_name,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    thinking_env = str(main_config.get("ollama", {}).get("thinking_enabled_env") or "")
    if thinking_env:
        payload["think"] = env_bool(thinking_env)
    if require_json:
        response_schema = load_schema(schema_env)
        properties = response_schema.setdefault("properties", {})
        if "model_role" in properties:
            properties.setdefault("model_role", {})["const"] = model_role
        format_mode_env = str(main_config.get("ollama", {}).get("json_format_mode_env") or "")
        format_mode = "prompt_only"
        if format_mode_env:
            format_mode = env_required(format_mode_env).strip().lower()
        if format_mode == "schema":
            payload["format"] = response_schema
        elif format_mode == "json":
            payload["format"] = "json"
        elif format_mode != "prompt_only":
            raise RuntimeError(f"Unsupported Ollama JSON format mode: {format_mode}")
    if options:
        payload["options"] = options
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url + endpoint_path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 500:
            detail = detail[:500] + "..."
        raise RuntimeError(f"Ollama HTTP {exc.code} {exc.reason}: {detail}") from exc
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict) or "content" not in message:
        raise RuntimeError("Ollama response did not contain message.content.")
    return sanitize_model_text(str(message["content"]))


def send_generate_request(
    main_config: Dict,
    model_name: str,
    model_role: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int,
    require_json: bool,
    schema_env: str,
    options: dict | None,
) -> str:
    ollama_config = main_config.get("ollama", {})
    endpoint_path = str(ollama_config.get("generate_endpoint_path") or "")
    if not endpoint_path:
        raise RuntimeError("Configured Ollama generate endpoint path is missing.")
    base_url = env_required("OLLAMA_BASE_URL").rstrip("/")
    prompt = build_generate_prompt(system_prompt, user_prompt)
    payload = {
        "model": model_name,
        "stream": False,
        "prompt": prompt,
    }
    raw_env = str(ollama_config.get("generate_raw_env") or "")
    if raw_env:
        payload["raw"] = env_bool(raw_env, default=False)
    if require_json:
        format_mode_env = str(ollama_config.get("json_format_mode_env") or "")
        format_mode = env_required(format_mode_env).strip().lower() if format_mode_env else "prompt_only"
        if format_mode == "schema":
            response_schema = load_schema(schema_env)
            properties = response_schema.setdefault("properties", {})
            if "model_role" in properties:
                properties.setdefault("model_role", {})["const"] = model_role
            payload["format"] = response_schema
        elif format_mode == "json":
            payload["format"] = "json"
        elif format_mode != "prompt_only":
            raise RuntimeError(f"Unsupported Ollama JSON format mode: {format_mode}")
    if options:
        payload["options"] = options
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url + endpoint_path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if len(detail) > 500:
            detail = detail[:500] + "..."
        raise RuntimeError(f"Ollama HTTP {exc.code} {exc.reason}: {detail}") from exc
    response = body.get("response") if isinstance(body, dict) else None
    if not isinstance(response, str):
        raise RuntimeError("Ollama generate response did not contain response text.")
    return sanitize_model_text(response)


def build_generate_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        "SYSTEM INSTRUCTIONS:\n"
        f"{system_prompt.strip()}\n\n"
        "USER TASK:\n"
        f"{user_prompt.strip()}\n\n"
        "OUTPUT CONTRACT:\n"
        "Return one valid JSON object only. Do not include markdown fences, prose, or analysis."
    )


def sanitize_model_text(text: str) -> str:
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
    cleaned = re.sub(r"(?is)^```(?:json)?\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?is)\s*```$", "", cleaned).strip()
    return cleaned


def log_error(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        append_log("ollama_client_errors.log", f"{stamp} {message}")
    except Exception:
        pass
