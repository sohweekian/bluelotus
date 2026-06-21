#!/usr/bin/env python3
"""
BlueLotus V2 — Hawkish Warsh Thesis Engine
============================================
Thesis ID: THESIS-HAWKISH-WARSH-FED

Tracks whether hawkish Fed / Warsh policy posture is confirming or invalidating
the BlueLotus multi-asset thesis across:
  - Banks (NIM benefit vs credit risk)
  - Gold / Miners (safe-haven vs real-yield / USD headwind)
  - High-beta (capped under hawkish regime)
  - Yen carry (BOJ / carry-trade stability)

Config: news_probe_sources.json + .env — zero hardcoding.
Data:   headlines_live.json (Fed tone) + yfinance (market data)
Output: data/warsh_thesis/warsh_thesis_live.json -> pushed to GitHub Pages

Doctrine: System advises. CIO decides. CIO executes manually. System records.
Forbidden outputs: BUY / SELL / EXECUTE / ROUTE_ORDER
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_THIS_DIR     = Path(__file__).parent.resolve()
_PROJECT_ROOT = _THIS_DIR.parent
_HEADLINES_PATH  = _PROJECT_ROOT / "data" / "headlines_live.json"
_DATASET_PATH    = _PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
_OUTPUT_DIR      = _PROJECT_ROOT / "data" / "warsh_thesis"
_OUTPUT_PATH     = _OUTPUT_DIR / "warsh_thesis_live.json"

# ── Keyword dictionaries — edit here, not in scoring logic ───────────────────
HAWKISH_KEYWORDS: List[str] = [
    "inflation", "restrictive", "higher for longer", "not done", "vigilance",
    "price stability", "tight labor", "premature easing", "resilient economy",
    "hawkish", "rate hike", "hike rates", "tightening", "warsh",
    "hold rates", "no cuts", "above target", "overshoot",
    "balance sheet reduction", "qt", "quantitative tightening",
]
DOVISH_KEYWORDS: List[str] = [
    "rate cuts", "rate cut", "easing", "slowdown", "recession risk",
    "labor weakness", "accommodative", "disinflation", "policy relief",
    "cut rates", "dovish", "pause", "pivot", "loosen", "softening",
    "unemployment rising", "cooling inflation", "below target",
]

# ── Tickers needed — kept in engine (market data config, not business logic) ──
_WARSH_TICKERS: List[str] = [
    # Rates ETFs + yield proxies
    "TLT", "IEF", "SHY",
    "^TNX", "^TYX", "^IRX",
    # Dollar
    "UUP",
    # Banks
    "XLF", "JPM", "BAC", "WFC", "GS", "MS",
    # Credit
    "HYG", "JNK", "LQD",
    # Gold + Miners
    "GLD", "SLV", "GDX", "GDXJ", "AU", "NEM",
    # Broad market
    "SPY", "QQQ", "IWM",
    # Volatility
    "VXX", "UVXY",
    # High-beta portfolio positions
    "NVDA", "ASTS", "RKLB", "LUNR", "PL", "QBTS", "QUBT",
    # Yen carry
    "EWJ",
]

# ── Scoring weights (must sum to 100) ─────────────────────────────────────────
_WEIGHTS = {
    "fed_tone":     20,
    "rates":        15,
    "dollar":       10,
    "banks":        15,
    "gold_miners":  15,
    "high_beta":    10,
    "credit":       10,
    "yen_carry":     5,
}
assert sum(_WEIGHTS.values()) == 100, "Weights must sum to 100"

# ── Status thresholds ─────────────────────────────────────────────────────────
_STATUS_THRESHOLDS = [
    (80, "CONFIRMING"),
    (65, "PARTIAL_CONFIRMATION"),
    (50, "MIXED"),
    (35, "WARNING"),
    (0,  "FAILING"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(v: Any, default: float = 0.0) -> float:
    """Safe float with NaN guard."""
    try:
        r = float(v)
        return default if r != r else r
    except (TypeError, ValueError):
        return default


def _opt_f(v: Any) -> Optional[float]:
    """Safe optional float. Missing values remain None, never fake zero."""
    try:
        if v is None or str(v).strip() in ("", "N/A", "null", "None"):
            return None
        r = float(v)
        return None if r != r else r
    except (TypeError, ValueError):
        return None

def _now_sgt() -> str:
    sgt = timezone(timedelta(hours=8))
    return datetime.now(sgt).strftime("%Y-%m-%dT%H:%M:%S")

# ── Fed Tone Scanner ──────────────────────────────────────────────────────────

def scan_fed_tone(headlines_path: Path = _HEADLINES_PATH,
                  lookback_hours: int = 8) -> Dict[str, Any]:
    """
    Count hawkish vs dovish keywords across all sources in headlines_live.json.
    Returns status (HAWKISH/MIXED/DOVISH/UNKNOWN), score (0-20), and evidence.
    """
    try:
        data = json.loads(headlines_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("Headlines not found at %s — news daemon may not have run yet", headlines_path)
        return {"status": "UNKNOWN", "score": 10, "hawkish_count": 0,
                "dovish_count": 0, "evidence": ["News daemon offline — no headlines yet"]}
    except Exception as exc:
        log.warning("Cannot read headlines: %s", exc)
        return {"status": "UNKNOWN", "score": 10, "hawkish_count": 0,
                "dovish_count": 0, "evidence": [f"Headlines read error: {type(exc).__name__}"]}

    hawkish_count = 0
    dovish_count  = 0
    evidence: List[str] = []

    sources = data.get("sources", {})
    for src_id, src_data in sources.items():
        for item in (src_data.get("items") or []):
            text = (item.get("text") or "").lower()
            for kw in HAWKISH_KEYWORDS:
                if kw in text:
                    hawkish_count += 1
                    if len(evidence) < 4:
                        snippet = (item.get("text") or "")[:80]
                        evidence.append(f"[H] {kw!r} — {src_id}: {snippet}…")
            for kw in DOVISH_KEYWORDS:
                if kw in text:
                    dovish_count += 1
                    if len(evidence) < 8:
                        snippet = (item.get("text") or "")[:80]
                        evidence.append(f"[D] {kw!r} — {src_id}: {snippet}…")

    total = hawkish_count + dovish_count
    if total == 0:
        return {
            "status": "UNKNOWN", "score": 10,
            "hawkish_count": 0, "dovish_count": 0,
            "evidence": ["No Fed/macro keywords found in recent headlines — neutral assumed"],
        }

    ratio = hawkish_count / total
    if ratio >= 0.65:
        status, score = "HAWKISH", _WEIGHTS["fed_tone"]        # 20
    elif ratio >= 0.40:
        status, score = "MIXED",   round(_WEIGHTS["fed_tone"] * 0.6)  # 12
    else:
        status, score = "DOVISH",  round(_WEIGHTS["fed_tone"] * 0.15) # 3

    return {
        "status": status, "score": score,
        "hawkish_count": hawkish_count, "dovish_count": dovish_count,
        "evidence": evidence[:8],
    }

# ── Market Data Fetcher ───────────────────────────────────────────────────────

def fetch_market_data(tickers: Optional[List[str]] = None) -> Dict[str, Optional[float]]:
    """
    Fetch day-change % for all Warsh thesis tickers via yfinance.
    Returns {ticker_lower: chg_pct | None}.
    """
    tickers = tickers or _WARSH_TICKERS
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed")
        return {}
    try:
        raw = yf.download(
            tickers, period="2d", interval="1d",
            auto_adjust=True, progress=False, timeout=20,
        )
        closes = raw["Close"] if "Close" in raw else raw
        result: Dict[str, Optional[float]] = {}
        for t in tickers:
            try:
                col = closes[t] if t in closes.columns else None
                if col is None or len(col.dropna()) < 2:
                    result[t] = None
                    continue
                col = col.dropna()
                prev, curr = float(col.iloc[-2]), float(col.iloc[-1])
                result[t] = round((curr - prev) / prev * 100.0, 3) if prev else None
            except Exception:
                result[t] = None
        # Normalise keys: "^TNX" -> "tnx", "XLF" -> "xlf"
        return {k.lstrip("^").lower(): v for k, v in result.items()}
    except Exception as exc:
        log.error("yfinance fetch failed: %s", exc)
        return {}

# ── Individual Gate Scorers ───────────────────────────────────────────────────

def _load_dataset_treasury(dataset_path: Path = _DATASET_PATH) -> Dict[str, Any]:
    """Read current official Treasury levels from dataset_raw.json."""
    try:
        ds = json.loads(dataset_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Treasury dataset read failed: %s", exc)
        return {}
    treasury = ds.get("treasury_yields")
    return treasury if isinstance(treasury, dict) else {}


def _load_previous_macro_yields(current_snapshot_date: Any) -> Dict[str, Any]:
    """Read the prior official macro_yields row when MySQL is available."""
    if not current_snapshot_date:
        return {}
    try:
        try:
            from dotenv import load_dotenv
            load_dotenv(_PROJECT_ROOT / ".env", override=False)
        except Exception:
            pass
        import mysql.connector

        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", 3306)),
            user=os.getenv("MYSQL_USER") or os.getenv("DB_USER", ""),
            password=os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "bluelotus3"),
            charset="utf8mb4",
        )
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT snapshot_date, cycle_ts, yield_10y, yield_30y
            FROM macro_yields
            WHERE snapshot_date < %s
              AND yield_10y IS NOT NULL
              AND yield_30y IS NOT NULL
            ORDER BY snapshot_date DESC, cycle_ts DESC
            LIMIT 1
            """,
            (str(current_snapshot_date),),
        )
        row = cur.fetchone() or {}
        cur.close()
        conn.close()
        return dict(row)
    except Exception as exc:
        log.warning("Previous macro_yields read skipped: %s", exc)
        return {}


