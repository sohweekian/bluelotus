from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_clients.config_loader import env_bool, load_dotenv
from orchestration.agent_execution_queue import load_execution_queue


ROOT = Path(__file__).resolve().parents[1]
PROMPT_ARCH_PATHS = [
    ROOT / "agents",
    ROOT / "orchestration",
    ROOT / "prompting",
    ROOT / "quality",
]


def _python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(
            p for p in path.rglob("*.py")
            if "__pycache__" not in p.parts
        )
    return files


def test_no_direct_ollama_bypass_in_prompt_architecture() -> None:
    offenders = []
    for path in _python_files(PROMPT_ARCH_PATHS):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.name == "ollama_client.py":
            continue
        if "/api/chat" in text or "urllib.request" in text or "requests.post" in text:
            offenders.append(str(path))
    assert not offenders, "Direct Ollama/API caller detected outside llm_clients.ollama_client: " + ", ".join(offenders)


def test_no_broker_execution_terms_in_prompt_architecture() -> None:
    forbidden = [
        "unlock_trade",
        "place_order",
        "modify_order",
        "cancel_order",
        "trade_password",
    ]
    offenders = []
    for path in _python_files(PROMPT_ARCH_PATHS):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden:
            if term in text:
                offenders.append(f"{path}:{term}")
    assert not offenders, "Broker execution term detected in prompt architecture path: " + ", ".join(offenders)


def test_no_v2_write_target_in_prompt_architecture() -> None:
    offenders = []
    for path in _python_files(PROMPT_ARCH_PATHS):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "C:\\bluelotus2" in text or "bluelotus2_app" in text:
            offenders.append(str(path))
    assert not offenders, "V2 write target detected in prompt architecture path: " + ", ".join(offenders)


def test_compiled_prompt_audit_default_off() -> None:
    load_dotenv()
    os.environ.pop("SAVE_COMPILED_PROMPTS_FOR_AUDIT", None)
    assert env_bool("SAVE_COMPILED_PROMPTS_FOR_AUDIT", False) is False


def test_execution_queue_still_linear() -> None:
    queue = load_execution_queue()
    assert queue["execution_mode"] == "linear"
    assert int(queue["max_concurrent_llm_calls"]) == 1


if __name__ == "__main__":
    test_no_direct_ollama_bypass_in_prompt_architecture()
    test_no_broker_execution_terms_in_prompt_architecture()
    test_no_v2_write_target_in_prompt_architecture()
    test_compiled_prompt_audit_default_off()
    test_execution_queue_still_linear()
    print("PASS prompt architecture safety tests")
