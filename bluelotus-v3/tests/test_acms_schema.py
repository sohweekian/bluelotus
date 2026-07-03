from pathlib import Path

from acms_cop.db.migrations import SCHEMA_PATH, split_sql


def test_acms_schema_contains_required_tables_and_indexes():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    for table in [
        "acms_cycle",
        "acms_ticker_cycle",
        "acms_theme_cycle",
        "acms_forecast",
        "acms_outcome",
        "acms_decision",
        "acms_agent_cycle",
        "acms_data_quality_event",
        "acms_signal_entropy",
        "acms_source_capacity",
        "acms_cost_basis_reconciliation",
        "acms_kelly_sizing_advisory",
        "acms_hedge_ratio_review",
        "acms_str_cycle_summary",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert sql.count("FOREIGN KEY") >= 7
    assert "idx_acms_ticker_cycle" in sql
    assert len(split_sql(sql)) >= 14
