from __future__ import annotations

from typing import Any, Dict, List

from llm_clients.config_loader import ConfigError, load_dotenv, load_yaml_from_env


def load_execution_queue() -> Dict[str, Any]:
    load_dotenv()
    queue = load_yaml_from_env("EXECUTION_QUEUE_PATH")
    if queue.get("execution_mode") != "linear":
        raise ConfigError("Execution queue must use linear mode.")
    if int(queue.get("max_concurrent_llm_calls", 0)) != 1:
        raise ConfigError("Execution queue must allow exactly one LLM call.")
    sequence = queue.get("agent_sequence")
    if not isinstance(sequence, list) or not sequence:
        raise ConfigError("Execution queue missing agent_sequence.")
    return queue


def ordered_agent_configs() -> List[Dict[str, Any]]:
    load_dotenv()
    registry = load_yaml_from_env("AGENT_REGISTRY_PATH")
    agents = registry.get("agents")
    if not isinstance(agents, list):
        raise ConfigError("Agent registry missing agents list.")
    queue = load_execution_queue()
    by_id = {str(item["agent_id"]): item for item in agents if item.get("enabled") is True}
    ordered: List[Dict[str, Any]] = []
    for agent_id in queue["agent_sequence"]:
        if str(agent_id) not in by_id:
            raise ConfigError(f"Execution queue references disabled or missing agent: {agent_id}")
        ordered.append(by_id[str(agent_id)])
    return sorted(ordered, key=lambda item: int(item.get("execution_order", 0)))
