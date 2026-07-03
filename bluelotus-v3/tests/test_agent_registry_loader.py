import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.agent_execution_queue import ordered_agent_configs


def main() -> None:
    agents = ordered_agent_configs()
    assert agents
    assert agents[0]["agent_id"] == "data_integrity"
    assert all(item.get("enabled") is True for item in agents)
    print("PASS agent registry loader")


if __name__ == "__main__":
    main()
