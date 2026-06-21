from __future__ import annotations

from typing import Any


def classify_causal_status(
    evidence_tier: Any = None,
    direct_catalyst: Any = None,
    source_count: Any = None,
    review_flags: Any = None,
    direction: Any = None,
) -> str:
    flags = review_flags if isinstance(review_flags, list) else []
    flag_text = " ".join(str(x).upper() for x in flags)
    if "OUTLIER" in flag_text or "MISMATCH" in flag_text:
        return "PARTIAL"
    if bool(direct_catalyst):
        return "CONFIRMED"
    try:
        tier = int(evidence_tier)
    except (TypeError, ValueError):
        tier = 9
    try:
        count = int(source_count or 0)
    except (TypeError, ValueError):
        count = 0
    if tier <= 1 and count >= 2:
        return "CONFIRMED"
    if tier <= 2 or count >= 1:
        return "PARTIAL_CONFIRMED"
    if str(direction or "").upper().startswith("PRICE_ACTION"):
        return "PARTIAL"
    return "UNCONFIRMED"

