#!/usr/bin/env python3
"""
global_leverage_unwind.py — BlueLotus V3 Thesis Widget
=======================================================
Global Leverage Unwind Thesis Monitor
Thesis ID: GLOBAL_LEVERAGE_UNWIND_THESIS
Dashboard: S8

THESIS DIRECTION:
  Higher score = more leverage-unwind risk (range 0–100).
  0 = leveraged positions calm, 100 = severe forced deleveraging.

  Detects whether market weakness is driven by forced deleveraging:
  yen carry unwind, volatility expansion, high-beta liquidation,
  credit/funding stress, Japan equity stress, and crypto weakness.

INDEPENDENCE GUARANTEE:
  Runs standalone. Does NOT require V3 Grand Pipeline, LLM clients, Chief
  Strategist, agent council, order routing, or V2 pipeline.

NO HARDCODING DOCTRINE:
  All tickers, symbols, weights, thresholds, keywords, and paths come from:
    config/thesis_widgets/global_leverage_unwind.yaml
  To change any value: edit the YAML, restart the widget.

TICKER FORMAT:
  Each basket uses per-ticker dicts with display, yf_symbol, and
  stress_on_rise fields. This allows mixed-direction signals within one
  basket (e.g., credit ETFs falling = stress, dollar rising = stress).

SAFETY:
  execution_authority : CIO_ONLY_MANUAL
  order_routing       : DISABLED
  llm_order_generation: false
  This widget is read-only intelligence. It never routes orders.

Run standalone:
    python thesis_widgets\\global_leverage_unwind.py

Run once (no loop):
    python thesis_widgets\\global_leverage_unwind.py --once
"""
import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
import yfinance as yf

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT     = Path(__file__).resolve().parent.parent
_CFG_PATH = _ROOT / "config" / "thesis_widgets" / "global_leverage_unwind.yaml"

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_DIR = _ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_DIR / "global_leverage_unwind.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("global_lev_unwind")

# Silence yfinance / urllib3 noise
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(path: Path = _CFG_PATH) -> Dict[str, Any]:
    """Load and return the YAML config. Raises on missing file."""
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_relative(val: Optional[float], ref: Optional[float]) -> Optional[float]:
    """Return val − ref (percentage points vs reference). None if either is None."""
    if val is None or ref is None:
        return None
    return round(val - ref, 3)


# ── Price Fetching ────────────────────────────────────────────────────────────

