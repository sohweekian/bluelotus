from __future__ import annotations

import json
from pathlib import Path

from chief_strategist_governance.csg_builder import build_chief_strategist_governance_pack
from chief_strategist_governance.partial_package import recover_csg_from_outputs
from chief_strategist_governance.reply_audit import audit_chief_strategist_reply
from chief_strategist_governance.report_renderers import render_csg_text_section


def _sample_dataset() -> dict:
    return {
        "meta": {"generated_at": "2026-06-19T00:00:00Z"},
        "portfolio": {"cash_pct": 0.94},
        "execution_governance": {
            "execution_authority": "CIO_ONLY_MANUAL",
            "order_routing_enabled": False,
        },
    }


def test_csg_builder_embeds_required_dataset_keys(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps(_sample_dataset()), encoding="utf-8")

    manifest = build_chief_strategist_governance_pack(dataset_path=dataset_path, output_dir=tmp_path / "csg")
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert manifest["status"] == "PASS"
    assert data["chief_strategist_governance"]["status"] == "ACTIVE"
    assert data["chief_strategist_governance"]["mandatory_for_chief_strategist"] is True
    assert "gold_miners" in data["active_thesis_reconciliation"]
    assert "banks_bac_wfc" in data["active_thesis_reconciliation"]
    assert data["execution_governance"]["order_routing_enabled"] is False


def test_csg_text_section_contains_core_doctrine(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps(_sample_dataset()), encoding="utf-8")
    build_chief_strategist_governance_pack(dataset_path=dataset_path, output_dir=tmp_path / "csg")
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    section = render_csg_text_section(data)

    assert "CHIEF STRATEGIST GOVERNANCE LAYER" in section
    assert "Tactical score modifies timing" in section
    assert "gold_miners" in section
    assert "banks_bac_wfc" in section
    assert "SCOUT_ORDER_FILLED" in section


def test_reply_audit_fails_bad_gold_invalidation(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps(_sample_dataset()), encoding="utf-8")
    build_chief_strategist_governance_pack(dataset_path=dataset_path, output_dir=tmp_path / "csg")
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    result = audit_chief_strategist_reply(
        "CHIEF STRATEGIST GOVERNANCE LAYER\nIran peace invalidates gold thesis. Sell all miners. CIO_ONLY_MANUAL.",
        data,
    )

    assert result["status"] == "FAIL"
    assert any(item["code"] == "IRAN_GOLD_INVALIDATION_ERROR" for item in result["failures"])


def test_reply_audit_fails_bank_context_without_nim_curve_credit(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps(_sample_dataset()), encoding="utf-8")
    build_chief_strategist_governance_pack(dataset_path=dataset_path, output_dir=tmp_path / "csg")
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    result = audit_chief_strategist_reply(
        "CHIEF STRATEGIST GOVERNANCE LAYER\nBanks are bullish. BAC should rally. Manual execution required.",
        data,
    )

    assert result["status"] == "FAIL"
    assert any(item["code"] == "BANK_CONTEXT_INCOMPLETE" for item in result["failures"])


def test_partial_package_recovers_csg_from_txt(tmp_path: Path) -> None:
    report = tmp_path / "Bluelotus_V3_Report.txt"
    report.write_text("Intro\nCHIEF STRATEGIST GOVERNANCE LAYER\nGovernance Version : v3.5-csg-001\nStatus : ACTIVE\n", encoding="utf-8")

    result = recover_csg_from_outputs([report])

    assert result["status"] == "PASS"
    assert result["findings"][0]["csg_present"] is True
    assert result["findings"][0]["governance_version"] == "v3.5-csg-001"
