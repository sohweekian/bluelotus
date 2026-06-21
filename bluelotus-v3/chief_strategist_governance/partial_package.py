from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List
from xml.etree import ElementTree as ET


CSG_MARKER = "CHIEF STRATEGIST GOVERNANCE LAYER"


def _read_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _xml_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    return " ".join(node.text or "" for node in root.iter())


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            return _xml_text(zf.read("word/document.xml"))
    except Exception:
        return ""


def _read_xlsx(path: Path) -> str:
    try:
        chunks: List[str] = []
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.startswith("xl/") and name.endswith(".xml"):
                    chunks.append(_xml_text(zf.read(name)))
        return " ".join(chunks)
    except Exception:
        return ""


def _read_any(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _read_txt(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".xlsx":
        return _read_xlsx(path)
    return ""


def recover_csg_from_outputs(paths: Iterable[Path]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        text = _read_any(Path(path))
        if not text:
            continue
        present = CSG_MARKER.lower() in text.lower() or "chief strategist governance" in text.lower()
        version_match = re.search(r"(v3\.5-csg-[0-9A-Za-z_-]+)", text)
        status_match = re.search(r"Status\s*:?\s*(ACTIVE|MISSING|MISSING_OR_INACTIVE)", text, re.IGNORECASE)
        findings.append({
            "path": str(path),
            "csg_present": present,
            "governance_version": version_match.group(1) if version_match else "",
            "status": status_match.group(1).upper() if status_match else "",
        })
    present_findings = [row for row in findings if row.get("csg_present")]
    return {
        "status": "PASS" if present_findings else "WARNING",
        "warning": "" if present_findings else "No Chief Strategist Governance section found in supplied artifacts.",
        "findings": findings,
    }
