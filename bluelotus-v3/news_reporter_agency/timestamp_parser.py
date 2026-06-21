from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple


SGT = timezone(timedelta(hours=8))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sgt_now() -> datetime:
    return utc_now().astimezone(SGT)


def fmt_sgt(dt: Optional[datetime] = None) -> str:
    return (dt or sgt_now()).astimezone(SGT).strftime("%Y-%m-%d %H:%M")


def parse_timestamp(raw: str, now_utc: Optional[datetime] = None) -> Tuple[Optional[datetime], str]:
    text = str(raw or "").strip()
    if not text:
        return None, "MISSING_TIMESTAMP"
    now = now_utc or utc_now()
    low = text.lower()

    if "just now" in low or "moments ago" in low:
        return now, "RELATIVE"

    m = re.search(r"(\d+)\s*(min|mins|minute|minutes)\s+ago", low)
    if m:
        return now - timedelta(minutes=int(m.group(1))), "RELATIVE"

    m = re.search(r"(\d+)\s*(hour|hours|hr|hrs)\s+ago", low)
    if m:
        return now - timedelta(hours=int(m.group(1))), "RELATIVE"

    for candidate in [text, text.replace("Z", "+00:00")]:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc), "ABSOLUTE"
        except Exception:
            pass

    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), "RFC2822"
    except Exception:
        return None, "UNPARSEABLE_TIMESTAMP"


def freshness_minutes(published_utc: Optional[datetime], now_utc: Optional[datetime] = None) -> Optional[float]:
    if not published_utc:
        return None
    return max(0.0, ((now_utc or utc_now()) - published_utc).total_seconds() / 60.0)
