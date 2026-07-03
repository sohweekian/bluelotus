from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

from .builder import DEFAULT_DATASET, compute_capsule_hash
from .master_prompt import compute_prompt_hash
from .partial_artifact import parse_capsule_markers
from .renderers import MASTER_PROMPT_TITLE, MASTER_PROMPT_TITLE_UNICODE, READ_FIRST_TITLE, READ_FIRST_TITLE_UNICODE, capsule_is_active, master_prompt_is_active


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_TXT = PROJECT_ROOT / "research" / "Bluelotus_V3_Report.txt"
DEFAULT_DOCX = PROJECT_ROOT / "research" / "Bluelotus_V3_Report.docx"
DEFAULT_XLSX = PROJECT_ROOT / "research" / "Bluelotus_V3_Report.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "cio_context" / "cio_context_capsule_validation_latest.json"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _xml_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    return " ".join(node.text or "" for node in root.iter())


def _docx_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        with zipfile.ZipFile(path) as zf:
            return _xml_text(zf.read("word/document.xml"))
    except Exception:
        return ""


def _xlsx_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        chunks: List[str] = []
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.startswith("xl/") and name.endswith(".xml"):
                    chunks.append(_xml_text(zf.read(name)))
        return " ".join(chunks)
    except Exception:
        return ""


def _xlsx_has_sheet(path: Path, sheet_name: str) -> bool:
    if not path.exists():
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            wb = zf.read("xl/workbook.xml").decode("utf-8", errors="replace")
        return sheet_name in wb
    except Exception:
        return False


