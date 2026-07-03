from pei.event_registry import build_candidate_events
from pei.event_to_sleeve_mapper import build_sleeve_map
from pei.event_tree_builder import build_scenario_trees
from pei.portfolio_playbook_renderer import build_portfolio_playbook


def _dataset():
    return {"law_governance_binding": {"governance_pack_id": "GOVPACK_TEST", "report_memory_binding_id": "BIND_TEST"}}


def test_pei_playbook_contains_allowed_and_blocked_actions():
    trees = build_scenario_trees(build_candidate_events(_dataset()))
    playbook = build_portfolio_playbook(trees, build_sleeve_map(trees))

    assert playbook
    assert all(row["allowed_action"] for row in playbook)
    assert all(row["blocked_action"] for row in playbook)
    assert all(row["execution_authority"] == "CIO_ONLY_MANUAL" for row in playbook)
