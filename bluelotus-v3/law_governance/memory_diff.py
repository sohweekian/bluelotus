from __future__ import annotations

from typing import Any, Dict, List


def summarize_diff(old_content: Dict[str, Any], new_content: Dict[str, Any]) -> Dict[str, Any]:
    old_keys = set(old_content or {})
    new_keys = set(new_content or {})
    shared = old_keys & new_keys
    changed: List[str] = [
        key for key in sorted(shared)
        if old_content.get(key) != new_content.get(key)
    ]
    return {
        "added_keys": sorted(new_keys - old_keys),
        "removed_keys": sorted(old_keys - new_keys),
        "changed_keys": changed,
        "change_count": len(new_keys - old_keys) + len(old_keys - new_keys) + len(changed),
    }
