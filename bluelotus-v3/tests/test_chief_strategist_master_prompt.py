from __future__ import annotations

import json
from pathlib import Path

from cio_context_capsule.master_prompt import (
    build_chief_strategist_master_prompt,
    build_master_prompt,
    compute_prompt_hash,
)
from cio_context_capsule.renderers import (
    build_master_prompt_rows,
    master_prompt_is_active,
    prepend_master_prompt_and_cio_context,
)
from cio_context_capsule.builder import build_cio_context_capsule
from cio_context_capsule.validator import validate_cio_context_capsule


def test_master_prompt_artifact_exists_and_dataset_contains_prompt(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    output_path = tmp_path / "chief_strategist_master_prompt_latest.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")

    manifest = build_chief_strategist_master_prompt(dataset_path=dataset_path, output_path=output_path)
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert manifest["status"] == "PASS"
    assert artifact["version"] == "v1.0-chief-strategist-master-prompt"
    assert artifact["prompt_hash"] == compute_prompt_hash(artifact)
    assert dataset["chief_strategist_master_prompt"]["read_first"] is True
    assert master_prompt_is_active(dataset)


def test_master_prompt_hash_changes_when_prompt_text_changes() -> None:
    prompt = build_master_prompt("2026-06-19T00:00:00Z")
    original_hash = compute_prompt_hash(prompt)
    prompt["master_prompt_text"] += "\nExtra deterministic test sentence."

    assert compute_prompt_hash(prompt) != original_hash


def test_txt_report_master_prompt_first(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    report = prepend_master_prompt_and_cio_context("PORTFOLIO\nTACTICAL DATA", dataset)

    assert report.index("CHIEF STRATEGIST MASTER PROMPT") < report.index("CIO CONTEXT CAPSULE")
    assert report.index("CIO CONTEXT CAPSULE") < report.index("PORTFOLIO")
    assert dataset["chief_strategist_master_prompt"]["prompt_hash"] in report


def test_xlsx_master_prompt_rows_include_required_front_page_fields(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    rows = build_master_prompt_rows(dataset)
    fields = {row[0] for row in rows[1:]}

    assert "Version" in fields
    assert "Prompt Hash" in fields
    assert "Core Instruction" in fields
    assert "Full Master Prompt Text" in fields


def test_missing_master_prompt_fails_validation(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    dataset.pop("chief_strategist_master_prompt", None)
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

    result = validate_cio_context_capsule(
        dataset_path=dataset_path,
        txt_path=tmp_path / "missing.txt",
        word_path=tmp_path / "missing.docx",
        excel_path=tmp_path / "missing.xlsx",
        output_path=tmp_path / "validation.json",
        partial_ok=True,
    )

    assert result["status"] == "FAIL"
    assert "chief_strategist_master_prompt_missing" in result["failed_checks"]
