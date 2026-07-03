import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.agent_execution_queue import load_execution_queue, ordered_agent_configs


def main() -> None:
    queue = load_execution_queue()
    assert queue["execution_mode"] == "linear"
    assert queue["max_concurrent_llm_calls"] == 1
    assert [item["agent_id"] for item in ordered_agent_configs()] == queue["agent_sequence"]
    print("PASS execution queue")


if __name__ == "__main__":
    main()
