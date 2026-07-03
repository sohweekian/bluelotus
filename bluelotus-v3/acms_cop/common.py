from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value or "").strip()
    if not text:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = text.replace("T", " ").replace("Z", "")
    if "." in text:
        text = text.split(".", 1)[0]
    if len(text) == 10:
        text += " 00:00:00"
    return text[:19]


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def latest_v3_cycle_dir(root: str | Path | None = None) -> Path | None:
    base = Path(root) if root else PROJECT_ROOT / "data" / "v3_cycles"
    if not base.exists():
        return None
    dirs = [p for p in base.glob("v3_cycle_*") if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime) if dirs else None


def compact_text(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    return text[: limit - 3] + "..." if len(text) > limit else text


def dominant(values: Iterable[str | None]) -> str | None:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

