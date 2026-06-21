#!/usr/bin/env python3
"""
credit_refinancing_liquidity.py — BlueLotus V3 Thesis Widget
==============================================================
Credit / Refinancing / Liquidity Thesis Monitor
Thesis ID: CREDIT_REFINANCING_LIQUIDITY_THESIS
Dashboard: S7

THESIS DIRECTION:
  Higher score = more credit/liquidity stress (range 0–100).
  0 = credit calm, 100 = severe systemic stress.
  This widget detects whether equity drawdowns are spreading into deeper
  credit, refinancing, and liquidity pressure.

INDEPENDENCE GUARANTEE:
  Runs standalone.  Does NOT require V3 Grand Pipeline, LLM clients, Chief Strategist,
  agent council, order routing, or V2 pipeline.

NO HARDCODING DOCTRINE:
  All tickers, weights, thresholds, keywords, and paths come from:
    C:\\bluelotus3\\config\\thesis_widgets\\credit_refinancing_liquidity.yaml
  To change any value: edit the YAML, restart the widget.

SAFETY:
  execution_authority : CIO_ONLY_MANUAL
  order_routing       : DISABLED
  llm_order_generation: false
  This widget is read-only intelligence. It never routes orders.

Run standalone:
    python thesis_widgets\\credit_refinancing_liquidity.py

Run once (no loop):
    python thesis_widgets\\credit_refinancing_liquidity.py --once
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
CONFIG_PATH = BASE_DIR / "config" / "thesis_widgets" / "credit_refinancing_liquidity.yaml"

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
            BASE_DIR / "logs" / "credit_refinancing_liquidity.log",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("credit_refi_liq")


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
        "headline_scoring_weight", "calm_offset", "blind_spots",
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
        for field in ("label", "scoring_weight", "enabled", "tickers", "stress_on_rise"):
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
    Supports index tickers such as ^VIX.
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
    stress_pct:     float,
    calm_pct:       float,
    stress_on_rise: bool,
) -> str:
    """
    Classify a single ticker into STRESS / WATCH / CALM / UNKNOWN.

    stress_on_rise=True  → rising prices = stress (volatility, dollar)
                           (VIX/VXX/UVXY going up, UUP going up)
    stress_on_rise=False → falling prices = stress (credit, banks, refinancing)
                           (HYG/JNK/XLF going down)

    Thresholds come from config — nothing hardcoded here.
    """
    if day_change_pct is None:
        return "UNKNOWN"
    if stress_on_rise:
        # Rising = stress (volatility, dollar funding)
        if day_change_pct >= stress_pct:
            return "STRESS"
        if day_change_pct <= -calm_pct:
            return "CALM"
    else:
        # Falling = stress (credit, banks, rate-sensitive)
        if day_change_pct <= -stress_pct:
            return "STRESS"
        if day_change_pct >= calm_pct:
            return "CALM"
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
    basket_id:  str,
    basket_cfg: Dict[str, Any],
    prices:     Dict[str, Dict[str, Any]],
    benchmarks: Dict[str, Optional[float]],
    cfg:        Dict[str, Any],
) -> Tuple[float, List[Dict[str, Any]], str]:
    """
    Score one basket and build its ticker evidence rows.

    Returns:
        (basket_score, ticker_evidence_rows, basket_signal)
        basket_signal is STRESS / WATCH / CALM / UNKNOWN
        basket_score is 0.0–basket_weight (proportional to stress level)
    """
    sig_cfg    = cfg["signal_thresholds"]

    # Per-basket threshold override (e.g. VOL_DOLLAR_LIQUIDITY uses 1.5%)
    basket_thr = basket_cfg.get("signal_thresholds", {})
    stress_pct = float(basket_thr.get("stress_pct") or sig_cfg["stress_pct"])
    calm_pct   = float(basket_thr.get("calm_pct")   or sig_cfg["calm_pct"])

    stress_on_rise  = bool(basket_cfg.get("stress_on_rise", False))
    contrib_weights = cfg.get("ticker_contribution_weights", {
        "STRESS": 1.0, "WATCH": 0.4, "CALM": 0.0, "UNKNOWN": 0.0
    })
    interpretations = basket_cfg.get("interpretations", {})
    basket_weight   = float(basket_cfg["scoring_weight"])
    spy_chg         = benchmarks.get("SPY")
    qqq_chg         = benchmarks.get("QQQ")

    ticker_rows:   List[Dict[str, Any]] = []
    contributions: List[float]          = []
    stress_count:  int = 0
    calm_count:    int = 0

    for ticker in basket_cfg["tickers"]:
        p           = prices.get(ticker, {})
        available   = p.get("available", False)
        price       = p.get("price")
        day_chg     = p.get("day_change_pct")
        signal      = classify_ticker_signal(day_chg, stress_pct, calm_pct, stress_on_rise)
        rel_spy     = compute_relative(day_chg, spy_chg)
        rel_qqq     = compute_relative(day_chg, qqq_chg)

        # Context-aware interpretation for this ticker's signal
        interp = interpretations.get(signal, interpretations.get("WATCH", ""))

        ticker_rows.append({
            "ticker":          ticker,
            "group":           basket_id,
            "price":           price,
            "day_change_pct":  day_chg,
            "relative_to_spy": rel_spy,
            "relative_to_qqq": rel_qqq,
            "signal":          signal,
            "interpretation":  interp,
        })

        if available:
            contributions.append(float(contrib_weights.get(signal, 0.0)))
            if signal == "STRESS":
                stress_count += 1
            elif signal == "CALM":
                calm_count += 1

    if not contributions:
        return 0.0, ticker_rows, "UNKNOWN"

    avg_contribution = sum(contributions) / len(contributions)
    basket_score     = round(avg_contribution * basket_weight, 2)

    n                  = len(contributions)
    stress_ratio       = stress_count / n
    calm_ratio         = calm_count   / n
    basket_stress_thr  = float(sig_cfg.get("basket_stress_ratio", 0.55))
    basket_calm_thr    = float(sig_cfg.get("basket_calm_ratio",   0.55))

    if stress_ratio >= basket_stress_thr:
        basket_signal = "STRESS"
    elif calm_ratio >= basket_calm_thr:
        basket_signal = "CALM"
    else:
        basket_signal = "WATCH"

    return basket_score, ticker_rows, basket_signal


# ── Calm offset ───────────────────────────────────────────────────────────────

def compute_calm_offset(basket_signals: Dict[str, str], cfg: Dict[str, Any]) -> float:
    """
    Negative score adjustment when both HIGH_YIELD_CREDIT and BANKS_FINANCIALS
    are simultaneously CALM.

    Prevents false-positive stress readings when the core credit and banking
    system is healthy despite equity volatility elsewhere.

    All values come from config — nothing hardcoded here.
    """
    co_cfg        = cfg.get("calm_offset", {})
    if not co_cfg.get("enabled", False):
        return 0.0
    required      = co_cfg.get("requires_calm_baskets", [])
    max_deduction = float(co_cfg.get("max_deduction", 10))
    if all(basket_signals.get(b) == "CALM" for b in required):
        log.info("Calm offset: %s all CALM — applying -%.1f pts", required, max_deduction)
        return max_deduction
    return 0.0


# ── Headline scoring ──────────────────────────────────────────────────────────

def score_headlines(cfg: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Scan available headline sources for credit/liquidity thesis keywords.
    Deterministic keyword matching — no LLM.
    Degrades gracefully if headline file is missing or stale.

    Returns: (headline_score, headline_evidence_rows)
    """
    keywords    = [kw.lower() for kw in cfg.get("headline_keywords", [])]
    sources_cfg = cfg.get("headline_sources", [])
    max_score   = float(cfg.get("headline_max_score",   15))
    pts_per_hit = float(cfg.get("headline_pts_per_hit", 1.5))

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


