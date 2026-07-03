from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config_loader import env_required, load_dotenv, load_main_config, project_root, resolve_project_path
from .model_router import get_default_model_role, get_model_config


NO_THINK_QWEN_TEMPLATE = r'''{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ range .Messages }}{{ if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ .Content }}<|im_end|>
{{ end }}{{ end }}<|im_start|>assistant
'''


def build_modelfile_text(model_config: dict) -> str:
    model_name = str(model_config.get("base_model_name") or model_config["model_name"])
    lines = [f"FROM {model_name}"]
    if bool(model_config.get("no_think_template", False)):
        lines.extend([
            'TEMPLATE """',
            NO_THINK_QWEN_TEMPLATE.rstrip(),
            '"""',
            "PARAMETER stop <|im_start|>",
            "PARAMETER stop <|im_end|>",
        ])
    options = model_config.get("options")
    if isinstance(options, dict):
        for key, value in options.items():
            lines.append(f"PARAMETER {key} {value}")
    return "\n".join(lines) + "\n"


def create_alias() -> dict:
    load_dotenv()
    main_config = load_main_config()
    ollama_config = main_config.get("ollama", {})
    cli_env = str(ollama_config.get("cli_path_env") or "")
    alias_env = str(ollama_config.get("alias_name_env") or "")
    if not cli_env or not alias_env:
        raise RuntimeError("Ollama CLI or alias environment key is missing from config.")

    cli_path = env_required(cli_env)
    alias_name = env_required(alias_env)
    model_role = get_default_model_role()
    model_config = get_model_config(model_role, resolve_runtime_model=False)

    out_dir = resolve_project_path(env_required("LLM_OUTPUT_DIR"))
    out_dir.mkdir(parents=True, exist_ok=True)
    modelfile_path = out_dir / "configured_ollama_alias.Modelfile"
    modelfile_path.write_text(build_modelfile_text(model_config), encoding="utf-8")

    completed = subprocess.run(
        [cli_path, "create", alias_name, "-f", str(modelfile_path)],
        cwd=str(project_root()),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "alias_name": alias_name,
        "model_role": model_role,
        "modelfile_path": str(modelfile_path),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }


def main() -> int:
    result = create_alias()
    import json

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
