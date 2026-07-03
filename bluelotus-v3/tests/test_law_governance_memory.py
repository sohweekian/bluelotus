from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

_V3_ROOT = Path(__file__).resolve().parent.parent
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))

from law_governance.bind_report_memory import bind_report_memory
from law_governance.export_active_governance_pack import build_active_governance_pack, export_active_governance_pack
from law_governance.law_core import ACTIVE_PACK_PATH, binding_hash, content_hash, make_id, require_memory_type, require_reason_code
from law_governance.memory_diff import summarize_diff
from research.research_report_generator import build_law_governance_binding_model, render_governance_law_binding_section

DATASET_RAW = _V3_ROOT / "data" / "frontend" / "dataset_raw.json"
TXT_REPORT = _V3_ROOT / "research" / "Bluelotus_V3_Report.txt"
DOCX_REPORT = _V3_ROOT / "research" / "Bluelotus_V3_Report.docx"
XLSX_REPORT = _V3_ROOT / "research" / "Bluelotus_V3_Report.xlsx"


def test_content_hash_is_order_independent():
    left = {"b": 2, "a": {"x": 1, "y": 2}}
    right = {"a": {"y": 2, "x": 1}, "b": 2}
    assert content_hash(left) == content_hash(right)


def test_memory_type_and_reason_code_allowlists():
    assert require_memory_type("master_prompt") == "MASTER_PROMPT"
    assert require_reason_code("founding_baseline") == "FOUNDING_BASELINE"


def test_make_id_contains_prefix_type_and_hash_prefix():
    memory_id = make_id("MEM", "EXECUTION_DOCTRINE", "abcdef1234567890")
    assert memory_id.startswith("MEM_EXECUTION_DOCTRINE_")
    assert memory_id.endswith("_abcdef1234")


def test_diff_summary_tracks_top_level_changes():
    diff = summarize_diff({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert diff["added_keys"] == ["c"]
    assert diff["removed_keys"] == ["a"]
    assert diff["changed_keys"] == ["b"]
    assert diff["change_count"] == 3


def test_governance_law_report_section_renders_active_memory():
    pack = {
        "version": "v1.0-governance-law-pack",
        "status": "ACTIVE",
        "generated_at": "2026-06-18T00:00:00",
        "active_pack_hash": "abc123",
        "active_memory": {
            "master_prompt": {
                "memory_id": "MEM_MASTER_PROMPT_1",
                "version": "v1",
                "hash": "hash1",
            }
        },
    }
    text = render_governance_law_binding_section(pack)
    assert "00A · LAW & ORDER GOVERNANCE BINDING" in text
    assert "MEM_MASTER_PROMPT_1" in text
    assert "The V3 pipeline operates under law and does not write the law" in text


def test_active_governance_pack_exported():
    result = export_active_governance_pack()
    assert result["status"] == "PASS"
    assert ACTIVE_PACK_PATH.exists()
    pack = json.loads(ACTIVE_PACK_PATH.read_text(encoding="utf-8"))
    assert pack["governance_pack_id"].startswith("GOVPACK_")
    assert pack["active_pack_hash"]


def test_report_memory_binding_created():
    result = bind_report_memory("pytest_law_binding", "pytest_cycle")
    assert result["status"] == "ACTIVE"
    assert result["binding_id"].startswith("BIND_REPORT_MEMORY_")
    assert result["active_pack_hash"]


def test_dataset_raw_contains_law_governance_binding():
    dataset = json.loads(DATASET_RAW.read_text(encoding="utf-8"))
    binding = dataset.get("law_governance_binding") or {}
    assert binding["status"] == "BOUND"
    assert binding["governance_pack_hash"]
    assert binding["report_memory_binding_id"]
    assert binding["execution_authority"] == "CIO_ONLY_MANUAL"
    assert binding["order_routing_enabled"] is False
    assert binding["system_orders_generated"] == 0


def test_txt_report_prints_law_governance_section():
    text = TXT_REPORT.read_text(encoding="utf-8")
    assert "00A · LAW & ORDER GOVERNANCE BINDING" in text
    assert "Active Governance Pack ID" in text
    assert "Report Memory Binding ID" in text
    assert "The V3 pipeline operates under law and does not write the law" in text


def test_docx_report_prints_law_governance_section():
    with zipfile.ZipFile(DOCX_REPORT) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "00A · LAW &amp; ORDER GOVERNANCE BINDING" in xml or "00A · LAW &amp;amp; ORDER GOVERNANCE BINDING" in xml
    assert "ACTIVE LAW PACK GOVERNING THIS REPORT" in xml
    assert "law_governance_memory" in xml


def test_xlsx_report_prints_law_governance_section():
    with zipfile.ZipFile(XLSX_REPORT) as z:
        workbook_xml = z.read("xl/workbook.xml").decode("utf-8")
        sheet_text = "\n".join(
            z.read(name).decode("utf-8")
            for name in z.namelist()
            if name.startswith("xl/worksheets/sheet")
        )
    assert "LAW_GOVERNANCE_BINDING" in workbook_xml
    assert "Active Governance Pack ID" in sheet_text
    assert "Report Memory Binding ID" in sheet_text
    assert "law_governance_memory" in sheet_text


def test_missing_law_pack_blocks_add_risk():
    model = build_law_governance_binding_model({}, {"status": "UNKNOWN"}, {"status": "MISSING"})
    assert model["status"] == "MISSING"
    assert model["cio_action_cap"] == "ADD_BLOCKED"
    assert model["warning"] == "ACTIVE_GOVERNANCE_PACK_MISSING"


def test_invalid_law_validation_marks_report_review_required():
    model = build_law_governance_binding_model({"active_pack_hash": "abc", "version": "v1"}, {"status": "FAIL"}, {"status": "ACTIVE"})
    assert model["status"] == "INVALID"
    assert model["report_status"] == "GOVERNANCE_REVIEW_REQUIRED"
    assert model["cio_action_cap"] == "ADD_BLOCKED"


def test_report_binding_hash_reproducible():
    payload = {
        "report_id": "report",
        "cycle_id": "cycle",
        "active_pack_hash": "packhash",
        "memory_ids": {"master_prompt_memory_id": "MEM1"},
        "binding_status": "ACTIVE",
    }
    assert binding_hash(payload) == binding_hash(dict(reversed(list(payload.items()))))


def test_execution_doctrine_unchanged_after_law_binding():
    dataset = json.loads(DATASET_RAW.read_text(encoding="utf-8"))
    binding = dataset.get("law_governance_binding") or {}
    assert binding["execution_authority"] == "CIO_ONLY_MANUAL"
    assert binding["pipeline_law_writing_authority"] is False
    assert binding["order_routing_enabled"] is False
    assert binding["system_orders_generated"] == 0
