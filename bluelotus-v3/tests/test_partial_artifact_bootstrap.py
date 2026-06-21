from __future__ import annotations

import json
from pathlib import Path

from cio_context_capsule.builder import build_cio_context_capsule
from cio_context_capsule.partial_artifact import recover_capsule_from_artifacts
from cio_context_capsule.renderers import render_cio_context_text_section


def test_txt_only_bootstrap_recovers_cio_memory(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_raw.json"
    dataset_path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    build_cio_context_capsule(dataset_path=dataset_path, output_dir=tmp_path / "cio_context")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    txt = tmp_path / "Bluelotus_V3_Report.txt"
    txt.write_text(render_cio_context_text_section(dataset) + "\nbody", encoding="utf-8")

    result = recover_capsule_from_artifacts([txt])

    assert result["status"] == "PASS"
    assert result["present_count"] == 1
    assert result["hashes_match"] is True
    assert result["findings"][0]["has_strategic_thinking"] is True
    assert result["findings"][0]["has_strategic_planning"] is True
    assert result["findings"][0]["has_strategic_execution"] is True
    assert result["findings"][0]["has_cio_only_manual"] is True


def test_missing_artifact_bootstrap_warns(tmp_path: Path) -> None:
    result = recover_capsule_from_artifacts([tmp_path / "missing.txt"])

    assert result["status"] == "WARNING"
    assert result["present_count"] == 0