# ── Score → Status / Confidence / CIO Action ─────────────────────────────────

def score_to_status(score: float, cfg: Dict[str, Any]) -> str:
    """Map stress score to status string. Higher score = more stress."""
    t = cfg["status_thresholds"]
    if score >= float(t["SEVERE_STRESS"]): return "SEVERE_STRESS"
    if score >= float(t["ACTIVE_STRESS"]): return "ACTIVE_STRESS"
    if score >= float(t["WATCH"]):         return "WATCH"
    if score >= float(t["LOW_STRESS"]):    return "LOW_STRESS"
    return "CALM"


def score_to_confidence(score: float, cfg: Dict[str, Any]) -> str:
    thresholds = cfg["confidence_thresholds"]
    if score >= float(thresholds.get("HIGH",   65)):
        return "HIGH"
    if score >= float(thresholds.get("MEDIUM", 40)):
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
        "message": f"credit_refi_liquidity widget {_utcnow().strftime('%H:%M')}",
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
    tz_name      = str(mh["timezone"])
    open_time    = str(mh["open_time"])
    close_time   = str(mh["close_time"])
    trading_days = set(int(d) for d in mh["trading_days"])
    label_map    = mh.get("data_freshness_labels", {})

    if _now_et_override is not None:
        now_et = _now_et_override
    else:
        try:
            tz = ZoneInfo(tz_name)
            now_et = datetime.now(tz)
        except Exception as exc:
            log.warning("Market-hours: could not load timezone '%s': %s — defaulting to UTC",
                        tz_name, exc)
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
        ref -= timedelta(days=1)          # today hasn't opened yet; use previous session
    while ref.weekday() not in trading_days:
        ref -= timedelta(days=1)

    freshness_label = label_map.get(market_status, "")

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

