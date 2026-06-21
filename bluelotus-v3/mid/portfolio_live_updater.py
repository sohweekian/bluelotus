#!/usr/bin/env python3
"""
BlueLotus V2 — Portfolio Live Updater
======================================
Standalone hourly daemon.

Pulls live position data directly from Moomoo API.
Builds extended portfolio_live.json (KPIs + full positions).
Pushes to GitHub Pages.
Runs independently of dataset_raw.json and the full intelligence pipeline.

Config:  mid/news_probe_config.json       (portfolio_update_interval_seconds)
Thesis:  mid/portfolio_thesis_labels.json (ticker -> label mapping)
Creds:   .env                             (GitHub token, Moomoo host/port)

Execution authority: CIO_ONLY_MANUAL. No orders. No execution.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# ── Project root ──────────────────────────────────────────────────────────────
_THIS_DIR    = Path(__file__).parent.resolve()
_PROJECT_ROOT = _THIS_DIR.parent

load_dotenv(_PROJECT_ROOT / ".env")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PORTFOLIO-LIVE] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            _PROJECT_ROOT / "logs" / "portfolio_live_updater.log",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger(__name__)

# ── Config paths (all from env / registry — no hardcoding) ───────────────────
_PROBE_CFG_PATH   = _THIS_DIR / "news_probe_config.json"
_THESIS_CFG_PATH  = _THIS_DIR / "portfolio_thesis_labels.json"
_DATASET_RAW_PATH = _PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
_OUTPUT_PATH      = _PROJECT_ROOT / "data" / "portfolio_live" / "portfolio_live.json"

# GitHub from .env
_GH_TOKEN    = os.getenv("GITHUB_TOKEN", "")
_GH_USER     = os.getenv("GITHUB_USERNAME", "")
_GH_REPO     = os.getenv("GITHUB_PAGES_REPO", "")
_GH_BRANCH   = os.getenv("GITHUB_BRANCH", "main")
_GH_TARGET   = "data/portfolio_live.json"   # path on GitHub Pages repo

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_probe_cfg() -> Dict[str, Any]:
    try:
        return json.loads(_PROBE_CFG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not load probe config (%s) - using defaults", exc)
        return {}


def _load_thesis_labels() -> Dict[str, str]:
    try:
        raw = json.loads(_THESIS_CFG_PATH.read_text(encoding="utf-8"))
        return {str(k).upper(): str(v) for k, v in raw.get("labels", {}).items()}
    except Exception as exc:
        log.warning("Could not load thesis labels (%s) - all positions = WATCH", exc)
        return {}


def _load_stale_context() -> Dict[str, Any]:
    """Load regime/fear_greed/vix from dataset_raw.json as background context.
    These are allowed to be stale — positions are what we refresh hourly."""
    try:
        raw = json.loads(_DATASET_RAW_PATH.read_text(encoding="utf-8"))
        return {
            "regime":     raw.get("regime", {}),
            "fear_greed": raw.get("fear_greed", {}),
        }
    except Exception as exc:
        log.warning("Could not load stale context (%s) - using empty", exc)
        return {"regime": {}, "fear_greed": {}}


def _load_watchlist_config() -> Dict[str, Any]:
    """Load watchlist and sector groups from portfolio_thesis_labels.json."""
    try:
        raw = json.loads(_THESIS_CFG_PATH.read_text(encoding="utf-8"))
        return {
            "watchlist":      raw.get("watchlist", []),
            "sector_groups":  raw.get("sector_groups", {}),
        }
    except Exception as exc:
        log.warning("Could not load watchlist config (%s)", exc)
        return {"watchlist": [], "sector_groups": {}}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _money(v: Any) -> str:
    f = _safe_float(v)
    return f"${f:,.2f}"


def _pct_short(v: Any) -> str:
    f = _safe_float(v)
    sign = "+" if f >= 0 else ""
    return f"{sign}{f:.1f}%"


def _regime_color(regime_short: str) -> str:
    s = regime_short.upper()
    if "RISK OFF" in s or "OFF" in s:
        return "#ff5566"
    if "RISK ON" in s or "ON" in s:
        return "#4ade80"
    return "#fbbf24"


def _regime_emoji(regime_short: str) -> str:
    s = regime_short.upper()
    if "RISK OFF" in s or "OFF" in s:
        return "\U0001f534"   # 🔴
    if "RISK ON" in s or "ON" in s:
        return "\U0001f7e2"   # 🟢
    return "\U0001f7e1"       # 🟡


def _now_sgt() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ── Moomoo extraction ─────────────────────────────────────────────────────────

def _fetch_live_positions() -> Dict[str, Any]:
    """Call fetch_portfolio_readonly.fetch_moomoo_portfolio + build_snapshot.
    Opens OpenSecTradeContext, queries, then closes. Channel: 1 (brief)."""
    sys.path.insert(0, str(_THIS_DIR))
    from fetch_portfolio_readonly import fetch_moomoo_portfolio, build_snapshot
    raw  = fetch_moomoo_portfolio()
    snap = build_snapshot(raw)
    return snap


def _fetch_market_snapshot(tickers: List[str]) -> List[Dict[str, Any]]:
    """Fetch intraday quote snapshot for watchlist tickers via OpenQuoteContext.
    Opens context, queries, closes immediately. Channel: 1 (brief, sequential
    after TradeContext is already closed). Max concurrent channels from this
    module = 1 at any point in time."""
    if not tickers:
        return []
    try:
        import moomoo as ft
        import moomoo.common.ft_logger as ft_logger
        ft_logger.logger.enable_console_log(False)

        opend_host = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
        opend_port = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))

        # Prefix tickers with market code
        coded = [f"US.{t}" if not t.startswith("US.") else t for t in tickers]

        ctx = ft.OpenQuoteContext(host=opend_host, port=opend_port)
        try:
            ret, data = ctx.get_market_snapshot(coded)
        finally:
            ctx.close()   # Always close — never leave channel open

        if ret != ft.RET_OK:
            log.warning("get_market_snapshot failed: %s", data)
            return []

        rows = []
        for _, row in data.iterrows():
            code  = str(row.get("code", "")).replace("US.", "").strip().upper()
            price = _safe_float(row.get("last_price") or row.get("cur_price"))
            chg_r = _safe_float(row.get("change_rate"))   # already in %
            open_ = _safe_float(row.get("open_price"))
            high  = _safe_float(row.get("high_price"))
            low   = _safe_float(row.get("low_price"))
            vol   = _safe_float(row.get("volume"))
            rows.append({
                "ticker":    code,
                "price":     round(price, 2),
                "chg_pct":   round(chg_r, 2),
                "open":      round(open_, 2),
                "high":      round(high, 2),
                "low":       round(low, 2),
                "volume":    int(vol),
            })

        log.info("Market snapshot OK - %d tickers fetched", len(rows))
        return rows

    except Exception as exc:
        log.warning("Market snapshot failed (%s) - Top Movers will be empty", exc)
        return []


# ── Payload builder ───────────────────────────────────────────────────────────

def _compute_market_signals(
        market_snapshot: List[Dict[str, Any]],
        sector_groups: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Derive simple market interpretation signals from the live quote snapshot."""
    by_ticker: Dict[str, float] = {
        r["ticker"]: r["chg_pct"] for r in market_snapshot if r.get("ticker")
    }

    def _group_avg(tickers: List[str]) -> Optional[float]:
        vals = [by_ticker[t] for t in tickers if t in by_ticker]
        return round(sum(vals) / len(vals), 2) if vals else None

    def_grp    = sector_groups.get("DEFENSIVE", [])
    grow_grp   = sector_groups.get("GROWTH", [])
    def_avg    = _group_avg(def_grp)
    grow_avg   = _group_avg(grow_grp)

    # Sentiment: which basket is doing better?
    if def_avg is not None and grow_avg is not None:
        gap = grow_avg - def_avg
        if gap > 0.5:
            sentiment = "GROWTH_LEADS"
            sentiment_color = "#4ade80"
        elif gap < -0.5:
            sentiment = "DEFENSIVE_LEADS"
            sentiment_color = "#fbbf24"
        else:
            sentiment = "NEUTRAL"
            sentiment_color = "#94a3b8"
    else:
        sentiment = "INSUFFICIENT_DATA"
        sentiment_color = "#94a3b8"

    return {
        "spy_chg":         by_ticker.get("SPY"),
        "qqq_chg":         by_ticker.get("QQQ"),
        "iwm_chg":         by_ticker.get("IWM"),
        "tlt_chg":         by_ticker.get("TLT"),
        "gld_chg":         by_ticker.get("GLD"),
        "uup_chg":         by_ticker.get("UUP"),
        "defensive_avg":   def_avg,
        "growth_avg":      grow_avg,
        "sentiment":       sentiment,
        "sentiment_color": sentiment_color,
    }


