from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agents.base_agent as base_agent_module
from agents.portfolio_structure_agent import PortfolioStructureAgent
from llm_clients.json_response_validator import validate_json_response
from orchestration.agent_execution_queue import load_execution_queue, ordered_agent_configs
from orchestration.cycle_context_builder import build_cycle_context
from prompting.context_builder import build_desk_context
from prompting.memory_retriever import retrieve_memory
from prompting.prompt_compiler import compile_prompts
from prompting.retry_prompt_builder import (
    build_retry_user_prompt,
    classify_error,
    should_retry,
)
from quality.agent_quality_scorer import score_agent_report, summarise_cycle_quality


ROOT = Path(__file__).resolve().parents[1]


def _set_env() -> None:
    os.environ.setdefault("BLUELOTUS_PROJECT_ROOT", str(ROOT))
    os.environ.setdefault("BLUELOTUS_CONFIG_FILE", "config/bluelotus3.yaml")
    os.environ.setdefault("AGENT_REGISTRY_PATH", "config/agent_registry.yaml")
    os.environ.setdefault("EXECUTION_QUEUE_PATH", "config/execution_queue.yaml")
    os.environ.setdefault("THESIS_REGISTRY_PATH", "config/thesis_registry.yaml")
    os.environ.setdefault("PROMPT_REGISTRY_PATH", "config/prompt_registry.yaml")
    os.environ.setdefault("AGENT_CONTEXT_MAP_PATH", "config/agent_context_map.yaml")
    os.environ.setdefault("MEMORY_RETRIEVAL_POLICY_PATH", "config/memory_retrieval_policy.yaml")
    os.environ.setdefault("V3_CYCLE_OUTPUT_DIR", "data/v3_cycles")
    os.environ.setdefault("AGENT_REPORT_SCHEMA_PATH", "schemas/agent_report.schema.json")
    os.environ.setdefault("LLM_MAX_RETRIES", "2")


def _agent_config(agent_id: str) -> dict:
    for item in ordered_agent_configs():
        if item["agent_id"] == agent_id:
            return item
    raise AssertionError(f"agent not found: {agent_id}")


def _sample_report(agent_id: str = "portfolio_structure") -> dict:
    return {
        "schema_version": "bluelotus_v3_agent_report_v1.0",
        "cycle_id": "placeholder",
        "agent_id": agent_id,
        "agent_name": "Portfolio Structure Agent",
        "agent_role": "Interpret concentration and cash.",
        "model_used": "test",
        "input_refs": {},
        "summary": "Portfolio structure desk flags concentration via equity HHI.",
        "key_findings": ["[DATASET] concentration_hhi_equity_only is elevated because VIXY is the largest equity weight."],
        "risk_flags": ["P1 PNL integrity conflicts require CIO review."],
        "blocked_actions_observed": [],
        "allowed_actions_observed": ["WAIT"],
        "affected_theses": [],
        "affected_assets": ["VIXY"],
        "causal_completeness": "partial",
        "blind_spots": ["risk_metrics field missing intraday liquidity depth."],
        "confidence": 0.72,
        "recommendation_to_chief_strategist": "RISK_REVIEW_REQUIRED",
        "requires_cio_attention": True,
        "manual_execution_required": True,
        "llm_order_generation": False,
        "created_at_sgt": "2026-06-17T00:00:00+08:00",
    }


def test_config_files_load() -> None:
    _set_env()
    for rel in [
        "config/agent_context_map.yaml",
        "config/memory_retrieval_policy.yaml",
        "config/prompt_registry.yaml",
        "config/execution_queue.yaml",
    ]:
        data = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8-sig"))
        assert isinstance(data, dict), rel
    queue = load_execution_queue()
    assert queue["execution_mode"] == "linear"
    assert isinstance(queue.get("retry_policy"), dict)
    assert int(queue["retry_policy"]["max_retries"]) >= 1


def test_context_builder_respects_whitelists() -> None:
    _set_env()
    ctx = build_cycle_context("test_prompt_arch_context")
    portfolio = build_desk_context("portfolio_structure", ctx)
    assert "portfolio" in portfolio
    assert "risk_metrics" in portfolio
    assert "regime" not in portfolio
    assert "ticker_sentiment" not in portfolio
    assert "live_news" not in portfolio

    catalyst = build_desk_context("catalyst_intelligence", ctx)
    assert "live_news" in catalyst

    risk = build_desk_context("risk_challenger", ctx)
    assert isinstance(risk.get("relevant_operators"), dict)

    thesis = build_desk_context("thesis_lifecycle", ctx)
    assert "thesis_registry" in thesis


def test_memory_retriever_is_safe_without_current_cycle() -> None:
    _set_env()
    memory = retrieve_memory("portfolio_structure", "test_prompt_arch_context")
    assert memory is None or isinstance(memory, dict)
    if memory:
        assert len(json.dumps(memory, ensure_ascii=False)) <= 1600


