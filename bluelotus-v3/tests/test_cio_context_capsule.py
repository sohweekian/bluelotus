from __future__ import annotations

import json
from pathlib import Path

from cio_context_capsule.builder import build_cio_context_capsule, compute_capsule_hash
from cio_context_capsule.renderers import capsule_is_active, render_cio_context_text_section
from cio_context_capsule.validator import validate_cio_context_capsule


def test_build_cio_context_capsule_embeds_dataset_and_hash(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}, "portfolio": {}, "execution": {}}), encoding="utf-8")

    manifest = build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    capsule = dataset["cio_context_capsule"]

    assert manifest["status"] == "PASS"
    assert capsule["version"] == "v3.5-cio-context-001"
    assert capsule["status"] == "ACTIVE"
    assert capsule["mandatory_for_all_chief_strategist_replies"] is True
    assert capsule["capsule_hash"] == compute_capsule_hash(capsule)
    assert capsule["core_doctrine"]["execution_authority"] == "CIO_ONLY_MANUAL"
    assert capsule["core_doctrine"]["order_routing_enabled"] is False
    assert capsule["core_doctrine"]["system_generated_orders"] == 0
    assert capsule_is_active(dataset)


def test_cio_context_text_renders_required_read_first_block(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    text = render_cio_context_text_section(dataset)

    assert "CIO CONTEXT CAPSULE - READ FIRST" in text
    assert "Strategic Thinking" in text
    assert "Strategic Planning" in text
    assert "Strategic Execution" in text
    assert "CIO_ONLY_MANUAL" in text
    assert "Scout positioning only, not second tranche" in text


def test_validator_accepts_json_only_as_partial_package(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")

    result = validate_cio_context_capsule(
        dataset_path=dataset_path,
        txt_path=tmp_path / "missing.txt",
        word_path=tmp_path / "missing.docx",
        excel_path=tmp_path / "missing.xlsx",
        output_path=tmp_path / "validation.json",
        partial_ok=True,
    )

    assert result["status"] == "WARNING"
    assert not result["failed_checks"]
    assert {"txt_report_missing", "word_report_missing", "excel_report_missing"}.issubset(set(result["warnings"]))
