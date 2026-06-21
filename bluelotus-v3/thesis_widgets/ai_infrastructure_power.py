#!/usr/bin/env python3
"""
ai_infrastructure_power.py — BlueLotus V3 Thesis Widget
=========================================================
AI Infrastructure / Power Bottleneck Thesis Monitor
Thesis ID: AI_INFRASTRUCTURE_POWER_THESIS

INDEPENDENCE GUARANTEE:
  Runs standalone.  Does NOT require V3 Grand Pipeline, LLM clients, Chief Strategist,
  agent council, order routing, or V2 pipeline.

NO HARDCODING DOCTRINE:
  All tickers, weights, thresholds, keywords, and paths come from:
    C:\\bluelotus3\\config\\thesis_widgets\\ai_infrastructure_power.yaml
  To change any value: edit the YAML, restart the widget.

SAFETY:
  execution_authority : CIO_ONLY_MANUAL
  order_routing       : DISABLED
  llm_order_generation: false
  This widget is read-only intelligence. It never routes orders.

Run standalone:
    python thesis_widgets\\ai_infrastructure_power.py

Run once (no loop):
    python thesis_widgets\\ai_infrastructure_power.py --once
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Force UTF-8 stdout so Unicode log characters survive Windows cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import yaml
import yfinance as yf
import requests
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "thesis_widgets" / "ai_infrastructure_power.yaml"

load_dotenv(BASE_DIR / ".env")

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sohweekian")
GITHUB_REPO     = os.getenv("GITHUB_PAGES_REPO", "bluelotus")
GITHUB_BRANCH   = os.getenv("GITHUB_BRANCH", "main")

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            BASE_DIR / "logs" / "ai_infrastructure_power.log",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("ai_infra_power")


# ── Config loader ─────────────────────────────────────────────────────────────

def load_config() -> Dict[str, Any]:
    """
    Load and validate the YAML config file.
    Raises RuntimeError with a clear message if config is invalid.
    This is the ONLY place where widget configuration is read.
    """
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"FATAL: Config file not found: {CONFIG_PATH}\n"
            "This widget cannot run without its config file. "
            "Do not hardcode values as a workaround."
        )

    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Validate required top-level keys
    required_keys = [
        "thesis_id", "schema_version", "title", "output",
        "baskets", "benchmarks", "signal_thresholds",
        "status_thresholds", "confidence_thresholds",
        "cio_action_map", "safety", "headline_keywords",
        "headline_scoring_weight", "risk_penalty",
        "market_hours",
    ]
    for key in required_keys:
        if key not in cfg:
            raise RuntimeError(
                f"FATAL: Config missing required key '{key}' in {CONFIG_PATH}. "
                "Add it to the YAML — do not add defaults in Python."
            )

    # Validate safety constants — these must always be set correctly
    safety = cfg["safety"]
    if safety.get("order_routing_enabled") is not False:
        raise RuntimeError("FATAL: safety.order_routing_enabled must be false in config.")
    if safety.get("llm_order_generation") is not False:
        raise RuntimeError("FATAL: safety.llm_order_generation must be false in config.")
    if safety.get("execution_authority") != "CIO_ONLY_MANUAL":
        raise RuntimeError("FATAL: safety.execution_authority must be 'CIO_ONLY_MANUAL'.")

    # Validate basket structure
    for basket_id, basket_cfg in cfg["baskets"].items():
        for field in ("label", "scoring_weight", "enabled", "tickers"):
            if field not in basket_cfg:
                raise RuntimeError(
                    f"FATAL: Basket '{basket_id}' missing required field '{field}' "
                    f"in {CONFIG_PATH}."
                )

    # Validate market_hours sub-keys
    mh = cfg["market_hours"]
    for mh_key in ("timezone", "open_time", "close_time", "trading_days"):
        if mh_key not in mh:
            raise RuntimeError(
                f"FATAL: Config missing market_hours.{mh_key} in {CONFIG_PATH}. "
                "Add it to the YAML — do not add defaults in Python."
            )

    log.info("Config loaded: thesis_id=%s  schema=%s",
             cfg["thesis_id"], cfg["schema_version"])
    return cfg


# ── Price fetching ────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fetch_prices(tickers: List[str], timeout_sec: int = 30) -> Dict[str, Dict[str, Any]]:
    """
    Batch download 2 days of daily closes for all tickers via yfinance.
    Returns dict: ticker → {price, day_change_pct, available}
    Handles missing/stale tickers gracefully — never crashes on bad data.
    """
    if not tickers:
        return {}

    try:
        raw = yf.download(
            tickers,
            period="5d",       # 5 days to ensure 2 trading days of data
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            timeout=timeout_sec,
        )
    except Exception as exc:
        log.warning("yfinance batch download failed: %s", exc)
        return {t: {"price": None, "day_change_pct": None, "available": False} for t in tickers}

    results: Dict[str, Dict[str, Any]] = {}

    # Detect column structure: newer yfinance uses (ticker, field) MultiIndex
    # older versions use (field, ticker). Normalise to ticker → Series[Close].
    col_sample = raw.columns[0] if len(raw.columns) > 0 else None
    _ticker_first = (
        isinstance(col_sample, tuple) and len(col_sample) == 2
        and col_sample[0] in tickers
    )

    for ticker in tickers:
        try:
            if len(tickers) == 1:
                # Single ticker — yfinance returns flat DataFrame
                closes = raw["Close"].dropna()
            elif _ticker_first:
                # New yfinance: columns are (ticker, field)
                closes = raw[ticker]["Close"].dropna()
            else:
                # Old yfinance: columns are (field, ticker)
                closes = raw["Close"][ticker].dropna()

            if len(closes) < 2:
                results[ticker] = {"price": None, "day_change_pct": None, "available": False}
                continue

            price_today = float(closes.iloc[-1])
            price_prev  = float(closes.iloc[-2])
            day_change  = ((price_today - price_prev) / price_prev) * 100.0 if price_prev else None

            results[ticker] = {
                "price":          round(price_today, 4),
                "day_change_pct": round(day_change, 4) if day_change is not None else None,
                "available":      True,
            }
        except Exception as exc:
            log.debug("Price parse failed for %s: %s", ticker, exc)
            results[ticker] = {"price": None, "day_change_pct": None, "available": False}

    return results


# ── Ticker signal classification ──────────────────────────────────────────────

def classify_ticker_signal(
    day_change_pct: Optional[float],
    pass_pct:       float,
    fail_pct:       float,
) -> str:
    """
    Classify a single ticker into PASS / WATCH / FAIL / UNKNOWN.
    Thresholds come from config — not hardcoded here.
    """
    if day_change_pct is None:
        return "UNKNOWN"
    if day_change_pct >= pass_pct:
        return "PASS"
    if day_change_pct <= fail_pct:
        return "FAIL"
    return "WATCH"


def compute_relative(
    ticker_chg: Optional[float],
    bench_chg:  Optional[float],
) -> Optional[float]:
    """Relative performance vs benchmark in percentage points."""
    if ticker_chg is None or bench_chg is None:
        return None
    return round(ticker_chg - bench_chg, 4)


# ── Basket scoring ────────────────────────────────────────────────────────────

def score_basket(
    basket_id:     str,
    basket_cfg:    Dict[str, Any],
    prices:        Dict[str, Dict[str, Any]],
    benchmarks:    Dict[str, Optional[float]],
    cfg:           Dict[str, Any],
) -> Tuple[float, List[Dict[str, Any]], str]:
    """
    Score one basket and build its ticker evidence rows.

    Returns:
        (basket_score, ticker_evidence_rows, basket_signal)
        basket_score is 0.0–basket_weight
    """
    sig_cfg          = cfg["signal_thresholds"]
    pass_pct         = float(sig_cfg["pass_pct"])
    fail_pct         = float(sig_cfg["fail_pct"])
    contrib_weights  = cfg.get("ticker_contribution_weights", {
        "PASS": 1.0, "WATCH": 0.4, "FAIL": 0.0, "UNKNOWN": 0.0
    })
    interpretations  = basket_cfg.get("interpretations", {})
    basket_weight    = float(basket_cfg["scoring_weight"])
    spy_chg          = benchmarks.get("SPY")
    qqq_chg          = benchmarks.get("QQQ")

    ticker_rows: List[Dict[str, Any]] = []
    contributions: List[float] = []

    for ticker in basket_cfg["tickers"]:
        p = prices.get(ticker, {})
        available     = p.get("available", False)
        price         = p.get("price")
        day_chg       = p.get("day_change_pct")
        signal        = classify_ticker_signal(day_chg, pass_pct, fail_pct)
        rel_spy       = compute_relative(day_chg, spy_chg)
        rel_qqq       = compute_relative(day_chg, qqq_chg)

        # Context-aware interpretation for this ticker
        interp_key = signal if signal in interpretations else "WATCH"
        interpretation = interpretations.get(interp_key, "")

        ticker_rows.append({
            "ticker":           ticker,
            "group":            basket_id,
            "price":            price,
            "day_change_pct":   day_chg,
            "relative_to_spy":  rel_spy,
            "relative_to_qqq":  rel_qqq,
            "signal":           signal,
            "interpretation":   interpretation,
        })

        if available:
            contributions.append(float(contrib_weights.get(signal, 0.0)))

    # Basket-level signal
    if not contributions:
        return 0.0, ticker_rows, "UNKNOWN"

    avg_contribution = sum(contributions) / len(contributions)
    basket_score     = round(avg_contribution * basket_weight, 2)

    pass_ratio       = sum(1 for c in contributions if c >= 1.0) / len(contributions)
    basket_pass_thr  = float(sig_cfg.get("basket_pass_ratio",  0.55))
    basket_watch_thr = float(sig_cfg.get("basket_watch_ratio", 0.35))

    if pass_ratio >= basket_pass_thr:
        basket_signal = "PASS"
    elif pass_ratio >= basket_watch_thr:
        basket_signal = "WATCH"
    else:
        basket_signal = "FAIL"

    return basket_score, ticker_rows, basket_signal


# ── Headline scoring ──────────────────────────────────────────────────────────

def score_headlines(cfg: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Scan available headline sources for thesis keywords.
    Deterministic keyword matching — no LLM.
    Degrades gracefully if headline file is missing or stale.

    Returns: (headline_score, headline_evidence_rows)
    """
    keywords     = [kw.lower() for kw in cfg.get("headline_keywords", [])]
    sources_cfg  = cfg.get("headline_sources", [])
    max_score    = float(cfg.get("headline_max_score",   15))
    pts_per_hit  = float(cfg.get("headline_pts_per_hit", 1.5))

    matched_keywords: set  = set()
    evidence_rows:    List = []

    for src_path in sources_cfg:
        full_path = BASE_DIR / src_path
        try:
            raw = json.loads(full_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.debug("Headline source not available: %s — %s", full_path, exc)
            continue

        # headlines_live.json structure: {sources: {src_id: {items: [{text, url, ts}]}}}
        sources_data = raw.get("sources", {})
        for src_id, src_content in sources_data.items():
            for item in src_content.get("items", []):
                headline_text = str(item.get("text", "")).lower()
                for kw in keywords:
                    if kw in headline_text and kw not in matched_keywords:
                        matched_keywords.add(kw)
                        evidence_rows.append({
                            "keyword":  kw,
                            "source":   src_id,
                            "headline": item.get("text", "")[:120],
                            "url":      item.get("url", ""),
                            "ts":       item.get("ts", ""),
                        })

    score = min(max_score, len(matched_keywords) * pts_per_hit)
    log.info("Headlines: %d unique keyword matches -> score %.1f / %.0f",
             len(matched_keywords), score, max_score)
    return round(score, 2), evidence_rows


# ── Risk penalty ──────────────────────────────────────────────────────────────

def compute_risk_penalty(
    prices: Dict[str, Dict[str, Any]],
    cfg:    Dict[str, Any],
) -> Tuple[float, Optional[str]]:
    """
    Check for broad high-beta liquidation and return penalty deduction.
    Returns (penalty_amount, reason_string_or_None)
    """
    rp_cfg         = cfg.get("risk_penalty", {})
    max_deduction  = float(rp_cfg.get("max_deduction",     10))
    spy_thr        = float(rp_cfg.get("spy_threshold_pct", -2.0))
    qqq_thr        = float(rp_cfg.get("qqq_threshold_pct", -2.0))
    both_required  = bool(rp_cfg.get("both_required",       True))

    spy_chg = (prices.get("SPY") or {}).get("day_change_pct")
    qqq_chg = (prices.get("QQQ") or {}).get("day_change_pct")

    if spy_chg is None or qqq_chg is None:
        return 0.0, None

    spy_breach = spy_chg < spy_thr
    qqq_breach = qqq_chg < qqq_thr

    trigger = (spy_breach and qqq_breach) if both_required else (spy_breach or qqq_breach)

    if not trigger:
        return 0.0, None

    # Scale penalty proportionally to severity
    avg_breach = (abs(spy_chg - spy_thr) + abs(qqq_chg - qqq_thr)) / 2
    penalty    = min(max_deduction, avg_breach * 3)
    reason     = (f"Broad market liquidation: SPY {spy_chg:+.2f}% / "
                  f"QQQ {qqq_chg:+.2f}% — risk penalty applied")
    log.warning("Risk penalty: %.1f pts — %s", penalty, reason)
    return round(penalty, 2), reason


# ── Score → Status / Confidence / CIO Action ─────────────────────────────────

def score_to_status(score: float, cfg: Dict[str, Any]) -> str:
    thresholds = cfg["status_thresholds"]
    if score >= float(thresholds.get("CONFIRMING", 75)):
        return "CONFIRMING"
    if score >= float(thresholds.get("WATCH",      55)):
        return "WATCH"
    if score >= float(thresholds.get("MIXED",      40)):
        return "MIXED"
    if score >= float(thresholds.get("WEAKENING",  20)):
        return "WEAKENING"
    return "CONTRADICTED"


def score_to_confidence(score: float, cfg: Dict[str, Any]) -> str:
    thresholds = cfg["confidence_thresholds"]
    if score >= float(thresholds.get("HIGH",   70)):
        return "HIGH"
    if score >= float(thresholds.get("MEDIUM", 45)):
        return "MEDIUM"
    if score >= float(thresholds.get("LOW",    20)):
        return "LOW"
    return "UNKNOWN"


def resolve_cio_action(status: str, confidence: str, cfg: Dict[str, Any]) -> str:
    action_map = cfg["cio_action_map"]
    # Try status_confidence compound key first
    key = f"{status}_{confidence}"
    if key in action_map:
        return action_map[key]
    # Fall back to status-only key
    if status in action_map:
        return action_map[status]
    return action_map.get("UNKNOWN", "CIO_REVIEW_REQUIRED")


# ── GitHub push ───────────────────────────────────────────────────────────────

def _gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def push_to_github(github_path: str, content_str: str) -> bool:
    """Push a file to GitHub Pages repo via GitHub Contents API."""
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping push")
        return False

    api_url = (
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}"
        f"/contents/{github_path}"
    )

    sha: Optional[str] = None
    try:
        r = requests.get(api_url, headers=_gh_headers(),
                         params={"ref": GITHUB_BRANCH}, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "message": f"ai_infra_power widget {_utcnow().strftime('%H:%M')}",
        "content": base64.b64encode(content_str.encode("utf-8")).decode("ascii"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=_gh_headers(), json=payload, timeout=30)
        ok = r.status_code in {200, 201}
        log.info("GitHub push %s: %s (%d)", github_path, "OK" if ok else "FAIL", r.status_code)
        return ok
    except Exception as exc:
        log.warning("GitHub push error: %s", exc)
        return False


# ── Market-hours detection ────────────────────────────────────────────────────

def get_market_status(
    cfg: Dict[str, Any],
    _now_et_override: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Determine current US equity market status.
    All parameters come from config — nothing hardcoded here.

    Args:
        cfg: widget config dict (contains market_hours section)
        _now_et_override: inject a specific datetime for unit testing only.
                          Never pass this in production code.

    Returns dict with:
        market_open          bool   True only during regular trading hours
        market_status        str    OPEN | CLOSED_PRE | CLOSED_POST | CLOSED_WEEKEND
        market_time_et       str    "HH:MM ET" for display
        last_market_session  str    ISO date of the most recent completed session
        data_freshness_label str    from config's data_freshness_labels map
    """
    from zoneinfo import ZoneInfo

    # market_hours is validated present + complete by load_config() — no defaults needed
    mh = cfg["market_hours"]
    tz_name       = str(mh["timezone"])
    open_time     = str(mh["open_time"])
    close_time    = str(mh["close_time"])
    trading_days  = set(int(d) for d in mh["trading_days"])
    label_map     = mh.get("data_freshness_labels", {})

    if _now_et_override is not None:
        now_et = _now_et_override
    else:
        try:
            tz = ZoneInfo(tz_name)
            now_et = datetime.now(tz)
        except Exception as exc:
            log.warning("Market-hours: could not load timezone '%s': %s — defaulting to UTC", tz_name, exc)
            now_et = _utcnow()

    weekday = now_et.weekday()

    oh, om = map(int, open_time.split(":"))
    ch, cm = map(int, close_time.split(":"))
    mkt_open_dt  = now_et.replace(hour=oh, minute=om, second=0, microsecond=0)
    mkt_close_dt = now_et.replace(hour=ch, minute=cm, second=0, microsecond=0)

    if weekday not in trading_days:
        market_status = "CLOSED_WEEKEND"
    elif now_et < mkt_open_dt:
        market_status = "CLOSED_PRE"
    elif now_et >= mkt_close_dt:
        market_status = "CLOSED_POST"
    else:
        market_status = "OPEN"

    market_open = (market_status == "OPEN")

    # Last completed market session — walk back from today (or yesterday if pre-market)
    ref: date = now_et.date()
    if market_status == "CLOSED_PRE":
        ref -= timedelta(days=1)          # today hasn't opened yet; previous session
    while ref.weekday() not in trading_days:
        ref -= timedelta(days=1)

    freshness_label = label_map.get(market_status, "LAST SESSION CLOSE")

    log.info("Market: status=%s  market_open=%s  time=%s  freshness=%s",
             market_status, market_open, now_et.strftime("%H:%M ET"), freshness_label)

    return {
        "market_open":          market_open,
        "market_status":        market_status,
        "market_time_et":       now_et.strftime("%H:%M ET"),
        "last_market_session":  ref.isoformat(),
        "data_freshness_label": freshness_label,
    }


# ── Output builder ────────────────────────────────────────────────────────────

def build_output(
    cfg:              Dict[str, Any],
    total_score:      float,
    status:           str,
    confidence:       str,
    cio_action:       str,
    add_allowed:      bool,
    basket_signals:   Dict[str, str],
    ticker_evidence:  List[Dict[str, Any]],
    headline_score:   float,
    headline_evidence: List[Dict[str, Any]],
    risk_penalty:     float,
    risk_reason:      Optional[str],
    blind_spots:      List[str],
    now_sgt:          datetime,
    data_quality:     str,
    market_status_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the final JSON output dict."""

    safety = cfg["safety"]

    pass_count  = sum(1 for t in ticker_evidence if t["signal"] == "PASS")
    watch_count = sum(1 for t in ticker_evidence if t["signal"] == "WATCH")
    fail_count  = sum(1 for t in ticker_evidence if t["signal"] == "FAIL")

    # Primary signals summary
    primary_signals = []
    for basket_id, basket_cfg in cfg["baskets"].items():
        if not basket_cfg.get("enabled", True):
            continue
        sig = basket_signals.get(basket_id, "UNKNOWN")
        primary_signals.append({
            "basket":         basket_id,
            "label":          basket_cfg["label"],
            "signal":         sig,
            "scoring_weight": basket_cfg["scoring_weight"],
        })

    # Summary sentence
    power_sig = basket_signals.get("POWER_GRID", "UNKNOWN")
    compute_sig = basket_signals.get("AI_COMPUTE", "UNKNOWN")
    hyper_sig = basket_signals.get("HYPERSCALER", "UNKNOWN")

    if status == "CONFIRMING":
        summary = (
            f"AI Infrastructure / Power thesis CONFIRMING (score {total_score:.0f}/100). "
            f"Power/Grid: {power_sig}, AI Compute: {compute_sig}, Hyperscalers: {hyper_sig}."
        )
    elif status == "WATCH":
        summary = (
            f"AI Infrastructure thesis on WATCH (score {total_score:.0f}/100). "
            f"Partial confirmation — Power/Grid: {power_sig}, AI Compute: {compute_sig}."
        )
    elif status == "MIXED":
        summary = (
            f"AI Infrastructure thesis MIXED (score {total_score:.0f}/100). "
            f"Signals diverging across baskets — CIO review advised."
        )
    elif status == "WEAKENING":
        summary = (
            f"AI Infrastructure thesis WEAKENING (score {total_score:.0f}/100). "
            f"Multiple baskets failing. No add recommended."
        )
    elif status == "CONTRADICTED":
        summary = (
            f"AI Infrastructure thesis CONTRADICTED (score {total_score:.0f}/100). "
            f"Broad weakness across thesis baskets."
        )
    else:
        summary = f"AI Infrastructure thesis status UNKNOWN — insufficient market data."

    risk_level = "HIGH" if risk_penalty > 5 else ("ELEVATED" if risk_penalty > 0 else "NORMAL")

    return {
        "schema_version":       cfg["schema_version"],
        "thesis_id":            cfg["thesis_id"],
        "title":                cfg["title"],
        "display_title":        cfg.get("display_title", cfg["title"]),
        "dashboard_section":    cfg.get("dashboard_section", "S6"),
        "status":               status,
        "score":                round(total_score, 1),
        "score_max":            100,
        "confidence":           confidence,
        "cio_action":           cio_action,
        "add_allowed":          add_allowed,
        "risk_level":           risk_level,
        "risk_penalty_applied": round(risk_penalty, 1),
        "risk_penalty_reason":  risk_reason,
        "data_quality":         data_quality,
        "last_updated_sgt":     now_sgt.strftime("%Y-%m-%d %H:%M SGT"),
        "last_updated_utc":     _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        # ── Market-hours fields (P1) ──────────────────────────────────────────
        "market_open":          market_status_info.get("market_open", False),
        "market_status":        market_status_info.get("market_status", "UNKNOWN"),
        "market_time_et":       market_status_info.get("market_time_et", ""),
        "last_market_session":  market_status_info.get("last_market_session", ""),
        "data_freshness_label": market_status_info.get("data_freshness_label", "LAST SESSION CLOSE"),
        # ── Evidence & signals ────────────────────────────────────────────────
        "summary":              summary,
        "primary_signals":      primary_signals,
        "headline_score":       headline_score,
        "headline_evidence":    headline_evidence[:10],  # cap for payload size
        "ticker_evidence":      ticker_evidence,
        "pass_count":           pass_count,
        "watch_count":          watch_count,
        "fail_count":           fail_count,
        "blind_spots":          blind_spots,
        "execution_authority":  safety["execution_authority"],
        "order_routing_enabled": safety["order_routing_enabled"],
        "llm_order_generation": safety["llm_order_generation"],
        "orders_generated":     0,
    }


# ── Main compute cycle ────────────────────────────────────────────────────────

def run_once(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute one full widget compute cycle.
    Returns the output dict.
    Degrades gracefully on any partial data failure.
    """
    now_utc = _utcnow()
    now_sgt = now_utc + timedelta(hours=8)

    log.info("=== AI Infrastructure / Power Thesis Cycle ===")

    # ── Collect all tickers ───────────────────────────────────────────────────
    all_tickers: List[str] = list(cfg["benchmarks"])
    for basket_id, basket_cfg in cfg["baskets"].items():
        if basket_cfg.get("enabled", True):
            all_tickers.extend(basket_cfg["tickers"])
    all_tickers = list(dict.fromkeys(all_tickers))  # deduplicate, preserve order
    log.info("Fetching %d tickers: %s", len(all_tickers), all_tickers)

    # ── Fetch prices ──────────────────────────────────────────────────────────
    prices = fetch_prices(all_tickers)

    available_count = sum(1 for t, p in prices.items() if p.get("available"))
    log.info("Price data: %d / %d tickers available", available_count, len(all_tickers))

    # ── Benchmark changes ─────────────────────────────────────────────────────
    benchmarks: Dict[str, Optional[float]] = {}
    for bench in cfg["benchmarks"]:
        benchmarks[bench] = (prices.get(bench) or {}).get("day_change_pct")

    spy_chg = benchmarks.get("SPY")
    qqq_chg = benchmarks.get("QQQ")
    log.info("Benchmarks: SPY=%s QQQ=%s",
             f"{spy_chg:+.2f}%" if spy_chg is not None else "n/a",
             f"{qqq_chg:+.2f}%" if qqq_chg is not None else "n/a")

    # ── Score baskets ─────────────────────────────────────────────────────────
    total_basket_score = 0.0
    basket_signals:  Dict[str, str]  = {}
    ticker_evidence: List[Dict[str, Any]] = []

    for basket_id, basket_cfg in cfg["baskets"].items():
        if not basket_cfg.get("enabled", True):
            log.info("[%s] disabled — skipping", basket_id)
            continue

        b_score, b_tickers, b_signal = score_basket(
            basket_id, basket_cfg, prices, benchmarks, cfg
        )
        total_basket_score += b_score
        basket_signals[basket_id] = b_signal
        ticker_evidence.extend(b_tickers)

        log.info("[%s] signal=%s  score=%.2f / %d",
                 basket_id, b_signal, b_score, basket_cfg["scoring_weight"])

    # ── Score headlines ───────────────────────────────────────────────────────
    headline_score, headline_evidence = score_headlines(cfg)

    # ── Risk penalty ──────────────────────────────────────────────────────────
    risk_penalty_amt, risk_reason = compute_risk_penalty(prices, cfg)

    # ── Total score ───────────────────────────────────────────────────────────
    raw_score   = total_basket_score + headline_score
    total_score = max(0.0, min(100.0, raw_score - risk_penalty_amt))
    log.info("Score: basket=%.1f + headline=%.1f - penalty=%.1f = total=%.1f",
             total_basket_score, headline_score, risk_penalty_amt, total_score)

    # ── Status / Confidence / CIO Action ─────────────────────────────────────
    # Handle insufficient data case
    if available_count < len(all_tickers) * 0.5:
        status     = "UNKNOWN"
        confidence = "UNKNOWN"
    else:
        status     = score_to_status(total_score, cfg)
        confidence = score_to_confidence(total_score, cfg)

    cio_action  = resolve_cio_action(status, confidence, cfg)
    add_allowed = status in cfg.get("add_allowed_statuses", [])

    # ── Data quality assessment ───────────────────────────────────────────────
    if available_count == len(all_tickers):
        data_quality = "FULL"
    elif available_count >= len(all_tickers) * 0.8:
        data_quality = "PARTIAL"
    elif available_count >= len(all_tickers) * 0.5:
        data_quality = "LIMITED"
    else:
        data_quality = "INSUFFICIENT"

    # ── Blind spots ───────────────────────────────────────────────────────────
    blind_spots: List[str] = []
    if spy_chg is None or qqq_chg is None:
        blind_spots.append("SPY/QQQ benchmark data unavailable — risk penalty disabled")

    unavailable_tickers = [t for t, p in prices.items() if not p.get("available")]
    if unavailable_tickers:
        blind_spots.append(
            f"No price data for: {', '.join(unavailable_tickers[:8])}"
        )

    if not headline_evidence:
        blind_spots.append("No thesis-relevant headlines matched — keyword scan returned empty")

    if risk_penalty_amt > 0 and risk_reason:
        blind_spots.append(risk_reason)

    log.info("Status=%s  Confidence=%s  CIO=%s  AddAllowed=%s",
             status, confidence, cio_action, add_allowed)

    # ── Market-hours detection ────────────────────────────────────────────────
    market_status_info = get_market_status(cfg)

    # ── Build output dict ─────────────────────────────────────────────────────
    output = build_output(
        cfg=cfg,
        total_score=total_score,
        status=status,
        confidence=confidence,
        cio_action=cio_action,
        add_allowed=add_allowed,
        basket_signals=basket_signals,
        ticker_evidence=ticker_evidence,
        headline_score=headline_score,
        headline_evidence=headline_evidence,
        risk_penalty=risk_penalty_amt,
        risk_reason=risk_reason,
        blind_spots=blind_spots,
        now_sgt=now_sgt,
        data_quality=data_quality,
        market_status_info=market_status_info,
    )

    # ── Save locally ──────────────────────────────────────────────────────────
    out_dir  = BASE_DIR / cfg["output"]["local_dir"]
    out_path = out_dir / cfg["output"]["local_file"]
    out_dir.mkdir(parents=True, exist_ok=True)

    json_str = json.dumps(output, ensure_ascii=False, indent=2)
    out_path.write_text(json_str, encoding="utf-8")
    log.info("Saved locally: %s", out_path)

    # ── Push to GitHub Pages ──────────────────────────────────────────────────
    push_to_github(cfg["output"]["github_path"], json_str)

    return output


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus AI Infrastructure / Power Bottleneck Thesis Widget"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single cycle then exit (default: run as daemon)"
    )
    args = parser.parse_args()

    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("BlueLotus V3 — AI Infrastructure / Power Thesis Widget")
    log.info("Config: %s", CONFIG_PATH)

    try:
        cfg = load_config()
    except RuntimeError as exc:
        log.critical(str(exc))
        sys.exit(1)

    refresh = int(cfg.get("refresh_interval_seconds", 600))

    log.info("Thesis  : %s", cfg["thesis_id"])
    log.info("Refresh : %d min", refresh // 60)
    log.info("Baskets : %s",
             [b for b, bc in cfg["baskets"].items() if bc.get("enabled", True)])
    log.info("=" * 60)

    if args.once:
        try:
            result = run_once(cfg)
            log.info("Single cycle complete — status=%s score=%.1f",
                     result["status"], result["score"])
        except Exception as exc:
            log.error("Cycle failed: %s", exc, exc_info=True)
            sys.exit(1)
        return

    # Daemon loop
    cycle = 0
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 10

    while True:
        cycle += 1
        log.info("── Cycle %d  %s ──", cycle, _utcnow().strftime("%H:%M:%S UTC"))
        try:
            result = run_once(cfg)
            consecutive_failures = 0
            log.info("Cycle %d done — status=%s  score=%.1f  confidence=%s\n",
                     cycle, result["status"], result["score"], result["confidence"])
        except Exception as exc:
            consecutive_failures += 1
            log.error("Cycle %d crashed (%d consecutive): %s",
                      cycle, consecutive_failures, exc, exc_info=True)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.critical(
                    "WIDGET: %d consecutive failures. Still running. "
                    "Check yfinance / GitHub token / config file.",
                    consecutive_failures,
                )

        log.info("Sleeping %d min until next cycle...", refresh // 60)
        time.sleep(refresh)


if __name__ == "__main__":
    main()
