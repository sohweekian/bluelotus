from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .canonical_schema import SECTION_COVERAGE_KEYS


def sha256_file(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return ""


def sha256_object(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def empty_section_coverage() -> Dict[str, Dict[str, bool]]:
    return {key: {"dataset": True, "txt": False, "docx": False, "xlsx": False, "dashboard": False} for key in SECTION_COVERAGE_KEYS}


def build_artifact_manifest(dataset: Dict[str, Any], paths: Dict[str, Any] | None = None) -> Dict[str, Any]:
    paths = paths or {}
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    readonly = dataset.get("portfolio_readonly") if isinstance(dataset.get("portfolio_readonly"), dict) else {}
    coverage = empty_section_coverage()
    status = "ARTIFACTS_CONSISTENT"
    errors = []
    for name, p in paths.items():
        if p and not Path(p).exists():
            status = "ARTIFACT_STALE"
            errors.append(f"{name}_missing")
    return {
        "report_id": paths.get("report_id") or meta.get("cycle_id") or meta.get("generated_at"),
        "archive_id": paths.get("archive_id"),
        "dataset_generated_at": meta.get("generated_at"),
        "formal_report_snapshot_ts": meta.get("generated_at"),
        "broker_portfolio_ts": readonly.get("cycle_ts") or portfolio.get("cycle_ts"),
        "dashboard_snapshot_ts": readonly.get("cycle_ts") or portfolio.get("cycle_ts") or meta.get("generated_at"),
        "txt_generated_at": paths.get("txt_generated_at"),
        "docx_generated_at": paths.get("docx_generated_at"),
        "xlsx_generated_at": paths.get("xlsx_generated_at"),
        "json_generated_at": datetime.now().isoformat(timespec="seconds"),
        "dashboard_generated_at": paths.get("dashboard_generated_at"),
        "dataset_sha256": sha256_file(Path(paths["dataset"])) if paths.get("dataset") else sha256_object(dataset),
        "txt_sha256": sha256_file(Path(paths["txt"])) if paths.get("txt") else "",
        "docx_sha256": sha256_file(Path(paths["docx"])) if paths.get("docx") else "",
        "xlsx_sha256": sha256_file(Path(paths["xlsx"])) if paths.get("xlsx") else "",
        "delivery_json_sha256": sha256_file(Path(paths["delivery_json"])) if paths.get("delivery_json") else "",
        "dashboard_payload_sha256": sha256_file(Path(paths["dashboard_payload"])) if paths.get("dashboard_payload") else "",
        "section_coverage_map": coverage,
        "artifact_consistency_status": status,
        "artifact_consistency_errors": errors,
        "publication_blocked": status != "ARTIFACTS_CONSISTENT",
    }

