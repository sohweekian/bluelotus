from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List
from xml.etree import ElementTree as ET

from .renderers import READ_FIRST_TITLE, READ_FIRST_TITLE_UNICODE


def _xml_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    return " ".join(node.text or "" for node in root.iter())


def _txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            return _xml_text(zf.read("word/document.xml"))
    except Exception:
        return ""


def _xlsx(path: Path) -> str:
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
        return _txt(path)
    if suffix == ".docx":
        return _docx(path)
    if suffix == ".xlsx":
        return _xlsx(path)
    if suffix == ".json":
        return _txt(path)
    return ""


def parse_capsule_markers(text: str) -> Dict[str, Any]:
    present = READ_FIRST_TITLE.lower() in text.lower() or READ_FIRST_TITLE_UNICODE.lower() in text.lower()
    version = ""
    capsule_hash = ""
    version_match = re.search(r"v3\.5-cio-context-[0-9A-Za-z_-]+", text)
    if version_match:
        version = version_match.group(0)
    hash_match = re.search(r"Capsule\s+Hash\s*:?\s*([a-fA-F0-9]{64})", text, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r"capsule_hash\s*:?\s*([a-fA-F0-9]{64})", text, re.IGNORECASE)
    if not hash_match:
        hash_match = re.search(r"\b[a-fA-F0-9]{64}\b", text)
    if hash_match:
        capsule_hash = (hash_match.group(1) if hash_match.lastindex else hash_match.group(0)).lower()
    return {
        "present": present,
        "version": version,
        "capsule_hash": capsule_hash,
        "has_strategic_thinking": "Strategic Thinking" in text or "strategic_thinking" in text,
        "has_strategic_planning": "Strategic Planning" in text or "strategic_planning" in text,
        "has_strategic_execution": "Strategic Execution" in text or "strategic_execution" in text,
        "has_cio_only_manual": "CIO_ONLY_MANUAL" in text,
    }


def recover_capsule_from_artifacts(paths: Iterable[Path]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    for path in paths:
        p = Path(path)
        text = _read_any(p)
        if not text:
            findings.append({"path": str(p), "readable": False, "present": False})
            continue
        markers = parse_capsule_markers(text)
        markers["path"] = str(p)
        markers["readable"] = True
        findings.append(markers)
    present = [row for row in findings if row.get("present")]
    hashes = sorted({row.get("capsule_hash") for row in present if row.get("capsule_hash")})
    return {
        "status": "PASS" if present else "WARNING",
        "warning": "" if present else "No CIO Context Capsule found in supplied artifacts.",
        "artifact_count": len(findings),
        "present_count": len(present),
        "hashes": hashes,
        "hashes_match": len(hashes) <= 1,
        "findings": findings,
    }