def _xlsx_sheet_names(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        import re
        with zipfile.ZipFile(path) as zf:
            wb = zf.read("xl/workbook.xml").decode("utf-8", errors="replace")
        return re.findall(r'name="([^"]+)"', wb)
    except Exception:
        return []


def _index_or_none(text: str, needles: List[str]) -> int | None:
    lowered = text.lower()
    positions = [lowered.find(needle.lower()) for needle in needles]
    positions = [pos for pos in positions if pos >= 0]
    return min(positions) if positions else None


def _master_markers(text: str) -> Dict[str, Any]:
    present = _index_or_none(text, [MASTER_PROMPT_TITLE, MASTER_PROMPT_TITLE_UNICODE, "Chief Strategist Master Prompt"]) is not None
    import re
    version_match = re.search(r"v1\.0-chief-strategist-master-prompt", text)
    hash_match = re.search(r"Prompt\s+Hash\s*:?\s*([a-fA-F0-9]{64})", text, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r"prompt_hash\s*:?\s*([a-fA-F0-9]{64})", text, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r"\b[a-fA-F0-9]{64}\b", text)
    return {
        "present": present,
        "version": version_match.group(0) if version_match else "",
        "prompt_hash": (hash_match.group(1) if hash_match and hash_match.lastindex else hash_match.group(0)).lower() if hash_match else "",
    }


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        tmp = Path(fh.name)
    tmp.replace(path)


def _fail(failed: List[str], code: str) -> None:
    failed.append(code)


def _warn(warnings: List[str], code: str) -> None:
    warnings.append(code)


def validate_cio_context_capsule(
    dataset_path: Path = DEFAULT_DATASET,
    txt_path: Path = DEFAULT_TXT,
    word_path: Path = DEFAULT_DOCX,
    excel_path: Path = DEFAULT_XLSX,
    output_path: Path = DEFAULT_OUTPUT,
    partial_ok: bool = False,
) -> Dict[str, Any]:
    failed: List[str] = []
    warnings: List[str] = []
    dataset = _read_json(Path(dataset_path))
    capsule = dataset.get("cio_context_capsule") if isinstance(dataset.get("cio_context_capsule"), dict) else {}
    master_prompt = dataset.get("chief_strategist_master_prompt") if isinstance(dataset.get("chief_strategist_master_prompt"), dict) else {}
    doctrine = capsule.get("core_doctrine") or {}
    record = capsule.get("cio_three_step_record") or {}
    sleeves = capsule.get("active_sleeve_rules") or {}
    expected_sleeves = {
        "gold_miners",
        "banks_bac_wfc",
        "high_beta_satellites",
        "foundational_tactical_cash_engine",
        "volatility_hedge",
        "cash_fortress",
    }

    if not dataset:
        _warn(warnings if partial_ok else failed, "dataset_raw_json_missing")
    if not capsule:
        _fail(failed, "cio_context_capsule_missing")
    else:
        if capsule.get("status") != "ACTIVE":
            _fail(failed, "status_not_active")
        if capsule.get("mandatory_for_all_chief_strategist_replies") is not True:
            _fail(failed, "mandatory_flag_not_true")
        if doctrine.get("execution_authority") != "CIO_ONLY_MANUAL":
            _fail(failed, "execution_authority_not_cio_only_manual")
        if doctrine.get("order_routing_enabled") is not False:
            _fail(failed, "order_routing_not_false")
        if int(doctrine.get("system_generated_orders", -1)) != 0:
            _fail(failed, "system_generated_orders_not_zero")
        if not doctrine.get("tactical_score_rule"):
            _fail(failed, "tactical_score_rule_missing")
        if not record.get("strategic_thinking"):
            _fail(failed, "strategic_thinking_missing")
        if not record.get("strategic_planning"):
            _fail(failed, "strategic_planning_missing")
        if not record.get("strategic_execution"):
            _fail(failed, "strategic_execution_missing")
        missing_sleeves = sorted(expected_sleeves - set(sleeves.keys()))
        if missing_sleeves:
            _fail(failed, "active_sleeve_rules_missing_" + ",".join(missing_sleeves))
        if len(capsule.get("kill_conditions") or []) < 8:
            _fail(failed, "kill_conditions_too_few")
        if not ((capsule.get("conversation_bootstrap_prompt") or {}).get("text")):
            _fail(failed, "bootstrap_prompt_missing")
        if capsule.get("capsule_hash") != compute_capsule_hash(capsule):
            _fail(failed, "dataset_capsule_hash_invalid")
        if not capsule_is_active(dataset):
            _fail(failed, "capsule_inactive_contract")

    if not master_prompt:
        _fail(failed, "chief_strategist_master_prompt_missing")
    else:
        if master_prompt.get("status") != "ACTIVE":
            _fail(failed, "master_prompt_status_not_active")
        if master_prompt.get("mandatory_for_chief_strategist") is not True:
            _fail(failed, "master_prompt_mandatory_not_true")
        if master_prompt.get("read_first") is not True:
            _fail(failed, "master_prompt_read_first_not_true")
        if int(master_prompt.get("priority", -1)) != 0:
            _fail(failed, "master_prompt_priority_not_zero")
        if not master_prompt.get("prompt_hash"):
            _fail(failed, "master_prompt_hash_missing")
        elif master_prompt.get("prompt_hash") != compute_prompt_hash(master_prompt):
            _fail(failed, "master_prompt_hash_invalid")
        if not master_prompt.get("master_prompt_text"):
            _fail(failed, "master_prompt_text_missing")
        if not master_prompt_is_active(dataset):
            _fail(failed, "master_prompt_inactive_contract")

    txt = _read_text(Path(txt_path))
    docx = _docx_text(Path(word_path))
    xlsx = _xlsx_text(Path(excel_path))
    txt_markers = parse_capsule_markers(txt)
    docx_markers = parse_capsule_markers(docx)
    xlsx_markers = parse_capsule_markers(xlsx)
    txt_master = _master_markers(txt)
    docx_master = _master_markers(docx)
    xlsx_master = _master_markers(xlsx)
    artifacts = {
        "dataset_raw_json": bool(dataset),
        "txt_report": bool(txt),
        "word_report": bool(docx),
        "excel_report": bool(xlsx),
    }

    expected_hash = capsule.get("capsule_hash", "")
    expected_prompt_hash = master_prompt.get("prompt_hash", "")
    for label, present, markers in [
        ("txt_report", bool(txt), txt_markers),
        ("word_report", bool(docx), docx_markers),
        ("excel_report", bool(xlsx), xlsx_markers),
    ]:
        if not present:
            _warn(warnings if partial_ok else failed, f"{label}_missing")
            continue
        if not markers.get("present"):
            _fail(failed, f"{label}_capsule_marker_missing")
        if expected_hash and markers.get("capsule_hash") != expected_hash:
            _fail(failed, f"{label}_capsule_hash_mismatch")

    for label, text, present, markers in [
        ("txt_report", txt, bool(txt), txt_master),
        ("word_report", docx, bool(docx), docx_master),
        ("excel_report", xlsx, bool(xlsx), xlsx_master),
    ]:
        if not present:
            continue
        if not markers.get("present"):
            _fail(failed, f"{label}_master_prompt_missing")
        if expected_prompt_hash and markers.get("prompt_hash") != expected_prompt_hash:
            _fail(failed, f"{label}_master_prompt_hash_mismatch")
        if label != "excel_report":
            master_idx = _index_or_none(text, [MASTER_PROMPT_TITLE, MASTER_PROMPT_TITLE_UNICODE, "Chief Strategist Master Prompt"])
            capsule_idx = _index_or_none(text, [READ_FIRST_TITLE, READ_FIRST_TITLE_UNICODE, "CIO Context Capsule"])
            if master_idx is None:
                _fail(failed, f"{label}_master_prompt_order_missing")
            elif capsule_idx is not None and master_idx > capsule_idx:
                _fail(failed, f"{label}_master_prompt_after_cio_context")
        if label in ("txt_report", "word_report") and "Chief Strategist Master Prompt: ACTIVE / MANDATORY / READ FIRST" not in text:
            _fail(failed, f"{label}_front_page_master_prompt_status_missing")

    if xlsx and not _xlsx_has_sheet(Path(excel_path), "00_CIO_CONTEXT_CAPSULE"):
        _fail(failed, "excel_sheet_00_cio_context_capsule_missing")
    sheet_names = _xlsx_sheet_names(Path(excel_path))
    if xlsx:
        if not sheet_names or sheet_names[0] != "00_CS_MASTER_PROMPT":
            _fail(failed, "excel_sheet_00_cs_master_prompt_not_first")
        if "00_CIO_CONTEXT_CAPSULE" in sheet_names and sheet_names.index("00_CS_MASTER_PROMPT") > sheet_names.index("00_CIO_CONTEXT_CAPSULE"):
            _fail(failed, "excel_master_prompt_after_cio_context")

    score = max(0, 100 - (len(failed) * 10) - (len(warnings) * 3))
    status = "FAIL" if failed else "WARNING" if warnings else "PASS"
    payload = {
        "status": status,
        "score": score,
        "failed_checks": failed,
        "warnings": warnings,
        "capsule_hash": expected_hash,
        "prompt_hash": expected_prompt_hash,
        "artifacts_checked": artifacts,
        "markers": {
            "txt": txt_markers,
            "word": docx_markers,
            "excel": xlsx_markers,
            "txt_master_prompt": txt_master,
            "word_master_prompt": docx_master,
            "excel_master_prompt": xlsx_master,
        },
    }
    _atomic_write(Path(output_path), payload)
    return payload


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate BlueLotus V3 CIO Context Capsule.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--txt", default=str(DEFAULT_TXT))
    parser.add_argument("--word", default=str(DEFAULT_DOCX))
    parser.add_argument("--excel", default=str(DEFAULT_XLSX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--partial-ok", action="store_true")
    args = parser.parse_args(argv)
    result = validate_cio_context_capsule(
        dataset_path=Path(args.dataset),
        txt_path=Path(args.txt),
        word_path=Path(args.word),
        excel_path=Path(args.excel),
        output_path=Path(args.output),
        partial_ok=args.partial_ok,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in ("PASS", "WARNING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
