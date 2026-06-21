#!/usr/bin/env python3
"""
news_probe_daemon.py — BlueLotus Live News Probe v1.3
======================================================
Independent 24/7 daemon.  No MySQL.  No ingest cycle dependency.

  • Polls 8 financial news sources (configured in news_probe_sources.json) every N min
  • Applies per-source freshness window (configured in news_probe_sources.json)
  • All timing settings loaded from news_probe_config.json
  • Pushes data/headlines_live.json to GitHub Pages on every cycle
  • Sends Telegram bulletin every N min (configured in news_probe_config.json)

NO HARDCODING RULE: All source URLs, freshness windows, and timing values are
read from config JSON files at startup. To change any setting, edit the JSON —
never modify this Python file for configuration changes.

Config files:
    C:\\bluelotus3\\mid\\news_probe_sources.json   (source URLs, freshness, logos)
    C:\\bluelotus3\\mid\\news_probe_config.json    (intervals, limits, telegram)

Run:
    python mid/news_probe_daemon.py

Stop:
    Ctrl-C  (or kill the process — no cleanup needed)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import feedparser
from dotenv import load_dotenv

# ── Paths & env ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GITHUB_TOKEN       = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME    = os.getenv("GITHUB_USERNAME", "sohweekian")
GITHUB_REPO        = os.getenv("GITHUB_PAGES_REPO", "bluelotus")
GITHUB_BRANCH      = os.getenv("GITHUB_BRANCH", "main")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

HEADLINES_JSON_PATH = "data/headlines_live.json"

# ── Config loaders ────────────────────────────────────────────────────────────
# All timing and source config comes from JSON files — no hardcoding here.

def _load_probe_config() -> Dict[str, Any]:
    """Load news_probe_config.json. Returns defaults if file missing."""
    cfg_path = BASE_DIR / "mid" / "news_probe_config.json"
    defaults: Dict[str, Any] = {
        "probe_interval_seconds":  600,
        "freshness_window_minutes": 720,
        "max_items_per_source":     6,
        "dedup_cache_hours":        24,
        "telegram_enabled":         True,
        "telegram_interval_minutes": 10,
        "source_timeout_seconds":   15,
    }
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        defaults.update({k: v for k, v in data.items() if not k.startswith("_")})
    except Exception as exc:
        print(f"[WARN] news_probe_config.json not loaded ({exc}) — using defaults")
    return defaults


def _load_sources_config() -> Dict[str, Any]:
    """
    Load news_probe_sources.json and return the 'sources' dict keyed by source_id,
    ordered according to source_order.

    Each entry must have:  label, url, method, freshness_min
    Logo data is passed through unchanged for dashboard use.
    """
    src_path = BASE_DIR / "mid" / "news_probe_sources.json"
    try:
        raw = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"FATAL: cannot load news_probe_sources.json: {exc}\n"
            "Daemon cannot start without source configuration."
        ) from exc

    source_order = raw.get("source_order", [])
    sources_raw  = raw.get("sources", {})

    # Build ordered dict following source_order; validate required fields
    sources: Dict[str, Any] = {}
    for src_id in source_order:
        cfg = sources_raw.get(src_id)
        if cfg is None:
            raise RuntimeError(
                f"FATAL: source_order lists '{src_id}' but it has no entry in sources dict "
                f"in news_probe_sources.json."
            )
        for required_field in ("label", "url", "method", "freshness_min"):
            if required_field not in cfg:
                raise RuntimeError(
                    f"FATAL: source '{src_id}' is missing required field '{required_field}' "
                    f"in news_probe_sources.json. Add it — do not hardcode defaults in Python."
                )
        sources[src_id] = cfg

    if not sources:
        raise RuntimeError("FATAL: news_probe_sources.json has no sources. Daemon cannot start.")

    return sources


# ── Load config at module level ───────────────────────────────────────────────
# Loaded once at startup. To change settings: edit the JSON files, restart daemon.

_CFG     = _load_probe_config()
SOURCES  = _load_sources_config()          # ordered dict: src_id → {label, url, method, freshness_min, logo, ...}

RSS_POLL_SEC          = int(_CFG["probe_interval_seconds"])
FRESHNESS_MIN_DEFAULT = int(_CFG["freshness_window_minutes"])   # fallback if source doesn't specify
MAX_ITEMS_PER_SOURCE  = int(_CFG["max_items_per_source"])
TELEGRAM_INTERVAL_MIN = int(_CFG["telegram_interval_minutes"])
SOURCE_TIMEOUT_SEC    = int(_CFG["source_timeout_seconds"])

RSS_HEADERS = {
    "User-Agent": "BlueLotus/3.0 (+https://sohweekian.github.io/bluelotus/)",
    "Accept":     "application/rss+xml, application/xml, text/xml, */*",
}

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "logs" / "news_probe.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("news_probe")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    """Current time as UTC-naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_to_sgt_display(dt_utc: Optional[datetime]) -> str:
    """Convert UTC naive datetime → 'YYYY-MM-DD HH:MM' SGT string for display."""
    if dt_utc is None:
        return ""
    sgt = dt_utc + timedelta(hours=8)
    return sgt.strftime("%Y-%m-%d %H:%M")


