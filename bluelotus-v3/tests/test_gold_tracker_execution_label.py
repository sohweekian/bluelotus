from pathlib import Path


def test_bad_gold_risk_off_and_confirming_phrases_removed_from_generators():
    for path in [
        Path(r"C:\bluelotus3\research\research_report_generator.py"),
        Path(r"C:\bluelotus3\research\research_report_generator_r6.py"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "EXECUTION_BLOCKED_BY_RISK_OFF" not in text
        assert "Gold thesis confirming" not in text
