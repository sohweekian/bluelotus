from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List


OUT_DIR = Path(r"C:\bluelotus3\data\live_news")
SGT = timezone(timedelta(hours=8))
SOURCE_ORDER = ["FT", "WSJ", "Bloomberg", "SCMP", "Nikkei Asia"]


def write_outputs(brief: Dict, market_pulse: Dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest_live_news_brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "latest_market_pulse.json").write_text(json.dumps(market_pulse, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "latest_live_news_brief.txt").write_text(render_brief_txt(brief, market_pulse), encoding="utf-8")
    (OUT_DIR / "latest_market_pulse.txt").write_text(render_market_txt(market_pulse), encoding="utf-8")


def render_brief_txt(brief: Dict, market_pulse: Dict) -> str:
    window = brief.get("freshness_window_minutes")
    window_label = str(window) if window is not None else "configured"
    lines = [
        f"BlueLotus {window_label}-Minute Live News Brief",
        f"Generated: {brief.get('generated_at_sgt')} SGT",
        f"Freshness Window: Last {window_label} minutes",
        "Database Write: NO",
        "LLM Used: NO",
        "",
    ]
    events = brief.get("fresh_events") or []
    if not events:
        lines.append(f"No material fresh news detected within the last {window_label} minutes.")
        lines.append("")
    for source, rows in group_events_by_source(events).items():
        lines.append(f"**{source}**")
        lines.append("")
        for e in sorted(rows, key=event_sort_key):
            lines.append(f"{format_published_time(e)} - {e.get('headline')} ({e.get('url') or 'No source link captured'})")
        lines.append("")
    lines.append("Market Pulse:")
    for row in market_pulse.get("indicators") or []:
        lines.append(f"- {row.get('symbol')}: {row.get('price')} ({row.get('change_pct')}%) [{row.get('status')}]")
    lines.extend([
        "",
        "CIO Note:",
        "Manual verification required.",
        "No execution.",
        "No database write.",
        "V3 intelligence pipeline remains official source of record.",
    ])
    return "\n".join(lines) + "\n"


def render_market_txt(market_pulse: Dict) -> str:
    lines = ["BlueLotus Live Market Pulse", f"Generated UTC: {market_pulse.get('generated_at_utc')}", ""]
    for row in market_pulse.get("indicators") or []:
        lines.append(f"{row.get('symbol'):<8} {str(row.get('price')):<14} {str(row.get('change_pct')):<10} {row.get('status')}")
    return "\n".join(lines) + "\n"


def format_published_time(event: Dict) -> str:
    raw = event.get("published_at_utc")
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return dt.astimezone(SGT).strftime("%Y-%m-%d %H:%M SGT")
        except Exception:
            pass
    return str(event.get("published_at_raw") or "Missing source timestamp")


def group_events_by_source(events: List[Dict]) -> "OrderedDict[str, List[Dict]]":
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