def clean_headline(raw: str) -> str:
    """Strip HTML, leaked URLs and source attribution from raw RSS text."""
    text = str(raw or "")
    # Cut before any anchor tag (handles truncated <a href= with no closing >)
    text = text.split("<a ")[0].split("<A ")[0]
    # Remove remaining complete HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    for ent, ch in [
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
        ("&gt;", ">"), ("&#39;", "'"), ("&quot;", '"'), ("&apos;", "'"),
    ]:
        text = text.replace(ent, ch)
    # Cut at leaked URL
    text = re.split(r"https?://", text)[0]
    # Strip trailing source attributions from Google News / RSS aggregation
    # e.g. " - Bloomberg.com", " - Nikkei Asia", " - South China Morning Post", etc.
    text = re.sub(
        r"\s*[-–]\s*(Reuters|WSJ|Wall\s+Street\s+Journal|FT|Financial\s+Times"
        r"|Bloomberg(?:\.com)?|Nikkei\s+Asia|South\s+China\s+Morning\s+Post|SCMP"
        r"|Yahoo[!！]?\s*[Ff]inance|Yahoo[!！]?\s*ファイナンス"
        r"|毎日新聞|日本経済新聞|時事通信|朝日新聞|産経新聞|NHK"
        r"|The\s+Wall\s+Street\s+Journal|Barron's"
        r")\s*\.?\s*$",
        "", text, flags=re.IGNORECASE,
    )
    # Also strip parenthetical agency tags at end: e.g. "(時事通信)" "(Reuters)"
    text = re.sub(r"\s*\([^)]{2,30}\)\s*$", "", text)
    return text.strip()


# Junk-article patterns: any headline matching these is silently dropped.
_JUNK_PATTERNS = re.compile(
    r"(^print\s+edition|^subscribe|^members?\s+only|^sign\s+in\s+to|"
    r"^log\s+in\s+to|^access\s+denied|^paywall|^digital\s+edition|"
    r"^weekend\s+edition|^morning\s+edition|^evening\s+edition)",
    re.IGNORECASE,
)


def is_junk_headline(text: str) -> bool:
    """Return True if the headline is a junk/administrative article to discard."""
    if not text or len(text) < 10:
        return True
    return bool(_JUNK_PATTERNS.search(text.strip()))


def _parse_pub_utc(entry: Any) -> Optional[datetime]:
    """Parse feedparser entry published field → UTC naive datetime."""
    pub_str = (
        getattr(entry, "published", None)
        or getattr(entry, "updated", None)
        or entry.get("published") if isinstance(entry, dict) else None
    )
    if not pub_str:
        return None
    try:
        dt = parsedate_to_datetime(str(pub_str))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _url_key(url: str) -> str:
    """Normalise URL for dedup — strip query string, lowercase."""
    return re.sub(r"\?.*$", "", url).lower().strip()


# ── RSS fetch ─────────────────────────────────────────────────────────────────

