import json
from pathlib import Path

from governance.contradiction_governance import (
    build_contradiction_governance,
    build_cio_decision_strip,
    write_contradiction_governance,
)


def _summary(payload):
    return {"exists": True, "excerpt": json.dumps(payload)}


def _cycle_context(operator_full=None, dataset=None):
    operator_full = operator_full or {
        "summary": {"blocked_actions": ["SCALE_IN_ADD", "INCREASE_GOLD_THESIS_RISK"]},
        "operators": {
            "gold_thesis": {"blocked_actions": ["INCREASE_GOLD_THESIS_RISK"]},
            "concentration_risk": {"blocked_actions": ["CONCENTRATION_REVIEW_REQUIRED"]},
        },
    }
    dataset = dataset or {
        "orders": {"open_order_count": 1, "orders": [{"ticker": "AU", "side": "BUY"}]},
        "risk_metrics": {
            "largest_position": {"ticker": "AU"},
            "constraint_breaches": ["AU_WEIGHT_BREACH"],
        },
    }
    return {
        "cycle_id": "test_cycle_001",
        "operator_verdict_pack": {
            "source_summary": _summary(operator_full),
            "blocked_actions": [],
            "allowed_actions": ["WAIT", "HOLD", "REVIEW"],
            "manual_execution_required": True,
            "llm_order_generation": False,
        },
        "dataset_summary": _summary(dataset),
    }


def _briefing(posture="WAIT"):
    return {
        "cycle_id": "test_cycle_001",
        "summary": "Chief Strategist synthesized test reports.",
        "recommended_posture": posture,
        "manual_execution_required": True,
        "llm_order_generation": False,
    }


def test_add_action_conflicts_with_deterministic_block():
    reports = [{
        "agent_id": "portfolio_structure",
        "allowed_actions_observed": ["SCALE_IN_ADD"],
        "recommendation_to_chief_strategist": "WAIT",
    }]
    payload = build_contradiction_governance(_cycle_context(), reports, _briefing(), {})
    domains = {item["domain"] for item in payload["contradiction_register"]["contradictions"]}
    assert "execution_governance" in domains
    assert payload["cio_decision_strip"]["posture"] == "CIO_VERIFICATION_REQUIRED"


def test_thesis_order_conflict_detected_for_gold_order_book():
    payload = build_contradiction_governance(_cycle_context(), [], _briefing("REVIEW"), {})
    domains = {item["domain"] for item in payload["contradiction_register"]["contradictions"]}
    assert "thesis_vs_order_book" in domains


def test_policy_concentration_conflict_detected():
    payload = build_contradiction_governance(_cycle_context(), [], _briefing("REVIEW"), {})
    domains = {item["domain"] for item in payload["contradiction_register"]["contradictions"]}
    assert "portfolio_policy_vs_risk" in domains


def test_degraded_council_posture_conflict_detected():
    payload = build_contradiction_governance(
        _cycle_context(operator_full={"summary": {"blocked_actions": []}, "operators": {}}),
        [],
        _briefing("HOLD"),
        {},
        agent_errors=[{"agent_id": "macro", "error": "timeout"}],
    )
    items = payload["contradiction_register"]["contradictions"]
    assert any(item["domain"] == "agent_runtime_vs_report_posture" for item in items)
    assert any(item["severity"] == "P1" for item in items)


def test_public_dashboard_freshness_conflict_detected():
    payload = build_contradiction_governance(
        _cycle_context(operator_full={"summary": {"blocked_actions": []}, "operators": {}}),
        [],
        _briefing("REVIEW"),
        {},
        public_state={"cycle_id": "old_cycle"},
    )
    assert any(item["domain"] == "publication_freshness" for item in payload["contradiction_register"]["contradictions"])


def test_weak_agent_quality_generates_differentiation_warning():
    payload = build_contradiction_governance(
        _cycle_context(operator_full={"summary": {"blocked_actions": []}, "operators": {}}),
        [],
        _briefing("REVIEW"),
        {"failed_agents": ["macro_strategist", "sentiment_narrative"]},
    )
    assert any(item["domain"] == "agent_quality" for item in payload["contradiction_register"]["contradictions"])


def test_safety_invariants_remain_manual_only():
    payload = build_contradiction_governance(_cycle_context(), [], _briefing("REVIEW"), {})
    register = payload["contradiction_register"]
    strip = payload["cio_decision_strip"]
    assert register["manual_execution_required"] is True
    assert register["llm_order_generation"] is False
    assert register["order_routing_enabled"] is False
    assert strip["manual_execution_required"] is True
    assert strip["llm_order_generation"] is False
    assert strip["order_routing_enabled"] is False


def test_write_contradiction_governance_outputs_cycle_and_latest_files(tmp_path, monkeypatch):
    monkeypatch.chdir(Path("C:/bluelotus3"))
    payload = build_contradiction_governance(_cycle_context(), [], _briefing("REVIEW"), {})
    paths = write_contradiction_governance(tmp_path, payload)
    for path in paths.values():
        assert Path(path).exists()
    assert json.loads(Path(paths["cycle_contradiction_register"]).read_text(encoding="utf-8"))["cycle_id"] == "test_cycle_001"

