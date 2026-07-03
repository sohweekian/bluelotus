import json
import zipfile
from pathlib import Path

from acms_cop.reports.signal_edge_dashboard_renderer import (
    build_shannon_thorp_refinement,
    cost_basis_rows,
    hedge_rows,
    kelly_rows,
    render_str_text_section,
    signal_entropy_rows,
    source_capacity_rows,
    str_summary_rows,
)
from research.research_report_generator import XlsxWorkbook


def _dataset():
    return {
        "meta": {"generated_at": "2026-06-20T00:00:00"},
        "law_governance_binding": {
            "governance_pack_id": "LAW-1",
            "report_memory_binding_id": "BIND-1",
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
            "system_orders_generated": 0,
        },
        "ticker_sentiment": {"GOOGL": {"clean_headline_count": 1, "dirty_headline_count": 1, "sentiment_label": "REVIEW"}},
        "source_health": [{"source": "Yahoo_Finance_RSS", "tier": 4, "signal_count": 5}],
        "portfolio": {
            "total_assets": 50000,
            "market_val": 10000,
            "positions": {"QBTS": {"unrealized": 104.82, "computed_unrealized": 10.57, "market_val": 1000}},
        },
        "research_forecasting": {
            "forecasts_by_ticker": {
                "QBTS": {"ANALYST_CONSENSUS": {"analyst_upside_pct": 50, "probability_90d": 0.7}}
            }
        },
    }


def test_str_json_root_and_text_sections_exist():
    root = build_shannon_thorp_refinement(_dataset())
    assert root["status"] == "OPERATIONAL"
    assert root["execution_authority"] == "CIO_ONLY_MANUAL"
    assert root["order_routing_enabled"] is False
    assert root["system_orders_generated"] == 0
    text = render_str_text_section(root)
    for section in [
        "STR-1 Signal Entropy Table",
        "STR-2 Source Capacity Watch",
        "STR-3 Cost Basis Reconciliation",
        "STR-4 Kelly Advisory Sizing",
        "STR-5 Hedge Ratio Review",
        "STR-6 STR Governance Footer",
    ]:
        assert section in text


def test_str_xlsx_sheets_render(tmp_path: Path):
    root = build_shannon_thorp_refinement(_dataset())
    workbook = XlsxWorkbook()
    workbook.add_sheet("STR_Signal_Entropy", signal_entropy_rows(root))
    workbook.add_sheet("STR_Source_Capacity", source_capacity_rows(root))
    workbook.add_sheet("STR_Cost_Basis", cost_basis_rows(root))
    workbook.add_sheet("STR_Kelly_Sizing", kelly_rows(root))
    workbook.add_sheet("STR_Hedge_Review", hedge_rows(root))
    workbook.add_sheet("STR_Cycle_Summary", str_summary_rows(root))
    out = tmp_path / "str.xlsx"
    workbook.save(out)
    with zipfile.ZipFile(out) as zf:
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")
    for name in [
        "STR_Signal_Entropy",
        "STR_Source_Capacity",
        "STR_Cost_Basis",
        "STR_Kelly_Sizing",
        "STR_Hedge_Review",
        "STR_Cycle_Summary",
    ]:
        assert name in workbook_xml


def test_str_rows_are_json_serializable():
    root = build_shannon_thorp_refinement(_dataset())
    json.dumps(root)