def fetch_prices(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch day-change price data for a list of yfinance symbols.
    Returns dict keyed by symbol → {available, price, day_change_pct}.
    Handles equity, ETF, currency (JPY=X), index (^VIX), and crypto (BTC-USD).
    """
    result: Dict[str, Dict] = {s: {"available": False, "price": None, "day_change_pct": None}
                                for s in symbols}
    if not symbols:
        return result

    try:
        raw = yf.download(
            symbols,
            period="2d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw.empty:
            return result

        close = raw["Close"] if "Close" in raw.columns else raw.get("close")
        if close is None or close.empty:
            return result

        # Normalise: single-ticker download may produce a Series
        if hasattr(close, "squeeze"):
            if len(symbols) == 1:
                close = close.to_frame(name=symbols[0])

        for sym in symbols:
            try:
                col = close[sym] if sym in close.columns else None
                if col is None:
                    continue
                col = col.dropna()
                if len(col) < 1:
                    continue
                latest = float(col.iloc[-1])
                prev   = float(col.iloc[-2]) if len(col) >= 2 else latest
                chg    = round((latest - prev) / prev * 100, 4) if prev != 0 else 0.0
                result[sym] = {"available": True, "price": round(latest, 4),
                               "day_change_pct": chg}
            except Exception:
                pass
    except Exception as exc:
        log.warning("fetch_prices error: %s", exc)

    return result


# ── Signal Classification ─────────────────────────────────────────────────────

def classify_ticker_signal(
    day_change_pct: Optional[float],
    stress_pct: float,
    calm_pct: float,
    stress_on_rise: bool,
) -> str:
    """
    Direction-aware signal classification.
    stress_on_rise=True:  rising price  >= +stress_pct → STRESS
                          falling price <= -calm_pct   → CALM
    stress_on_rise=False: falling price <= -stress_pct → STRESS
                          rising price  >= +calm_pct   → CALM
    """
    if day_change_pct is None:
        return "UNKNOWN"
    if stress_on_rise:
        if day_change_pct >= stress_pct:
            return "STRESS"
        if day_change_pct <= -calm_pct:
            return "CALM"
    else:
        if day_change_pct <= -stress_pct:
            return "STRESS"
        if day_change_pct >= calm_pct:
            return "CALM"
    return "WATCH"


# ── Basket Scoring ────────────────────────────────────────────────────────────

def score_basket(
    basket_id: str,
    basket_cfg: Dict[str, Any],
    prices: Dict[str, Dict],
    spy_chg: Optional[float],
    qqq_chg: Optional[float],
    cfg: Dict[str, Any],
) -> Tuple[str, float, List[Dict]]:
    """
    Score one basket using per-ticker dict format.
    Each ticker dict has: display, yf_symbol, stress_on_rise.
    Returns: (basket_signal, basket_score, ticker_rows)
    """
    sig_cfg = cfg["signal_thresholds"]
    bkt_thr = basket_cfg.get("signal_thresholds", {})
    stress_pct = float(bkt_thr.get("stress_pct") or sig_cfg["stress_pct"])
    calm_pct   = float(bkt_thr.get("calm_pct")   or sig_cfg["calm_pct"])
    bsr = float(sig_cfg.get("basket_stress_ratio", 0.55))
    bcr = float(sig_cfg.get("basket_calm_ratio",   0.55))
    cw  = cfg.get("ticker_contribution_weights",
                  {"STRESS": 1.0, "WATCH": 0.4, "CALM": 0.0, "UNKNOWN": 0.0})
    interps       = basket_cfg.get("interpretations", {})
    basket_weight = float(basket_cfg["scoring_weight"])

    rows:     List[Dict] = []
    contribs: List[float] = []
    n_stress = 0
    n_calm   = 0
    n_available = 0

    for tk in basket_cfg["tickers"]:
        display  = tk["display"]
        yf_sym   = tk["yf_symbol"]
        sor      = bool(tk.get("stress_on_rise", False))

        p        = prices.get(yf_sym, {})
        avail    = p.get("available", False)
        price    = p.get("price")
        day_chg  = p.get("day_change_pct")
        signal   = classify_ticker_signal(day_chg, stress_pct, calm_pct, sor)
        rel_spy  = compute_relative(day_chg, spy_chg)
        rel_qqq  = compute_relative(day_chg, qqq_chg)
        interp   = interps.get(signal, interps.get("WATCH", ""))

        if signal == "STRESS":
            n_stress += 1
        elif signal == "CALM":
            n_calm += 1
        if avail:
            n_available += 1

        rows.append({
            "display_symbol":  display,
            "yf_symbol":       yf_sym,
            "group":           basket_id,
            "price":           price,
            "day_change_pct":  day_chg,
            "relative_to_spy": rel_spy,
            "relative_to_qqq": rel_qqq,
            "signal":          signal,
            "interpretation":  interp,
            "available":       avail,
        })
        contribs.append(float(cw.get(signal, 0.0)))

    n = len(rows)
    if n == 0 or n_available == 0:
        return "UNKNOWN", 0.0, rows

    if n_stress / n >= bsr:
        basket_signal = "STRESS"
    elif n_calm / n >= bcr:
        basket_signal = "CALM"
    else:
        basket_signal = "WATCH"

    avg_contrib  = sum(contribs) / n
    basket_score = avg_contrib * basket_weight

    return basket_signal, basket_score, rows


# ── Calm Offset ───────────────────────────────────────────────────────────────

def compute_calm_offset(basket_signals: Dict[str, str], cfg: Dict[str, Any]) -> float:
    """
    Negative score adjustment when all required baskets are simultaneously CALM.
    Prevents false-positive readings when all major stress channels are quiet.
    """
    co_cfg = cfg.get("calm_offset", {})
    if not co_cfg.get("enabled", False):
        return 0.0
    required     = co_cfg.get("requires_calm_baskets", [])
    max_deduction = float(co_cfg.get("max_deduction", 10))
    if all(basket_signals.get(b) == "CALM" for b in required):
        return max_deduction
    return 0.0


# ── Headline Scoring ──────────────────────────────────────────────────────────

def score_headlines(cfg: Dict[str, Any]) -> Tuple[float, List[Dict]]:
    """
    Deterministic keyword search across headline feeds.
    Returns (score, evidence_list). Degrades gracefully if file missing.
    """
    keywords     = [str(k).lower() for k in cfg.get("headline_keywords", [])]
    pts_per_hit  = float(cfg.get("headline_pts_per_hit", 1.5))
    max_score    = float(cfg.get("headline_max_score", 15))
    sources      = cfg.get("headline_sources", [])

    all_items: List[Dict] = []
    for src_path in sources:
        path = _ROOT / src_path
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_items.extend(data)
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        all_items.extend(v)
        except Exception:
            pass

    score    = 0.0
    evidence = []
    seen: set = set()

    for item in all_items:
        if not isinstance(item, dict):
            continue
        text = (item.get("headline") or item.get("title") or "").lower()
        if not text or text in seen:
            continue
        for kw in keywords:
            if kw in text:
                score += pts_per_hit
                evidence.append({
                    "headline":       item.get("headline") or item.get("title", ""),
                    "keyword_matched": kw,
                    "source":         item.get("source", ""),
                })
                seen.add(text)
                break

    return min(score, max_score), evidence


# ── External Evidence ─────────────────────────────────────────────────────────

def read_external_evidence(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Read optional S5 BOJ/Yen and S7 Credit widget outputs.
    All sources are optional — missing files produce 'UNAVAILABLE' entries.
    Never crashes regardless of file state.
    """
    ext_cfg = cfg.get("external_evidence", {})
    if not ext_cfg.get("enabled", False):
        return []

    evidence: List[Dict] = []
    for src_id, src in ext_cfg.get("sources", {}).items():
        path_str     = src.get("path", "")
        label        = src.get("label", src_id)
        status_field = src.get("status_field", "status")
        path         = _ROOT / path_str

        if not path.exists():
            evidence.append({
                "source":    src_id,
                "label":     label,
                "status":    "UNAVAILABLE",
                "available": False,
            })
            log.debug("External evidence not available: %s (%s)", src_id, path_str)
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ext_status   = data.get(status_field, "UNKNOWN")
            ext_score    = data.get("score")
            generated_at = data.get("last_updated_utc") or data.get("last_updated_sgt", "")
            evidence.append({
                "source":       src_id,
                "label":        label,
                "status":       ext_status,
                "score":        ext_score,
                "generated_at": generated_at,
                "available":    True,
            })
            log.info("External evidence: %s → %s", src_id, ext_status)
        except Exception as exc:
            evidence.append({
                "source":    src_id,
                "label":     label,
                "status":    "READ_ERROR",
                "available": False,
                "error":     str(exc),
            })
            log.warning("External evidence read error: %s — %s", src_id, exc)

    return evidence


# ── Market Hours ──────────────────────────────────────────────────────────────

def get_market_status(
    cfg: Dict[str, Any],
    _now_et_override: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Compute market open/closed status from YAML market_hours config.
    _now_et_override injects a fixed datetime for testing.
    All timezone and session strings come from YAML — nothing hardcoded.
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    mh          = cfg["market_hours"]
    tz_name     = mh["timezone"]
    open_str    = mh["open_time"]
    close_str   = mh["close_time"]
    trading_days = list(mh["trading_days"])
    label_map   = mh.get("data_freshness_labels", {})

    tz      = ZoneInfo(tz_name)
    now_et  = _now_et_override or datetime.now(tz)

    oh, om  = (int(x) for x in open_str.split(":"))
    ch, cm  = (int(x) for x in close_str.split(":"))
    mkt_open_dt  = now_et.replace(hour=oh, minute=om, second=0, microsecond=0)
    mkt_close_dt = now_et.replace(hour=ch, minute=cm, second=0, microsecond=0)

    weekday = now_et.weekday()
    if weekday not in trading_days:
        market_status = "CLOSED_WEEKEND"
    elif now_et < mkt_open_dt:
        market_status = "CLOSED_PRE"
    elif now_et >= mkt_close_dt:
        market_status = "CLOSED_POST"
    else:
        market_status = "OPEN"

    market_open = (market_status == "OPEN")

    # Walk back to find last completed market session
    ref: date = now_et.date()
    if market_status == "CLOSED_PRE":
        ref -= timedelta(days=1)
    while ref.weekday() not in trading_days:
        ref -= timedelta(days=1)

    freshness_label = label_map.get(market_status, "")

    log.info(
        "Market: status=%s  market_open=%s  time=%s  freshness=%s",
        market_status, market_open, now_et.strftime("%H:%M ET"), freshness_label,
    )

    return {
        "market_open":         market_open,
        "market_status":       market_status,
        "market_time_et":      now_et.strftime("%H:%M ET"),
        "last_market_session": ref.isoformat(),
        "data_freshness_label": freshness_label,
    }


# ── Status / Confidence / CIO ─────────────────────────────────────────────────

_STATUS_TO_RISK: Dict[str, str] = {
    "SEVERE_UNWIND": "CRITICAL",
    "ACTIVE_UNWIND": "HIGH",
    "WATCH":         "ELEVATED",
    "LOW":           "LOW",
    "CALM":          "MINIMAL",
    "UNKNOWN":       "UNKNOWN",
}


def score_to_status(score: float, cfg: Dict[str, Any]) -> str:
    t = cfg["status_thresholds"]
    if score >= float(t["SEVERE_UNWIND"]): return "SEVERE_UNWIND"
    if score >= float(t["ACTIVE_UNWIND"]): return "ACTIVE_UNWIND"
    if score >= float(t["WATCH"]):         return "WATCH"
    if score >= float(t["LOW"]):           return "LOW"
    return "CALM"


def score_to_confidence(score: float, cfg: Dict[str, Any]) -> str:
    t = cfg["confidence_thresholds"]
    if score >= float(t["HIGH"]):   return "HIGH"
    if score >= float(t["MEDIUM"]): return "MEDIUM"
    if score >= float(t["LOW"]):    return "LOW"
    return "UNKNOWN"


def get_cio_action(status: str, confidence: str, cfg: Dict[str, Any]) -> str:
    action_map = cfg.get("cio_action_map", {})
    key = f"{status}_{confidence}"
    return action_map.get(key, action_map.get("UNKNOWN", "CIO_REVIEW_REQUIRED"))


# ── Output Builder ────────────────────────────────────────────────────────────

def build_output(
    cfg:               Dict[str, Any],
    total_score:       float,
    status:            str,
    confidence:        str,
    cio_action:        str,
    add_allowed:       bool,
    basket_signals:    Dict[str, str],
    primary_signals:   List[Dict[str, Any]],
    ticker_evidence:   List[Dict[str, Any]],
    headline_score:    float,
    headline_evidence: List[Dict[str, Any]],
    external_evidence: List[Dict[str, Any]],
    calm_offset_applied: float,
    blind_spots:       List[str],
    now_sgt:           datetime,
    data_quality:      str,
    market_status_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the canonical JSON output dict."""
    safety     = cfg["safety"]
    risk_level = _STATUS_TO_RISK.get(status, "UNKNOWN")

    # Ticker-level counts (not basket-level)
    stress_count = sum(1 for t in ticker_evidence if t.get("signal") == "STRESS")
    watch_count  = sum(1 for t in ticker_evidence if t.get("signal") == "WATCH")
    calm_count   = sum(1 for t in ticker_evidence if t.get("signal") == "CALM")

    # Summary line
    top_stress = [p["label"] for p in primary_signals if p["signal"] == "STRESS"]
    if status in ("SEVERE_UNWIND", "ACTIVE_UNWIND"):
        summary = f"Leverage unwind signal: {', '.join(top_stress) or 'multiple channels'}."
    elif status == "WATCH":
        summary = "Elevated leverage-unwind risk — monitoring multiple channels."
    elif status == "LOW":
        summary = "Low leverage-unwind signal — conditions mostly calm."
    else:
        summary = "No leverage-unwind signal detected — leveraged positions appear stable."

    return {
        # ── Identity ────────────────────────────────────────────────────────
        "schema_version":        cfg.get("schema_version", "thesis_widget_v1.1"),
        "thesis_id":             cfg["thesis_id"],
        "title":                 cfg.get("title", ""),
        # ── Scores & Status ─────────────────────────────────────────────────
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
        # ── Market Hours ────────────────────────────────────────────────────
        "market_open":           market_status_info.get("market_open", False),
        "market_status":         market_status_info.get("market_status", "UNKNOWN"),
        "market_time_et":        market_status_info.get("market_time_et", ""),
        "last_market_session":   market_status_info.get("last_market_session", ""),
        "data_freshness_label":  market_status_info.get("data_freshness_label", ""),
        # ── Evidence & Signals ───────────────────────────────────────────────
        "summary":               summary,
        "primary_signals":       primary_signals,
        "headline_score":        headline_score,
        "headline_evidence":     headline_evidence[:10],
        "ticker_evidence":       ticker_evidence,
        "external_evidence":     external_evidence,
        # ── Counts ──────────────────────────────────────────────────────────
        "stress_count":          stress_count,
        "watch_count":           watch_count,
        "calm_count":            calm_count,
        "pass_count":            calm_count,     # alias
        "fail_count":            stress_count,   # alias
        # ── Blind Spots ─────────────────────────────────────────────────────
        "blind_spots":           blind_spots,
        # ── Safety ──────────────────────────────────────────────────────────
        "execution_authority":   safety["execution_authority"],
        "order_routing_enabled": safety["order_routing_enabled"],
        "llm_order_generation":  safety["llm_order_generation"],
        "orders_generated":      0,
    }


# ── Main Compute Cycle ────────────────────────────────────────────────────────

def run_once(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute one full widget compute cycle.
    Returns the output dict.
    Degrades gracefully on any partial data failure.
    """
    now_utc = _utcnow()
    now_sgt = now_utc + timedelta(hours=8)

    log.info("=== Global Leverage Unwind Thesis Cycle ===")

    # ── Collect all yf_symbols to fetch ───────────────────────────────────
    all_yf_symbols: List[str] = list(cfg["benchmarks"])
    for basket_cfg in cfg["baskets"].values():
        if basket_cfg.get("enabled", True):
            for tk in basket_cfg["tickers"]:
                sym = tk["yf_symbol"]
                if sym not in all_yf_symbols:
                    all_yf_symbols.append(sym)
    log.info("Fetching %d symbols", len(all_yf_symbols))

    # ── Fetch prices ───────────────────────────────────────────────────────
    prices = fetch_prices(all_yf_symbols)
    available_count = sum(1 for p in prices.values() if p.get("available"))
    log.info("Price data: %d / %d symbols available", available_count, len(all_yf_symbols))

    # ── Benchmark changes ──────────────────────────────────────────────────
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

    # ── Score baskets ──────────────────────────────────────────────────────
    total_basket_score = 0.0
    basket_signals:  Dict[str, str]       = {}
    ticker_evidence: List[Dict[str, Any]] = []
    primary_signals_list: List[Dict]      = []

    for basket_id, basket_cfg in cfg["baskets"].items():
        if not basket_cfg.get("enabled", True):
            continue
        signal, b_score, rows = score_basket(
            basket_id, basket_cfg, prices, spy_chg, qqq_chg, cfg
        )
        basket_signals[basket_id]  = signal
        total_basket_score        += b_score
        ticker_evidence.extend(rows)
        primary_signals_list.append({
            "basket":         basket_id,
            "label":          basket_cfg.get("label", basket_id),
            "signal":         signal,
            "scoring_weight": basket_cfg["scoring_weight"],
            "basket_score":   round(b_score, 2),
        })
        log.info("[%s] signal=%s  score=%.2f / %s",
                 basket_id, signal, b_score, basket_cfg["scoring_weight"])

    # ── Headline scoring ───────────────────────────────────────────────────
    headline_score, headline_evidence = score_headlines(cfg)
    log.info("Headlines: %d matches → score %.1f / %s",
             len(headline_evidence), headline_score, cfg.get("headline_max_score", 15))

    # ── Calm offset ────────────────────────────────────────────────────────
    calm_offset_amt = compute_calm_offset(basket_signals, cfg)
    if calm_offset_amt > 0:
        log.info("Calm offset applied: -%.1f pts", calm_offset_amt)

    # ── Total score ────────────────────────────────────────────────────────
    total_score = max(0.0, min(100.0,
                               total_basket_score + headline_score - calm_offset_amt))
    log.info("Score: basket=%.1f + headline=%.1f - calm_offset=%.1f = total=%.1f",
             total_basket_score, headline_score, calm_offset_amt, total_score)

    # ── Status / confidence / CIO ──────────────────────────────────────────
    status     = score_to_status(total_score, cfg)
    confidence = score_to_confidence(total_score, cfg)
    cio_action = get_cio_action(status, confidence, cfg)
    add_allowed = (
        len(cfg.get("add_allowed_statuses", [])) > 0
        and status in cfg.get("add_allowed_statuses", [])
    )
    log.info("Status=%s  Confidence=%s  CIO=%s  AddAllowed=%s",
             status, confidence, cio_action, add_allowed)

    # ── Optional external evidence ─────────────────────────────────────────
    external_evidence = read_external_evidence(cfg)

    # ── Market hours ───────────────────────────────────────────────────────
    market_status_info = get_market_status(cfg)

    # ── Data quality ───────────────────────────────────────────────────────
    data_quality = "FULL" if available_count >= len(all_yf_symbols) else (
        "PARTIAL" if available_count > 0 else "UNAVAILABLE"
    )

    # ── Blind spots ────────────────────────────────────────────────────────
    blind_spots = list(cfg.get("blind_spots", []))

    # ── Assemble output ────────────────────────────────────────────────────
    output = build_output(
        cfg=cfg,
        total_score=total_score,
        status=status,
        confidence=confidence,
        cio_action=cio_action,
        add_allowed=add_allowed,
        basket_signals=basket_signals,
        primary_signals=primary_signals_list,
        ticker_evidence=ticker_evidence,
        headline_score=headline_score,
        headline_evidence=headline_evidence,
        external_evidence=external_evidence,
        calm_offset_applied=calm_offset_amt,
        blind_spots=blind_spots,
        now_sgt=now_sgt,
        data_quality=data_quality,
        market_status_info=market_status_info,
    )

    return output


# ── Persist & Push ────────────────────────────────────────────────────────────

def _load_env_token() -> str:
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("GITHUB_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def save_output(output: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """Write JSON to local file."""
    out_cfg  = cfg.get("output", {})
    local_dir  = _ROOT / out_cfg["local_dir"]
    local_file = out_cfg["local_file"]
    local_dir.mkdir(parents=True, exist_ok=True)
    path = local_dir / local_file
    path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("Saved locally: %s", path)


def push_to_github(output: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """Push JSON to GitHub Pages via Contents API."""
    import base64
    import urllib.request

    token = _load_env_token()
    if not token:
        log.warning("GITHUB_TOKEN not found — skipping GitHub push")
        return

    out_cfg     = cfg.get("output", {})
    github_path = out_cfg["github_path"]
    content     = json.dumps(output, indent=2, default=str).encode("utf-8")
    api_url     = f"https://api.github.com/repos/sohweekian/bluelotus/contents/{github_path}"
    headers     = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
    }

    # Get current SHA (for update) or None (first push)
    sha = None
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read())["sha"]
    except Exception:
        pass

    body: Dict[str, Any] = {
        "message": f"update(s8): global leverage unwind — {output.get('status', 'UNKNOWN')} {output.get('score', 0):.0f}/100",
        "content": base64.b64encode(content).decode(),
        "branch":  "main",
    }
    if sha:
        body["sha"] = sha

    req = urllib.request.Request(
        api_url, data=json.dumps(body).encode(), method="PUT", headers=headers
    )
    try:
        with urllib.request.urlopen(req) as r:
            resp_code = r.status
        log.info("GitHub push %s: OK (%d)", github_path, resp_code)
    except Exception as exc:
        log.error("GitHub push failed: %s", exc)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="BlueLotus V3 S8 Thesis Widget")
    parser.add_argument("--once", action="store_true", help="Run one cycle then exit")
    args = parser.parse_args()

    cfg = load_config()
    log.info("=" * 60)
    log.info("BlueLotus V3 — Global Leverage Unwind Thesis Widget")
    log.info("Config: %s", _CFG_PATH)
    log.info("Config loaded: thesis_id=%s  schema=%s",
             cfg.get("thesis_id"), cfg.get("schema_version"))
    log.info("Thesis  : %s", cfg.get("thesis_id"))
    log.info("Refresh : %d min", cfg.get("refresh_interval_seconds", 600) // 60)
    log.info("Baskets : %s", list(cfg["baskets"].keys()))
    log.info("=" * 60)

    cycle = 0
    while True:
        cycle += 1
        now_utc = _utcnow()
        log.info("── Cycle %d  %s UTC ──", cycle, now_utc.strftime("%H:%M:%S"))
        try:
            output = run_once(cfg)
            save_output(output, cfg)
            push_to_github(output, cfg)
            log.info("Cycle done — status=%s  score=%.1f  confidence=%s",
                     output.get("status"), output.get("score", 0), output.get("confidence"))
        except Exception as exc:
            log.error("Cycle error: %s", exc, exc_info=True)

        if args.once:
            log.info("--once flag set — exiting after cycle 1")
            break

        refresh_sec = cfg.get("refresh_interval_seconds", 600)
        log.info("Sleeping %d min until next cycle...", refresh_sec // 60)
        time.sleep(refresh_sec)


if __name__ == "__main__":
    main()
