import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chief_strategist.cio_briefing_generator import build_cio_action_menu, render_cio_action_menu
from llm_clients.prompt_guard import forbidden_term_matches, load_safety_policy


def main() -> None:
    briefing = {
        "cycle_id": "test_cycle",
        "recommended_posture": "REVIEW",
        "summary": "Manual review only.",
        "operator_blocks": [],
        "agent_consensus": [],
        "disagreements": [],
    }
    text = render_cio_action_menu(build_cio_action_menu(briefing), briefing)
    policy = load_safety_policy()
    assert not forbidden_term_matches([text], policy["forbidden_terms"])
    print("PASS no order language")


if __name__ == "__main__":
    main()
