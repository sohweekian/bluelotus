from pei.event_registry import build_candidate_events
from pei.event_tree_builder import build_scenario_trees


def _dataset():
    return {"law_governance_binding": {"governance_pack_id": "GOVPACK_TEST", "report_memory_binding_id": "BIND_TEST"}}


def test_pei_branch_probabilities_sum_to_one_per_event():
    trees = build_scenario_trees(build_candidate_events(_dataset()))

    assert trees
    for tree in trees:
        probabilities = [float(branch["branch_probability"]) for branch in tree["branches"]]
        assert len(probabilities) >= 3
        assert abs(sum(probabilities) - 1.0) < 0.0001


def test_pei_branches_have_confirmations_and_kill_conditions():
    trees = build_scenario_trees(build_candidate_events(_dataset()))

    for tree in trees:
        for branch in tree["branches"]:
            assert branch["confirmation_signals"]
            assert branch["kill_conditions"]
            assert branch["resolution_criteria"]