def fetch_rss(src_id: str, url: str) -> List[Dict[str, Any]]:
    """Fetch an RSS feed and return list of raw item dicts."""
    try:
        resp = requests.get(url, headers=RSS_HEADERS, timeout=SOURCE_TIMEOUT_SEC)
        resp.raise_for_status()
        # Use raw bytes so feedparser detects encoding from XML declaration.
        # Critical for Japanese (UTF-8) feeds — resp.text can corrupt non-ASCII
        # if requests guesses the wrong charset from the Content-Type header.
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        log.warning("[%s] RSS fetch failed: %s", src_id, exc)
        return []

    items: List[Dict[str, Any]] = []
    for entry in feed.entries[:25]:
        link = (getattr(entry, "link", None) or entry.get("link") or
                getattr(entry, "id", None) or entry.get("id") or "").strip()
        title   = clean_headline(getattr(entry, "title",   None) or entry.get("title",   "") or "")
        summary = clean_headline(getattr(entry, "summary", None) or entry.get("summary", "") or
                                  getattr(entry, "description", None) or "")
        text = title if title else summary
        if not text or not link:
            continue
        if is_junk_headline(text):
            log.debug("[%s] Junk skipped: %s", src_id, text[:60])
            continue
        pub_utc = _parse_pub_utc(entry)
        items.append({
            "url":     link,
            "text":    text,
            "pub_utc": pub_utc,
        })

    log.debug("[%s] RSS returned %d entries", src_id, len(items))
    return items


# ── Freshness + dedup ─────────────────────────────────────────────────────────

def apply_freshness(items: List[Dict[str, Any]], cutoff_utc: datetime) -> List[Dict[str, Any]]:
    """Keep only items where pub_utc >= cutoff. Items with no pub_utc pass through."""
    fresh = []
    for item in items:
        pub = item.get("pub_utc")
        if pub is not None and pub < cutoff_utc:
            continue
        fresh.append(item)
    return fresh


