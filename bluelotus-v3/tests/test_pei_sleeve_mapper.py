from pei.event_registry import build_candidate_events
from pei.event_to_sleeve_mapper import build_sleeve_map
from pei.event_tree_builder import build_scenario_trees


def _dataset():
    return {"law_governance_binding": {"governance_pack_id": "GOVPACK_TEST", "report_memory_binding_id": "BIND_TEST"}}


def test_pei_sleeve_mapper_links_events_to_portfolio_sleeves():
    rows = build_sleeve_map(build_scenario_trees(build_candidate_events(_dataset())))
    sleeves = {row["affected_sleeve"] for row in rows}

    assert "high_beta_relief_basket" in sleeves
    assert "volatility_hedge" in sleeves
    assert "pl_asts_tactical_cash_generation_engine" in sleeves
    assert all(row["required_confirmation"] for row in rows)
    assert all(row["kill_condition"] for row in rows)
