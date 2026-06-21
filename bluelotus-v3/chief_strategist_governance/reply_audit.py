from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .report_renderers import governance_is_active


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_REPORT = PROJECT_ROOT / "research" / "Bluelotus_V3_Report.txt"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "chief_strategist" / "chief_strategist_reply_audit_latest.json"
AUDIT_VERSION = "v3.5-csg-audit-001"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    return value if isinstance(value, dict) else {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        tmp = Path(fh.name)
    tmp.replace(path)


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _add(issue_list: List[Dict[str, Any]], code: str, severity: str, message: str) -> None:
    issue_list.append({"code": code, "severity": severity, "message": message})


def audit_chief_strategist_reply(report_text: str, dataset: Dict[str, Any]) -> Dict[str, Any]:
    text = report_text or ""
    lowered = text.lower()
    narrative_text = re.split(r"=+\s*CHIEF STRATEGIST GOVERNANCE LAYER", text, maxsplit=1, flags=re.IGNORECASE)[0]
    narrative_lowered = narrative_text.lower()
    issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    if not governance_is_active(dataset):
        _add(issues, "CSG_MISSING_OR_INACTIVE", "FAIL", "Chief Strategist Governance pack is missing or inactive.")

    if "chief strategist governance layer" not in lowered:
        _add(issues, "CSG_SECTION_MISSING", "FAIL", "Report does not contain CHIEF STRATEGIST GOVERNANCE LAYER section.")

    if _has(narrative_text, r"\bgold\b", r"\bgdx\b", r"\bgdxj\b", r"\bau\b", r"\bnem\b"):
        if not _has(text, r"structural inflation", r"fiscal dominance", r"kill condition"):
            _add(issues, "GOLD_STRUCTURAL_CONTEXT_MISSING", "FAIL", "Gold/gold-miner discussion lacks structural thesis or kill-condition context.")

    if _has(narrative_text, r"\biran\b") and _has(narrative_text, r"peace|de-?escalat|ceasefire"):
        if _has(narrative_text, r"invalidat|kill|sell all|exit all|thesis.*dead") and not _has(text, r"structural inflation", r"fiscal dominance"):
            _add(issues, "IRAN_GOLD_INVALIDATION_ERROR", "FAIL", "Iran peace/de-escalation is treated as gold invalidation without structural reconciliation.")

    if _has(narrative_text, r"\bbanks?\b", r"\bbac\b", r"\bwfc\b", r"\bxlf\b"):
        missing_bank_terms = [term for term, pat in {
            "NIM": r"\bnim\b|net interest margin",
            "credit": r"\bcredit\b",
            "curve": r"\bcurve\b|yield curve",
            "BAC/WFC/XLF": r"\bbac\b.*\bwfc\b.*\bxlf\b|\bxlf\b.*\bbac\b.*\bwfc\b",
        }.items() if not _has(text, pat)]
        if missing_bank_terms:
            _add(issues, "BANK_CONTEXT_INCOMPLETE", "FAIL", f"Bank discussion missing required context: {', '.join(missing_bank_terms)}.")

    if _has(narrative_text, r"scout") and _has(narrative_text, r"second tranche"):
        if _has(narrative_text, r"scout.*authori[sz]es.*second tranche|second tranche.*authori[sz]ed.*scout|scout fill.*full deployment"):
            _add(issues, "SCOUT_SECOND_TRANCHE_CONFUSION", "FAIL", "Scout order language implies second-tranche authorization.")
    if _has(narrative_text, r"scout") and not _has(text, r"second tranche"):
        _add(warnings, "SCOUT_SECOND_TRANCHE_NOT_EXPLICIT", "WARNING", "Scout language appears without explicit second-tranche distinction.")

    if _has(narrative_text, r"\basts\b|\brklb\b|\bqbts\b|\bqubt\b|\blunr\b|\bionq\b|\brgti\b"):
        if _has(narrative_text, r"core holding|core allocation|core portfolio") and not _has(text, r"satellite|scout"):
            _add(issues, "SATELLITE_CORE_CONFUSION", "FAIL", "Satellite/convexity names are described as core without registry approval.")

    if _has(narrative_text, r"forecast|probability|scenario|expected") and not _has(text, r"confidence|probability|provisional|confirmed"):
        _add(warnings, "CONFIDENCE_LANGUAGE_WEAK", "WARNING", "Forecast-like language should include confidence/probability status.")

    event_terms = [
        "iran", "warsh", "boj", "yen", "credit", "vix", "volatility",
        "tariff", "stargate", "golden dome", "petrodollar",
    ]
    if not any(term in narrative_lowered for term in event_terms):
        _add(warnings, "CURRENT_EVENT_LINKAGE_WEAK", "WARNING", "No obvious current-event linkage detected.")

    if _has(
        narrative_text,
        r"\bexecute now\b",
        r"\broute now\b",
        r"automatic(?:ally)?\s+(?:execute|route|order|trade)",
        r"\bauto(?:matic)?\s+(?:execute|route|order|trade)",
        r"without\s+CIO\s+(?:approval|sign.?off|review)",
        r"no\s+CIO\s+(?:approval|sign.?off|review)",
    ):
        _add(issues, "CIO_ONLY_MANUAL_VIOLATION", "FAIL", "Language may imply automatic execution or broker routing.")

    if "cio_only_manual" not in lowered and "manual execution" not in lowered:
        _add(warnings, "CIO_ONLY_MANUAL_NOT_VISIBLE", "WARNING", "CIO_ONLY_MANUAL was not visibly restated.")

    status = "FAIL" if issues else "WARNING" if warnings else "PASS"
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": _utc_now(),
        "status": status,
        "fail_count": len(issues),
        "warning_count": len(warnings),
        "failures": issues,
        "warnings": warnings,
        "checks": {
            "governance_active": governance_is_active(dataset),
            "csg_section_present": "chief strategist governance layer" in lowered,
            "cio_only_manual_visible": "cio_only_manual" in lowered or "manual execution" in lowered,
        },
    }


def run_audit(
    report_path: Path = DEFAULT_REPORT,
    dataset_path: Path = DEFAULT_DATASET,
    output_path: Path = DEFAULT_OUTPUT,
) -> Dict[str, Any]:
    report_text = _read_text(report_path)
    dataset = _read_json(dataset_path)
    result = audit_chief_strategist_reply(report_text, dataset)
    result["report_path"] = str(report_path)
    result["dataset_path"] = str(dataset_path)
    _atomic_write_json(output_path, result)
    archive_path = output_path.with_name(
        f"chief_strategist_reply_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    _atomic_write_json(archive_path, result)
    return result


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit BlueLotus V3 Chief Strategist report language.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = run_audit(Path(args.report), Path(args.dataset), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in ("PASS", "WARNING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
