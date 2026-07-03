import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.linear_agent_orchestrator import LinearAgentOrchestrator


def main() -> None:
    orchestrator = LinearAgentOrchestrator()
    orchestrator._llm_call_active = True
    try:
        orchestrator.run_one_agent({"agent_id": "x"}, {})
        raise AssertionError("Parallel guard failed.")
    except RuntimeError as exc:
        assert "Parallel LLM call blocked" in str(exc)
    print("PASS linear agent orchestrator")


if __name__ == "__main__":
    main()
