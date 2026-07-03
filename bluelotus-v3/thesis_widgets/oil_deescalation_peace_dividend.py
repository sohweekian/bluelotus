#!/usr/bin/env python3
"""
BlueLotus V3 S9 thesis widget: Oil De-escalation / Peace Dividend.

The widget is deterministic, YAML-driven, broker-free, and LLM-free.
Higher score means stronger peace-dividend confirmation.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
import yfinance as yf

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parent.parent
_CFG_PATH = _ROOT / "config" / "thesis_widgets" / "oil_deescalation_peace_dividend.yaml"
_LOG_DIR = _ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_DIR / "oil_deescalation_peace_dividend.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("oil_peace_dividend")
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)


def load_config(path: Path = _CFG_PATH) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_relative(value: Optional[float], reference: Optional[float]) -> Optional[float]:
    if value is None or reference is None:
        return None
    return round(value - reference, 3)


def fetch_prices(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {
        symbol: {"available": False, "price": None, "day_change_pct": None}
        for symbol in symbols
    }
    if not symbols:
        return result
    try:
        raw = yf.download(
            symbols,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw.empty:
            return result
        close = raw["Close"] if "Close" in raw.columns else raw.get("close")
        if close is None or close.empty:
            return result
        if len(symbols) == 1 and hasattr(close, "to_frame"):
            close = close.to_frame(name=symbols[0])
        for symbol in symbols:
            try:
                column = close[symbol] if symbol in close.columns else None
                if column is None:
                    continue
                column = column.dropna()
                if len(column) < 2:
                    continue
                latest = float(column.iloc[-1])
                prev = float(column.iloc[-2])
                pct = round((latest - prev) / prev * 100, 4) if prev else None
                result[symbol] = {
                    "available": True,
                    "price": round(latest, 4),
                    "day_change_pct": pct,
                }
            except Exception:
                continue
    except Exception as exc:
        log.warning("price fetch failed: %s", exc)
    return result


def classify_ticker_signal(
    day_change_pct: Optional[float],
    pass_pct: float,
    fail_pct: float,
    benefit_on_rise: bool,
) -> str:
    if day_change_pct is None:
        return "UNKNOWN"
    if benefit_on_rise:
        if day_change_pct >= pass_pct:
            return "PASS"
        if day_change_pct <= -fail_pct:
            return "FAIL"
    else:
        if day_change_pct <= -pass_pct:
            return "PASS"
        if day_change_pct >= fail_pct:
            return "FAIL"
    return "WATCH"


def score_basket(
    basket_id: str,
    basket_cfg: Dict[str, Any],
    prices: Dict[str, Dict[str, Any]],
    spy_chg: Optional[float],
    qqq_chg: Optional[float],
    cfg: Dict[str, Any],
) -> Tuple[str, float, List[Dict[str, Any]]]:
    thresholds = cfg["signal_thresholds"]
    basket_thresholds = basket_cfg.get("signal_thresholds", {})
    pass_pct = float(basket_thresholds.get("pass_pct") or thresholds["pass_pct"])
    fail_pct = float(basket_thresholds.get("fail_pct") or thresholds["fail_pct"])
    pass_ratio = float(thresholds["basket_pass_ratio"])
    fail_ratio = float(thresholds["basket_fail_ratio"])
    weights = cfg["ticker_contribution_weights"]
    interpretations = basket_cfg.get("interpretations", {})
    basket_weight = float(basket_cfg["scoring_weight"])

    rows: List[Dict[str, Any]] = []
    contributions: List[float] = []
    pass_count = 0
    fail_count = 0
    available_count = 0

    for ticker in basket_cfg.get("tickers", []):
        display = str(ticker["display"])
        yf_symbol = str(ticker["yf_symbol"])
        benefit_on_rise = bool(ticker["benefit_on_rise"])
        price_info = prices.get(yf_symbol, {})
        available = bool(price_info.get("available"))
        day_change = price_info.get("day_change_pct")
        signal = classify_ticker_signal(day_change, pass_pct, fail_pct, benefit_on_rise)
        if signal == "PASS":
            pass_count += 1
        elif signal == "FAIL":
            fail_count += 1
        if available:
            available_count += 1
        contributions.append(float(weights.get(signal, 0.0)))
        rows.append({
            "display_symbol": display,
            "yf_symbol": yf_symbol,
            "group": basket_id,
            "price": price_info.get("price"),
            "day_change_pct": day_change,
            "relative_to_spy": compute_relative(day_change, spy_chg),
            "relative_to_qqq": compute_relative(day_change, qqq_chg),
            "signal": signal,
            "interpretation": interpretations.get(signal, interpretations.get("WATCH", "")),
            "available": available,
        })

    if not rows or available_count == 0:
        return "UNKNOWN", 0.0, rows

    row_count = len(rows)
    if pass_count / row_count >= pass_ratio:
        basket_signal = "PASS"
    elif fail_count / row_count >= fail_ratio:
        basket_signal = "FAIL"
    else:
        basket_signal = "WATCH"
    return basket_signal, (sum(contributions) / row_count) * basket_weight, rows


def _headline_items(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for source_path in cfg.get("headline_sources", []):
        path = _ROOT / str(source_path)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            items.extend([item for item in data if isinstance(item, dict)])
        elif isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    items.extend([item for item in value if isinstance(item, dict)])
                elif isinstance(value, dict):
                    nested = value.get("items")
                    if isinstance(nested, list):
                        items.extend([item for item in nested if isinstance(item, dict)])
    return items


def score_headlines(cfg: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    keywords = [str(item).lower() for item in cfg.get("headline_keywords", [])]
    points = float(cfg.get("headline_pts_per_hit", 0))
    max_score = float(cfg.get("headline_max_score", 0))
    score = 0.0
    evidence: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in _headline_items(cfg):
        text = str(item.get("headline") or item.get("title") or item.get("text") or "")
        text_l = text.lower()
        if not text_l or text_l in seen:
            continue
        for keyword in keywords:
            if keyword in text_l:
                score += points
                evidence.append({
                    "headline": text,
                    "keyword_matched": keyword,
                    "source": item.get("source", ""),
                    "url": item.get("url", item.get("link", "")),
                })
                seen.add(text_l)
                break
    return min(score, max_score), evidence


def score_escalation(cfg: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    keywords = [str(item).lower() for item in cfg.get("escalation_keywords", [])]
    penalty_cfg = cfg.get("escalation_penalty", {})
    points = float(penalty_cfg.get("pts_per_hit", 0))
    max_penalty = float(penalty_cfg.get("max_penalty", 0))
    penalty = 0.0
    evidence: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in _headline_items(cfg):
        text = str(item.get("headline") or item.get("title") or item.get("text") or "")
        text_l = text.lower()
        if not text_l or text_l in seen:
            continue
        for keyword in keywords:
            if keyword in text_l:
                penalty += points
                evidence.append({
                    "headline": text,
                    "keyword_matched": keyword,
                    "source": item.get("source", ""),
                    "url": item.get("url", item.get("link", "")),
                })
                seen.add(text_l)
                break
    return min(penalty, max_penalty), evidence


def read_external_evidence(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    ext_cfg = cfg.get("external_evidence", {})
    if not ext_cfg.get("enabled", False):
        return []
    evidence: List[Dict[str, Any]] = []
    for source_id, source_cfg in ext_cfg.get("sources", {}).items():
        path = _ROOT / str(source_cfg.get("path", ""))
        label = source_cfg.get("label", source_id)
        status_field = source_cfg.get("status_field", "status")
        score_field = source_cfg.get("score_field", "score")
        block_statuses = set(source_cfg.get("block_statuses", []))
        watch_statuses = set(source_cfg.get("watch_statuses", []))
        if not path.exists():
            evidence.append({
                "source": source_id,
                "label": label,
                "status": "UNAVAILABLE",
                "available": False,
                "blocks_add": False,
            })
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            status = str(data.get(status_field, "UNKNOWN"))
            evidence.append({
                "source": source_id,
                "label": label,
                "status": status,
                "score": data.get(score_field),
                "generated_at": data.get("last_updated_utc") or data.get("last_updated_sgt", ""),
                "available": True,
                "blocks_add": status in block_statuses,
                "watch_context": status in watch_statuses,
            })
        except Exception as exc:
            evidence.append({
                "source": source_id,
                "label": label,
                "status": "READ_ERROR",
                "available": False,
                "blocks_add": False,
                "error": str(exc),
            })
    return evidence


def evaluate_false_positive_rules(
    basket_signals: Dict[str, str],
    cfg: Dict[str, Any],
) -> Tuple[float, List[Dict[str, Any]]]:
    penalty = 0.0
    flags: List[Dict[str, Any]] = []
    for rule_id, rule in cfg.get("false_positive_rules", {}).items():
        if not rule.get("enabled", False):
            continue
        required = rule.get("required_signals", {})
        matched = all(basket_signals.get(group) == expected for group, expected in required.items())
        if matched:
            rule_penalty = float(rule.get("penalty", 0))
            penalty += rule_penalty
            flags.append({
                "rule": rule_id,
                "message": rule.get("message", rule_id),
                "penalty": rule_penalty,
            })
    return penalty, flags


def get_market_status(
    cfg: Dict[str, Any],
    _now_et_override: Optional[datetime] = None,
) -> Dict[str, Any]:
    from zoneinfo import ZoneInfo

    mh = cfg["market_hours"]
    tz = ZoneInfo(str(mh["timezone"]))
    now_et = _now_et_override or datetime.now(tz)
    open_hour, open_minute = (int(part) for part in str(mh["open_time"]).split(":"))
    close_hour, close_minute = (int(part) for part in str(mh["close_time"]).split(":"))
    open_dt = now_et.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    close_dt = now_et.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    trading_days = list(mh["trading_days"])
    labels = mh.get("data_freshness_labels", {})

    if now_et.weekday() not in trading_days:
        market_status = "CLOSED_WEEKEND"
    elif now_et < open_dt:
        market_status = "CLOSED_PRE"
    elif now_et >= close_dt:
        market_status = "CLOSED_POST"
    else:
        market_status = "OPEN"

    ref: date = now_et.date()
    if market_status == "CLOSED_PRE":
        ref -= timedelta(days=1)
    while ref.weekday() not in trading_days:
        ref -= timedelta(days=1)

    return {
        "market_open": market_status == "OPEN",
        "market_status": market_status,
        "market_time_et": now_et.strftime("%H:%M ET"),
        "last_market_session": ref.isoformat(),
        "data_freshness_label": labels.get(market_status, ""),
    }


def score_to_status(score: Optional[float], cfg: Dict[str, Any]) -> str:
    if score is None:
        return "UNKNOWN"
    thresholds = cfg["status_thresholds"]
    if score >= float(thresholds["CONFIRMING"]):
        return "CONFIRMING"
    if score >= float(thresholds["WATCH"]):
        return "WATCH"
    if score >= float(thresholds["MIXED"]):
        return "MIXED"
    if score >= float(thresholds["WEAKENING"]):
        return "WEAKENING"
    return "CONTRADICTED"


def score_to_confidence(score: Optional[float], basket_signals: Dict[str, str], cfg: Dict[str, Any]) -> str:
    if score is None:
        return "UNKNOWN"
    rules = cfg.get("confidence_rules", {})
    required = rules.get("high_required_baskets", [])
    pass_count = sum(1 for value in basket_signals.values() if value == "PASS")
    if required and all(basket_signals.get(group) == "PASS" for group in required):
        return "HIGH"
    if pass_count >= int(rules.get("medium_min_pass_count", 3)):
        return "MEDIUM"
    if pass_count >= int(rules.get("low_min_pass_count", 1)):
        return "LOW"
    thresholds = cfg.get("confidence_thresholds", {})
    if score >= float(thresholds.get("MEDIUM", 55)):
        return "MEDIUM"
    if score >= float(thresholds.get("LOW", 20)):
        return "LOW"
    return "UNKNOWN"


def get_cio_action(status: str, confidence: str, cfg: Dict[str, Any]) -> str:
    mapping = cfg.get("cio_action_map", {})
    return mapping.get(f"{status}_{confidence}", mapping.get(status, mapping.get("UNKNOWN", "CIO_REVIEW_REQUIRED")))


def compute_add_allowed(
    status: str,
    confidence: str,
    basket_signals: Dict[str, str],
    escalation_penalty: float,
    false_positive_penalty: float,
    external_evidence: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> bool:
    rules = cfg.get("add_allowed_rules", {})
    if status not in set(rules.get("allowed_statuses", [])):
        return False
    if confidence not in set(rules.get("allowed_confidences", [])):
        return False
    if any(basket_signals.get(group) != "PASS" for group in rules.get("required_pass_baskets", [])):
        return False
    if escalation_penalty > float(rules.get("max_escalation_penalty", 0)):
        return False
    if false_positive_penalty > float(rules.get("max_false_positive_penalty", 0)):
        return False
    if any(item.get("blocks_add") for item in external_evidence):
        return False
    return True


def risk_level_for(status: str, escalation_penalty: float, false_positive_penalty: float) -> str:
    if escalation_penalty > 0 or false_positive_penalty > 0:
        return "ELEVATED"
    if status == "CONFIRMING":
        return "LOW"
    if status in {"WATCH", "MIXED"}:
        return "MODERATE"
    if status in {"WEAKENING", "CONTRADICTED"}:
        return "HIGH"
    return "UNKNOWN"


def build_output(
    cfg: Dict[str, Any],
    total_score: float,
    status: str,
    confidence: str,
    cio_action: str,
    add_allowed: bool,
    primary_signals: List[Dict[str, Any]],
    ticker_evidence: List[Dict[str, Any]],
    headline_score: float,
    headline_evidence: List[Dict[str, Any]],
    escalation_penalty: float,
    escalation_evidence: List[Dict[str, Any]],
    external_evidence: List[Dict[str, Any]],
    false_positive_penalty: float,
    false_positive_flags: List[Dict[str, Any]],
    blind_spots: List[str],
    now_sgt: datetime,
    data_quality: str,
    market_status_info: Dict[str, Any],
) -> Dict[str, Any]:
    safety = cfg["safety"]
    pass_count = sum(1 for row in ticker_evidence if row.get("signal") == "PASS")
    watch_count = sum(1 for row in ticker_evidence if row.get("signal") == "WATCH")
    fail_count = sum(1 for row in ticker_evidence if row.get("signal") == "FAIL")
    if status == "CONFIRMING":
        summary = "Oil de-escalation peace-dividend thesis confirming across market channels."
    elif status == "WATCH":
        summary = "Peace-dividend setup under watch; confirmation is present but incomplete."
    elif status == "MIXED":
        summary = "Oil relief signals are mixed; false-positive risk remains material."
    elif status == "WEAKENING":
        summary = "Peace-dividend thesis weakening; insufficient confirmation from risk assets."
    elif status == "CONTRADICTED":
        summary = "Peace-dividend thesis contradicted by market or escalation signals."
    else:
        summary = "Peace-dividend thesis status unknown due to insufficient data."

    return {
        "schema_version": cfg["schema_version"],
        "thesis_id": cfg["thesis_id"],
        "title": cfg["title"],
        "status": status,
        "score": round(total_score, 1),
        "score_max": 100,
        "confidence": confidence,
        "cio_action": cio_action,
        "add_allowed": add_allowed,
        "risk_level": risk_level_for(status, escalation_penalty, false_positive_penalty),
        "data_quality": data_quality,
        "last_updated_sgt": now_sgt.strftime("%Y-%m-%d %H:%M SGT"),
        "last_updated_utc": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_open": market_status_info.get("market_open", False),
        "market_status": market_status_info.get("market_status", "UNKNOWN"),
        "market_time_et": market_status_info.get("market_time_et", ""),
        "last_market_session": market_status_info.get("last_market_session", ""),
        "data_freshness_label": market_status_info.get("data_freshness_label", ""),
        "summary": summary,
        "primary_signals": primary_signals,
        "ticker_evidence": ticker_evidence,
        "headline_score": round(headline_score, 1),
        "headline_evidence": headline_evidence[:10],
        "escalation_penalty": round(escalation_penalty, 1),
        "escalation_evidence": escalation_evidence[:10],
        "external_evidence": external_evidence,
        "false_positive_penalty": round(false_positive_penalty, 1),
        "false_positive_flags": false_positive_flags,
        "pass_count": pass_count,
        "watch_count": watch_count,
        "fail_count": fail_count,
        "blind_spots": blind_spots,
        "execution_authority": safety["execution_authority"],
        "order_routing_enabled": safety["order_routing_enabled"],
        "llm_order_generation": safety["llm_order_generation"],
        "orders_generated": 0,
    }


def run_once(cfg: Dict[str, Any]) -> Dict[str, Any]:
    now_sgt = _utcnow() + timedelta(hours=8)
    log.info("=== Oil De-escalation / Peace Dividend Thesis Cycle ===")

    symbols: List[str] = list(cfg["benchmarks"])
    for basket in cfg["baskets"].values():
        if not basket.get("enabled", True):
            continue
        for ticker in basket.get("tickers", []):
            symbol = ticker["yf_symbol"]
            if symbol not in symbols:
                symbols.append(symbol)

    prices = fetch_prices(symbols)
    available_count = sum(1 for item in prices.values() if item.get("available"))
    spy_symbol = cfg["benchmarks"][0] if cfg.get("benchmarks") else ""
    qqq_symbol = cfg["benchmarks"][1] if len(cfg.get("benchmarks", [])) > 1 else ""
    spy_chg = prices.get(spy_symbol, {}).get("day_change_pct")
    qqq_chg = prices.get(qqq_symbol, {}).get("day_change_pct")

    basket_signals: Dict[str, str] = {}
    primary_signals: List[Dict[str, Any]] = []
    ticker_evidence: List[Dict[str, Any]] = []
    basket_score = 0.0
    for basket_id, basket in cfg["baskets"].items():
        if not basket.get("enabled", True):
            continue
        signal, score, rows = score_basket(basket_id, basket, prices, spy_chg, qqq_chg, cfg)
        basket_signals[basket_id] = signal
        basket_score += score
        ticker_evidence.extend(rows)
        primary_signals.append({
            "basket": basket_id,
            "label": basket.get("label", basket_id),
            "signal": signal,
            "scoring_weight": basket["scoring_weight"],
            "basket_score": round(score, 2),
        })
        log.info("[%s] signal=%s score=%.2f / %s", basket_id, signal, score, basket["scoring_weight"])

    headline_score, headline_evidence = score_headlines(cfg)
    escalation_penalty, escalation_evidence = score_escalation(cfg)
    external_evidence = read_external_evidence(cfg)
    false_positive_penalty, false_positive_flags = evaluate_false_positive_rules(basket_signals, cfg)

    total_score = max(0.0, min(100.0, basket_score + headline_score - escalation_penalty - false_positive_penalty))
    status = score_to_status(total_score, cfg)
    confidence = score_to_confidence(total_score, basket_signals, cfg)
    cio_action = get_cio_action(status, confidence, cfg)
    add_allowed = compute_add_allowed(
        status,
        confidence,
        basket_signals,
        escalation_penalty,
        false_positive_penalty,
        external_evidence,
        cfg,
    )
    market_status = get_market_status(cfg)
    data_quality = "FULL" if available_count >= len(symbols) else ("PARTIAL" if available_count else "UNAVAILABLE")
    blind_spots = list(cfg.get("blind_spots", []))
    for item in external_evidence:
        if not item.get("available"):
            blind_spots.append(f"External evidence unavailable: {item.get('label')}")

    output = build_output(
        cfg=cfg,
        total_score=total_score,
        status=status,
        confidence=confidence,
        cio_action=cio_action,
        add_allowed=add_allowed,
        primary_signals=primary_signals,
        ticker_evidence=ticker_evidence,
        headline_score=headline_score,
        headline_evidence=headline_evidence,
        escalation_penalty=escalation_penalty,
        escalation_evidence=escalation_evidence,
        external_evidence=external_evidence,
        false_positive_penalty=false_positive_penalty,
        false_positive_flags=false_positive_flags,
        blind_spots=blind_spots,
        now_sgt=now_sgt,
        data_quality=data_quality,
        market_status_info=market_status,
    )
    log.info("Status=%s confidence=%s score=%.1f add_allowed=%s", status, confidence, total_score, add_allowed)
    return output


def _load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    env_path = _ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def save_output(output: Dict[str, Any], cfg: Dict[str, Any]) -> Path:
    out_cfg = cfg["output"]
    directory = _ROOT / out_cfg["local_dir"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / out_cfg["local_file"]
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    log.info("Saved locally: %s", path)
    return path


def push_to_github(output: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    env = _load_env()
    token = env.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN", "")
    if not token:
        log.warning("GITHUB_TOKEN not found - skipping GitHub push")
        return
    owner = env.get("GITHUB_USERNAME") or os.getenv("GITHUB_USERNAME", "sohweekian")
    repo = env.get("GITHUB_PAGES_REPO") or os.getenv("GITHUB_PAGES_REPO", "bluelotus")
    branch = env.get("GITHUB_BRANCH") or os.getenv("GITHUB_BRANCH", "main")
    path = cfg["output"]["github_path"]
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    sha = None
    try:
        req = urllib.request.Request(f"{url}?ref={branch}", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            sha = json.loads(response.read().decode("utf-8")).get("sha")
    except Exception:
        pass
    body: Dict[str, Any] = {
        "message": f"s9 oil peace dividend widget {_utcnow().strftime('%H:%M')}",
        "content": base64.b64encode(
            json.dumps(output, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        ).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="PUT",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        log.info("GitHub push %s: HTTP %s", path, response.status)


def main() -> None:
    parser = argparse.ArgumentParser(description="BlueLotus S9 Oil De-escalation / Peace Dividend widget")
    parser.add_argument("--once", action="store_true", help="Run one cycle then exit")
    args = parser.parse_args()

    cfg = load_config()
    refresh = int(cfg.get("refresh_interval_seconds", 600))
    if args.once:
        output = run_once(cfg)
        save_output(output, cfg)
        push_to_github(output, cfg)
        return

    while True:
        try:
            output = run_once(cfg)
            save_output(output, cfg)
            push_to_github(output, cfg)
        except Exception as exc:
            log.error("cycle failed: %s", exc, exc_info=True)
        log.info("Sleeping %d seconds", refresh)
        time.sleep(refresh)


if __name__ == "__main__":
    main()
