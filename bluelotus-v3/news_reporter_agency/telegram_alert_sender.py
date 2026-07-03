from __future__ import annotations

import os
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Dict, Iterable, List


SIGNOFF = "Dr. Codex & Dr. Claude Windows Platform Team"
SGT = timezone(timedelta(hours=8))
SOURCE_ORDER = ["FT", "WSJ", "Bloomberg", "SCMP", "Nikkei Asia"]
MAX_TELEGRAM_TEXT = 3900


def load_env(path: str = r"C:\bluelotus3\.env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def build_alert_message(event: Dict, generated_at_sgt: str, freshness_window_minutes: int) -> str:
    labels = "\n".join(f"- {x}" for x in event.get("event_labels") or ["UNCLASSIFIED"])
    theses = "\n".join(f"- {x}" for x in event.get("linked_theses") or ["None mapped"])
    assets = "\n".join(f"- {x}" for x in event.get("linked_assets") or ["None mapped"])
    published = format_published_time(event)
    link = event.get("url") or "No source link captured"
    freshness = event.get("freshness_minutes")
    freshness_text = f"{freshness} minutes" if freshness is not None else "unverified"
    return (
        "BlueLotus Live News Alert\n"
        f"Report Time: {generated_at_sgt} SGT\n"
        f"Freshness Window: Last {freshness_window_minutes} minutes\n"
        f"Priority: {event.get('priority')}\n"
        f"Source: {event.get('source')}\n"
        f"Published: {published}\n"
        f"Freshness: {freshness_text}\n"
        f"Link: {link}\n\n"
        "Headline:\n"
        f"{event.get('headline')}\n\n"
        "Summary:\n"
        f"{event.get('summary') or 'Public headline/snippet only.'}\n\n"
        "Event Classification:\n"
        f"{labels}\n\n"
        "Affected Theses:\n"
        f"{theses}\n\n"
        "Affected Assets / Sectors:\n"
        f"{assets}\n\n"
        "Market Meaning:\n"
        f"{event.get('market_meaning')}\n\n"
        "CIO Action:\n"
        "Manual verification required.\n"
        "No execution.\n"
        "No database write.\n"
        "V3 intelligence pipeline remains official source of record.\n\n"
        f"- {SIGNOFF}"
    )


def build_grouped_news_messages(events: Iterable[Dict], generated_at_sgt: str, freshness_window_minutes: int) -> List[str]:
    groups = group_events_by_source(events)
    header = (
        f"BlueLotus News Reporter\n"
        f"{generated_at_sgt} SGT\n"
        f"Freshness Window: {freshness_window_minutes} minutes\n"
    )
    messages: List[str] = []
    current = header
    for source, rows in groups.items():
        block_lines = ["", f"<b>{escape(source)}</b>", ""]
        for event in sorted(rows, key=event_sort_key):
            block_lines.append(format_linked_event_line(event))
        block = "\n".join(block_lines) + "\n"
        footer = f"\n- {SIGNOFF}"
        if len(current) + len(block) + len(footer) > MAX_TELEGRAM_TEXT and current != header:
            messages.append(current.rstrip() + footer)
            current = header + block
        else:
            current += block
    if current != header:
        messages.append(current.rstrip() + f"\n\n- {SIGNOFF}")
    return messages


def group_events_by_source(events: Iterable[Dict]) -> "OrderedDict[str, List[Dict]]":
    buckets: Dict[str, List[Dict]] = {}
    for event in events:
        source = str(event.get("source") or "Unknown")
        buckets.setdefault(source, []).append(event)
    ordered: "OrderedDict[str, List[Dict]]" = OrderedDict()
    for source in SOURCE_ORDER:
        if source in buckets:
            ordered[source] = buckets.pop(source)
    for source in sorted(buckets):
        ordered[source] = buckets[source]
    return ordered


def event_sort_key(event: Dict):
    raw = event.get("published_at_utc")
    if raw:
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def format_linked_event_line(event: Dict) -> str:
    published = escape(format_published_time(event))
    headline = escape(str(event.get("headline") or "Untitled"))
    url = str(event.get("url") or "").strip()
    if url:
        safe_url = escape(url, quote=True)
        return f'{published} - <a href="{safe_url}">{headline}</a>'
    return f"{published} - {headline}"


def format_published_time(event: Dict) -> str:
    raw = event.get("published_at_utc")
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return dt.astimezone(SGT).strftime("%Y-%m-%d %H:%M SGT")
        except Exception:
            pass
    return str(event.get("published_at_raw") or "Missing source timestamp")


def send_telegram(text: str, timeout: int = 20, parse_mode: str | None = "HTML") -> Dict:
    load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"ok": False, "skipped": True, "reason": "missing Telegram credentials"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = urllib.parse.urlencode(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "response": resp.read().decode("utf-8", "ignore")[:400]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240]}
