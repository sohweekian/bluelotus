#!/usr/bin/env python3
"""
thesis_probe_daemon.py — BlueLotus Thesis Evidence Probe v2.0
=============================================================
Fully independent 10-minute probe. No MySQL. No pipeline dependency.

  • Fetches live intraday prices via yfinance (single batch, 70+ tickers)
  • Runs 8-check Gold Safe-Haven Thesis Tracker against live prices
  • Runs standalone ECE (Event Correlation Engine) — 12 themes, ticker baskets
  • Evidence column shows per-ticker % changes + qualifying logic
  • Pushes data/thesis_evidence_live.json to GitHub Pages every 10 min

Run:
    python mid/thesis_probe_daemon.py

Stop:
    Ctrl-C
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import concurrent.futures

import feedparser
import requests
import yfinance as yf
from dotenv import load_dotenv

# ── Paths & env ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sohweekian")
GITHUB_REPO     = os.getenv("GITHUB_PAGES_REPO", "bluelotus")
GITHUB_BRANCH   = os.getenv("GITHUB_BRANCH", "main")

THESIS_JSON_PATH = "data/thesis_evidence_live.json"
DATASET_PATH     = BASE_DIR / "data" / "frontend" / "dataset_raw.json"

# ── Constants ────────────────────────────────────────────────────────────────
PROBE_SEC = 600   # 10 min

# ── Ticker universe ───────────────────────────────────────────────────────────
# Gold thesis tickers (for the 8-check model)
GOLD_TICKERS = [
    "GLD", "SLV", "GDX", "GDXJ",
    "AU", "NEM",
    "UUP", "TLT", "IEF",
    "SPY", "QQQ", "IWM", "VXX", "UVXY",
    "XLE", "^VIX",
]

# ECE theme definitions — basket of tickers per theme
ECE_THEMES: List[Dict[str, Any]] = [
    {
        "theme":   "MAG7 / BIG TECH",
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
        "tier":    "T1:EARNINGS/MACRO",
    },
    {
        "theme":   "CONSUMER TECH / APPLE",
        "tickers": ["AAPL", "NFLX", "SPOT", "SNAP", "PINS"],
        "tier":    "T1:EARNINGS/MACRO",
    },
    {
        "theme":   "OIL / GAS",
        "tickers": ["XLE", "XOM", "CVX", "COP", "OXY"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "QUANTUM",
        "tickers": ["QBTS", "IONQ", "RGTI", "QUBT", "IBM"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "AI / SEMIS",
        "tickers": ["NVDA", "AMD", "AVGO", "AMAT", "ARM", "SMCI"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "CLEAN ENERGY / SOLAR",
        "tickers": ["ENPH", "FSLR", "SEDG", "RUN", "PLUG"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "SPACE / DEFENSE",
        "tickers": ["ASTS", "RKLB", "LUNR", "PL", "SPCE", "LMT", "RTX"],
        "tier":    "T1:EARNINGS/MACRO",
    },
    {
        "theme":   "MACRO / FED",
        "tickers": ["SPY", "QQQ", "IWM"],
        "tier":    "T1:EARNINGS/MACRO",
    },
    {
        "theme":   "GOLD / SAFE HAVEN",
        "tickers": ["GLD", "GDX", "GDXJ", "AU", "NEM", "SLV"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "SOFTWARE / CYBER",
        "tickers": ["PANW", "CRWD", "FTNT", "ZS", "OKTA"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "BANKS / LIQUIDITY",
        "tickers": ["XLF", "JPM", "BAC", "GS", "MS"],
        "tier":    "T2:NEWS",
    },
    {
        "theme":   "EARNINGS CATALYST",
        "tickers": ["ORCL", "DAL", "FDX", "NKE", "ACN", "ADBE", "COST"],
        "tier":    "T1:EARNINGS/MACRO",
    },
]

# All unique tickers for one batched yfinance download
_ECE_TICKERS = sorted({t for th in ECE_THEMES for t in th["tickers"]})
ALL_TICKERS  = sorted(set(GOLD_TICKERS + _ECE_TICKERS))

OIL_RSS_URL = (
    "https://news.google.com/rss/search"
    "?q=when:24h+site:reuters.com+commodities&ceid=US:en&hl=en-US&gl=US"
)
OIL_KEYWORDS = {
    "hormuz", "iran", "oil shock", "supply disruption", "tanker", "shipping",
    "opec", "crude", "brent", "wti", "sanctions", "war risk", "strait",
    "barrel", "petroleum", "energy supply",
}
RSS_HEADERS = {
    "User-Agent": "BlueLotus/2.0 (+https://sohweekian.github.io/bluelotus/)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "logs" / "thesis_probe.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("thesis_probe")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_to_sgt(dt_utc: datetime) -> str:
    return (dt_utc + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


# ── Live prices via yfinance (single batch) ───────────────────────────────────

def fetch_live_prices() -> Dict[str, Dict[str, Any]]:
    """
    Fetch intraday % change for ALL tickers (gold + ECE) in one yfinance batch.
    chg_pct = (today's close - yesterday's close) / yesterday's close × 100
    """
    prices: Dict[str, Dict[str, Any]] = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(
                yf.download, ALL_TICKERS,
                period="2d", interval="1d",
                auto_adjust=True, progress=False, threads=True,
            )
            try:
                data = _fut.result(timeout=60)
            except concurrent.futures.TimeoutError:
                log.warning("yfinance: timed out after 60s — skipping prices this cycle")
                return prices

        if hasattr(data.columns, "levels"):
            close = data["Close"]
        else:
            close = data[["Close"]] if "Close" in data.columns else data

        for sym in ALL_TICKERS:
            col_sym = sym if sym in close.columns else None
            if col_sym is None:
                continue
            series = close[col_sym].dropna()
            if len(series) < 2:
                continue
            prev_close  = float(series.iloc[-2])
            today_close = float(series.iloc[-1])
            if prev_close == 0:
                continue
            chg_pct = round((today_close / prev_close - 1) * 100, 3)
            prices[sym] = {"price": round(today_close, 4), "chg_pct": chg_pct}

        log.info("yfinance: %d/%d tickers fetched", len(prices), len(ALL_TICKERS))
    except Exception as exc:
        log.warning("yfinance fetch error: %s", exc)
    return prices


# ── Oil news from Reuters RSS ─────────────────────────────────────────────────

def fetch_oil_news_count() -> Tuple[int, List[str]]:
    """Count oil-keyword headlines from Reuters Commodities RSS."""
    try:
        resp = requests.get(OIL_RSS_URL, headers=RSS_HEADERS, timeout=15)
        resp.raise_for_status()
        feed  = feedparser.parse(resp.text)
        count = 0
        headlines: List[str] = []
        for entry in feed.entries[:25]:
            title   = str(getattr(entry, "title",   "") or "").lower()
            summary = str(getattr(entry, "summary", "") or "").lower()
            if any(kw in title or kw in summary for kw in OIL_KEYWORDS):
                count += 1
                if len(headlines) < 3:
                    headlines.append(str(getattr(entry, "title", ""))[:80])
        log.info("Oil news: %d keyword hits", count)
        return count, headlines
    except Exception as exc:
        log.warning("Oil RSS failed: %s", exc)
        return 0, []


# ── Standalone ECE — Event Correlation Engine ─────────────────────────────────

def _classify_direction(avg_chg: float, n_pos: int, n_avail: int) -> str:
    """
    Classify basket direction from average % change and positive-ticker ratio.

    Thresholds (tuned to match V2 pipeline ECE output):
      avg >= +0.5% and >=60% pos  → RISK_ON
      avg >= +0.1%                → SELECTIVE_RISK_ON
      avg <  -0.5% and <=40% pos → RISK_OFF
      avg <  -0.1%                → SELECTIVE_RISK_OFF
      else                        → NEUTRAL
    """
    ratio_pos = n_pos / n_avail if n_avail else 0.5
    if avg_chg >= 0.5 and ratio_pos >= 0.6:
        return "RISK_ON"
    elif avg_chg >= 0.1:
        return "SELECTIVE_RISK_ON"
    elif avg_chg <= -0.5 and ratio_pos <= 0.4:
        return "RISK_OFF"
    elif avg_chg < -0.1:
        return "SELECTIVE_RISK_OFF"
    else:
        return "NEUTRAL"


def compute_ece_themes(prices: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Standalone Event Correlation Engine.
    For each theme: collect basket ticker changes, compute avg, classify direction.
    Evidence = per-ticker % changes (sorted by absolute move, largest first).
    Qualifying rule = "N/M pos · avg +X.XX%"
    """
    rows: List[Dict[str, Any]] = []

    for theme_def in ECE_THEMES:
        theme   = theme_def["theme"]
        tickers = theme_def["tickers"]
        tier    = theme_def["tier"]

        # Gather available ticker data
        ticker_data: List[Dict[str, Any]] = []
        for t in tickers:
            row = prices.get(t)
            if row and row.get("chg_pct") is not None:
                ticker_data.append({
                    "t":   t,
                    "chg": round(float(row["chg_pct"]), 2),
                    "px":  round(float(row.get("price", 0)), 2),
                })

        if not ticker_data:
            rows.append({
                "theme":           theme,
                "direction":       "WATCH",
                "basket_move":     0.0,
                "tickers":         [],
                "qualifying_rule": "No market data available",
                "tier":            tier,
                "n_pos":           0,
                "n_neg":           0,
                "n_avail":         0,
            })
            continue

        # Sort by absolute % move (largest first) for display impact
        ticker_data_display = sorted(ticker_data, key=lambda x: abs(x["chg"]), reverse=True)

        # Basket statistics
        chgs    = [td["chg"] for td in ticker_data]
        avg_chg = round(sum(chgs) / len(chgs), 3)
        n_pos   = sum(1 for c in chgs if c > 0)
        n_neg   = sum(1 for c in chgs if c < 0)
        n_avail = len(chgs)

        direction = _classify_direction(avg_chg, n_pos, n_avail)

        # Qualifying rule text shown below ticker chips
        sign = "+" if avg_chg >= 0 else ""
        qual = f"{n_pos}/{n_avail} pos · avg {sign}{avg_chg:.2f}%"

        rows.append({
            "theme":           theme,
            "direction":       direction,
            "basket_move":     avg_chg,
            "tickers":         ticker_data_display,
            "qualifying_rule": qual,
            "tier":            tier,
            "n_pos":           n_pos,
            "n_neg":           n_neg,
            "n_avail":         n_avail,
        })

    risk_off = sum(1 for r in rows if "OFF" in r["direction"])
    log.info("ECE: %d themes | %d RISK_OFF | %d RISK_ON",
             len(rows), risk_off, len(rows) - risk_off)
    return rows