def test_prompt_compiler_builds_prompts() -> None:
    _set_env()
    ctx = build_cycle_context("test_prompt_arch_prompt")
    agent_config = _agent_config("portfolio_structure")
    desk_context = build_desk_context("portfolio_structure", ctx)
    memory = retrieve_memory("portfolio_structure", str(ctx["cycle_id"]))
    system_prompt, user_prompt = compile_prompts(
        "portfolio_structure",
        agent_config,
        desk_context,
        memory,
        ctx,
    )
    assert "BlueLotus" in system_prompt
    assert "desk_context" in user_prompt
    assert len(system_prompt) > 1000
    assert len(user_prompt) > 1000


def test_retry_builder_classifies_and_limits() -> None:
    _set_env()
    assert classify_error("Model response is not valid JSON") == "JSON_PARSE_ERROR"
    assert classify_error("Missing required key: summary") == "MISSING_FIELD"
    assert classify_error("Key confidence must be number") == "WRONG_TYPE"
    assert classify_error("Key risk_flags must contain no more than 3 items") == "ARRAY_TOO_LONG"
    assert classify_error("Key recommendation must be one of the configured enum values") == "ENUM_VIOLATION"
    assert should_retry("Missing required key: summary", 0, "portfolio_structure") is True
    assert should_retry("Missing required key: summary", 2, "portfolio_structure") is False
    retry_prompt = build_retry_user_prompt("Missing required key: summary", "{}", "portfolio_structure", 1)
    assert "RETRY ATTEMPT 1" in retry_prompt
    assert "VALIDATION ERROR" in retry_prompt


def test_quality_scorer_and_summary() -> None:
    _set_env()
    report = _sample_report()
    report["cycle_id"] = "test_cycle"
    quality = score_agent_report("portfolio_structure", report, _agent_config("portfolio_structure"))
    assert quality.pct_score > 60
    summary = summarise_cycle_quality({"portfolio_structure": quality})
    assert "average_score" in summary


def test_feature_flag_selection_without_llm_call() -> None:
    _set_env()
    config = _agent_config("portfolio_structure")
    agent = PortfolioStructureAgent(config)
    os.environ["USE_NEW_PROMPT_ARCH"] = "false"
    os.environ["PROMPT_ARCH_TEST_AGENT"] = ""
    assert agent.use_new_prompt_architecture() is False
    os.environ["USE_NEW_PROMPT_ARCH"] = "true"
    os.environ["PROMPT_ARCH_TEST_AGENT"] = "portfolio_structure"
    assert agent.use_new_prompt_architecture() is True
    os.environ["PROMPT_ARCH_TEST_AGENT"] = "risk_challenger"
    assert agent.use_new_prompt_architecture() is False


def test_runtime_old_new_and_retry_paths_with_mocked_llm() -> None:
    _set_env()
    config = _agent_config("portfolio_structure")
    agent = PortfolioStructureAgent(config)
    ctx = build_cycle_context("test_prompt_arch_mock")
    cycle_dir = ROOT / "data" / "v3_cycles" / "test_prompt_arch_mock"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    ctx["cycle_dir"] = str(cycle_dir)

    original_chat = base_agent_module.chat_with_model
    calls = []

    def fake_chat_success(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "parsed": _sample_report(), "response_text": json.dumps(_sample_report())}

    try:
        base_agent_module.chat_with_model = fake_chat_success
        os.environ["USE_NEW_PROMPT_ARCH"] = "false"
        os.environ["PROMPT_ARCH_TEST_AGENT"] = ""
        legacy = agent.run(ctx)
        validate_json_response(json.dumps(legacy), "AGENT_REPORT_SCHEMA_PATH", save_failed=False)
        assert legacy["prompt_architecture_enabled"] is False

        os.environ["USE_NEW_PROMPT_ARCH"] = "true"
        os.environ["PROMPT_ARCH_TEST_AGENT"] = "portfolio_structure"
        new = agent.run(ctx)
        validate_json_response(json.dumps(new), "AGENT_REPORT_SCHEMA_PATH", save_failed=False)
        assert new["prompt_architecture_enabled"] is True
        assert (cycle_dir / "prompt_audit_portfolio_structure.json").exists()
    finally:
        base_agent_module.chat_with_model = original_chat

    attempts = {"count": 0}

    def fake_chat_retry(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return {"ok": False, "error": "Missing required key: summary", "response_text": "{}"}
        return {"ok": True, "parsed": _sample_report(), "response_text": json.dumps(_sample_report())}

    try:
        base_agent_module.chat_with_model = fake_chat_retry
        os.environ["USE_NEW_PROMPT_ARCH"] = "true"
        os.environ["PROMPT_ARCH_TEST_AGENT"] = "portfolio_structure"
        report = agent.run(ctx)
        assert report["retry_count"] == 1
        assert (cycle_dir / "agent_portfolio_structure_raw_failed_attempt_1.txt").exists()
        assert (cycle_dir / "agent_portfolio_structure_retry_record.json").exists()
    finally:
        base_agent_module.chat_with_model = original_chat


if __name__ == "__main__":
    test_config_files_load()
    test_context_builder_respects_whitelists()
    test_memory_retriever_is_safe_without_current_cycle()
    test_prompt_compiler_builds_prompts()
    test_retry_builder_classifies_and_limits()
    test_quality_scorer_and_summary()
    test_feature_flag_selection_without_llm_call()
    test_runtime_old_new_and_retry_paths_with_mocked_llm()
    print("PASS prompt architecture runtime tests")