def _build_payload(snap: Dict[str, Any], thesis_labels: Dict[str, str],
                   ctx: Dict[str, Any],
                   market_snapshot: Optional[List[Dict[str, Any]]] = None,
                   sector_groups: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    """Build the extended portfolio_live.json payload."""

    regime     = ctx.get("regime", {})
    fear       = ctx.get("fear_greed", {})

    cash        = _safe_float(snap.get("cash"))
    total_assets = _safe_float(snap.get("total_assets"))
    market_val   = _safe_float(snap.get("market_value") or snap.get("market_val") or snap.get("account_market_value"))
    total_pnl    = _safe_float(snap.get("total_pnl"))
    cash_pct     = (cash / total_assets * 100.0) if total_assets else 0.0
    total_cost   = _safe_float(snap.get("total_cost"))
    total_pnl_pct = (total_pnl / total_cost * 100.0) if total_cost else 0.0

    integrity_ok = not snap.get("integrity_flag", False)

    regime_short = str(regime.get("regime_short") or regime.get("regime") or "UNKNOWN")
    rc           = _regime_color(regime_short)
    score_str    = str(regime.get("score", "N/A"))
    vix_raw      = regime.get("vix_level")
    vix_str      = str(vix_raw) if vix_raw is not None else "N/A"
    fg_score     = fear.get("score", regime.get("fg_score", "N/A"))
    fg_label     = str(fear.get("label", fear.get("rating", "UNKNOWN"))).upper()
    fg_color     = "#4ade80" if _safe_float(fg_score) >= 55 else (
                   "#ff5566" if _safe_float(fg_score) <= 30 else "#fbbf24")
    cio_action   = "WAIT" if not integrity_ok else (
                   "WAIT / HOLD" if "RISK OFF" in regime_short.upper() else "HOLD / WAIT")

    pnl_color  = "#4ade80" if total_pnl >= 0 else "#ff5566"
    cash_color = "#4ade80" if cash_pct >= 30 else ("#fbbf24" if cash_pct >= 15 else "#ff5566")

    # ── Positions ─────────────────────────────────────────────────────────────
    raw_positions = snap.get("positions", {})
    positions_list: List[Dict[str, Any]] = []
    for ticker, p in raw_positions.items():
        thesis = thesis_labels.get(str(ticker).upper(), "WATCH")
        qty    = _safe_float(p.get("qty"))
        price  = _safe_float(p.get("price"))
        avg_raw = p.get("avg_price")
        if avg_raw is None:
            avg_raw = p.get("avg_cost")
        if avg_raw is None:
            avg_raw = p.get("average_cost")
        if avg_raw is None and qty:
            avg_raw = _safe_float(p.get("cost_basis")) / qty
        chg    = _safe_float(p.get("day_change_pct") or p.get("chg_pct"))
        unrl   = _safe_float(p.get("unrealized_pnl") or p.get("unrealized"))
        unrl_p = _safe_float(p.get("unrealized_pnl_pct") or p.get("unrealized_p"))
        positions_list.append({
            "ticker":       ticker,
            "qty":          round(qty, 0),
            "price":        round(price, 2),
            "avg_price":    round(_safe_float(avg_raw), 3) if avg_raw is not None else None,
            "avg_cost":     round(_safe_float(avg_raw), 3) if avg_raw is not None else None,
            "cost_basis":   round(_safe_float(p.get("cost_basis")), 2),
            "chg_pct":      round(chg, 2) if chg else None,
            "unrealized":   round(unrl, 2),
            "unrealized_p": round(unrl_p, 2),
            "thesis":       thesis,
        })

    # ── Top Movers (from market snapshot) ────────────────────────────────────
    snap_rows = market_snapshot or []
    top_movers: List[Dict[str, Any]] = []
    if snap_rows:
        sorted_rows = sorted(snap_rows, key=lambda r: abs(_safe_float(r.get("chg_pct"))),
                             reverse=True)
        top_movers = sorted_rows[:10]

    # ── Market signals (sector sentiment interpretation) ──────────────────────
    market_signals = _compute_market_signals(snap_rows, sector_groups or {})

    return {
        "generated_at":       _now_sgt(),
        "portfolio_updated_at": _now_sgt(),
        "source":             "moomoo_direct",
        # ── Regime context (from dataset_raw — may be up to one pipeline cycle stale) ──
        "regime_short":       regime_short,
        "regime_score":       score_str,
        "regime_color":       rc,
        "regime_emoji":       _regime_emoji(regime_short),
        "cio_action":         cio_action,
        "vix":                vix_str,
        "vix_alert":          _safe_float(vix_raw) > 20,
        "fg_score":           fg_score,
        "fg_label":           fg_label,
        "fg_color":           fg_color,
        # ── Live portfolio (from Moomoo direct) ──────────────────────────────
        "market_val":         round(market_val, 2),
        "market_val_fmt":     _money(market_val),
        "total_pnl":          round(total_pnl, 2),
        "total_pnl_pct":      round(total_pnl_pct, 3),
        "pnl_fmt":            _money(total_pnl),
        "pnl_color":          pnl_color,
        "cash":               round(cash, 2),
        "cash_fmt":           _money(cash),
        "cash_pct":           round(cash_pct, 2),
        "cash_pct_fmt":       f"{cash_pct:.1f}%",
        "cash_color":         cash_color,
        "integrity":          "PASS" if integrity_ok else "DATA WARNING",
        "integrity_color":    "#4ade80" if integrity_ok else "#ff5566",
        "positions":          positions_list,
        # ── Live market data ───────────────────────────────────────────────────
        "top_movers":         top_movers,
        "market_signals":     market_signals,
    }


# ── GitHub push ───────────────────────────────────────────────────────────────

def _github_push(content: str) -> bool:
    """Push portfolio_live.json to GitHub Pages repo."""
    if not all([_GH_TOKEN, _GH_USER, _GH_REPO]):
        log.warning("GitHub credentials missing - skipping push (set GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_PAGES_REPO in .env)")
        return False
    try:
        import urllib.request
        import urllib.error

        api_url = (
            f"https://api.github.com/repos/{_GH_USER}/{_GH_REPO}"
            f"/contents/{_GH_TARGET}"
        )
        headers = {
            "Authorization": f"token {_GH_TOKEN}",
            "Accept":        "application/vnd.github.v3+json",
            "Content-Type":  "application/json",
            "User-Agent":    "BlueLotusV2-PortfolioLive/1.0",
        }

        # Fetch current SHA
        sha: Optional[str] = None
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                existing = json.loads(resp.read().decode())
                sha = existing.get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

        body: Dict[str, Any] = {
            "message": f"portfolio live update {_now_sgt()}",
            "branch":  _GH_BRANCH,
            "content": base64.b64encode(content.encode("utf-8")).decode(),
        }
        if sha:
            body["sha"] = sha

        req = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
        log.info("GitHub push OK - HTTP %s -> %s", status, _GH_TARGET)
        return True

    except Exception as exc:
        log.error("GitHub push failed: %s", exc)
        return False


# ── Save locally ──────────────────────────────────────────────────────────────

def _save_local(payload_json: str) -> None:
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(payload_json, encoding="utf-8")
    log.info("Saved local copy -> %s", _OUTPUT_PATH)


# ── Single cycle ──────────────────────────────────────────────────────────────

def run_update() -> bool:
    log.info("--- Portfolio Live Update cycle starting ---")

    thesis_labels  = _load_thesis_labels()
    wl_cfg         = _load_watchlist_config()
    watchlist      = wl_cfg.get("watchlist", [])
    sector_groups  = wl_cfg.get("sector_groups", {})
    ctx            = _load_stale_context()

    # 1. Positions (TradeContext — opens then closes)
    try:
        snap = _fetch_live_positions()
        log.info("Moomoo extraction OK - %d positions, cash $%.2f, mkt $%.2f",
                 len(snap.get("positions", {})),
                 _safe_float(snap.get("cash")),
                 _safe_float(snap.get("market_value") or snap.get("market_val")))
    except Exception as exc:
        log.error("Moomoo extraction failed: %s", exc)
        return False

    # 2. Market snapshot (QuoteContext — sequential, TradeContext already closed)
    market_snapshot: List[Dict[str, Any]] = []
    if watchlist:
        market_snapshot = _fetch_market_snapshot(watchlist)
        log.info("Market snapshot - %d tickers returned", len(market_snapshot))

    payload = _build_payload(snap, thesis_labels, ctx,
                             market_snapshot=market_snapshot,
                             sector_groups=sector_groups)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

    _save_local(payload_json)
    ok = _github_push(payload_json)
    log.info("--- Cycle complete - GitHub push: %s ---", "OK" if ok else "FAILED")
    return ok


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    cfg      = _load_probe_cfg()
    interval = int(cfg.get("portfolio_update_interval_seconds", 3600))

    log.info("=" * 60)
    log.info("BlueLotus V3 - Portfolio Live Updater")
    log.info("Interval: %d seconds (%d min)", interval, interval // 60)
    log.info("Source:   Moomoo API (read-only)")
    log.info("Target:   GitHub Pages / data/portfolio_live.json")
    log.info("Execution authority: CIO_ONLY_MANUAL - no orders, no routing")
    log.info("=" * 60)

    consecutive_failures = 0
    while True:
        try:
            ok = run_update()
            consecutive_failures = 0 if ok else consecutive_failures + 1
        except Exception as exc:
            consecutive_failures += 1
            log.error("Unexpected error in cycle: %s", exc, exc_info=True)

        if consecutive_failures >= 5:
            log.critical("5 consecutive failures - check Moomoo connection and GitHub token")

        log.info("Sleeping %d seconds until next portfolio refresh...", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