# ── Live Market Regime (10-min, no pipeline dependency) ──────────────────────

def compute_live_regime(
    prices:   Dict[str, Dict[str, Any]],
    ece_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute a live market regime from three independent signals:
      1. Market momentum  — SPY + QQQ + IWM average % change   (-3 to +3)
      2. VIX level        — ^VIX price (index value)             (-2 to +2)
      3. ECE breadth      — risk_on themes minus risk_off themes (-3 to +3)

    Total score range: -8 to +8
    Regime thresholds:  >= 4 RISK ON | 2–3 MILD RISK ON | -1–1 NEUTRAL |
                        -3–-2 MILD RISK OFF | <= -4 RISK OFF
    """
    def _chg(sym: str) -> Optional[float]:
        row = prices.get(sym)
        return float(row["chg_pct"]) if row and row.get("chg_pct") is not None else None

    def _px(sym: str) -> Optional[float]:
        row = prices.get(sym)
        return float(row["price"]) if row and row.get("price") is not None else None

    score = 0
    basis_parts: List[str] = []
    n_components = 0

    # ── Component 1: Market momentum (SPY + QQQ + IWM) ───────────────────────
    spy_chg = _chg("SPY")
    qqq_chg = _chg("QQQ")
    iwm_chg = _chg("IWM")
    mkt_chgs = [c for c in [spy_chg, qqq_chg, iwm_chg] if c is not None]
    if mkt_chgs:
        avg_mkt = sum(mkt_chgs) / len(mkt_chgs)
        if   avg_mkt >= 1.5:   score += 3
        elif avg_mkt >= 0.5:   score += 2
        elif avg_mkt >= 0.15:  score += 1
        elif avg_mkt <= -1.5:  score -= 3
        elif avg_mkt <= -0.5:  score -= 2
        elif avg_mkt < -0.15:  score -= 1
        sign = "+" if avg_mkt >= 0 else ""
        basis_parts.append(f"MKT {sign}{avg_mkt:.1f}%")
        n_components += 1

    # ── Component 2: VIX level ────────────────────────────────────────────────
    vix_level = _px("^VIX")
    if vix_level is not None and vix_level > 0:
        if   vix_level < 15:  score += 2
        elif vix_level < 20:  score += 1
        elif vix_level < 25:  pass   # neutral band
        elif vix_level < 30:  score -= 1
        else:                 score -= 2
        basis_parts.append(f"VIX {vix_level:.1f}")
        n_components += 1

    # ── Component 3: ECE breadth ──────────────────────────────────────────────
    risk_on_n  = sum(1 for r in ece_rows
                     if r["direction"] in ("RISK_ON", "SELECTIVE_RISK_ON"))
    risk_off_n = sum(1 for r in ece_rows
                     if r["direction"] in ("RISK_OFF", "SELECTIVE_RISK_OFF"))
    if ece_rows:
        breadth = risk_on_n - risk_off_n
        if   breadth >= 8:  score += 3
        elif breadth >= 5:  score += 2
        elif breadth >= 2:  score += 1
        elif breadth <= -8: score -= 3
        elif breadth <= -5: score -= 2
        elif breadth <= -2: score -= 1
        basis_parts.append(f"ECE {risk_on_n}/{len(ece_rows)} ON")
        n_components += 1

    # ── Regime label & colour ─────────────────────────────────────────────────
    if   score >= 4:   regime = "RISK ON";       rc = "#4ade80"
    elif score >= 2:   regime = "MILD RISK ON";  rc = "#86efac"
    elif score >= -1:  regime = "NEUTRAL";       rc = "#fbbf24"
    elif score >= -3:  regime = "MILD RISK OFF"; rc = "#fca5a5"
    else:              regime = "RISK OFF";      rc = "#ff5566"

    sign         = "+" if score >= 0 else ""
    regime_short = f"{regime} ({sign}{score})"
    regime_emoji = "🔴" if "OFF" in regime else ("🟢" if "ON" in regime else "🟡")

    confidence = ("MEDIUM_HIGH" if n_components >= 3 else
                  "MEDIUM"      if n_components >= 2 else "LOW")

    log.info(
        "Live regime: %s | score=%+d | VIX=%.1f | ECE %d/%d ON | conf=%s",
        regime, score,
        vix_level or 0.0,
        risk_on_n, len(ece_rows),
        confidence,
    )

    return {
        "regime":         regime,
        "regime_score":   score,
        "regime_short":   regime_short,
        "regime_color":   rc,
        "regime_emoji":   regime_emoji,
        "confidence":     confidence,
        "basis":          " | ".join(basis_parts),
        "vix_level":      round(vix_level, 2) if vix_level else None,
        "spy_chg":        spy_chg,
        "qqq_chg":        qqq_chg,
        "iwm_chg":        iwm_chg,
        "ece_risk_on_n":  risk_on_n,
        "ece_risk_off_n": risk_off_n,
        "ece_total_n":    len(ece_rows),
    }


# ── Load gold-miner cluster weight (soft fallback from pipeline) ──────────────

def load_gm_cluster_weight() -> float:
    """Read gold-miner cluster weight from pipeline dataset if available."""
    try:
        if not DATASET_PATH.exists():
            return 0.0
        with open(DATASET_PATH, encoding="utf-8") as f:
            ds = json.load(f)
        cd  = (ds.get("consistency_discipline") or {})
        rc  = cd.get("report_control") or {}
        ot  = rc.get("operating_truth") or {}
        val = ot.get("gold_miner_cluster_pct")
        if val is not None:
            w = float(val)
            return w / 100.0 if w > 1.0 else w
    except Exception:
        pass
    return 0.0


# ── 8-Check Gold Thesis (standalone, no pipeline imports) ────────────────────

def _chk(status: str, score: float, evidence: str,
         interpretation: str, cio_implication: str) -> Dict[str, Any]:
    return {
        "status": status, "score": score, "evidence": evidence,
        "interpretation": interpretation, "cio_implication": cio_implication,
    }


def compute_gold_thesis(
    prices:         Dict[str, Dict[str, Any]],
    oil_news_count: int,
    oil_headlines:  List[str],
    gm_cluster_weight: float = 0.0,
) -> Dict[str, Any]:
    """
    Standalone 8-check Gold Safe-Haven Thesis Tracker.
    Runs purely from yfinance live prices — no pipeline or DB dependency.
    """
    def _c(sym: str) -> Optional[float]:
        row = prices.get(sym)
        return float(row["chg_pct"]) if row and row.get("chg_pct") is not None else None

    def _p(sym: str) -> Optional[float]:
        row = prices.get(sym)
        return float(row["price"]) if row and row.get("price") is not None else None

    def _sp(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return round(a - b, 3) if (a is not None and b is not None) else None

    gld_chg  = _c("GLD");  slv_chg  = _c("SLV")
    gdx_chg  = _c("GDX");  gdxj_chg = _c("GDXJ")
    au_chg   = _c("AU");   nem_chg  = _c("NEM")
    uup_chg  = _c("UUP");  tlt_chg  = _c("TLT")
    ief_chg  = _c("IEF");  spy_chg  = _c("SPY")
    vxx_chg  = _c("VXX");  uvxy_chg = _c("UVXY")
    xle_chg  = _c("XLE")
    gld_price = _p("GLD"); slv_price = _p("SLV")

    gsr_proxy = (round(gld_price / slv_price, 2)
                 if (gld_price and slv_price and slv_price > 0) else None)

    gdx_vs_gld  = _sp(gdx_chg,  gld_chg)
    gdxj_vs_gld = _sp(gdxj_chg, gld_chg)
    au_vs_gdx   = _sp(au_chg,   gdx_chg)
    nem_vs_gdx  = _sp(nem_chg,  gdx_chg)
    gdx_vs_spy  = _sp(gdx_chg,  spy_chg)

    checks: Dict[str, Any] = {}

    # ── CHECK 1: Gold spot stabilizes and rises ───────────────────────────────
    if gld_chg is None:
        checks["gold_stabilizes_and_rises"] = _chk("MISSING", 0.0,
            "GLD unavailable", "Cannot determine gold trend.",
            "Gold spot data unavailable — treat as uncertain.")
    elif gld_chg >= 0:
        checks["gold_stabilizes_and_rises"] = _chk("PASS", 1.0, f"GLD {gld_chg:+.2f}%",
            "Gold flat/positive — thesis supportive.",
            "Gold leg intact; monitor for continuation.")
    elif gld_chg >= -2.0:
        checks["gold_stabilizes_and_rises"] = _chk("WATCH", 0.5, f"GLD {gld_chg:+.2f}%",
            "Gold slightly negative — not yet breakdown.",
            "Monitor gold; no immediate action required.")
    else:
        checks["gold_stabilizes_and_rises"] = _chk("FAIL", 0.0, f"GLD {gld_chg:+.2f}%",
            "Gold materially negative — thesis weakening.",
            "Gold leg failing; review miner thesis immediately.")

    # ── CHECK 2: Silver confirms or GSR compresses ────────────────────────────
    if slv_chg is None or gld_chg is None:
        checks["silver_confirms_or_gsr_compresses"] = _chk("MISSING", 0.0,
            f"SLV={slv_chg}, GLD={gld_chg}, GSR={gsr_proxy}",
            "Silver or gold data unavailable.",
            "Cannot confirm precious metals breadth.")
    else:
        slv_vs_gld = round(slv_chg - gld_chg, 3)
        if slv_vs_gld >= 0:
            st, sc = "PASS", 1.0
            interp = "Silver outperforming gold — breadth confirming."
            cio    = "Precious metals broad confirmation; thesis strengthened."
        elif slv_vs_gld >= -1.0:
            st, sc = "WATCH", 0.5
            interp = "Silver tracking gold — neutral breadth."
            cio    = "Silver not diverging; wait for confirmation direction."
        else:
            st, sc = "FAIL", 0.0
            interp = "Silver sharply underperforming gold — breadth failing."
            cio    = "Silver weakness undermines thesis; watch for gold isolation."
        checks["silver_confirms_or_gsr_compresses"] = _chk(st, sc,
            f"SLV {slv_chg:+.2f}% | GLD {gld_chg:+.2f}% | SLV-GLD {slv_vs_gld:+.2f}% | GSR {gsr_proxy}",
            interp, cio)

    # ── CHECK 3: GDX/GDXJ stop underperforming GLD ───────────────────────────
    if gdx_vs_gld is None and gdxj_vs_gld is None:
        checks["miners_vs_gold"] = _chk("MISSING", 0.0,
            f"GDX={gdx_chg}, GDXJ={gdxj_chg}, GLD={gld_chg}",
            "Miner ETF data unavailable.", "Cannot assess miner-vs-gold confirmation.")
    else:
        best = max(s for s in [gdx_vs_gld, gdxj_vs_gld] if s is not None)
        ev   = " | ".join(filter(None, [
            f"GDX-GLD {gdx_vs_gld:+.2f}%"  if gdx_vs_gld  is not None else None,
            f"GDXJ-GLD {gdxj_vs_gld:+.2f}%" if gdxj_vs_gld is not None else None,
        ]))
        if best >= 0:
            checks["miners_vs_gold"] = _chk("PASS", 1.0, ev,
                "Miner ETFs confirming gold move — positive divergence.",
                "Miner ETF leg confirming; thesis intact.")
        elif best >= -1.0:
            checks["miners_vs_gold"] = _chk("WATCH", 0.5, ev,
                "Miners slightly behind gold — minor drag.",
                "Acceptable underperformance; monitor.")
        else:
            checks["miners_vs_gold"] = _chk("FAIL", 0.0, ev,
                "Miners materially underperforming gold — negative divergence.",
                "Miner ETF rejection; consider whether gold move is credible for equity miners.")

    # ── CHECK 4: AU/NEM outperform GDX ───────────────────────────────────────
    spreads_4 = [s for s in [au_vs_gdx, nem_vs_gdx] if s is not None]
    if not spreads_4:
        checks["au_nem_vs_gdx"] = _chk("MISSING", 0.0,
            f"AU={au_chg}, NEM={nem_chg}, GDX={gdx_chg}",
            "Portfolio miner data unavailable.", "Cannot assess portfolio expression quality.")
    else:
        avg4 = round(sum(spreads_4) / len(spreads_4), 3)
        ev   = " | ".join(filter(None, [
            f"AU-GDX {au_vs_gdx:+.2f}%"  if au_vs_gdx  is not None else None,
            f"NEM-GDX {nem_vs_gdx:+.2f}%" if nem_vs_gdx is not None else None,
        ]))
        if avg4 >= 0:
            checks["au_nem_vs_gdx"] = _chk("PASS", 1.0, ev,
                "Portfolio miners outperforming GDX — alpha captured.",
                "Portfolio selection alpha confirmed; maintain HOLD.")
        elif avg4 >= -1.0:
            checks["au_nem_vs_gdx"] = _chk("WATCH", 0.5, ev,
                "Portfolio miners slightly lagging GDX — marginal.",
                "Monitor relative performance; no immediate action.")
        else:
            checks["au_nem_vs_gdx"] = _chk("FAIL", 0.0, ev,
                "Portfolio miners materially underperforming GDX.",
                "Review AU/NEM thesis independently.")

    # ── CHECK 5: Real yields do not spike ─────────────────────────────────────
    bond_chgs = [c for c in [tlt_chg, ief_chg] if c is not None]
    rate_ev   = " | ".join(filter(None, [
        f"TLT {tlt_chg:+.2f}%" if tlt_chg is not None else None,
        f"IEF {ief_chg:+.2f}%" if ief_chg is not None else None,
    ])) or "No bond data"
    if not bond_chgs:
        checks["real_yields_do_not_spike"] = _chk("MISSING", 0.0, rate_ev,
            "Bond proxy data unavailable.", "Cannot assess rate pressure.")
    else:
        worst = min(bond_chgs)
        if worst >= 0:
            checks["real_yields_do_not_spike"] = _chk("PASS", 1.0, rate_ev,
                "Bonds flat/up — no yield spike; gold supportive.",
                "Rate environment not hostile to gold.")
        elif worst >= -1.0:
            checks["real_yields_do_not_spike"] = _chk("WATCH", 0.5, rate_ev,
                "Mild bond weakness — modest yield pressure, manageable.",
                "Gold can withstand mild yield rise.")
        else:
            checks["real_yields_do_not_spike"] = _chk("FAIL", 0.0, rate_ev,
                "Bonds selling off materially — real yield pressure rising.",
                "Rising real yields hostile to gold; thesis under rate pressure.")

    # ── CHECK 6: DXY does not surge ───────────────────────────────────────────
    if uup_chg is None:
        checks["dxy_does_not_surge"] = _chk("MISSING", 0.0, "UUP unavailable",
            "USD proxy unavailable.", "Cannot assess dollar headwind.")
    elif uup_chg <= 0.2:
        checks["dxy_does_not_surge"] = _chk("PASS", 1.0, f"UUP {uup_chg:+.2f}%",
            "Dollar flat/down — no USD headwind for gold.",
            "USD not pressuring gold; favourable environment.")
    elif uup_chg <= 0.7:
        checks["dxy_does_not_surge"] = _chk("WATCH", 0.5, f"UUP {uup_chg:+.2f}%",
            "Dollar modestly up — mild headwind.",
            "Moderate strengthening can dampen gold.")
    else:
        checks["dxy_does_not_surge"] = _chk("FAIL", 0.0, f"UUP {uup_chg:+.2f}%",
            "Dollar surging — significant gold headwind.",
            "Strong USD materially hostile to gold.")

    # ── CHECK 7: Oil-risk premium elevated ────────────────────────────────────
    xle_ev  = f"XLE {xle_chg:+.2f}%" if xle_chg is not None else "XLE unavailable"
    oil_ev  = f"{xle_ev} | Oil news hits: {oil_news_count}"
    if oil_headlines:
        oil_ev += f" | {oil_headlines[0][:60]}"
    if oil_news_count >= 2 and (xle_chg is None or xle_chg >= -1.0):
        checks["oil_risk_premium_elevated"] = _chk("PASS", 1.0, oil_ev,
            "Oil-risk news active and energy price holding — premium intact.",
            "Geopolitical oil-risk premium supports safe-haven gold thesis.")
    elif oil_news_count >= 1 or (xle_chg is not None and xle_chg >= 0):
        checks["oil_risk_premium_elevated"] = _chk("WATCH", 0.5, oil_ev,
            "Oil news present but limited, or price firm without news.",
            "Partial oil-risk premium — not fully validating macro thesis.")
    else:
        checks["oil_risk_premium_elevated"] = _chk("FAIL", 0.0, oil_ev,
            "No fresh oil-risk news and energy selling off.",
            "Oil-risk premium fading — reduces macro catalyst for gold.")

    # ── CHECK 8: Miners not liquidated as equity beta ─────────────────────────
    spreads_8  = [s for s in [au_vs_gdx, nem_vs_gdx] if s is not None]
    avg8       = sum(spreads_8) / len(spreads_8) if spreads_8 else 0.0
    vxx_rising = ((vxx_chg  is not None and vxx_chg  > 1.0) or
                  (uvxy_chg is not None and uvxy_chg > 1.5))
    miners_lag = gdx_vs_spy is not None and gdx_vs_spy < -2.0
    au_nem_lag = avg8 < -1.0 if spreads_8 else False
    liq_ev     = " | ".join(filter(None, [
        f"GDX {gdx_chg:+.2f}%"        if gdx_chg    is not None else None,
        f"SPY {spy_chg:+.2f}%"        if spy_chg    is not None else None,
        f"GDX-SPY {gdx_vs_spy:+.2f}%" if gdx_vs_spy is not None else None,
        f"VXX {vxx_chg:+.2f}%"        if vxx_chg    is not None else None,
    ])) or "Equity data unavailable"
    if gdx_vs_spy is None and spy_chg is None:
        checks["miners_not_liquidated_as_equity_beta"] = _chk("MISSING", 0.0, liq_ev,
            "Equity data unavailable.", "Cannot assess liquidation risk.")
    elif miners_lag and vxx_rising and au_nem_lag:
        checks["miners_not_liquidated_as_equity_beta"] = _chk("FAIL", 0.0, liq_ev,
            "Miners sharply lagging equities AND vol rising AND portfolio miners underperforming — liquidation pattern.",
            "Miners being sold as equity beta; gold thesis temporarily disconnected from miners.")
    elif gdx_vs_spy is not None and gdx_vs_spy >= 0:
        checks["miners_not_liquidated_as_equity_beta"] = _chk("PASS", 1.0, liq_ev,
            "Miners holding up or outperforming equities — not sold as beta.",
            "Miner/equity divergence positive; safe-haven function intact.")
    elif gdx_vs_spy is not None and gdx_vs_spy >= -2.0:
        checks["miners_not_liquidated_as_equity_beta"] = _chk("WATCH", 0.5, liq_ev,
            "Miners slightly lagging equities — within tolerable range.",
            "Watch for further divergence; not yet liquidation.")
    else:
        checks["miners_not_liquidated_as_equity_beta"] = _chk("WATCH", 0.5, liq_ev,
            "Partial data — cannot confirm or deny liquidation risk.",
            "Monitor miner-vs-equity spread.")

    # ── Scoring ───────────────────────────────────────────────────────────────
    available = [c for c in checks.values() if c["status"] != "MISSING"]
    score_sum = sum(c["score"] for c in available)
    n_avail   = len(available) if available else 1
    score     = round(score_sum / n_avail, 3)

    if   score >= 0.75: status = "CONFIRMING"
    elif score >= 0.50: status = "WATCH"
    elif score >= 0.30: status = "WARNING"
    else:               status = "FAILING"

    _CRITICAL = {
        "gold_stabilizes_and_rises", "au_nem_vs_gdx",
        "miners_not_liquidated_as_equity_beta", "miners_vs_gold",
        "real_yields_do_not_spike",
    }
    crit_fail = sum(1 for k, c in checks.items() if k in _CRITICAL and c["status"] == "FAIL")

    if status == "CONFIRMING":
        confidence = "HIGH" if crit_fail == 0 else "MEDIUM"
    elif status == "WATCH":
        confidence = "MEDIUM"
    elif status == "WARNING":
        confidence = "MEDIUM_LOW" if crit_fail >= 3 else "MEDIUM"
    else:
        confidence = "LOW"
    if score < 0.50 and confidence == "HIGH":
        confidence = "MEDIUM"
    if crit_fail >= 3 and confidence in ("HIGH", "MEDIUM_HIGH"):
        confidence = "MEDIUM"

    add_blocked = gm_cluster_weight >= 0.50 or status in ("WARNING", "FAILING")
    if   status == "CONFIRMING": core_action = "HOLD"
    elif status == "WATCH":      core_action = "HOLD / WAIT"
    elif status == "WARNING":    core_action = "HOLD / REVIEW"
    else:                        core_action = "REVIEW / REDUCE"

    pass_n  = sum(1 for c in checks.values() if c["status"] == "PASS")
    fail_n  = sum(1 for c in checks.values() if c["status"] == "FAIL")
    watch_n = sum(1 for c in checks.values() if c["status"] == "WATCH")
    miss_n  = sum(1 for c in checks.values() if c["status"] == "MISSING")

    log.info("Gold thesis: %s | score=%.3f | confidence=%s | P=%d W=%d F=%d M=%d",
             status, score, confidence, pass_n, watch_n, fail_n, miss_n)

    return {
        "status":                 status,
        "score":                  score,
        "max_score":              1.0,
        "n_available":            n_avail,
        "n_pass":                 pass_n,
        "n_watch":                watch_n,
        "n_fail":                 fail_n,
        "n_missing":              miss_n,
        "confidence":             confidence,
        "critical_fail_count":    crit_fail,
        "core_action":            core_action,
        "add_allowed":            not add_blocked,
        "gold_miner_cluster_pct": round(gm_cluster_weight * 100, 1),
        "checks":                 checks,
        "key_metrics": {
            "gld_chg_pct":    gld_chg,
            "slv_chg_pct":    slv_chg,
            "gdx_chg_pct":    gdx_chg,
            "gdxj_chg_pct":   gdxj_chg,
            "au_chg_pct":     au_chg,
            "nem_chg_pct":    nem_chg,
            "uup_chg_pct":    uup_chg,
            "tlt_chg_pct":    tlt_chg,
            "xle_chg_pct":    xle_chg,
            "spy_chg_pct":    spy_chg,
            "gsr_proxy":      gsr_proxy,
            "oil_news_count": oil_news_count,
            "gdx_vs_gld":     gdx_vs_gld,
            "gdx_vs_spy":     gdx_vs_spy,
        },
    }


# ── GitHub push ───────────────────────────────────────────────────────────────

def _gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def push_to_github(json_str: str) -> bool:
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping push")
        return False
    api_url = (
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}"
        f"/contents/{THESIS_JSON_PATH}"
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
        "message": f"thesis probe {datetime.now().strftime('%H:%M')}",
        "content": base64.b64encode(json_str.encode("utf-8")).decode("ascii"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(api_url, headers=_gh_headers(), json=payload, timeout=30)
        ok = r.status_code in {200, 201}
        log.info("GitHub push: %s (%d)", "OK" if ok else "FAIL", r.status_code)
        if not ok:
            log.warning("GitHub push body: %s", r.text[:200])
        return ok
    except Exception as exc:
        log.warning("GitHub push error: %s", exc)
        return False


# ── Probe cycle ───────────────────────────────────────────────────────────────

def run_probe() -> None:
    """One full thesis evidence probe cycle — fully independent of the V2 pipeline."""
    now_utc = _utcnow()
    now_sgt = _utc_to_sgt(now_utc)

    # Single batch yfinance download for all 70+ tickers
    prices = fetch_live_prices()

    # Oil news (for gold thesis check 7)
    oil_count, oil_heads = fetch_oil_news_count()

    # Gold-miner cluster weight (soft fallback from pipeline dataset if available)
    gm_weight = load_gm_cluster_weight()

    # Gold thesis (8-check standalone)
    gold_thesis = compute_gold_thesis(prices, oil_count, oil_heads, gm_weight)

    # ECE themes (fully standalone — no pipeline dependency)
    ece_rows = compute_ece_themes(prices)

    # Live regime (10-min, derived from VIX + ECE breadth + market momentum)
    live_regime = compute_live_regime(prices, ece_rows)

    # Top movers — all fetched tickers sorted by abs(chg_pct), largest first
    top_movers = sorted(
        [{"ticker": t, "chg_pct": v["chg_pct"], "price": v["price"]}
         for t, v in prices.items() if v.get("chg_pct") is not None],
        key=lambda x: abs(x["chg_pct"]),
        reverse=True,
    )[:15]

    # Market reference signals for the ref bar
    def _chg(sym: str) -> Optional[float]:
        return prices[sym]["chg_pct"] if sym in prices else None

    market_signals = {
        "spy_chg": _chg("SPY"),
        "qqq_chg": _chg("QQQ"),
        "gld_chg": _chg("GLD"),
        "tlt_chg": _chg("TLT"),
    }

    payload = {
        "generated_at":       now_sgt + " SGT",
        "probe_type":         "thesis_evidence_v2",
        "live_regime":        live_regime,
        "gold_thesis":        gold_thesis,
        "event_correlations": ece_rows,
        "correlations_as_of": now_sgt + " SGT",
        "top_movers":         top_movers,
        "market_signals":     market_signals,
    }
    push_to_github(json.dumps(payload, ensure_ascii=False, default=str))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
    log.info("=" * 60)
    log.info("BlueLotus Thesis Evidence Probe v2.0  [starting]")
    log.info("  Probe interval  : %d min", PROBE_SEC // 60)
    log.info("  All tickers     : %d  (gold + ECE)", len(ALL_TICKERS))
    log.info("  ECE themes      : %d", len(ECE_THEMES))
    log.info("  Pipeline dep.   : NONE (fully standalone)")
    log.info("  GitHub repo     : %s/%s (branch: %s)",
             GITHUB_USERNAME, GITHUB_REPO, GITHUB_BRANCH)
    log.info("=" * 60)

    cycle = 0
    while True:
        cycle += 1
        log.info("── Cycle %d  %s ───────────────────────────────────────",
                 cycle, datetime.now().strftime("%H:%M:%S"))
        try:
            run_probe()
        except Exception as exc:
            log.error("Cycle %d crashed: %s", cycle, exc, exc_info=True)
        log.info("Cycle %d done — sleeping %d min\n", cycle, PROBE_SEC // 60)
        time.sleep(PROBE_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped by user (Ctrl-C).")
        sys.exit(0)
