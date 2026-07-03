import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.agent_execution_queue import load_execution_queue


def main() -> None:
    queue = load_execution_queue()
    assert queue["execution_mode"] == "linear"
    assert queue["max_concurrent_llm_calls"] == 1
    print("PASS no parallel llm calls")


if __name__ == "__main__":
    main()
