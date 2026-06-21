from __future__ import annotations

import json
from pathlib import Path

from cio_context_capsule.builder import build_cio_context_capsule
from cio_context_capsule.renderers import build_cio_context_rows, prepend_cio_context_text_section


def _dataset(tmp_path: Path) -> dict:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    return json.loads(dataset_path.read_text(encoding="utf-8"))


def test_txt_injection_prepends_capsule_before_report_body(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    text = prepend_cio_context_text_section("EXECUTIVE SUMMARY\nbody", dataset)

    assert text.startswith("==============================================================================\n  CIO CONTEXT CAPSULE - READ FIRST")
    assert text.index("CIO CONTEXT CAPSULE - READ FIRST") < text.index("EXECUTIVE SUMMARY")
    assert dataset["cio_context_capsule"]["capsule_hash"] in text


def test_excel_context_rows_include_required_fields(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    rows = build_cio_context_rows(dataset)
    fields = {row[0] for row in rows}

    assert "section_title" in fields
    assert "version" in fields
    assert "latest_cio_decision" in fields
    assert "strategic_thinking" in fields
    assert "strategic_planning" in fields
    assert "strategic_execution" in fields
    assert "execution_authority" in fields
    assert "second_tranche_authorized" in fields
    assert "capsule_hash" in fields
