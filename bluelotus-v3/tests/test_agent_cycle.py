import json

from acms_cop.extractors.agent_extractor import extract_agent_cycles


def test_agent_extractor_stores_path_not_verbose_output(tmp_path):
    reports = tmp_path / "agent_reports"
    reports.mkdir()
    (reports / "risk.json").write_text(json.dumps({
        "agent_name": "Risk Challenger",
        "agent_role": "Risk desk",
        "recommendation_to_chief_strategist": "WAIT",
        "confidence": 0.8,
        "key_findings": ["A" * 5000],
    }), encoding="utf-8")
    rows = extract_agent_cycles(tmp_path)
    assert len(rows) == 1
    assert rows[0]["raw_output_path"].endswith("risk.json")
    assert len(rows[0]["summary"]) < 1900

