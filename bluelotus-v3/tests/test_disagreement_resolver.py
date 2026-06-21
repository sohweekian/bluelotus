import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chief_strategist.disagreement_resolver import resolve_disagreements


def main() -> None:
    reports = [
        {"agent_id": "macro", "recommendation_to_chief_strategist": "WAIT", "risk_flags": []},
        {"agent_id": "risk", "recommendation_to_chief_strategist": "RISK_REVIEW_REQUIRED", "risk_flags": ["stress"], "requires_cio_attention": True},
    ]
    log = resolve_disagreements("test_cycle", reports)
    assert log["disagreements"]
    print("PASS disagreement resolver")


if __name__ == "__main__":
    main()
