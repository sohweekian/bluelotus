from agents.base_agent import semantic_content_error
from prompting.retry_prompt_builder import build_retry_user_prompt, classify_error, should_retry


def test_semantic_gate_detects_scaffold_empty_response():
    assert semantic_content_error({
        "summary": "",
        "key_findings": [],
        "confidence": 0.5,
    }) is True


def test_semantic_gate_detects_nonempty_summary_with_empty_findings():
    assert semantic_content_error({
        "summary": "Risk appears stable.",
        "key_findings": [],
        "confidence": 0.5,
    }) is True


def test_semantic_gate_detects_blank_finding_items():
    assert semantic_content_error({
        "summary": "Risk appears stable.",
        "key_findings": ["", "   "],
        "confidence": 0.7,
    }) is True


def test_semantic_gate_accepts_summary_and_one_finding():
    assert semantic_content_error({
        "summary": "Risk challenger found a concentration issue.",
        "key_findings": ["[DATASET] ASTS remains largest exposure."],
        "confidence": 0.5,
    }) is False


def test_empty_content_response_retry_contract_requires_key_finding():
    assert classify_error("EMPTY_CONTENT_RESPONSE: key_findings empty") == "EMPTY_CONTENT_RESPONSE"
    assert should_retry("EMPTY_CONTENT_RESPONSE: key_findings empty", 0, "risk_challenger") is True
    prompt = build_retry_user_prompt(
        "EMPTY_CONTENT_RESPONSE: key_findings empty",
        '{"summary":"Risk appears stable.","key_findings":[],"confidence":0.5}',
        "risk_challenger",
        1,
    )
    assert "key_findings" in prompt
    assert "at least one" in prompt.lower()
    assert "Do NOT return empty arrays again." in prompt