# Risk level mapping — derived from status, not from a penalty amount
_STATUS_TO_RISK: Dict[str, str] = {
    "SEVERE_STRESS": "CRITICAL",
    "ACTIVE_STRESS": "HIGH",
    "WATCH":         "ELEVATED",
    "LOW_STRESS":    "LOW",
    "CALM":          "MINIMAL",
    "UNKNOWN":       "UNKNOWN",
}


def build_output(
    cfg:               Dict[str, Any],
    total_score:       float,
    status:            str,
    confidence:        str,
    cio_action:        str,
    add_allowed:       bool,
    basket_signals:    Dict[str, str],
    ticker_evidence:   List[Dict[str, Any]],
    headline_score:    float,
    headline_evidence: List[Dict[str, Any]],
    calm_offset_applied: float,
    blind_spots:       List[str],
    now_sgt:           datetime,
    data_quality:      str,
    market_status_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the final JSON output dict."""

    safety = cfg["safety"]

    stress_count = sum(1 for t in ticker_evidence if t["signal"] == "STRESS")
    watch_count  = sum(1 for t in ticker_evidence if t["signal"] == "WATCH")
    calm_count   = sum(1 for t in ticker_evidence if t["signal"] == "CALM")

    # Primary signals summary — one entry per enabled basket
    primary_signals: List[Dict[str, Any]] = []
    for basket_id, basket_cfg in cfg["baskets"].items():
        if not basket_cfg.get("enabled", True):
            continue
        sig = basket_signals.get(basket_id, "UNKNOWN")
        primary_signals.append({
            "basket":         basket_id,
            "label":          basket_cfg["label"],
            "signal":         sig,
            "scoring_weight": basket_cfg["scoring_weight"],
            "stress_on_rise": basket_cfg.get("stress_on_rise", False),
        })

    # Summary sentence — answers the key question: is credit stress systemic?
    hy_sig   = basket_signals.get("HIGH_YIELD_CREDIT",   "UNKNOWN")
    bank_sig = basket_signals.get("BANKS_FINANCIALS",    "UNKNOWN")
    vol_sig  = basket_signals.get("VOL_DOLLAR_LIQUIDITY","UNKNOWN")

    if status == "SEVERE_STRESS":
        summary = (
            f"SEVERE credit/liquidity stress confirmed (score {total_score:.0f}/100). "
            f"HY Credit: {hy_sig}, Banks: {bank_sig}, Volatility: {vol_sig}. "
            "Systemic risk elevated — CIO risk review required."
        )
    elif status == "ACTIVE_STRESS":
        summary = (
            f"ACTIVE credit/liquidity stress — equity weakness spreading to credit "
            f"(score {total_score:.0f}/100). HY: {hy_sig}, Banks: {bank_sig}. "
            "Hedge review advised."
        )
    elif status == "WATCH":
        summary = (
            f"Credit/liquidity on WATCH — partial stress signals (score {total_score:.0f}/100). "
            f"HY: {hy_sig}, Banks: {bank_sig}. Monitor for escalation to ACTIVE_STRESS."
        )
    elif status == "LOW_STRESS":
        summary = (
            f"Low credit/liquidity stress (score {total_score:.0f}/100). "
            "Equity weakness not yet confirmed in credit channels. Hold posture."
        )
    elif status == "CALM":
        summary = (
            f"Credit markets calm (score {total_score:.0f}/100). "
            f"Banks: {bank_sig}, HY: {hy_sig}. "
            "No systemic stress detected — equity volatility appears contained."
        )
    else:
        summary = (
            "Credit/liquidity thesis status UNKNOWN — insufficient market data. "
            "CIO review required before any action."
        )

    risk_level = _STATUS_TO_RISK.get(status, "UNKNOWN")

    return {
        "schema_version":        cfg["schema_version"],
        "thesis_id":             cfg["thesis_id"],
        "title":                 cfg["title"],
        "display_title":         cfg.get("display_title", cfg["title"]),
        "dashboard_section":     cfg.get("dashboard_section", "S7"),
        "status":                status,
        "score":                 round(total_score, 1),
        "score_max":             100,
        "confidence":            confidence,
        "cio_action":            cio_action,
        "add_allowed":           add_allowed,
        "risk_level":            risk_level,
        "calm_offset_applied":   round(calm_offset_applied, 1),
        "data_quality":          data_quality,
        "last_updated_sgt":      now_sgt.strftime("%Y-%m-%d %H:%M SGT"),
        "last_updated_utc":      _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        # ── Market-hours fields ───────────────────────────────────────────────
        "market_open":           market_status_info.get("market_open", False),
        "market_status":         market_status_info.get("market_status", "UNKNOWN"),
        "market_time_et":        market_status_info.get("market_time_et", ""),
        "last_market_session":   market_status_info.get("last_market_session", ""),
        "data_freshness_label":  market_status_info.get("data_freshness_label", ""),
        # ── Evidence & signals ────────────────────────────────────────────────
        "summary":               summary,
        "primary_signals":       primary_signals,
        "headline_score":        headline_score,
        "headline_evidence":     headline_evidence[:10],  # cap payload size
        "ticker_evidence":       ticker_evidence,
        # ── Counts ───────────────────────────────────────────────────────────
        "stress_count":          stress_count,
        "watch_count":           watch_count,
        "calm_count":            calm_count,
        "pass_count":            calm_count,    # alias: CALM = passing for risk monitor
        "fail_count":            stress_count,  # alias: STRESS = failing
        # ── Blind spots ───────────────────────────────────────────────────────
        "blind_spots":           blind_spots,
        # ── Safety ────────────────────────────────────────────────────────────
        "execution_authority":   safety["execution_authority"],
        "order_routing_enabled": safety["order_routing_enabled"],
        "llm_order_generation":  safety["llm_order_generation"],
        "orders_generated":      0,
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

    log.info("=== Credit / Refinancing / Liquidity Thesis Cycle ===")

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

    spy_chg = benchmarks.get(cfg["benchmarks"][0]) if cfg["benchmarks"] else None
    qqq_chg = benchmarks.get(cfg["benchmarks"][1]) if len(cfg["benchmarks"]) > 1 else None
    bench_log = "  ".join(
        f"{t}={benchmarks[t]:+.2f}%" if benchmarks.get(t) is not None else f"{t}=n/a"
        for t in cfg["benchmarks"]
    )
    log.info("Benchmarks: %s", bench_log)

    # ── Score baskets ─────────────────────────────────────────────────────────
    total_basket_score = 0.0
    basket_signals:  Dict[str, str]       = {}
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

    # ── Calm offset (negative adjustment when credit + banks are calm) ────────
    calm_offset_amt = compute_calm_offset(basket_signals, cfg)

    # ── Total score ───────────────────────────────────────────────────────────
    raw_score   = total_basket_score + headline_score - calm_offset_amt
    total_score = max(0.0, min(100.0, raw_score))
    log.info(
        "Score: basket=%.1f + headline=%.1f - calm_offset=%.1f = total=%.1f",
        total_basket_score, headline_score, calm_offset_amt, total_score
    )

    # ── Status / Confidence / CIO Action ─────────────────────────────────────
    if available_count < len(all_tickers) * 0.5:
        status     = "UNKNOWN"
        confidence = "UNKNOWN"
    else:
        status     = score_to_status(total_score, cfg)
        confidence = score_to_confidence(total_score, cfg)

    cio_action  = resolve_cio_action(status, confidence, cfg)
    add_allowed = status in cfg.get("add_allowed_statuses", [])

    log.info("Status=%s  Confidence=%s  CIO=%s  AddAllowed=%s",
             status, confidence, cio_action, add_allowed)

    # ── Data quality assessment ───────────────────────────────────────────────
    if available_count == len(all_tickers):
        data_quality = "FULL"
    elif available_count >= len(all_tickers) * 0.8:
        data_quality = "PARTIAL"
    elif available_count >= len(all_tickers) * 0.5:
        data_quality = "LIMITED"
    else:
        data_quality = "INSUFFICIENT"

    # ── Blind spots (static from YAML + runtime-detected issues) ─────────────
    blind_spots: List[str] = list(cfg.get("blind_spots", []))
    if spy_chg is None or qqq_chg is None:
        blind_spots.append("SPY/QQQ benchmark data unavailable")
    unavailable_tickers = [t for t, p in prices.items() if not p.get("available")]
    if unavailable_tickers:
        blind_spots.append(
            f"No price data for: {', '.join(unavailable_tickers[:8])}"
        )
    if not headline_evidence:
        blind_spots.append("No credit/liquidity headlines matched in keyword scan")

    # ── Market-hours detection ────────────────────────────────────────────────
    market_status_info = get_market_status(cfg)
    log.info("Market: status=%s  market_open=%s  time=%s  freshness=%s",
             market_status_info["market_status"],
             market_status_info["market_open"],
             market_status_info["market_time_et"],
             market_status_info["data_freshness_label"])

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
        calm_offset_applied=calm_offset_amt,
        blind_spots=blind_spots,
        now_sgt=now_sgt,
        data_quality=data_quality,
        market_status_info=market_status_info,
    )

    # ── Save locally ──────────────────────────────────────────────────────────
    out_cfg    = cfg["output"]
    local_path = BASE_DIR / out_cfg["local_dir"] / out_cfg["local_file"]
    local_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(output, indent=2, ensure_ascii=False)
    local_path.write_text(json_str, encoding="utf-8")
    log.info("Saved locally: %s", local_path)

    # ── Push to GitHub ────────────────────────────────────────────────────────
    push_to_github(out_cfg["github_path"], json_str)

    log.info("Cycle done — status=%s  score=%.1f  confidence=%s",
             status, total_score, confidence)
    return output


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BlueLotus V3 — Credit / Refinancing / Liquidity Thesis Widget"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run one cycle and exit (default: run in daemon loop)"
    )
    args = parser.parse_args()

    cfg = load_config()

    refresh_sec = int(cfg.get("refresh_interval_seconds", 600))

    log.info("=" * 60)
    log.info("BlueLotus V3 — Credit / Refinancing / Liquidity Thesis Widget")
    log.info("Config: %s", CONFIG_PATH)
    log.info("Config loaded: thesis_id=%s  schema=%s",
             cfg["thesis_id"], cfg["schema_version"])
    log.info("Thesis  : %s", cfg["thesis_id"])
    log.info("Refresh : %d min", refresh_sec // 60)
    log.info("Baskets : %s", list(cfg["baskets"].keys()))
    log.info("=" * 60)

    cycle = 0
    while True:
        cycle += 1
        now_str = _utcnow().strftime("%H:%M:%S UTC")
        log.info("── Cycle %d  %s ──", cycle, now_str)
        try:
            run_once(cfg)
        except Exception as exc:
            log.error("Cycle %d crashed: %s", cycle, exc, exc_info=True)
            # Do not re-raise — daemon must survive individual cycle failures

        if args.once:
            log.info("--once flag set — exiting after cycle %d", cycle)
            break

        log.info("Sleeping %d min until next cycle...", refresh_sec // 60)
        time.sleep(refresh_sec)


if __name__ == "__main__":
    main()