def enrich_market_data_with_treasury(md: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """
    Add official FRED Treasury level and delta fields.

    yfinance does not reliably return ^TNX/^TYX here. Missing yield proxies
    must stay None unless official FRED history can compute a real change.
    """
    enriched: Dict[str, Optional[float]] = dict(md)
    treasury = _load_dataset_treasury()
    current_date = treasury.get("snapshot_date")
    y10 = _opt_f(treasury.get("yield_10y"))
    y30 = _opt_f(treasury.get("yield_30y"))
    previous = _load_previous_macro_yields(current_date)
    p10 = _opt_f(previous.get("yield_10y"))
    p30 = _opt_f(previous.get("yield_30y"))

    if y10 is not None:
        enriched["us_10y_level"] = y10
    if y30 is not None:
        enriched["us_30y_level"] = y30
    if current_date:
        enriched["yield_snapshot_date"] = str(current_date)
    if previous.get("snapshot_date"):
        enriched["yield_previous_snapshot_date"] = str(previous.get("snapshot_date"))

    enriched["tnx"] = round(y10 - p10, 4) if y10 is not None and p10 is not None else enriched.get("tnx")
    enriched["tyx"] = round(y30 - p30, 4) if y30 is not None and p30 is not None else enriched.get("tyx")
    if enriched.get("tnx") is None:
        enriched["tnx"] = None
    if enriched.get("tyx") is None:
        enriched["tyx"] = None

    if (y10 is not None and p10 is not None) or (y30 is not None and p30 is not None):
        enriched["yield_delta_source"] = "FRED_DB_HISTORY"
    elif y10 is not None or y30 is not None:
        enriched["yield_delta_source"] = "FRED_LEVEL_ONLY"
    else:
        enriched["yield_delta_source"] = "UNAVAILABLE"
    return enriched


def _gate_fed_tone(fed: Dict[str, Any]) -> Tuple[str, float, Dict[str, Any]]:
    score = _f(fed.get("score"), 10.0)
    status = fed.get("status", "UNKNOWN")
    return status, score, {
        "status": status, "score": round(score, 1),
        "hawkish_count": fed.get("hawkish_count", 0),
        "dovish_count":  fed.get("dovish_count", 0),
        "evidence":      fed.get("evidence", []),
    }


def _gate_rates(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """0-15 pts. Yields rising + TLT falling = hawkish confirmation."""
    tlt = _f(md.get("tlt"))
    ief = _f(md.get("ief"))
    shy = _f(md.get("shy"))
    tnx = _opt_f(md.get("tnx"))    # 10Y yield percentage-point delta
    tyx = _opt_f(md.get("tyx"))    # 30Y yield percentage-point delta
    irx = _opt_f(md.get("irx"))    # short-term proxy
    y10_level = _opt_f(md.get("us_10y_level"))
    y30_level = _opt_f(md.get("us_30y_level"))

    score    = _WEIGHTS["rates"] * 0.5  # neutral = 7.5
    evidence = []

    # 10Y yield direction — hawkish if rising, recession signal if falling
    if tnx is not None and tnx > 0.03:
        score += 4
        evidence.append(f"10Y yield rising +{tnx:.3f} (hawkish rate confirmation)")
    elif tnx is not None and tnx < -0.03:
        score -= 5
        evidence.append(f"10Y yield falling {tnx:.3f} (recession / safety bid dominates)")
    elif tnx is None:
        evidence.append("10Y yield delta unavailable; using ETF rate proxies")

    # TLT price (inverse of rates) — falling = rates up = hawkish
    if tlt < -0.4:
        score += 2
        evidence.append(f"TLT {tlt:.1f}% (rate pressure active)")
    elif tlt > 0.6:
        score -= 3
        evidence.append(f"TLT +{tlt:.1f}% (safety bid overriding hawkish)")

    # Curve shape: short rates (IRX) vs long (TNX)
    if irx is not None and tnx is not None and irx > 0 and tnx > irx + 0.02:
        evidence.append("Long rates > short rates (curve steepening)")
    elif irx is not None and tnx is not None and irx > tnx + 0.05:
        score -= 1
        evidence.append("Short > long (inversion deepening — recession risk)")

    if y10_level is not None and y30_level is not None:
        evidence.append(f"FRED levels: 10Y {y10_level:.2f}%, 30Y {y30_level:.2f}%")

    score = max(0.0, min(float(_WEIGHTS["rates"]), score))
    status = "PASS" if score >= 10 else ("WATCH" if score >= 5 else "FAIL")
    return status, score, {
        "status": status, "score": round(score, 1),
        "tlt_change_pct": tlt, "ief_change_pct": ief, "shy_change_pct": shy,
        "us_10y_proxy": tnx, "us_30y_proxy": tyx,
        "us_10y_level": y10_level, "us_30y_level": y30_level,
        "yield_snapshot_date": md.get("yield_snapshot_date"),
        "yield_previous_snapshot_date": md.get("yield_previous_snapshot_date"),
        "yield_delta_source": md.get("yield_delta_source", "UNAVAILABLE"),
        "evidence": evidence,
    }


def _gate_dollar(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """0-10 pts. USD strength confirms hawkish posture."""
    uup = _f(md.get("uup"))

    score    = _WEIGHTS["dollar"] * 0.5  # neutral = 5
    evidence = []

    if uup > 0.4:
        score += 4
        evidence.append(f"UUP +{uup:.1f}% (USD strength — hawkish confirmed)")
    elif uup > 0.1:
        score += 1
        evidence.append(f"UUP +{uup:.1f}% (mild USD support)")
    elif uup < -0.6:
        score -= 4
        evidence.append(f"UUP {uup:.1f}% (USD weakening — hawkish signal contradicted)")
    elif uup < -0.2:
        score -= 2
        evidence.append(f"UUP {uup:.1f}% (USD soft)")

    score = max(0.0, min(float(_WEIGHTS["dollar"]), score))
    status = "PASS" if score >= 7 else ("WATCH" if score >= 4 else "FAIL")
    return status, score, {
        "status": status, "score": round(score, 1),
        "uup_change_pct": uup,
        "evidence": evidence,
    }


def _gate_banks(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """0-15 pts. Banks PASS only if stable/rising AND credit stays calm."""
    xlf = _f(md.get("xlf"))
    jpm = _f(md.get("jpm"))
    bac = _f(md.get("bac"))
    wfc = _f(md.get("wfc"))
    gs  = _f(md.get("gs"))
    ms  = _f(md.get("ms"))
    hyg = _f(md.get("hyg"))
    jnk = _f(md.get("jnk"))

    score    = _WEIGHTS["banks"] * 0.5   # neutral = 7.5
    evidence = []
    credit_stress = False

    # XLF direction (sector ETF — cleanest signal)
    if xlf > 0.6:
        score += 3
        evidence.append(f"XLF +{xlf:.1f}% (financials rally)")
    elif xlf > 0:
        score += 1
    elif xlf < -1.0:
        score -= 4
        evidence.append(f"XLF {xlf:.1f}% (financials sell off)")
    elif xlf < -0.3:
        score -= 2

    # Individual bank basket
    bank_vals = [v for v in [jpm, bac, wfc, gs, ms] if v is not None]
    if bank_vals:
        bank_avg = sum(bank_vals) / len(bank_vals)
        if bank_avg > 0.5:
            score += 2
            evidence.append(f"Bank basket avg +{bank_avg:.1f}% (names confirm)")
        elif bank_avg < -0.6:
            score -= 2
            evidence.append(f"Bank basket avg {bank_avg:.1f}% (names weak)")

    # Critical rule: hawkish is only good for banks if credit stays calm
    if hyg < -0.6 or jnk < -0.6:
        score -= 5
        credit_stress = True
        evidence.append(f"CREDIT STRESS: HYG {hyg:.1f}% JNK {jnk:.1f}% — bank thesis invalidated")
    elif hyg > 0 and jnk > 0:
        score += 1
        evidence.append(f"Credit calm: HYG +{hyg:.1f}% JNK +{jnk:.1f}%")

    score = max(0.0, min(float(_WEIGHTS["banks"]), score))
    status = "PASS" if score >= 10 else ("WATCH" if score >= 5 else "FAIL")
    return status, score, {
        "status": status, "score": round(score, 1),
        "xlf_change_pct": xlf,
        "jpm_change_pct": jpm, "bac_change_pct": bac,
        "wfc_change_pct": wfc, "gs_change_pct": gs, "ms_change_pct": ms,
        "credit_stress": credit_stress,
        "hyg_change_pct": hyg, "jnk_change_pct": jnk,
        "evidence": evidence,
    }


def _gate_gold_miners(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """
    0-15 pts. Gold miners PASS only if safe-haven demand beats real-yield + USD pressure.
    Hawkish Fed is NOT automatically bullish for gold miners.
    """
    gld  = _f(md.get("gld"))
    slv  = _f(md.get("slv"))
    gdx  = _f(md.get("gdx"))
    gdxj = _f(md.get("gdxj"))
    au   = _f(md.get("au"))
    nem  = _f(md.get("nem"))
    uup  = _f(md.get("uup"))
    tnx  = _f(md.get("tnx"))

    score    = _WEIGHTS["gold_miners"] * 0.5  # neutral = 7.5
    evidence = []

    # Gold itself — safe-haven active?
    if gld > 0.5:
        score += 3
        evidence.append(f"GLD +{gld:.1f}% (safe-haven demand active)")
    elif gld > 0:
        score += 1
    elif gld < -0.6:
        score -= 4
        evidence.append(f"GLD {gld:.1f}% (gold weakness — thesis stress)")

    # Miners vs GLD (must outperform or at least keep up)
    gdx_vs_gld = gdx - gld
    if gdx > 0 and gdxj > 0:
        if gdx_vs_gld >= -0.5:
            score += 3
            evidence.append(f"GDX +{gdx:.1f}% GDXJ +{gdxj:.1f}% (miners confirm gold)")
        else:
            score += 1
            evidence.append(f"GDX +{gdx:.1f}% but lags GLD by {-gdx_vs_gld:.1f}% (watch)")
    elif gdx < 0 and gld > 0:
        score -= 3
        evidence.append(f"GDX {gdx:.1f}% while GLD +{gld:.1f}% (miner divergence — WARNING)")
    elif gdx < -1.0:
        score -= 4
        evidence.append(f"GDX {gdx:.1f}% (miners breaking down)")

    # Portfolio positions
    miner_avg = (au + nem) / 2
    if miner_avg > 0.3:
        score += 2
        evidence.append(f"AU/NEM avg +{miner_avg:.1f}% (portfolio miners holding)")
    elif miner_avg < -0.5:
        score -= 2
        evidence.append(f"AU/NEM avg {miner_avg:.1f}% (portfolio miners weak)")

    # Real-yield / USD headwind — hawkish + USD surge + yield spike = miner risk
    if uup > 0.6 and tnx > 0.05:
        score -= 2
        evidence.append(f"UUP+TNX surge: real-yield + USD headwind for miners")
    elif uup > 0.4 and gld < 0:
        score -= 1
        evidence.append(f"USD strength + gold down = real-yield pressure")

    score = max(0.0, min(float(_WEIGHTS["gold_miners"]), score))
    status = "PASS" if score >= 10 else ("WATCH" if score >= 5 else "FAIL")
    return status, score, {
        "status": status, "score": round(score, 1),
        "gld_change_pct": gld, "slv_change_pct": slv,
        "gdx_change_pct": gdx, "gdxj_change_pct": gdxj,
        "au_change_pct": au, "nem_change_pct": nem,
        "gdx_vs_gld_spread": round(gdx_vs_gld, 3),
        "evidence": evidence,
    }


def _gate_high_beta(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """0-10 pts. High beta capped under hawkish regime. VXX/UVXY spikes are red flags."""
    qqq  = _f(md.get("qqq"))
    iwm  = _f(md.get("iwm"))
    spy  = _f(md.get("spy"))
    vxx  = _f(md.get("vxx"))
    uvxy = _f(md.get("uvxy"))
    nvda = _f(md.get("nvda"))
    asts = _f(md.get("asts"))
    rklb = _f(md.get("rklb"))

    score    = _WEIGHTS["high_beta"] * 0.5  # neutral = 5
    evidence = []
    red_flag = False

    # VXX — most critical
    if vxx > 5.0:
        score -= 6
        red_flag = True
        evidence.append(f"RED FLAG: VXX +{vxx:.1f}% (fear spike — no add)")
    elif vxx > 2.0:
        score -= 3
        evidence.append(f"VXX +{vxx:.1f}% (vol rising — caution)")
    elif vxx < 0:
        score += 2
        evidence.append(f"VXX {vxx:.1f}% (volatility calm)")

    # UVXY
    if uvxy > 8.0:
        score -= 4
        red_flag = True
        evidence.append(f"RED FLAG: UVXY +{uvxy:.1f}% (leveraged vol — REDUCE RISK)")
    elif uvxy > 4.0:
        score -= 2

    # QQQ / IWM
    if qqq < -1.0:
        score -= 2
        evidence.append(f"QQQ {qqq:.1f}% (tech selling under hawkish)")
    elif qqq > 1.0:
        score += 1

    # IWM vs SPY spread
    if spy > 0 and iwm < spy - 1.5:
        score -= 1
        evidence.append(f"IWM underperforms SPY by {spy-iwm:.1f}% (small-cap stress)")

    score = max(0.0, min(float(_WEIGHTS["high_beta"]), score))
    status = "PASS" if score >= 7 else ("WATCH" if score >= 3 else "FAIL")
    return status, score, {
        "status": status, "score": round(score, 1),
        "qqq_change_pct": qqq, "iwm_change_pct": iwm,
        "vxx_change_pct": vxx, "uvxy_change_pct": uvxy,
        "nvda_change_pct": nvda,
        "red_flag": red_flag,
        "evidence": evidence,
    }


def _gate_credit(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """0-10 pts. Credit calm = hawkish can proceed; credit stress = critical warning."""
    hyg = _f(md.get("hyg"))
    jnk = _f(md.get("jnk"))
    lqd = _f(md.get("lqd"))

    score    = _WEIGHTS["credit"] * 0.5  # neutral = 5
    evidence = []

    if hyg < -0.6 and jnk < -0.6:
        score -= 6
        status = "STRESS"
        evidence.append(f"CREDIT STRESS: HYG {hyg:.1f}% JNK {jnk:.1f}%")
    elif hyg < -0.25 or jnk < -0.25:
        score -= 3
        status = "WATCH"
        evidence.append(f"Credit softening: HYG {hyg:.1f}% JNK {jnk:.1f}%")
    elif hyg >= 0 and jnk >= 0:
        score += 4
        status = "CALM"
        evidence.append(f"Credit calm: HYG +{hyg:.1f}% JNK +{jnk:.1f}%")
    else:
        status = "WATCH"

    score = max(0.0, min(float(_WEIGHTS["credit"]), score))
    return status, score, {
        "status": status, "score": round(score, 1),
        "hyg_change_pct": hyg, "jnk_change_pct": jnk, "lqd_change_pct": lqd,
        "evidence": evidence,
    }


def _gate_yen_carry(md: Dict[str, Optional[float]]) -> Tuple[str, float, Dict[str, Any]]:
    """0-5 pts. Yen carry stability (EWJ as Nikkei proxy, VXX cross-confirm)."""
    ewj = _f(md.get("ewj"))
    vxx = _f(md.get("vxx"))
    hyg = _f(md.get("hyg"))

    score    = _WEIGHTS["yen_carry"] * 0.5  # neutral = 2.5
    evidence = []

    if ewj < -2.0:
        score -= 3
        status = "ACTIVE"
        evidence.append(f"EWJ {ewj:.1f}% (Japan/Nikkei weak — yen carry stress)")
    elif ewj < -0.5:
        score -= 1
        status = "WATCH"
        evidence.append(f"EWJ {ewj:.1f}% (Japan soft)")
    elif ewj >= 0:
        score += 1.5
        status = "LOW"
        evidence.append(f"EWJ +{ewj:.1f}% (Japan/carry stable)")
    else:
        status = "WATCH"

    # Cross-confirm: VXX spike + EWJ weak = carry unwind
    if vxx > 3.0 and ewj < 0:
        score -= 1.5
        if status == "WATCH":
            status = "ACTIVE"
        evidence.append(f"VXX +{vxx:.1f}% + EWJ {ewj:.1f}% — carry unwind signal")

    if ewj < -3.0 and vxx > 5.0:
        status = "SEVERE"
        score -= 1

    score = max(0.0, min(float(_WEIGHTS["yen_carry"]), score))
    return status, score, {
        "status": status, "score": round(score, 1),
        "ewj_change_pct": ewj, "vxx_change_pct": vxx,
        "evidence": evidence,
    }

# ── CIO Action Mapping ────────────────────────────────────────────────────────
# Forbidden: BUY / SELL / EXECUTE / ROUTE_ORDER
_CIO_MAP: Dict[str, str] = {
    "CONFIRMING":           "STAGED_REVIEW_ONLY",
    "PARTIAL_CONFIRMATION": "STAGED_REVIEW_ONLY",
    "MIXED":                "NO_ADD",
    "WARNING":              "NO_ADD",
    "FAILING":              "REDUCE_RISK_REVIEW",
    "INSUFFICIENT_DATA":    "NO_ADD",
}

# ── Main Thesis Builder ───────────────────────────────────────────────────────

def build_warsh_thesis(
    headlines_path: Path = _HEADLINES_PATH,
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Full thesis computation.  All gate scores are additive.
    Returns the complete JSON-serialisable output dict.
    """
    fed = scan_fed_tone(headlines_path)
    md  = enrich_market_data_with_treasury(fetch_market_data(tickers))

    if not md:
        return {
            "thesis_id":    "THESIS-HAWKISH-WARSH-FED",
            "generated_at": _now_sgt(),
            "status":       "INSUFFICIENT_DATA",
            "score":        0,
            "error":        "Market data unavailable (yfinance timeout or not installed)",
            "cio_action":   "NO_ADD",
            "blocked_actions": ["NO_ADD"],
            "notes": ["Market data fetch failed — standing by for next cycle"],
        }

    # Score all gates
    fed_st,    fed_sc,    fed_d    = _gate_fed_tone(fed)
    rates_st,  rates_sc,  rates_d  = _gate_rates(md)
    dollar_st, dollar_sc, dollar_d = _gate_dollar(md)
    banks_st,  banks_sc,  banks_d  = _gate_banks(md)
    gold_st,   gold_sc,   gold_d   = _gate_gold_miners(md)
    beta_st,   beta_sc,   beta_d   = _gate_high_beta(md)
    credit_st, credit_sc, credit_d = _gate_credit(md)
    yen_st,    yen_sc,    yen_d    = _gate_yen_carry(md)

    total = round(
        fed_sc + rates_sc + dollar_sc + banks_sc +
        gold_sc + beta_sc + credit_sc + yen_sc, 1
    )
    total = max(0.0, min(100.0, total))

    # Overall status
    status = "FAILING"
    for threshold, label in _STATUS_THRESHOLDS:
        if total >= threshold:
            status = label
            break

    # Build notes and blocked actions
    notes: List[str] = []
    blocked: List[str] = []

    vxx_v  = _f(md.get("vxx"))
    uvxy_v = _f(md.get("uvxy"))
    hyg_v  = _f(md.get("hyg"))
    jnk_v  = _f(md.get("jnk"))
    xlf_v  = _f(md.get("xlf"))
    gdx_v  = _f(md.get("gdx"))
    gld_v  = _f(md.get("gld"))
    ewj_v  = _f(md.get("ewj"))
    spy_v  = _f(md.get("spy"))
    iwm_v  = _f(md.get("iwm"))

    # Red flag checks (from spec §10)
    if vxx_v > 5.0:
        notes.append(f"RED FLAG: VXX +{vxx_v:.1f}% — no new entries")
        blocked.append("NO_ADD")
    if uvxy_v > 8.0:
        notes.append(f"RED FLAG: UVXY +{uvxy_v:.1f}% — reduce risk review")
        blocked.append("REDUCE_RISK_REVIEW")
    if hyg_v < -0.5 and _f(md.get("tnx")) > 0.03:
        notes.append(f"RED FLAG: HYG {hyg_v:.1f}% while yields rising — credit stress")
        blocked.append("NO_ADD")
    if xlf_v < -0.5 and fed_st == "HAWKISH":
        notes.append(f"RED FLAG: XLF {xlf_v:.1f}% despite hawkish signal — bank thesis stress")
    if gdx_v < -1.0 and gld_v > 0.3:
        notes.append(f"RED FLAG: GDX {gdx_v:.1f}% while GLD +{gld_v:.1f}% — miner divergence")
    if spy_v > 0 and iwm_v < spy_v - 1.5:
        notes.append(f"RED FLAG: IWM underperforms SPY by {spy_v-iwm_v:.1f}% — small-cap stress")
    if ewj_v < -2.0 and vxx_v > 3.0:
        notes.append(f"RED FLAG: Yen carry unwind signal (EWJ {ewj_v:.1f}%, VXX +{vxx_v:.1f}%)")
        blocked.append("NO_ADD")
    if banks_d.get("credit_stress"):
        notes.append("RED FLAG: Credit stress detected — hawkish-bank thesis invalidated")
        blocked.append("NO_ADD")

    # CIO action
    cio_action = _CIO_MAP.get(status, "NO_ADD")
    if "REDUCE_RISK_REVIEW" in blocked:
        cio_action = "REDUCE_RISK_REVIEW"

    return {
        "thesis_id":    "THESIS-HAWKISH-WARSH-FED",
        "generated_at": _now_sgt(),
        "status":       status,
        "score":        total,
        "fed_tone":                  fed_d,
        "rates_confirmation":        rates_d,
        "dollar_confirmation":       dollar_d,
        "bank_confirmation":         banks_d,
        "gold_miner_confirmation":   gold_d,
        "high_beta_risk":            beta_d,
        "credit_stress":             credit_d,
        "yen_carry_risk":            yen_d,
        "cio_action":                cio_action,
        "blocked_actions":           sorted(set(blocked)),
        "notes":                     notes,
    }


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("Running Warsh Thesis Engine — standalone test")
    result = build_warsh_thesis()
    print(json.dumps(result, indent=2))
