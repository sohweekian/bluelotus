from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List


def event_key(event: Dict) -> str:
    basis = f"{event.get('source','')}|{event.get('headline','')}|{event.get('url','')}"
    return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()


def load_cache(path: Path, max_hours: int = 24) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
    except Exception:
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    out = {}
    for key, ts in data.items():
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                out[key] = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return out


def filter_new(events: Iterable[Dict], cache: Dict[str, str]) -> List[Dict]:
    fresh = []
    for event in events:
        key = event_key(event)
        event["dedup_key"] = key
        if key not in cache:
            fresh.append(event)
    return fresh


def mark_sent(events: Iterable[Dict], cache: Dict[str, str], path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for event in events:
        cache[event.get("dedup_key") or event_key(event)] = now
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
