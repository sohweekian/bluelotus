#!/usr/bin/env python3
"""
BlueLotus V3 — BOJ / Yen Carry Event Watcher Engine
=====================================================
Thesis ID: THESIS-BOJ-YEN-CARRY-UNWIND

Tracks whether BOJ policy shifts and yen strengthening are triggering a
carry-trade unwind that threatens the BlueLotus multi-asset portfolio:
  - USD/JPY multi-timeframe breakdown (5m / 15m / 1h)
  - BOJ statement detection + hawkish/dovish tone parsing
  - Japan equity (EWJ / DXJ) selling off
  - Volatility spike (VXX / VIXY / UVXY)
  - US equity selling off (SPY / QQQ / IWM)
  - Credit weakening (HYG / JNK)
  - Portfolio high-beta liquidation

Config: news_probe_sources.json + .env — zero hardcoding.
Data:   headlines_live.json (BOJ tone) + yfinance (market + intraday)
Output: data/boj_yen_carry_live.json -> pushed to GitHub Pages

Doctrine: System advises. CIO decides. CIO executes manually. System records.
Forbidden outputs: BUY / SELL / EXECUTE / ROUTE_ORDER / CANCEL_ORDER
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_THIS_DIR     = Path(__file__).parent.resolve()
_PROJECT_ROOT = _THIS_DIR.parent
_HEADLINES_PATH = _PROJECT_ROOT / "data" / "headlines_live.json"
_HEADLINES_REMOTE = "https://sohweekian.github.io/bluelotus/data/headlines_live.json"
_OUTPUT_DIR     = _PROJECT_ROOT / "data"
_OUTPUT_PATH    = _OUTPUT_DIR / "boj_yen_carry_live.json"

# ── BOJ keyword dictionaries ──────────────────────────────────────────────────
BOJ_KEYWORDS: List[str] = [
    # English
    "boj", "bank of japan", "ueda", "uchida", "yen", "jpy", "usdjpy", "usd/jpy",
    "carry trade", "rate hike", "policy rate", "monetary policy", "jgb",
    "government bond", "intervention", "fx volatility", "yen-funded",
    "deleveraging", "japan rate", "boj hike", "boj hold", "boj rate",
    "nikkei", "topix", "yen strength", "yen weakness", "yen unwind",
    # Japanese — BOJ always announces in Japanese first; NHK/Jiji/Kyodo coverage
    # appears in Japanese 10-30 min before English wires translate.
    "日銀",        # Bank of Japan (short form)
    "日本銀行",    # Bank of Japan (formal)
    "植田",        # Ueda (BOJ Governor)
    "内田",        # Uchida (BOJ Deputy Governor)
    "金融政策",    # Monetary policy
    "政策金利",    # Policy rate
    "利上げ",      # Rate hike
    "利下げ",      # Rate cut
    "円高",        # Yen appreciation (= carry unwind risk)
    "円安",        # Yen depreciation
    "円相場",      # Yen exchange rate
    "為替",        # Foreign exchange
    "為替介入",    # FX intervention
    "円キャリー",  # Yen carry trade
    "キャリートレード",  # Carry trade
    "国債",        # Government bond (JGB)
    "日銀会合",    # BOJ meeting
    "金融政策決定会合",  # Monetary policy meeting
    "量的緩和",    # Quantitative easing
    "イールドカーブ",    # Yield curve
    "物価",        # Prices / CPI
    "インフレ",    # Inflation
]
BOJ_HAWKISH_KEYWORDS: List[str] = [
    # English
    "rate hike", "hike", "tightening", "hawkish", "inflation target",
    "wage growth", "above target", "reduce bond purchases", "bond tapering",
    "jgb tapering", "reduce jgb", "exit", "normalisation", "normalization",
    "policy shift", "unexpected hike", "surprise hike",
    # Japanese hawkish signals
    "利上げ",        # Rate hike
    "引き締め",      # Tightening
    "正常化",        # Normalization
    "タカ派",        # Hawkish
    "国債買い入れ縮小",  # Reduce JGB purchases
    "緩和縮小",      # Taper easing
    "政策転換",      # Policy shift/pivot
    "インフレ目標",  # Inflation target (hawkish context)
    "賃金上昇",      # Wage growth
    "物価上昇",      # Price rise
    "早期",          # Early (as in early rate hike)
    "想定外",        # Unexpected (surprise move)
]
BOJ_DOVISH_KEYWORDS: List[str] = [
    # English
    "hold", "steady", "unchanged", "dovish", "accommodative", "easing",
    "no change", "pause", "below target", "deflation risk", "maintain purchases",
    "bond buying", "yield curve control", "ycc", "priced in", "as expected",
    # Japanese dovish signals
    "据え置き",      # Hold / unchanged
    "現状維持",      # Status quo maintained
    "変更なし",      # No change
    "ハト派",        # Dovish
    "緩和継続",      # Continue easing
    "金融緩和",      # Monetary easing
    "維持",          # Maintain
    "緩和的",        # Accommodative
    "デフレ",        # Deflation
    "予想通り",      # As expected
    "市場予想",      # Market expectation (matched = dovish)
]

# ── Tickers needed ─────────────────────────────────────────────────────────────
_BOJ_TICKERS: List[str] = [
    "JPY=X",            # USD/JPY (falling = yen strengthening = carry unwind)
    "FXY",              # Yen ETF (inverse of USD/JPY, rising = yen up)
    "EWJ", "DXJ",       # Japan equity ETFs
    "VXX", "VIXY", "UVXY",  # Volatility
    "SPY", "QQQ", "IWM", "RSP",  # US equity
    "HYG", "JNK", "LQD", "AGG",  # Credit
    "XLF", "JPM", "BAC", "WFC", "GS", "MS",  # Banks
    "NVDA", "ASTS", "RKLB", "LUNR", "PL", "QBTS", "QUBT", "IONQ", "RGTI",  # High beta
    "GLD", "SLV", "GDX", "GDXJ", "AU", "NEM",  # Gold/miners
    "UUP",              # Dollar
]
_INTRADAY_TICKER = "JPY=X"  # For multi-timeframe USD/JPY analysis

# ── Scoring weights (must sum to 100) ─────────────────────────────────────────
_WEIGHTS = {
    "boj_statement":    15,   # BOJ official statement detected in headlines
    "boj_tone":         15,   # Hawkish/surprise tone vs expectations
    "usd_jpy":          20,   # Yen strength (JPY=X falling = yen up = risk)
    "japan_equity":     10,   # EWJ/DXJ selling off
    "volatility":       15,   # VXX/VIXY/UVXY rising
    "us_equity":        10,   # SPY/QQQ/IWM selling off
    "credit":           10,   # HYG/JNK weakening
    "high_beta":         5,   # Portfolio high-beta liquidation
}
assert sum(_WEIGHTS.values()) == 100, "Weights must sum to 100"

# ── Status thresholds ──────────────────────────────────────────────────────────
_STATUS_THRESHOLDS = [
    (75, "SEVERE"),
    (50, "ACTIVE"),
    (25, "WATCH"),
    (0,  "LOW"),
]

# ── CIO action mapping ────────────────────────────────────────────────────────
# Governance-permanently-blocked actions — always present regardless of status.
# These are NEVER allowed by any pipeline (CIO_ONLY_MANUAL enforced).
_GOVERNANCE_BLOCKED = ["BUY", "SELL", "EXECUTE", "ROUTE_ORDER", "CANCEL_ORDER"]

_CIO_MAP: Dict[str, Dict[str, Any]] = {
    "LOW":    {"cio_action": "WAIT",
               "blocked_actions": _GOVERNANCE_BLOCKED},
    "WATCH":  {"cio_action": "HOLD_HEDGE",
               "blocked_actions": _GOVERNANCE_BLOCKED + ["BLOCK_SECOND_TRANCHE"]},
    "ACTIVE": {"cio_action": "TAKE_PARTIAL_HEDGE_PROFIT_REVIEW",
               "blocked_actions": _GOVERNANCE_BLOCKED + ["BLOCK_SECOND_TRANCHE"]},
    "SEVERE": {"cio_action": "BLOCK_SECOND_TRANCHE",
               "blocked_actions": _GOVERNANCE_BLOCKED + ["BLOCK_SECOND_TRANCHE", "BLOCK_DCA", "BLOCK_HIGH_BETA_ADD"]},
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _f(v: Any, default: float = 0.0) -> float:
    """Safe float with NaN guard."""
    try:
        r = float(v)
        return default if r != r else r
    except (TypeError, ValueError):
        return default


def _now_sgt() -> str:
    sgt = timezone(timedelta(hours=8))
    return datetime.now(sgt).strftime("%Y-%m-%dT%H:%M:%S")


# ── USD/JPY Multi-Timeframe Intraday Fetcher ──────────────────────────────────

def fetch_usdjpy_intraday() -> Dict[str, Any]:
    """
    Fetch USD/JPY 1-minute intraday data and compute multi-timeframe changes.
    Returns dict with: price, change_5m_pct, change_15m_pct, change_1h_pct, breakdown_flag.

    INVERTED logic: JPY=X falling means yen STRENGTHENING = carry unwind risk.
    Negative pct = yen strengthening = elevated carry unwind signal.
    """
    result: Dict[str, Any] = {
        "price":           None,
        "change_5m_pct":   None,
        "change_15m_pct":  None,
        "change_1h_pct":   None,
        "breakdown_flag":  False,
        "data_source":     "intraday_1m",
        "note":            "",
    }
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed")
        result["note"] = "yfinance not installed"
        return result

    try:
        raw = yf.download(
            _INTRADAY_TICKER,
            period="1d",
            interval="1m",
            auto_adjust=True,
            progress=False,
            timeout=20,
        )
    except Exception as exc:
        log.warning("Intraday fetch failed for %s: %s", _INTRADAY_TICKER, exc)
        raw = None

    # Attempt intraday path
    if raw is not None and not raw.empty and len(raw) >= 2:
        try:
            closes = raw["Close"].squeeze() if "Close" in raw.columns else raw.iloc[:, 0].squeeze()
            closes = closes.dropna()
            if len(closes) >= 2:
                last_price = float(closes.iloc[-1].item() if hasattr(closes.iloc[-1], "item") else closes.iloc[-1])
                result["price"] = round(last_price, 4)

                def _pct_ago(n_bars: int) -> Optional[float]:
                    if len(closes) > n_bars:
                        _v = closes.iloc[-(n_bars + 1)]
                        ref = float(_v.item() if hasattr(_v, "item") else _v)
                        if ref and ref == ref:
                            return round((last_price / ref - 1.0) * 100.0, 4)
                    return None

                result["change_5m_pct"]  = _pct_ago(5)
                result["change_15m_pct"] = _pct_ago(15)
                # 1h cascade: try 60-bar, fall back to best available
                result["change_1h_pct"] = (
                    _pct_ago(60) or _pct_ago(45) or _pct_ago(30) or _pct_ago(15)
                )

                chg_1h = result["change_1h_pct"]
                if chg_1h is not None:
                    result["breakdown_flag"] = chg_1h < -0.5
                available_bars = len(closes)
                if available_bars < 61:
                    result["note"] = f"1h approx ({available_bars}min data)"
                result["data_source"] = "intraday_1m"
                return result
        except Exception as exc:
            log.warning("Intraday parse error: %s", exc)

    # Fallback: day change from daily data
    log.info("No intraday data — falling back to daily close for JPY=X")
    try:
        daily = yf.download(
            _INTRADAY_TICKER,
            period="2d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            timeout=20,
        )
        if daily is not None and not daily.empty:
            closes = daily["Close"] if "Close" in daily.columns else daily.iloc[:, 0]
            closes = closes.dropna()
            if len(closes) >= 2:
                prev  = float(closes.iloc[-2])
                curr  = float(closes.iloc[-1])
                day_pct = round((curr / prev - 1.0) * 100.0, 4) if prev else None
                result["price"]          = round(curr, 4)
                result["change_1h_pct"]  = day_pct   # best available proxy
                result["change_5m_pct"]  = None
                result["change_15m_pct"] = None
                if day_pct is not None:
                    result["breakdown_flag"] = day_pct < -0.5
                result["data_source"] = "daily_fallback"
                result["note"] = "Intraday unavailable — using daily close change as 1h proxy"
                return result
    except Exception as exc:
        log.warning("Daily fallback also failed: %s", exc)

    result["note"] = "All JPY=X data unavailable"
    return result


# ── BOJ Headline Scanner ───────────────────────────────────────────────────────

def scan_boj_headlines(
    headlines_path: Path = _HEADLINES_PATH,
    lookback_hours: int = 24,
) -> Dict[str, Any]:
    """
    Scan headlines_live.json for BOJ-related keywords.
    Returns: boj_statement_detected, hawkish_count, dovish_count, tone, evidence, headline_score.
    """
    blank = {
        "boj_statement_detected": False,
        "hawkish_count": 0,
        "dovish_count": 0,
        "tone": "UNKNOWN",
        "evidence": [],
        "headline_score": 0,
    }

    # Try local file first; fall back to GitHub Pages if not available locally
    data = None
    try:
        data = json.loads(headlines_path.read_text(encoding="utf-8"))
        log.debug("Headlines loaded from local file (%s)", headlines_path)
    except FileNotFoundError:
        log.warning("Local headlines not found at %s — trying GitHub Pages fallback", headlines_path)
    except Exception as exc:
        log.warning("Local headlines read error: %s — trying GitHub Pages fallback", exc)

    if data is None:
        try:
            req = urllib.request.Request(
                _HEADLINES_REMOTE + "?t=" + str(int(datetime.now().timestamp())),
                headers={"User-Agent": "BlueLotus-BOJ-Engine/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            # Cache locally for next run
            try:
                headlines_path.parent.mkdir(parents=True, exist_ok=True)
                headlines_path.write_text(raw, encoding="utf-8")
            except Exception:
                pass
            log.info("Headlines fetched from GitHub Pages fallback (%d sources)", len(data.get("sources", {})))
        except Exception as exc:
            log.warning("GitHub Pages headlines fallback also failed: %s", exc)
            blank["evidence"] = ["Headlines unavailable — local file missing and remote fetch failed"]
            return blank

    hawkish_count = 0
    dovish_count  = 0
    boj_found     = False
    evidence: List[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    sources = data.get("sources", {})
    for src_id, src_data in sources.items():
        for item in (src_data.get("items") or []):
            text = (item.get("text") or "").lower()

            # Check if this headline contains any BOJ keyword at all
            has_boj = any(kw in text for kw in BOJ_KEYWORDS)
            if not has_boj:
                continue

            boj_found = True

            # Count hawkish signals in this BOJ headline
            for kw in BOJ_HAWKISH_KEYWORDS:
                if kw in text:
                    hawkish_count += 1
                    if len(evidence) < 5:
                        snippet = (item.get("text") or "")[:80]
                        evidence.append(f"[H] {kw!r} — {src_id}: {snippet}…")

            # Count dovish signals in this BOJ headline
            for kw in BOJ_DOVISH_KEYWORDS:
                if kw in text:
                    dovish_count += 1
                    if len(evidence) < 10:
                        snippet = (item.get("text") or "")[:80]
                        evidence.append(f"[D] {kw!r} — {src_id}: {snippet}…")

    if not boj_found:
        blank["evidence"] = ["No BOJ/yen keywords found in recent headlines"]
        return blank

    # Determine tone from hawkish vs dovish balance
    total = hawkish_count + dovish_count
    if total == 0:
        tone = "NEUTRAL"
    else:
        ratio = hawkish_count / total
        if ratio >= 0.60:
            tone = "HAWKISH"
        elif ratio <= 0.35:
            tone = "DOVISH"
        else:
            tone = "NEUTRAL"

    return {
        "boj_statement_detected": boj_found,
        "hawkish_count": hawkish_count,
        "dovish_count": dovish_count,
        "tone": tone,
        "evidence": evidence[:10],
        "headline_score": 0,  # set by scorer
    }


# ── Market Data Fetcher ────────────────────────────────────────────────────────

def fetch_market_data(tickers: Optional[List[str]] = None) -> Dict[str, Optional[float]]:
    """
    Fetch day-change % for all BOJ/Yen Carry tickers via yfinance.
    Returns {ticker_lower: chg_pct | None}.
    """
    tickers = tickers or _BOJ_TICKERS
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
        # Normalise keys: "JPY=X" -> "jpy=x", "VXX" -> "vxx", etc.
        return {k.lstrip("^").lower(): v for k, v in result.items()}
    except Exception as exc:
        log.error("yfinance fetch failed: %s", exc)
        return {}


# ── Individual Scorers ────────────────────────────────────────────────────────

def score_boj_statement(headline_result: Dict[str, Any]) -> float:
    """
    0-15 pts based on whether a BOJ statement / headline was detected.
    - No BOJ headlines at all: 0
    - BOJ headlines found but neutral/unknown tone: 5
    - Hawkish tone detected: 15
    - Dovish tone: 2
    """
    if not headline_result.get("boj_statement_detected", False):
        return 0.0
    tone = headline_result.get("tone", "UNKNOWN")
    if tone == "HAWKISH":
        return float(_WEIGHTS["boj_statement"])   # 15
    if tone == "DOVISH":
        return 2.0
    # NEUTRAL or UNKNOWN but BOJ headlines exist
    return 5.0


def score_boj_tone(headline_result: Dict[str, Any]) -> float:
    """
    0-15 pts based on hawkish vs dovish keyword ratio.
    HAWKISH: 15, NEUTRAL: 7, DOVISH: 2, UNKNOWN: 0
    """
    tone = headline_result.get("tone", "UNKNOWN")
    if tone == "HAWKISH":
        return float(_WEIGHTS["boj_tone"])   # 15
    if tone == "NEUTRAL":
        return round(_WEIGHTS["boj_tone"] * 0.47)  # 7
    if tone == "DOVISH":
        return 2.0
    return 0.0  # UNKNOWN


def score_usd_jpy(intraday: Dict[str, Any]) -> float:
    """
    0-20 pts. INVERTED: yen strengthening (JPY=X falling) = HIGH score = carry unwind risk.
    Uses 1h change as primary signal.
      change_1h_pct < -1.5  →  20 (severe yen strength)
      change_1h_pct < -1.0  →  16
      change_1h_pct < -0.5  →  12
      change_1h_pct < -0.2  →  6
      stable or yen weakening → 0-2
    """
    chg = intraday.get("change_1h_pct")
    if chg is None:
        # Try day change as fallback
        return 0.0
    chg = _f(chg)
    if chg < -1.5:
        return 20.0
    if chg < -1.0:
        return 16.0
    if chg < -0.5:
        return 12.0
    if chg < -0.2:
        return 6.0
    if chg < 0.0:
        return 2.0
    # Yen weakening (USD/JPY rising) = low carry unwind risk
    return 0.0


def score_japan_equity(prices: Dict[str, Optional[float]]) -> float:
    """
    0-10 pts. EWJ and DXJ selling off = Japan equity stress = carry unwind risk.
    """
    ewj = _f(prices.get("ewj"))
    dxj = _f(prices.get("dxj"))
    score = 0.0

    if ewj < -2.0:
        score += 5.0
    elif ewj < -1.0:
        score += 3.0
    elif ewj < -0.5:
        score += 1.5
    elif ewj >= 0:
        score += 0.0

    if dxj < -2.0:
        score += 5.0
    elif dxj < -1.0:
        score += 3.0
    elif dxj < -0.5:
        score += 1.5
    elif dxj >= 0:
        score += 0.0

    return min(float(_WEIGHTS["japan_equity"]), score)


def score_volatility(prices: Dict[str, Optional[float]]) -> float:
    """
    0-15 pts. VXX / VIXY / UVXY rising = fear spike = carry unwind risk.
    UVXY up >10% = full 15.
    """
    vxx  = _f(prices.get("vxx"))
    vixy = _f(prices.get("vixy"))
    uvxy = _f(prices.get("uvxy"))
    score = 0.0

    # UVXY — leveraged vol, strongest signal
    if uvxy > 10.0:
        return float(_WEIGHTS["volatility"])  # full 15
    if uvxy > 6.0:
        score = max(score, 12.0)
    elif uvxy > 3.0:
        score = max(score, 8.0)
    elif uvxy > 1.0:
        score = max(score, 4.0)

    # VXX
    if vxx > 6.0:
        score = max(score, 12.0)
    elif vxx > 3.0:
        score = max(score, 8.0)
    elif vxx > 1.5:
        score = max(score, 5.0)
    elif vxx > 0.5:
        score = max(score, 2.0)

    # VIXY as tiebreaker
    if vixy > 5.0:
        score = max(score, 10.0)
    elif vixy > 2.0:
        score = max(score, 6.0)

    return min(float(_WEIGHTS["volatility"]), score)


def score_us_equity(prices: Dict[str, Optional[float]]) -> float:
    """
    0-10 pts. SPY / QQQ / IWM selling off = risk-off = carry unwind confirmation.
    """
    spy = _f(prices.get("spy"))
    qqq = _f(prices.get("qqq"))
    iwm = _f(prices.get("iwm"))

    basket = [v for v in [spy, qqq, iwm] if v is not None]
    if not basket:
        return 0.0
    avg = sum(basket) / len(basket)

    if avg < -2.0:
        return 10.0
    if avg < -1.5:
        return 8.0
    if avg < -1.0:
        return 6.0
    if avg < -0.5:
        return 4.0
    if avg < -0.2:
        return 2.0
    return 0.0


def score_credit(prices: Dict[str, Optional[float]]) -> float:
    """
    0-10 pts. HYG / JNK weakening = credit stress = carry unwind amplifier.
    """
    hyg = _f(prices.get("hyg"))
    jnk = _f(prices.get("jnk"))

    score = 0.0
    if hyg < -1.0 and jnk < -1.0:
        score = 10.0
    elif hyg < -0.6 and jnk < -0.6:
        score = 7.0
    elif hyg < -0.4 or jnk < -0.4:
        score = 4.0
    elif hyg < -0.2 or jnk < -0.2:
        score = 2.0

    return min(float(_WEIGHTS["credit"]), score)


def score_high_beta(prices: Dict[str, Optional[float]]) -> float:
    """
    0-5 pts. Portfolio high-beta names (NVDA, ASTS, QBTS, QUBT, IONQ, RKLB, LUNR, PL)
    falling = carry unwind liquidation hitting the book.
    """
    names = ["nvda", "asts", "qbts", "qubt", "ionq", "rklb", "lunr", "pl"]
    vals  = [_f(prices.get(n)) for n in names if prices.get(n) is not None]
    if not vals:
        return 0.0
    avg = sum(vals) / len(vals)

    if avg < -3.0:
        return 5.0
    if avg < -2.0:
        return 4.0
    if avg < -1.0:
        return 2.5
    if avg < -0.5:
        return 1.0
    return 0.0


# ── Status / CIO / Alerts ─────────────────────────────────────────────────────

def compute_status(total_score: float) -> str:
    """Returns LOW / WATCH / ACTIVE / SEVERE based on total score 0-100."""
    for threshold, label in _STATUS_THRESHOLDS:
        if total_score >= threshold:
            return label
    return "LOW"


def compute_cio_action(
    status: str,
    prices: Dict[str, Optional[float]],
) -> Tuple[str, List[str]]:
    """
    Returns (cio_action, blocked_actions) for the given carry-unwind status.
    Governance: NEVER output BUY / SELL / EXECUTE / ROUTE_ORDER / CANCEL_ORDER.
    """
    mapping = _CIO_MAP.get(status, _CIO_MAP["LOW"])
    cio_action     = mapping["cio_action"]
    blocked_actions: List[str] = list(mapping["blocked_actions"])

    # Additional override: if volatility is truly extreme, escalate to SEVERE actions
    uvxy = _f(prices.get("uvxy"))
    vxx  = _f(prices.get("vxx"))
    if uvxy > 12.0 or vxx > 8.0:
        if "BLOCK_HIGH_BETA_ADD" not in blocked_actions:
            blocked_actions.append("BLOCK_HIGH_BETA_ADD")
        if "BLOCK_DCA" not in blocked_actions:
            blocked_actions.append("BLOCK_DCA")

    return cio_action, sorted(set(blocked_actions))


def compute_alerts(
    status: str,
    intraday: Dict[str, Any],
    prices: Dict[str, Optional[float]],
    headline_result: Dict[str, Any],
) -> List[str]:
    """
    Returns list of alert strings triggered by threshold checks (WO section 10 equivalent).
    """
    alerts: List[str] = []

    chg_1h = intraday.get("change_1h_pct")
    if chg_1h is not None:
        chg_1h_f = _f(chg_1h)
        if chg_1h_f < -1.0:
            alerts.append(
                f"ALERT: USD/JPY 1h change {chg_1h_f:+.3f}% — yen strengthening >1% in 1h, carry unwind accelerating"
            )
        elif chg_1h_f < -0.5:
            alerts.append(
                f"ALERT: USD/JPY 1h change {chg_1h_f:+.3f}% — yen breakdown threshold crossed"
            )

    if intraday.get("breakdown_flag"):
        alerts.append("ALERT: USD/JPY breakdown flag ACTIVE — yen strengthened >0.5% in 1h")

    vxx  = _f(prices.get("vxx"))
    uvxy = _f(prices.get("uvxy"))
    if uvxy > 10.0:
        alerts.append(f"ALERT: UVXY +{uvxy:.1f}% — leveraged volatility extreme, BLOCK_HIGH_BETA_ADD")
    elif vxx > 5.0:
        alerts.append(f"ALERT: VXX +{vxx:.1f}% — volatility spike, no high-beta adds")

    ewj = _f(prices.get("ewj"))
    if ewj < -3.0:
        alerts.append(f"ALERT: EWJ {ewj:.1f}% — Japan equity severe, yen carry unwind confirmed")
    elif ewj < -1.5:
        alerts.append(f"ALERT: EWJ {ewj:.1f}% — Japan equity selling off, watch carry positions")

    hyg = _f(prices.get("hyg"))
    jnk = _f(prices.get("jnk"))
    if hyg < -0.6 and jnk < -0.6:
        alerts.append(f"ALERT: Credit stress — HYG {hyg:.1f}% JNK {jnk:.1f}% — carry unwind hitting credit")

    if headline_result.get("boj_statement_detected") and headline_result.get("tone") == "HAWKISH":
        alerts.append(
            "ALERT: BOJ hawkish statement detected — policy shift risk elevated, monitor USD/JPY closely"
        )

    if status == "SEVERE":
        alerts.append(
            "ALERT: CARRY UNWIND SEVERE — BLOCK_SECOND_TRANCHE + BLOCK_DCA + BLOCK_HIGH_BETA_ADD active"
        )
    elif status == "ACTIVE":
        alerts.append("ALERT: Carry unwind ACTIVE — partial hedge profit review recommended")

    return alerts


# ── Main Watcher Builder ──────────────────────────────────────────────────────

def build_boj_yen_carry_watcher() -> Dict[str, Any]:
    """
    Full BOJ / Yen Carry Event Watcher computation.
    Returns the complete JSON-serialisable output dict.

    Output schema (section 8):
      thesis_id, generated_at, status, score,
      boj_statement, boj_tone_gate, usd_jpy_gate, japan_equity_gate,
      volatility_gate, us_equity_gate, credit_gate, high_beta_gate,
      intraday_usdjpy, cio_action, blocked_actions, alerts, notes,
      human_summary, yen_carry_unwind_status
    """
    headline_result = scan_boj_headlines(_HEADLINES_PATH)
    intraday        = fetch_usdjpy_intraday()
    prices          = fetch_market_data()

    if not prices:
        return {
            "thesis_id":              "THESIS-BOJ-YEN-CARRY-UNWIND",
            "generated_at":           _now_sgt(),
            "status":                 "LOW",
            "score":                  0,
            "error":                  "Market data unavailable (yfinance timeout or not installed)",
            "cio_action":             "WAIT",
            "blocked_actions":        [],
            "alerts":                 [],
            "notes":                  ["Market data fetch failed — standing by for next cycle"],
            "human_summary":          "Market data unavailable; BOJ carry unwind status cannot be assessed this cycle.",
            "yen_carry_unwind_status": "UNKNOWN",
        }

    # ── Score all gates ──────────────────────────────────────────────────────
    sc_boj_stmt  = score_boj_statement(headline_result)
    sc_boj_tone  = score_boj_tone(headline_result)
    sc_usd_jpy   = score_usd_jpy(intraday)
    sc_jpn_eq    = score_japan_equity(prices)
    sc_vol       = score_volatility(prices)
    sc_us_eq     = score_us_equity(prices)
    sc_credit    = score_credit(prices)
    sc_hb        = score_high_beta(prices)

    total = round(
        sc_boj_stmt + sc_boj_tone + sc_usd_jpy + sc_jpn_eq +
        sc_vol + sc_us_eq + sc_credit + sc_hb, 1
    )
    total = max(0.0, min(100.0, total))

    status = compute_status(total)
    cio_action, blocked_actions = compute_cio_action(status, prices)
    alerts = compute_alerts(status, intraday, prices, headline_result)

    # ── Yen carry unwind status string: matches top-level status enum ────────
    # Spec values: LOW / WATCH / ACTIVE / SEVERE
    yen_carry_unwind_status = status  # LOW / WATCH / ACTIVE / SEVERE

    # ── Build gate detail dicts ──────────────────────────────────────────────
    tone     = headline_result.get("tone", "UNKNOWN")
    boj_stmt = headline_result.get("boj_statement_detected", False)

    boj_statement_gate = {
        "status":                   "DETECTED" if boj_stmt else "NONE",
        "score":                    round(sc_boj_stmt, 1),
        "boj_statement_detected":   boj_stmt,
        "tone":                     tone,
        "hawkish_count":            headline_result.get("hawkish_count", 0),
        "dovish_count":             headline_result.get("dovish_count", 0),
        "evidence":                 headline_result.get("evidence", []),
    }

    boj_tone_gate = {
        "status": tone,
        "score":  round(sc_boj_tone, 1),
        "tone":   tone,
        "hawkish_count": headline_result.get("hawkish_count", 0),
        "dovish_count":  headline_result.get("dovish_count", 0),
    }

    chg_1h = intraday.get("change_1h_pct")
    usd_jpy_gate = {
        "status":          "BREAKDOWN" if intraday.get("breakdown_flag") else ("WATCH" if (chg_1h is not None and _f(chg_1h) < -0.2) else "CALM"),
        "score":           round(sc_usd_jpy, 1),
        "price":           intraday.get("price"),
        "change_5m_pct":   intraday.get("change_5m_pct"),
        "change_15m_pct":  intraday.get("change_15m_pct"),
        "change_1h_pct":   intraday.get("change_1h_pct"),
        "breakdown_flag":  intraday.get("breakdown_flag", False),
        "data_source":     intraday.get("data_source", "unknown"),
        "note":            intraday.get("note", ""),
    }

    ewj = _f(prices.get("ewj"))
    dxj = _f(prices.get("dxj"))
    japan_equity_gate = {
        "status":          "SHOCK" if sc_jpn_eq >= 7 else ("ACTIVE" if sc_jpn_eq >= 5 else ("WATCH" if sc_jpn_eq >= 3 else "CALM")),
        "score":           round(sc_jpn_eq, 1),
        "ewj_change_pct":  ewj,
        "dxj_change_pct":  dxj,
    }

    vxx  = _f(prices.get("vxx"))
    vixy = _f(prices.get("vixy"))
    uvxy = _f(prices.get("uvxy"))
    volatility_gate = {
        "status":           "SPIKE" if sc_vol >= 12 else ("ACTIVE" if sc_vol >= 6 else ("WATCH" if sc_vol >= 3 else "CALM")),
        "score":            round(sc_vol, 1),
        "vxx_change_pct":   vxx,
        "vixy_change_pct":  vixy,
        "uvxy_change_pct":  uvxy,
    }

    spy = _f(prices.get("spy"))
    qqq = _f(prices.get("qqq"))
    iwm = _f(prices.get("iwm"))
    us_equity_gate = {
        "status":          "SELL_OFF" if sc_us_eq >= 7 else ("ACTIVE" if sc_us_eq >= 5 else ("WATCH" if sc_us_eq >= 3 else "CALM")),
        "score":           round(sc_us_eq, 1),
        "spy_change_pct":  spy,
        "qqq_change_pct":  qqq,
        "iwm_change_pct":  iwm,
    }

    hyg = _f(prices.get("hyg"))
    jnk = _f(prices.get("jnk"))
    lqd = _f(prices.get("lqd"))
    credit_gate = {
        "status":          "STRESS" if sc_credit >= 7 else ("ACTIVE" if sc_credit >= 5 else ("WATCH" if sc_credit >= 3 else "CALM")),
        "score":           round(sc_credit, 1),
        "hyg_change_pct":  hyg,
        "jnk_change_pct":  jnk,
        "lqd_change_pct":  lqd,
    }

    hb_names = ["nvda", "asts", "qbts", "qubt", "ionq", "rklb", "lunr", "pl"]
    hb_vals  = {n: _f(prices.get(n)) for n in hb_names}
    high_beta_gate = {
        "status": "LIQUIDATING" if sc_hb >= 4 else ("ACTIVE" if sc_hb >= 3 else ("WATCH" if sc_hb >= 2 else "CALM")),
        "score":  round(sc_hb, 1),
        **{f"{n}_change_pct": hb_vals[n] for n in hb_names},
    }

    # ── Human summary ────────────────────────────────────────────────────────
    chg_1h_str = (
        f"USD/JPY 1h change {_f(chg_1h):+.3f}%"
        if chg_1h is not None
        else "USD/JPY intraday data unavailable"
    )
    human_summary = (
        f"BOJ/Yen Carry Event Watcher: status {status} (score {total}/100) — "
        f"{chg_1h_str}, yen carry unwind {yen_carry_unwind_status}, "
        f"BOJ tone {tone}, CIO action {cio_action}."
    )

    notes: List[str] = []
    if intraday.get("note"):
        notes.append(intraday["note"])
    if boj_stmt and tone == "HAWKISH":
        notes.append("BOJ hawkish signal detected — monitor USD/JPY 5m/15m for acceleration")
    if intraday.get("breakdown_flag"):
        notes.append("USD/JPY breakdown flag active — yen strength >0.5% in 1h")
    if uvxy > 10.0:
        notes.append(f"UVXY +{uvxy:.1f}% — extreme volatility, high-beta add blocked")
    if ewj < -2.0 and vxx > 3.0:
        notes.append(f"Yen carry unwind confirmed: EWJ {ewj:.1f}% + VXX +{vxx:.1f}%")

    return {
        "thesis_id":               "THESIS-BOJ-YEN-CARRY-UNWIND",
        "generated_at":            _now_sgt(),
        "status":                  status,
        "score":                   total,
        "yen_carry_unwind_status": yen_carry_unwind_status,
        # Top-level USD/JPY summary (mirrors intraday_usdjpy for dashboard convenience)
        "usd_jpy": {
            "price":           intraday.get("price"),
            "change_5m_pct":   intraday.get("change_5m_pct"),
            "change_15m_pct":  intraday.get("change_15m_pct"),
            "change_1h_pct":   intraday.get("change_1h_pct"),
            "breakdown_flag":  intraday.get("breakdown_flag", False),
            "data_source":     intraday.get("data_source", "unknown"),
            "note":            intraday.get("note", ""),
        },
        "boj_statement":           boj_statement_gate,
        "boj_tone_gate":           boj_tone_gate,
        "usd_jpy_gate":            usd_jpy_gate,
        "japan_equity_gate":       japan_equity_gate,
        "volatility_gate":         volatility_gate,
        "us_equity_gate":          us_equity_gate,
        "credit_gate":             credit_gate,
        "high_beta_gate":          high_beta_gate,
        "intraday_usdjpy":         intraday,
        "cio_action":              cio_action,
        "blocked_actions":         blocked_actions,
        "alerts":                  alerts,
        "notes":                   notes,
        "human_summary":           human_summary,
    }


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("Running BOJ/Yen Carry Event Watcher — standalone test")
    result = build_boj_yen_carry_watcher()
    print(json.dumps(result, indent=2, default=str))
