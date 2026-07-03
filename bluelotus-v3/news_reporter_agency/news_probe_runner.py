from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

from deterministic_news_classifier import classify_event
from headline_extractor import fetch_source
from live_news_brief_writer import OUT_DIR, write_outputs
from market_indicator_probe import fetch_market_pulse
from news_deduplicator import filter_new, load_cache, mark_sent
from telegram_alert_sender import build_grouped_news_messages, send_telegram
from timestamp_parser import fmt_sgt, freshness_minutes, utc_now


ROOT = Path(r"C:\bluelotus3")
AGENCY_DIR = ROOT / "news_reporter_agency"
REGISTRY_PATH = AGENCY_DIR / "news_source_registry.yaml"
CONFIG_PATH = AGENCY_DIR / "news_reporter_config.yaml"
DEDUP_PATH = ROOT / "data" / "live_news" / "dedup_cache.json"


def require_config(cfg: Dict, key: str):
    if key not in cfg:
        raise KeyError(f"Missing required news reporter config: {key}")
    return cfg[key]


def parse_simple_config(path: Path) -> Dict:
    cfg = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line or line.startswith("-"):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.lower() in {"true", "false"}:
            cfg[k.strip()] = v.lower() == "true"
        else:
            try:
                cfg[k.strip()] = int(v)
            except ValueError:
                try:
                    cfg[k.strip()] = float(v)
                except ValueError:
                    cfg[k.strip()] = v
    return cfg


def parse_registry(path: Path) -> List[Dict]:
    sources = []
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- id:"):
            if current:
                sources.append(current)
            current = {"id": line.split(":", 1)[1].strip()}
        elif current and ":" in line:
            k, v = line.split(":", 1)
            current[k.strip()] = v.strip()
    if current:
        sources.append(current)
    return sources


def run_once() -> Dict:
    cfg = parse_simple_config(CONFIG_PATH)
    freshness_window = int(require_config(cfg, "freshness_window_minutes"))
    threshold = float(cfg.get("market_relevance_alert_threshold", 0.55))
    timeout = int(cfg.get("source_timeout_seconds", 15))
    now = utc_now()
    generated_sgt = fmt_sgt()
    sources = parse_registry(REGISTRY_PATH)

    source_health = []
    raw_events = []
    discarded_old = 0
    for source in sources:
        result = fetch_source(source, timeout=timeout, user_agent=str(cfg.get("user_agent", "BlueLotus3-NewsReporter/1.0")))
        source_health.append({k: result.get(k) for k in ["source", "status", "error", "content_type"] if result.get(k) is not None})
        for event in result.get("events", []):
            mins = freshness_minutes_from_event(event, now)
            if mins is None:
                event["freshness_status"] = "UNVERIFIED_FRESHNESS"
                event["freshness_minutes"] = None
                raw_events.append(event)
            elif mins <= freshness_window:
                event["freshness_status"] = "FRESH"
                event["freshness_minutes"] = round(mins, 2)
                raw_events.append(event)
            else:
                discarded_old += 1

    classified = [classify_event(e, threshold=threshold) for e in raw_events]
    fresh_events = [e for e in classified if e.get("freshness_status") == "FRESH"]
    alert_candidates = [e for e in fresh_events if e.get("telegram_alert_required")]

    dedup_enabled = bool(cfg.get("telegram_dedup_enabled", True))
    cache = load_cache(DEDUP_PATH, max_hours=int(cfg.get("dedup_cache_hours", 24)))
    new_alerts = filter_new(alert_candidates, cache) if dedup_enabled else alert_candidates
    dedup_blocked_alerts = [
        {
            "headline": e.get("headline"),
            "source": e.get("source"),
            "priority": e.get("priority"),
            "dedup_key": e.get("dedup_key"),
            "reason": "already_sent_within_dedup_window",
        }
        for e in alert_candidates
        if dedup_enabled and e not in new_alerts
    ]
    sent = []
    if cfg.get("telegram_enabled", True):
        messages = build_grouped_news_messages(new_alerts, generated_sgt, freshness_window)
        for index, message in enumerate(messages, start=1):
            result = send_telegram(message)
            sent.append({"message_index": index, "items": len(new_alerts), **result})
    if dedup_enabled and sent and all(r.get("ok") for r in sent):
        mark_sent(new_alerts, cache, DEDUP_PATH)
    elif dedup_enabled:
        mark_sent([], cache, DEDUP_PATH)

    market_pulse = fetch_market_pulse(timeout=12)
    brief = {
        "schema_version": "bluelotus_live_news_brief_v1.0",
        "generated_at_sgt": generated_sgt,
        "freshness_window_minutes": freshness_window,
        "mode": "report_and_forget",
        "database_write": False,
        "llm_used": False,
        "sources_checked": [s.get("id") for s in sources],
        "source_health": source_health,
        "fresh_events": fresh_events,
        "telegram_alert_candidates_count": len(alert_candidates),
        "telegram_dedup_enabled": dedup_enabled,
        "telegram_alerts_dedup_blocked": dedup_blocked_alerts,
        "telegram_alerts_sent": sent,
        "discarded_old_events_count": discarded_old,
        "notes": "V3 intelligence pipeline remains official archive source.",
    }
    write_outputs(brief, market_pulse)
    return brief


def freshness_minutes_from_event(event: Dict, now) -> float | None:
    raw = event.get("published_at_utc")
    if not raw:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return freshness_minutes(dt, now)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=None)
    args = ap.parse_args()
    cfg = parse_simple_config(CONFIG_PATH)
    interval = int(args.interval or cfg.get("loop_interval_seconds", 600))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            brief = run_once()
            print(f"{brief['generated_at_sgt']} SGT | fresh={len(brief['fresh_events'])} | telegram={len(brief['telegram_alerts_sent'])}")
        except Exception as exc:
            print(f"News reporter cycle failed: {exc}", file=sys.stderr)
        if not args.loop:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
