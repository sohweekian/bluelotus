import json
from pathlib import Path

from research.research_report_generator import (
    REQUIRED_STR_REMEDIATION_SHEETS,
    build_excel_report,
    validate_required_xlsx_sheets,
)


def test_xlsx_contains_all_str_remediation_and_manifest_sheets(tmp_path):
    dataset = json.loads(Path(r"C:\bluelotus3\data\frontend\dataset_raw.json").read_text(encoding="utf-8"))
    out = tmp_path / "Bluelotus_V3_Report.xlsx"
    build_excel_report(dataset, {"archive_id": "TEST_ARCHIVE"}, out)
    result = validate_required_xlsx_sheets(out)
    assert result["missing_required_sheets"] == []
    assert set(REQUIRED_STR_REMEDIATION_SHEETS).issubset(set(result["sheet_names"]))
