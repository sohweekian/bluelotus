#!/usr/bin/env python3
"""
BlueLotus News Channel Headline Feed Generator

Purpose:
    Ad hoc, simple TXT report writer for CIO headline reading.
    Reads existing dataset_raw.json and writes FRESH news headlines only.

Input default:
    C:\\bluelotus2\\data\\frontend\\dataset_raw.json

Output default:
    C:\\bluelotus2\\news\\news_channel_feed.txt

Design doctrine:
    - No new database table
    - No JSON output
    - No archive requirement
    - No automation requirement
    - Dataset remains source of truth
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPORT_TITLE = "BLUELOTUS NEWS CHANNEL HEADLINE FEED"
FRESH_MINUTES_DEFAULT = 60

WINDOWS_INPUT = r"C:\bluelotus3\data\frontend\dataset_raw.json"
WINDOWS_OUTPUT = r"C:\bluelotus3\news\news_channel_feed.txt"
SANDBOX_INPUT = "/mnt/data/dataset_raw.json"
SANDBOX_OUTPUT = "/mnt/data/news_channel_feed.txt"

TIER_LABELS = {
    1: "TIER 1 — OFFICIAL / INSTITUTIONAL SOURCES",
    2: "TIER 2 — MAJOR BUSINESS / MARKET NEWS",
    3: "TIER 3 — SPECIALIST / SECTOR INTELLIGENCE",
    4: "TIER 4 — SENTIMENT / BROAD MARKET / NOISY FEEDS",
}


def choose_default_input() -> str:
    if os.path.exists(WINDOWS_INPUT):
        return WINDOWS_INPUT
    if os.path.exists(SANDBOX_INPUT):
        return SANDBOX_INPUT
    return WINDOWS_INPUT


def choose_default_output() -> str:
    # On Windows production, write to the intended folder.
    if os.path.exists(r"C:\bluelotus3"):
        return WINDOWS_OUTPUT
    return SANDBOX_OUTPUT


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse common ISO/RSS date strings. Return naive datetime in source clock where needed."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    s = str(value).strip()
    if not s:
        return None

    # Handle ISO with Z.
    try:
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        pass

    # Handle RFC/RSS dates.
    try:
        dt = parsedate_to_datetime(s)
        return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def fmt_time(value: Any) -> str:
    if not value:
        return "N/A"
    dt = parse_dt(value)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(value).strip() or "N/A"


def clean_text(s: Any, limit: int = 180) -> str:
    if s is None:
        return ""
    text = html.unescape(str(s))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Remove duplicate title-summary pattern: "X. X"
    if ". " in text:
        left, right = text.split(". ", 1)
        if right.startswith(left[:50]):
            text = left
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def source_tiers(dataset: Dict[str, Any]) -> Dict[str, int]:
    tiers: Dict[str, int] = {}
    for row in dataset.get("source_health", []) or []:
        source = row.get("source")
        tier = row.get("tier")
        if source and isinstance(tier, int):
            tiers[str(source)] = tier
    return tiers


def dataset_generated_at(dataset: Dict[str, Any]) -> datetime:
    meta = dataset.get("meta", {}) or {}
    dt = parse_dt(meta.get("generated_at"))
    if dt:
        return dt
    return datetime.now().replace(microsecond=0)


def signal_headline(row: Dict[str, Any]) -> str:
    payload = row.get("raw_payload") or {}
    if isinstance(payload, dict):
        title = payload.get("title") or payload.get("headline") or payload.get("name")
        summary = payload.get("summary") or payload.get("description")
        if title:
            return clean_text(title, 180)
        if summary:
            return clean_text(summary, 180)
    return clean_text(row.get("raw_text"), 180)


def signal_published(row: Dict[str, Any]) -> Any:
    payload = row.get("raw_payload") or {}
    if isinstance(payload, dict):
        for key in ("published", "published_at", "pubDate", "date", "timestamp"):
            if payload.get(key):
                return payload.get(key)
    return row.get("published_at") or row.get("timestamp")


def signal_url(row: Dict[str, Any]) -> str:
    if row.get("source_url"):
        return str(row.get("source_url"))
    payload = row.get("raw_payload") or {}
    if isinstance(payload, dict):
        for key in ("link", "url", "source_url"):
            if payload.get(key):
                return str(payload.get(key))
    return ""


def collect_fresh_items(dataset: Dict[str, Any], freshness_minutes: int) -> List[Dict[str, Any]]:
    generated_at = dataset_generated_at(dataset)
    tiers = source_tiers(dataset)
    items: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()

    signals = dataset.get("signals", {}) or {}
    if not isinstance(signals, dict):
        return items

    for source, rows in signals.items():
        if not isinstance(rows, list):
            continue
        tier = tiers.get(source)
        if tier not in (1, 2, 3, 4):
            # Keep simple: this report follows source_health tiers only.
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            received_raw = row.get("received_at")
            received_dt = parse_dt(received_raw)
            if not received_dt:
                continue
            age = (generated_at - received_dt).total_seconds() / 60.0
            if age < 0:
                age = 0
            if age > freshness_minutes:
                continue
            headline = signal_headline(row)
            if not headline:
                continue
            published = signal_published(row)
            url = signal_url(row)
            dedupe_key = (str(source), headline.lower(), str(published or ""))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(
                {
                    "tier": tier,
                    "source": str(source),
                    "received_at": received_raw,
                    "received_display": fmt_time(received_raw),
                    "published_at": published,
                    "published_display": fmt_time(published),
                    "age_minutes": round(age, 1),
                    "headline": headline,
                    "url": url,
                }
            )

    items.sort(key=lambda x: (x["tier"], x["source"], x["age_minutes"], x["headline"]))
    return items


def render_report(dataset: Dict[str, Any], items: List[Dict[str, Any]], freshness_minutes: int) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dataset_ts = (dataset.get("meta", {}) or {}).get("generated_at", "N/A")
    lines: List[str] = []
    sep = "=" * 78
    sub = "-" * 78
    lines.append(sep)
    lines.append(REPORT_TITLE)
    lines.append(sep)
    lines.append(f"Generated        : {generated}")
    lines.append(f"Dataset Generated: {dataset_ts}")
    lines.append(f"Freshness Rule   : FRESH only, received age <= {freshness_minutes} minutes")
    lines.append(f"Total Fresh Items: {len(items)}")
    lines.append("Purpose          : CIO headline reading only; no scoring, no causality claims")
    lines.append(sep)
    lines.append("")

    for tier in (1, 2, 3, 4):
        group = [x for x in items if x["tier"] == tier]
        lines.append(TIER_LABELS[tier])
        lines.append(sub)
        if not group:
            lines.append("No fresh items.")
            lines.append("")
            continue
        current_source = None
        for item in group:
            if item["source"] != current_source:
                current_source = item["source"]
                lines.append(f"\n{current_source}")
            lines.append(
                f"  [{item['received_display']} | published {item['published_display']} | age {item['age_minutes']:.1f}m] "
                f"{item['headline']}"
            )
        lines.append("")

    lines.append(sep)
    lines.append("END OF NEWS CHANNEL HEADLINE FEED")
    lines.append(sep)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate BlueLotus fresh news channel headline feed TXT.")
    parser.add_argument("--input", default=choose_default_input(), help="Path to dataset_raw.json")
    parser.add_argument("--output", default=choose_default_output(), help="Path to news_channel_feed.txt")
    parser.add_argument("--fresh-minutes", type=int, default=FRESH_MINUTES_DEFAULT, help="Freshness cutoff in minutes")
    args = parser.parse_args()

    dataset = load_json(args.input)
    items = collect_fresh_items(dataset, args.fresh_minutes)
    report = render_report(dataset, items, args.fresh_minutes)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    print("BlueLotus News Channel Headline Feed generated successfully.")
    print(f"Dataset : {args.input}")
    print(f"Output  : {args.output}")
    print(f"Fresh   : {len(items)} items <= {args.fresh_minutes} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