def dedup_by_url(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate URLs, keeping first occurrence."""
    seen: set = set()
    out = []
    for item in items:
        key = _url_key(item["url"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# ── Telegram ─────────────────────────────────────────────────────────────────

def _tg_escape(text: str) -> str:
    """Escape characters that break Telegram HTML parse_mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_telegram_headlines(sources: Dict[str, Any], generated_at: str) -> str:
    """
    Build Telegram bulletin in BlueLotus News Reporter format.
    Sources appear in SOURCES dict order (from news_probe_sources.json source_order).
    Empty sources are skipped entirely.
    Uses HTML parse_mode for clickable article links.
    """
    SIGNOFF = "Dr. Codex &amp; Dr. Claude Windows Platform Team"

    # Freshness window range for header — read from loaded SOURCES config
    windows = [int(cfg.get("freshness_min", FRESHNESS_MIN_DEFAULT)) for cfg in SOURCES.values()]
    min_w, max_w = min(windows), max(windows)
    fw_label = (
        f"{min_w}-{max_w} minutes" if min_w != max_w else f"{min_w} minutes"
    )

    # Header — matches BlueLotus News Reporter format exactly
    lines = [
        "BlueLotus News Reporter",
        generated_at,
        f"Freshness Window: {fw_label}",
    ]

    any_items = False
    for src_id, src_cfg in SOURCES.items():
        label = src_cfg.get("label", src_id)
        src   = sources.get(src_id, {})
        items = src.get("items", [])
        if not items:
            continue
        any_items = True
        lines.append("")
        lines.append(f"<b>{_tg_escape(label)}</b>")
        lines.append("")
        for it in items:
            ts       = it.get("ts", "")          # "YYYY-MM-DD HH:MM" SGT display string
            ts_label = (ts + " SGT") if ts else "Unknown"
            raw      = it.get("text", "").strip()
            url      = it.get("url", "").strip()
            safe_txt = _tg_escape(raw)
            if url:
                # Escape & in URL for HTML attribute (Google News URLs contain &)
                safe_url = url.replace("&", "&amp;")
                lines.append(f'{ts_label} - <a href="{safe_url}">{safe_txt}</a>')
            else:
                lines.append(f"{ts_label} - {safe_txt}")

    if not any_items:
        lines.append("")
        lines.append("No fresh news across all channels.")

    lines.append("")
    lines.append(f"- {SIGNOFF}")
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """Send a Telegram message, splitting at 3900 chars if needed."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram: skipped — token/chat_id missing")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Split into chunks ≤ 3900 chars
    chunks, cur = [], ""
    for line in message.splitlines(keepends=True):
        if len(cur) + len(line) > 3900:
            chunks.append(cur)
            cur = ""
        cur += line
    if cur:
        chunks.append(cur)

    ok = True
    for i, chunk in enumerate(chunks, 1):
        try:
            r = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk,
                      "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=20,
            )
            resp_json = {}
            try:
                resp_json = r.json()
            except Exception:
                pass
            if r.status_code != 200 or not resp_json.get("ok"):
                desc = resp_json.get("description", r.text[:200])
                log.warning("Telegram chunk %d: HTTP %d ok=%s — %s",
                            i, r.status_code, resp_json.get("ok"), desc)
                ok = False
        except Exception as exc:
            log.warning("Telegram chunk %d error: %s", i, exc)
            ok = False
    if ok:
        log.info("Telegram: PASS (%d chunk(s))", len(chunks))
    return ok


# ── GitHub push ───────────────────────────────────────────────────────────────

def _gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def push_to_github(json_str: str) -> bool:
    """PUT headlines_live.json to GitHub Pages."""
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping push")
        return False

    api_url = (
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}"
        f"/contents/{HEADLINES_JSON_PATH}"
    )
    # Fetch current SHA so we can update (not create duplicate)
    sha: Optional[str] = None
    try:
        r = requests.get(api_url, headers=_gh_headers(),
                         params={"ref": GITHUB_BRANCH}, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "message": f"news probe {datetime.now().strftime('%H:%M')}",
        "content": base64.b64encode(json_str.encode("utf-8")).decode("ascii"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=_gh_headers(), json=payload, timeout=30)
        ok = r.status_code in {200, 201}
        if ok:
            log.info("GitHub push: OK (%d)", r.status_code)
        else:
            log.warning("GitHub push: FAIL (%d) %s", r.status_code, r.text[:200])
        return ok
    except Exception as exc:
        log.warning("GitHub push error: %s", exc)
        return False


# ── Build headlines JSON ──────────────────────────────────────────────────────

def build_headlines_json(
    rss_results: Dict[str, List[Dict[str, Any]]],
) -> str:
    """Assemble headlines_live.json payload string using per-source freshness windows."""
    now_utc = _utcnow()
    now_sgt = now_utc + timedelta(hours=8)

    sources: Dict[str, Any] = {}
    for src_id, src_cfg in SOURCES.items():
        src_freshness = int(src_cfg.get("freshness_min", FRESHNESS_MIN_DEFAULT))
        cutoff_utc = now_utc - timedelta(minutes=src_freshness)
        raw = rss_results.get(src_id, [])
        fresh = apply_freshness(raw, cutoff_utc)
        unique = dedup_by_url(fresh)

        # Sort by publish time descending (freshest first), cap at MAX_ITEMS_PER_SOURCE
        unique_sorted = sorted(
            (it for it in unique if it.get("pub_utc") is not None),
            key=lambda x: x["pub_utc"],
            reverse=True,
        )[:MAX_ITEMS_PER_SOURCE]

        sources[src_id] = {
            "label":       src_cfg["label"],
            "window_min":  src_freshness,      # per-source — JS reads this for the "no news" message
            "items": [
                {
                    "ts":   _utc_to_sgt_display(item["pub_utc"]),
                    "text": item["text"],
                    "url":  item["url"],
                }
                for item in unique_sorted
            ],
        }

    payload = {
        "generated_at":  now_sgt.strftime("%Y-%m-%d %H:%M") + " SGT",
        "window_min":    FRESHNESS_MIN_DEFAULT,
        "sources":       sources,
    }
    return json.dumps(payload, ensure_ascii=False)


# ── Probe cycle ───────────────────────────────────────────────────────────────

def run_probe() -> Dict[str, Any]:
    """
    One full RSS probe cycle — fetch all RSS sources, apply per-source freshness
    filters, build headlines_live.json, push to GitHub.
    Returns the parsed payload dict so the caller can decide when to send Telegram.
    """
    now_utc = _utcnow()

    # Poll RSS sources — freshness applied per-source in build_headlines_json
    rss_results: Dict[str, List[Dict[str, Any]]] = {}
    for src_id, src_cfg in SOURCES.items():
        src_freshness = int(src_cfg.get("freshness_min", FRESHNESS_MIN_DEFAULT))
        items  = fetch_rss(src_id, src_cfg["url"])
        cutoff = now_utc - timedelta(minutes=src_freshness)
        fresh  = apply_freshness(items, cutoff)
        unique = dedup_by_url(fresh)
        rss_results[src_id] = unique
        log.info("[%s] %d fresh items (of %d fetched, window=%dmin)",
                 src_id, len(unique), len(items), src_freshness)

    # Build + save locally + push to GitHub
    json_str = build_headlines_json(rss_results)

    # Always save local copy so other daemons (BOJ engine, etc.) can read it
    _local_headlines = BASE_DIR / "data" / "headlines_live.json"
    _local_headlines.parent.mkdir(parents=True, exist_ok=True)
    _local_headlines.write_text(json_str, encoding="utf-8")
    log.info("Local headlines saved: %s", _local_headlines)

    push_to_github(json_str)

    return json.loads(json_str)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Ensure logs dir exists
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("BlueLotus News Probe Daemon v1.3  [starting]")
    log.info("  Sources loaded     : %d (from news_probe_sources.json)", len(SOURCES))
    log.info("  RSS poll interval  : %d min", RSS_POLL_SEC // 60)
    log.info("  Freshness window   : %d min (default — see per-source config)", FRESHNESS_MIN_DEFAULT)
    log.info("  Max items/source   : %d", MAX_ITEMS_PER_SOURCE)
    log.info("  Telegram interval  : %d min", TELEGRAM_INTERVAL_MIN)
    log.info("  GitHub repo        : %s/%s (branch: %s)", GITHUB_USERNAME, GITHUB_REPO, GITHUB_BRANCH)
    for src_id, src_cfg in SOURCES.items():
        log.info("  [src] %-25s freshness=%dmin", src_id, src_cfg.get("freshness_min", FRESHNESS_MIN_DEFAULT))
    log.info("=" * 60)

    cycle = 0
    last_telegram: Optional[datetime] = None   # tracks last successful Telegram send

    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 10   # log loud warning after this many, but NEVER exit

    while True:
        cycle += 1
        now = _utcnow()
        log.info("── Cycle %d  %s ──────────────────────────────────",
                 cycle, datetime.now().strftime("%H:%M:%S"))

        try:
            payload = run_probe()
            consecutive_failures = 0   # reset on success

            # Telegram bulletin — every TELEGRAM_INTERVAL_MIN minutes
            tg_due = (
                last_telegram is None
                or (now - last_telegram).total_seconds() >= TELEGRAM_INTERVAL_MIN * 60
            )
            if tg_due:
                tg_msg = build_telegram_headlines(payload["sources"], payload["generated_at"])
                if send_telegram(tg_msg):
                    last_telegram = now
                    log.info("Telegram: bulletin sent (next in %d min)", TELEGRAM_INTERVAL_MIN)
                else:
                    log.warning("Telegram: send failed — will retry next cycle")

        except Exception as exc:
            consecutive_failures += 1
            log.error("Cycle %d crashed (%d consecutive): %s",
                      cycle, consecutive_failures, exc, exc_info=True)
            # NEVER exit the loop — just back off slightly on repeated failures
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.critical(
                    "DAEMON: %d consecutive failures. Still running. "
                    "Check network / GitHub token / RSS feed availability.",
                    consecutive_failures,
                )

        next_run = datetime.now().strftime("%H:%M:%S")
        log.info("Cycle %d done — sleeping %d min (next ~%s + %ds)\n",
                 cycle, RSS_POLL_SEC // 60, next_run, RSS_POLL_SEC)
        time.sleep(RSS_POLL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped by user (Ctrl-C).")
        sys.exit(0)
