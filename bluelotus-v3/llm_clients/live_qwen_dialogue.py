from __future__ import annotations

import json
import sys
import urllib.request
from typing import Iterable

from .config_loader import env_bool, env_int, env_required, load_dotenv, load_main_config
from .model_router import get_default_model_role, get_model_config


def model_display_label(model_config: dict) -> str:
    return str(model_config.get("model_name") or "configured local model")


def stream_qwen_reply(prompt: str) -> None:
    load_dotenv()
    main_config = load_main_config()
    model_role = get_default_model_role()
    model_config = get_model_config(model_role)
    endpoint_path = str(main_config.get("ollama", {}).get("chat_endpoint_path") or "")
    if not endpoint_path:
        raise RuntimeError("Configured Ollama chat endpoint path is missing.")

    payload = {
        "model": model_config["model_name"],
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are {model_display_label(model_config)} running locally for BlueLotus V3. "
                    "Reply conversationally and briefly. Do not include hidden reasoning."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    thinking_env = str(main_config.get("ollama", {}).get("thinking_enabled_env") or "")
    if thinking_env:
        payload["think"] = env_bool(thinking_env)
    options = model_config.get("options")
    if isinstance(options, dict):
        payload["options"] = options

    data = json.dumps(payload).encode("utf-8")
    base_url = env_required("OLLAMA_BASE_URL").rstrip("/")
    request = urllib.request.Request(
        base_url + endpoint_path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout_seconds = int(model_config.get("timeout_seconds") or env_int("OLLAMA_TIMEOUT_SECONDS"))
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        for token in iter_ollama_tokens(response):
            print(token, end="", flush=True)
    print()


def iter_ollama_tokens(response) -> Iterable[str]:
    suppress_thinking = True
    pending = ""
    for raw_line in response:
        line = raw_line.decode("utf-8").strip()
        if not line:
            continue
        event = json.loads(line)
        message = event.get("message") if isinstance(event, dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if content:
                text = str(content)
                if suppress_thinking:
                    pending += text
                    marker = "</think>"
                    if marker in pending:
                        _, pending = pending.split(marker, 1)
                        suppress_thinking = False
                        if pending.lstrip():
                            yield pending.lstrip()
                        pending = ""
                    elif len(pending) > 2048 and "<think>" not in pending:
                        suppress_thinking = False
                        yield pending
                        pending = ""
                else:
                    yield text
        if event.get("done"):
            break


def interactive_loop() -> None:
    load_dotenv()
    model_config = get_model_config(get_default_model_role())
    label = model_display_label(model_config)
    print(f"BlueLotus V3 live {label} dialogue")
    print("Type a message for Dr. Codex to send to Qwen. Type exit to close.")
    while True:
        try:
            prompt = input("\nDr. Codex > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            return
        print(f"{label} > ", end="", flush=True)
        stream_qwen_reply(prompt)


def main() -> int:
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:]).strip()
        load_dotenv()
        model_config = get_model_config(get_default_model_role())
        label = model_display_label(model_config)
        print(f"Dr. Codex > {prompt}")
        print(f"{label} > ", end="", flush=True)
        stream_qwen_reply(prompt)
        return 0
    interactive_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
