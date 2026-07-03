r"""
================================================================================
  BlueLotus MID — Institutional Short Squeeze Probe v2.1 ALL-TICKERS
  probe_short_squeeze_institutional_v2_1_ALL_TICKERS.py

  Purpose:
    Upgrade the original snapshot probe into an institutional-style squeeze
    monitor using BlueLotus doctrine:

      1. Fuel first       — structural short pressure.
      2. Direction second — is pressure building or fading over time?
      3. Trigger third    — is the squeeze firing now?
      4. Catalyst fourth  — is there news forcing shorts to reprice?
      5. Risk last        — do not confuse squeeze potential with investment quality.

  Outputs:
    C:\bluelotus3\data\probe_short_squeeze_institutional_result.json
    C:\bluelotus3\reports\short_squeeze_watch_report.txt
    C:\bluelotus3\data\short_squeeze_history.json  (local time-series archive)

  Notes:
    - This file is safe to run repeatedly.
    - It appends lightweight squeeze snapshots to a local history JSON file.
    - If Moomoo / yfinance / dataset fields are unavailable, the probe degrades
      gracefully and marks missing inputs as UNKNOWN instead of inventing data.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Path handling — supports both local BlueLotus and sandbox review.
# -----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR).lower() == "mid" else r"C:\bluelotus3"

DEFAULT_DATASET_PATHS = [
    os.path.join(PROJECT_ROOT, "data", "frontend", "dataset_raw.json"),
    os.path.join(os.getcwd(), "data", "frontend", "dataset_raw.json"),
    "/mnt/data/dataset_raw.json",
]

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
REPORT_DIR = os.path.join(PROJECT_ROOT, "reports")
OUTPUT_JSON = os.path.join(DATA_DIR, "probe_short_squeeze_institutional_result.json")
OUTPUT_REPORT = os.path.join(REPORT_DIR, "short_squeeze_watch_report.txt")
HISTORY_JSON = os.path.join(DATA_DIR, "short_squeeze_history.json")

OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

DEFAULT_TICKERS = ["QBTS", "QUBT", "RGTI", "IONQ", "HOOD", "COIN", "RKLB"]

# BlueLotus governance exclusions / notes.
EXCLUDED_CRYPTO = {"COIN"}
OBSERVE_ONLY = set()

# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------

def now_sgt() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=8)


def ts_sgt_str() -> str:
    return now_sgt().strftime("%Y-%m-%d %H:%M:%S SGT")


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null", "n/a"}:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100.0, 2)


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def load_json(path: str, default: Any) -> Any:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)


def find_dataset_path(explicit: Optional[str] = None) -> Optional[str]:
    candidates = [explicit] if explicit else []
    candidates += DEFAULT_DATASET_PATHS
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def text_of(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (str, int, float, bool)):
        return str(x)
    if isinstance(x, dict):
        keys = ["headline", "title", "summary", "text", "message", "source", "ticker", "tickers", "theme", "published", "received_at"]
        return " ".join(text_of(x.get(k)) for k in keys if k in x)
    if isinstance(x, list):
        return " ".join(text_of(i) for i in x[:20])
    return str(x)


def recursively_collect_text_items(obj: Any, max_items: int = 5000) -> List[str]:
    out: List[str] = []

    def walk(v: Any) -> None:
        if len(out) >= max_items:
            return
        if isinstance(v, dict):
            s = text_of(v)
            if len(s) > 20:
                out.append(s)
            for vv in v.values():
                walk(vv)
        elif isinstance(v, list):
            for vv in v:
                walk(vv)
        elif isinstance(v, str) and len(v) > 20:
            out.append(v)

    walk(obj)
    return out


# -----------------------------------------------------------------------------
# Data source functions
# -----------------------------------------------------------------------------

def load_dataset(path: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    ds_path = find_dataset_path(path)
    if not ds_path:
        return None, {}
    try:
        with open(ds_path, "r", encoding="utf-8") as f:
            return ds_path, json.load(f)
    except Exception:
        return ds_path, {}


def get_live_from_dataset(dataset: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    live = dataset.get("live_prices") or dataset.get("prices") or {}
    if isinstance(live, dict):
        return live.get(ticker, {}) or live.get(f"US.{ticker}", {}) or {}
    return {}


def normalize_ticker_symbol(x: Any) -> Optional[str]:
    """Return a clean US-style ticker, or None if the string is not a ticker."""
    if x is None:
        return None
    s = str(x).strip().upper()
    if s.startswith("US."):
        s = s[3:]
    # Keep common US ticker formats. Avoid long words and source names.
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,5}", s):
        return None
    reject = {
        "USD", "SGT", "ETF", "RSS", "API", "NEWS", "TRUE", "FALSE", "NONE",
        "CALL", "PUT", "BUY", "SELL", "HOLD", "WAIT", "HIGH", "LOW", "OPEN",
        "CASH", "GOLD", "BANK", "VIX", "SPX", "DOW", "IPO", "CEO", "EPS",
        "PRICES", "PRICE", "SOURCE", "STALE", "FRESH", "ALL", "NONE", "NULL",
        "DATA", "TOTAL", "OPEN", "CLOSE", "HIGH", "LOW", "TRUE", "FALSE",
    }
    if s in reject:
        return None
    return s


def extract_all_tickers_from_dataset(dataset: Dict[str, Any]) -> List[str]:
    """
    Build the scan universe from dataset_raw.json instead of hardcoding quantum names.
    Priority: live_prices keys, then known ticker-bearing sections, then recursive ticker fields.
    """
    found: List[str] = []

    def add(x: Any) -> None:
        t = normalize_ticker_symbol(x)
        if t and t not in found:
            found.append(t)

    # 1) Most reliable: live_prices dictionary keys.
    live = dataset.get("live_prices") or dataset.get("prices") or {}
    if isinstance(live, dict):
        for k, v in live.items():
            # Add only actual price rows, not metadata keys inside the live_prices block.
            if isinstance(v, dict) and any(field in v for field in ("price", "prev_close", "volume", "chg_pct", "pre_price")):
                add(k)

    # 2) Common structured sections.
    section_names = [
        "portfolio", "positions", "holdings", "watchlist", "analyst_targets",
        "fundamentals", "capital_flow", "ticker_sentiment", "earnings",
        "portfolio_catalyst_calendar", "catalyst_calendar",
    ]
    for name in section_names:
        section = dataset.get(name)
        if isinstance(section, dict):
            for k, v in section.items():
                add(k)
                if isinstance(v, dict):
                    for key in ("ticker", "symbol", "code"):
                        if key in v:
                            add(v.get(key))
        elif isinstance(section, list):
            for item in section:
                if isinstance(item, dict):
                    for key in ("ticker", "symbol", "code"):
                        if key in item:
                            add(item.get(key))

    # 3) Recursive fallback: only fields explicitly named ticker/symbol/code/tickers.
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, val in v.items():
                kl = str(k).lower()
                if kl in {"ticker", "symbol", "code"}:
                    add(val)
                elif kl == "tickers" and isinstance(val, list):
                    for t in val:
                        add(t)
                elif isinstance(val, (dict, list)):
                    walk(val)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    # Recursive fallback only if structured extraction failed or is clearly too small.
    # This prevents words such as SOURCE/STALE/ALL from noisy text fields polluting the universe.
    if len(found) < 20:
        walk(dataset)

    return found


def fetch_yfinance_short_and_volume(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    try:
        import yfinance as yf  # type: ignore
    except Exception as e:
        return {t: {"status": "ERROR", "error": f"yfinance unavailable: {e}"} for t in tickers}

    for ticker in tickers:
        item: Dict[str, Any] = {"status": "UNKNOWN"}
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            short_pct_raw = safe_float(info.get("shortPercentOfFloat"))
            short_pct = round(short_pct_raw * 100, 2) if short_pct_raw is not None and short_pct_raw <= 1.5 else short_pct_raw
            item.update({
                "short_pct_float": short_pct,
                "days_to_cover": safe_float(info.get("shortRatio")),
                "shares_short": safe_float(info.get("sharesShort")),
                "float_shares": safe_float(info.get("floatShares")),
                "status": "OK" if short_pct is not None else "NO_SHORT_DATA",
            })
            try:
                fi = tk.fast_info
                item["three_month_avg_volume"] = safe_float(getattr(fi, "three_month_average_volume", None))
                item["last_volume"] = safe_float(getattr(fi, "last_volume", None))
            except Exception as e:
                item["fast_info_error"] = str(e)

            # 20D / 60D average volume improves institutional rel-vol quality.
            try:
                hist = tk.history(period="3mo", interval="1d", auto_adjust=False)
                if hist is not None and not hist.empty and "Volume" in hist.columns:
                    vols = [safe_float(v) for v in hist["Volume"].tolist()]
                    vols = [v for v in vols if v is not None and v > 0]
                    if vols:
                        item["avg_volume_20d"] = round(sum(vols[-20:]) / min(20, len(vols)), 0)
                        item["avg_volume_60d"] = round(sum(vols[-60:]) / min(60, len(vols)), 0)
                        closes = [safe_float(v) for v in hist["Close"].tolist()] if "Close" in hist.columns else []
                        closes = [v for v in closes if v is not None and v > 0]
                        if len(closes) >= 4:
                            item["price_chg_3d"] = pct_change(closes[-1], closes[-4])
                        if len(closes) >= 6:
                            item["price_chg_5d"] = pct_change(closes[-1], closes[-6])
            except Exception as e:
                item["history_error"] = str(e)

        except Exception as e:
            item = {"status": "ERROR", "error": str(e)}
        results[ticker] = item
    return results


def fetch_moomoo_borrow(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    try:
        import moomoo as ft  # type: ignore
        import moomoo.common.ft_logger as _ftl  # type: ignore
        _ftl.logger.enable_console_log(False)
    except Exception as e:
        return {t: {"status": "ERROR", "error": f"moomoo unavailable: {e}"} for t in tickers}

    out: Dict[str, Dict[str, Any]] = {t: {"status": "NO_DATA"} for t in tickers}
    try:
        trd_ctx = ft.OpenSecTradeContext(
            filter_trdmarket=ft.TrdMarket.US,
            host=OPEND_HOST,
            port=OPEND_PORT,
            security_firm=ft.SecurityFirm.FUTUSG,
        )
        codes = [f"US.{t}" for t in tickers]
        ret, data = trd_ctx.get_margin_ratio(code_list=codes)
        trd_ctx.close()
        if ret != ft.RET_OK or data is None or getattr(data, "empty", True):
            for t in tickers:
                out[t] = {"status": "ERROR", "error": f"get_margin_ratio failed: ret={ret}, data={data}"}
            return out
        for _, row in data.iterrows():
            ticker = str(row.get("code", "")).replace("US.", "")
            out[ticker] = {
                "status": "OK",
                "is_short_permit": bool(row.get("is_short_permit")),
                "short_pool_remain": safe_float(row.get("short_pool_remain")),
                "short_fee_rate": safe_float(row.get("short_fee_rate")),
                "is_long_permit": bool(row.get("is_long_permit")),
            }
    except Exception as e:
        for t in tickers:
            out[t] = {"status": "ERROR", "error": str(e)}
    return out


def catalyst_score_from_dataset(dataset: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    if not dataset:
        return {"score": 0, "count": 0, "positive_count": 0, "negative_count": 0, "sample": []}

    items = recursively_collect_text_items(dataset, max_items=4000)
    ticker_re = re.compile(rf"(?<![A-Z]){re.escape(ticker)}(?![A-Z])", re.I)
    positive_words = re.compile(r"\b(rally|surge|jump|beat|raise|upgrade|contract|partnership|approval|ipo|launch|bullish|accumulate|buy|record|strong|rebound|squeeze)\b", re.I)
    negative_words = re.compile(r"\b(drop|fall|plunge|miss|cut|downgrade|lawsuit|probe|bearish|selloff|weak|delay|halt|risk|loss)\b", re.I)

    matched = []
    pos = neg = 0
    for s in items:
        if ticker_re.search(s):
            clean = re.sub(r"\s+", " ", s).strip()
            matched.append(clean[:220])
            if positive_words.search(clean):
                pos += 1
            if negative_words.search(clean):
                neg += 1
            if len(matched) >= 12:
                break

    # Score only modestly; headline matching is context, not proof.
    score = 0
    if pos >= 5:
        score = 20
    elif pos >= 3:
        score = 14
    elif pos >= 1:
        score = 8
    if neg >= pos and neg > 0:
        score = max(0, score - 6)
    return {"score": score, "count": len(matched), "positive_count": pos, "negative_count": neg, "sample": matched[:5]}


# -----------------------------------------------------------------------------
# Scoring functions
# -----------------------------------------------------------------------------

def score_short_pct(short_pct: Optional[float]) -> int:
    if short_pct is None:
        return 0
    if short_pct >= 50: return 40
    if short_pct >= 30: return 38
    if short_pct >= 20: return 30
    if short_pct >= 10: return 20
    if short_pct >= 5: return 10
    return 0


def score_dtc(dtc: Optional[float]) -> int:
    if dtc is None:
        return 0
    if dtc >= 10: return 25
    if dtc >= 7: return 22
    if dtc >= 5: return 18
    if dtc >= 3: return 10
    return 0


def score_short_change(chg: Optional[float]) -> int:
    if chg is None:
        return 5  # unknown but structurally neutral, not zeroed out
    if chg >= 25: return 15
    if chg >= 10: return 10
    if chg >= -5: return 5
    return 0


def score_borrow_fee(fee: Optional[float]) -> int:
    if fee is None:
        return 0
    if fee >= 100: return 10
    if fee >= 50: return 7
    if fee >= 20: return 4
    if fee >= 10: return 2
    return 0


def score_borrow_pool(pool: Optional[float], is_short_permit: Optional[bool]) -> int:
    # Pool=0 with shorting not permitted is ambiguous: could be no borrow supply or broker limitation.
    # Award limited stress points, but mark as ambiguous in diagnosis.
    if pool is None:
        return 0
    if pool <= 0:
        return 6 if is_short_permit is False else 10
    if pool < 100_000: return 8
    if pool < 1_000_000: return 5
    return 0


def score_relvol(relvol: Optional[float]) -> int:
    if relvol is None:
        return 0
    if relvol >= 10: return 30
    if relvol >= 5: return 25
    if relvol >= 3: return 18
    if relvol >= 2: return 10
    if relvol >= 1.5: return 5
    return 0


def score_price_momentum(price_chg: Optional[float], chg3d: Optional[float], chg5d: Optional[float]) -> int:
    score = 0
    if price_chg is not None:
        if price_chg >= 10: score += 20
        elif price_chg >= 5: score += 15
        elif price_chg >= 2: score += 8
        elif price_chg > 0: score += 4
    if chg3d is not None and chg3d > 5:
        score += 3
    if chg5d is not None and chg5d > 8:
        score += 2
    return min(score, 25)


def score_premarket(pre_chg: Optional[float]) -> int:
    if pre_chg is None:
        return 0
    if pre_chg >= 8: return 15
    if pre_chg >= 5: return 10
    if pre_chg >= 3: return 5
    return 0


def classify(score: float) -> str:
    if score >= 80: return "EXTREME"
    if score >= 60: return "HIGH"
    if score >= 40: return "MEDIUM"
    if score >= 20: return "LOW"
    return "MINIMAL"


def probability_label(prob: float) -> str:
    if prob >= 70: return "HIGH_PROBABILITY"
    if prob >= 50: return "ELEVATED_WATCH"
    if prob >= 30: return "MEDIUM_WATCH"
    if prob >= 15: return "LOW_WATCH"
    return "MINIMAL"


def derive_history_metrics(history: Dict[str, Any], ticker: str, current: Dict[str, Any]) -> Dict[str, Any]:
    records = history.get("records", {}).get(ticker, []) if isinstance(history, dict) else []
    prev = records[-1] if records else {}

    metrics = {
        "previous_snapshot_found": bool(prev),
        "short_pct_change_from_prev": pct_change(current.get("short_pct_float"), prev.get("short_pct_float")),
        "shares_short_change_from_prev": pct_change(current.get("shares_short"), prev.get("shares_short")),
        "borrow_fee_change_from_prev": pct_change(current.get("short_fee_rate"), prev.get("short_fee_rate")),
        "borrow_pool_change_from_prev": pct_change(current.get("short_pool_remain"), prev.get("short_pool_remain")),
        "price_change_from_prev_snapshot": pct_change(current.get("price"), prev.get("price")),
    }
    return metrics


def trend_score(metrics: Dict[str, Any]) -> int:
    score = 0
    si_chg = metrics.get("short_pct_change_from_prev")
    sh_chg = metrics.get("shares_short_change_from_prev")
    fee_chg = metrics.get("borrow_fee_change_from_prev")
    pool_chg = metrics.get("borrow_pool_change_from_prev")
    px_chg = metrics.get("price_change_from_prev_snapshot")

    if si_chg is not None:
        if si_chg >= 20: score += 25
        elif si_chg >= 10: score += 15
        elif si_chg >= 0: score += 5
        elif si_chg < -10: score -= 10
    elif sh_chg is not None:
        if sh_chg >= 20: score += 20
        elif sh_chg >= 10: score += 12
        elif sh_chg >= 0: score += 5

    if fee_chg is not None:
        if fee_chg >= 50: score += 20
        elif fee_chg >= 20: score += 10
        elif fee_chg >= 0: score += 3
    if pool_chg is not None:
        if pool_chg <= -50: score += 15
        elif pool_chg <= -20: score += 8
    if px_chg is not None and px_chg > 0:
        score += min(10, int(px_chg))
    return int(clamp(score, 0, 100))


# -----------------------------------------------------------------------------
# Main analysis
# -----------------------------------------------------------------------------

def analyze_ticker(
    ticker: str,
    dataset: Dict[str, Any],
    yf_data: Dict[str, Any],
    borrow_data: Dict[str, Any],
    history: Dict[str, Any],
) -> Dict[str, Any]:
    live = get_live_from_dataset(dataset, ticker)

    price = safe_float(live.get("price"))
    prev_close = safe_float(live.get("prev_close"))
    pre_price = safe_float(live.get("pre_price"))
    volume = safe_float(live.get("volume"))
    price_chg = safe_float(live.get("chg_pct"))
    if price_chg is None:
        price_chg = pct_change(price, prev_close)
    pre_chg = pct_change(pre_price, prev_close)

    avg20 = safe_float(yf_data.get("avg_volume_20d")) or safe_float(yf_data.get("three_month_avg_volume"))
    avg60 = safe_float(yf_data.get("avg_volume_60d")) or safe_float(yf_data.get("three_month_avg_volume"))
    relvol = round(volume / avg20, 2) if volume and avg20 and avg20 > 0 else None

    short_pct = safe_float(yf_data.get("short_pct_float"))
    dtc = safe_float(yf_data.get("days_to_cover"))
    shares_short = safe_float(yf_data.get("shares_short"))
    float_shares = safe_float(yf_data.get("float_shares"))

    fee = safe_float(borrow_data.get("short_fee_rate"))
    pool = safe_float(borrow_data.get("short_pool_remain"))
    is_short_permit = borrow_data.get("is_short_permit") if borrow_data.get("status") == "OK" else None

    current_snapshot = {
        "timestamp_sgt": ts_sgt_str(),
        "ticker": ticker,
        "short_pct_float": short_pct,
        "days_to_cover": dtc,
        "shares_short": shares_short,
        "float_shares": float_shares,
        "short_fee_rate": fee,
        "short_pool_remain": pool,
        "price": price,
        "price_chg_pct": price_chg,
        "volume": volume,
        "relvol": relvol,
    }
    hist_metrics = derive_history_metrics(history, ticker, current_snapshot)

    catalyst = catalyst_score_from_dataset(dataset, ticker)

    # Structural fuel score: 100 possible.
    si_score = score_short_pct(short_pct)
    dtc_score = score_dtc(dtc)
    si_chg_score = score_short_change(hist_metrics.get("short_pct_change_from_prev"))
    borrow_fee_score = score_borrow_fee(fee)
    pool_score = score_borrow_pool(pool, is_short_permit)
    structural_score = si_score + dtc_score + si_chg_score + borrow_fee_score + pool_score
    structural_score = int(clamp(structural_score))

    # Trigger score: 100 possible.
    relvol_score = score_relvol(relvol)
    momentum_score = score_price_momentum(price_chg, yf_data.get("price_chg_3d"), yf_data.get("price_chg_5d"))
    pre_score = score_premarket(pre_chg)
    volume_z_proxy = 10 if relvol and relvol >= 5 else (5 if relvol and relvol >= 3 else 0)
    catalyst_component = int(catalyst.get("score", 0))
    trigger_score = int(clamp(relvol_score + momentum_score + pre_score + volume_z_proxy + catalyst_component))

    t_score = trend_score(hist_metrics)

    # Composite: fuel dominates, but trigger and trend decide timing.
    composite = round(structural_score * 0.55 + trigger_score * 0.30 + t_score * 0.15, 1)

    # Convert to 7-day probability. This is a heuristic probability band, not a prediction guarantee.
    prob = 5 + composite * 0.65
    # If no live trigger, cap probability unless structural is very high.
    if trigger_score < 20 and structural_score < 70:
        prob = min(prob, 35)
    if price_chg is not None and price_chg < 0 and relvol is not None and relvol < 2:
        prob = min(prob, 30)
    if ticker in EXCLUDED_CRYPTO:
        prob = min(prob, 20)
    prob = round(clamp(prob, 0, 85), 1)

    # Classification logic.
    if structural_score >= 60 and trigger_score >= 50:
        status = "SQUEEZE_ACTIVE_CANDIDATE"
    elif structural_score >= 60 and trigger_score >= 25:
        status = "TRIGGER_FORMING"
    elif structural_score >= 60:
        status = "HIGH_FUEL_WATCH"
    elif structural_score >= 40 and trigger_score >= 25:
        status = "MEDIUM_FUEL_TRIGGER_WATCH"
    elif structural_score >= 40:
        status = "MONITOR"
    else:
        status = "BACKGROUND"

    if ticker in EXCLUDED_CRYPTO:
        governance = "EXCLUDED_CRYPTO"
    elif ticker in OBSERVE_ONLY:
        governance = "OBSERVE_ONLY"
    else:
        governance = "TRADE_OK"

    diagnostics: List[str] = []
    if short_pct is not None and short_pct >= 20:
        diagnostics.append(f"High short fuel: {short_pct:.2f}% of float shorted")
    elif short_pct is not None and short_pct >= 10:
        diagnostics.append(f"Moderate short fuel: {short_pct:.2f}% of float shorted")
    if dtc is not None and dtc < 3:
        diagnostics.append(f"Weak days-to-cover: {dtc:.2f}d; shorts can exit quickly if volume remains normal")
    if fee is not None and fee >= 20:
        diagnostics.append(f"Borrow stress: CTB {fee:.2f}%")
    if pool == 0:
        diagnostics.append("Borrow pool is zero; interpret carefully because broker may mark name non-shortable")
    if relvol is not None and relvol < 2:
        diagnostics.append(f"No volume trigger: rel-vol {relvol:.2f}x")
    if price_chg is not None and price_chg <= 0:
        diagnostics.append(f"No positive price trigger: {price_chg:.2f}%")
    if catalyst.get("positive_count", 0) > 0:
        diagnostics.append(f"Ticker catalyst/news mentions detected: {catalyst.get('positive_count')} positive-like")
    if governance != "TRADE_OK":
        diagnostics.append(f"Governance: {governance}")

    return {
        "ticker": ticker,
        "governance": governance,
        "status": status,
        "classification": {
            "structural_class": classify(structural_score),
            "trigger_class": classify(trigger_score),
            "trend_class": classify(t_score),
            "seven_day_probability_label": probability_label(prob),
        },
        "scores": {
            "structural_score": structural_score,
            "trigger_score": trigger_score,
            "trend_score": t_score,
            "composite_score": composite,
            "squeeze_probability_7d_pct": prob,
        },
        "structural_fuel": {
            "short_pct_float": short_pct,
            "days_to_cover": dtc,
            "shares_short": shares_short,
            "float_shares": float_shares,
            "component_scores": {
                "short_pct_float": si_score,
                "days_to_cover": dtc_score,
                "short_interest_change": si_chg_score,
                "borrow_fee": borrow_fee_score,
                "borrow_pool": pool_score,
            },
        },
        "borrow_stress": {
            "short_fee_rate": fee,
            "short_pool_remain": pool,
            "is_short_permit": is_short_permit,
            "borrow_status": borrow_data.get("status"),
        },
        "live_trigger": {
            "session": live.get("session"),
            "price": price,
            "prev_close": prev_close,
            "price_chg_pct": price_chg,
            "pre_price": pre_price,
            "pre_chg_pct": pre_chg,
            "volume": volume,
            "avg_volume_20d_or_3m": avg20,
            "avg_volume_60d_or_3m": avg60,
            "relvol": relvol,
            "price_chg_3d": yf_data.get("price_chg_3d"),
            "price_chg_5d": yf_data.get("price_chg_5d"),
        },
        "time_series_direction": hist_metrics,
        "catalyst_context": catalyst,
        "diagnostics": diagnostics,
    }


def update_history(history_path: str, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    history = load_json(history_path, {"version": "v2.1", "records": {}})
    if "records" not in history or not isinstance(history["records"], dict):
        history["records"] = {}
    for a in analyses:
        ticker = a["ticker"]
        rec = {
            "timestamp_sgt": ts_sgt_str(),
            "ticker": ticker,
            "short_pct_float": a["structural_fuel"].get("short_pct_float"),
            "days_to_cover": a["structural_fuel"].get("days_to_cover"),
            "shares_short": a["structural_fuel"].get("shares_short"),
            "float_shares": a["structural_fuel"].get("float_shares"),
            "short_fee_rate": a["borrow_stress"].get("short_fee_rate"),
            "short_pool_remain": a["borrow_stress"].get("short_pool_remain"),
            "price": a["live_trigger"].get("price"),
            "price_chg_pct": a["live_trigger"].get("price_chg_pct"),
            "volume": a["live_trigger"].get("volume"),
            "relvol": a["live_trigger"].get("relvol"),
            "structural_score": a["scores"].get("structural_score"),
            "trigger_score": a["scores"].get("trigger_score"),
            "composite_score": a["scores"].get("composite_score"),
            "squeeze_probability_7d_pct": a["scores"].get("squeeze_probability_7d_pct"),
            "status": a.get("status"),
        }
        history["records"].setdefault(ticker, []).append(rec)
        # Keep file small: last 120 snapshots per ticker.
        history["records"][ticker] = history["records"][ticker][-120:]
    history["last_updated_sgt"] = ts_sgt_str()
    history["note"] = "Local time-series archive for pressure direction; safe to rebuild if deleted."
    save_json(history_path, history)
    return history


def build_report(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("BLUELOTUS MID — INSTITUTIONAL SHORT SQUEEZE WATCH REPORT v2.0")
    lines.append("=" * 78)
    lines.append(f"Generated        : {result['timestamp_sgt']}")
    lines.append(f"Dataset Path     : {result.get('dataset_path') or 'NOT FOUND'}")
    lines.append(f"Tickers Scanned  : {len(result['analyses'])}")
    lines.append("Doctrine         : Fuel first. Direction second. Trigger third. Risk last.")
    lines.append("")
    lines.append("SUMMARY RANKING — 7D SHORT SQUEEZE PROBABILITY")
    lines.append("-" * 78)
    lines.append(f"{'Rank':<5}{'Ticker':<8}{'Prob':<8}{'Status':<28}{'Struct':<8}{'Trig':<8}{'Gov'}")
    for i, a in enumerate(result["analyses"], 1):
        s = a["scores"]
        lines.append(f"{i:<5}{a['ticker']:<8}{s['squeeze_probability_7d_pct']:<8}{a['status']:<28}{s['structural_score']:<8}{s['trigger_score']:<8}{a['governance']}")
    lines.append("")

    lines.append("CHIEF STRATEGIST VERDICT")
    lines.append("-" * 78)
    if result["analyses"]:
        top = result["analyses"][0]
        lines.append(f"Top watch candidate: {top['ticker']} — {top['classification']['seven_day_probability_label']} ({top['scores']['squeeze_probability_7d_pct']}%).")
    active = [a for a in result["analyses"] if a["status"] in {"SQUEEZE_ACTIVE_CANDIDATE", "TRIGGER_FORMING"}]
    if active:
        lines.append("Active/trigger-forming squeeze candidates exist. Confirm price + volume before execution.")
    else:
        lines.append("No active high-confidence squeeze trigger detected. Treat as watchlist screening, not a squeeze call.")
    lines.append("")

    lines.append("DETAILS")
    lines.append("-" * 78)
    for a in result["analyses"]:
        lines.append(f"\n{a['ticker']} — {a['status']} | {a['classification']['seven_day_probability_label']}")
        lines.append(f"  7D probability : {a['scores']['squeeze_probability_7d_pct']}%")
        lines.append(f"  Structural     : {a['scores']['structural_score']}/100 ({a['classification']['structural_class']})")
        lines.append(f"  Trigger        : {a['scores']['trigger_score']}/100 ({a['classification']['trigger_class']})")
        lines.append(f"  Trend          : {a['scores']['trend_score']}/100 ({a['classification']['trend_class']})")
        sf = a["structural_fuel"]
        lt = a["live_trigger"]
        bs = a["borrow_stress"]
        lines.append(f"  Short % float  : {sf.get('short_pct_float')}")
        lines.append(f"  Days to cover  : {sf.get('days_to_cover')}")
        lines.append(f"  CTB / pool     : {bs.get('short_fee_rate')}% / {bs.get('short_pool_remain')}")
        lines.append(f"  Price / RelVol : {lt.get('price_chg_pct')}% / {lt.get('relvol')}x")
        for d in a.get("diagnostics", [])[:6]:
            lines.append(f"    • {d}")
    lines.append("")
    lines.append("END OF SHORT SQUEEZE WATCH REPORT")
    lines.append("=" * 78)
    return "\n".join(lines)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    dataset_path, dataset = load_dataset(args.dataset)
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        universe_source = "manual --tickers"
    else:
        tickers = extract_all_tickers_from_dataset(dataset)
        universe_source = "dataset auto-universe"
        if not tickers:
            tickers = list(DEFAULT_TICKERS)
            universe_source = "fallback DEFAULT_TICKERS"

    if args.max_tickers and args.max_tickers > 0:
        tickers = tickers[:args.max_tickers]

    history_before = load_json(args.history, {"version": "v2.1", "records": {}})

    print("=" * 78)
    print("BlueLotus MID — Institutional Short Squeeze Probe v2.1 ALL-TICKERS")
    print(f"Timestamp: {ts_sgt_str()}")
    print(f"Universe : {universe_source}")
    print(f"Tickers  : {len(tickers)} scanned")
    print(f"List     : {', '.join(tickers[:30])}" + (" ..." if len(tickers) > 30 else ""))
    print("=" * 78)

    yf = fetch_yfinance_short_and_volume(tickers) if not args.no_yfinance else {t: {"status": "SKIPPED"} for t in tickers}
    borrow = fetch_moomoo_borrow(tickers) if not args.no_moomoo else {t: {"status": "SKIPPED"} for t in tickers}

    analyses = [analyze_ticker(t, dataset, yf.get(t, {}), borrow.get(t, {}), history_before) for t in tickers]
    analyses.sort(key=lambda a: a["scores"]["squeeze_probability_7d_pct"], reverse=True)

    result = {
        "probe": "probe_short_squeeze_institutional_v2_1_ALL_TICKERS.py",
        "version": "v2.1",
        "timestamp_sgt": ts_sgt_str(),
        "dataset_path": dataset_path,
        "method": {
            "doctrine": "Fuel first; direction second; trigger third; catalyst fourth; risk last.",
            "composite_formula": "0.55*structural_score + 0.30*trigger_score + 0.15*trend_score",
            "warning": "Heuristic screening model. Not a prediction guarantee and not investment advice.",
        },
        "inputs_status": {
            "dataset_loaded": bool(dataset),
            "universe_source": universe_source,
            "tickers_scanned": len(tickers),
            "yfinance_used": not args.no_yfinance,
            "moomoo_used": not args.no_moomoo,
            "history_path": args.history,
        },
        "analyses": analyses,
    }

    if not args.no_history:
        update_history(args.history, analyses)
        result["history_updated"] = True
    else:
        result["history_updated"] = False

    save_json(args.output_json, result)
    report = build_report(result)
    os.makedirs(os.path.dirname(args.output_report), exist_ok=True)
    with open(args.output_report, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print()
    print(f"JSON saved  : {args.output_json}")
    print(f"Report saved: {args.output_report}")
    if not args.no_history:
        print(f"History     : {args.history}")
    return result


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="BlueLotus institutional short squeeze probe v2.0")
    ap.add_argument("--tickers", default=None, help="Optional comma-separated ticker override. If omitted, scan all tickers discovered from dataset_raw.json.")
    ap.add_argument("--max-tickers", type=int, default=200, help="Optional safety cap. Default 200 for the capped BlueLotus universe; use 0 for no cap.")
    ap.add_argument("--dataset", default=None, help="Path to dataset_raw.json")
    ap.add_argument("--output-json", default=OUTPUT_JSON)
    ap.add_argument("--output-report", default=OUTPUT_REPORT)
    ap.add_argument("--history", default=HISTORY_JSON)
    ap.add_argument("--no-history", action="store_true", help="Do not append to local time-series history")
    ap.add_argument("--no-yfinance", action="store_true", help="Skip yfinance calls")
    ap.add_argument("--no-moomoo", action="store_true", help="Skip Moomoo borrow calls")
    return ap.parse_args()


if __name__ == "__main__":
    run(parse_args())

