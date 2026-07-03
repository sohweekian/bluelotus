#!/usr/bin/env python3
"""
BlueLotus Superforecast/Brier forecast generator.

Research-only:
- Reads dataset_raw.json
- Generates BlueLotus Conservative forecasts and Analyst Consensus benchmark
- Writes research_forecasts.json
- Inserts forecasts into ticker_forecasts

No trade execution. No order APIs. No order recommendations are routed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_RESEARCH_OUTPUT = PROJECT_ROOT / "research" / "research_forecasts.json"
DEFAULT_DATA_OUTPUT = PROJECT_ROOT / "data" / "forecasts" / "research_forecasts_latest.json"

ENGINE_VERSION = "BlueLotus_Superforecast_v1.0"
HORIZONS = (7, 14, 30, 60, 90)
HORIZON_WEIGHTS = {7: 0.15, 14: 0.25, 30: 0.45, 60: 0.72, 90: 1.00}


def project_root() -> Path:
    p = Path.cwd()
    if (p / "core").exists() or (p / "mid").exists():
        return p
    if p.name.lower() in {"mid", "research"}:
        return p.parent
    return PROJECT_ROOT


def n(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).replace("SGT", "").replace("Z", "").strip()
    s = s.replace("T", " ").split("+")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return None


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def load_dataset(path: Path) -> Tuple[Dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def live_prices(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lp = dataset.get("live_prices") or {}
    if isinstance(lp, dict) and isinstance(lp.get("prices"), dict):
        lp = lp["prices"]
    skip = {"vix", "market_session", "top_movers", "cycle_ts", "ticker_count", "source", "_relative_volume_meta"}
    out: Dict[str, Dict[str, Any]] = {}
    for ticker, row in lp.items() if isinstance(lp, dict) else []:
        t = str(ticker).upper()
        if t.lower() in skip or t.startswith("_"):
            continue
        if isinstance(row, dict) and n(row.get("price")):
            out[t] = row
    return out


def get_universe(dataset: Dict[str, Any]) -> List[str]:
    root = project_root()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "mid"))
    try:
        from mid.ticker_universe import get_universe as central_universe  # type: ignore
        universe = central_universe(limit=200)
    except Exception:
        universe = sorted(live_prices(dataset).keys())[:200]
    prices = live_prices(dataset)
    return [t for t in universe if t in prices and n(prices[t].get("price"))][:200]


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, ensure_ascii=False), encoding="utf-8")


def sector_for(ticker: str, dataset: Dict[str, Any]) -> str:
    sec = (dataset.get("security_master") or {}).get(ticker, {})
    if isinstance(sec, dict):
        return str(sec.get("sector") or "UNKNOWN")
    return "UNKNOWN"


def theme_for(ticker: str, dataset: Dict[str, Any]) -> str:
    sec = (dataset.get("security_master") or {}).get(ticker, {})
    if isinstance(sec, dict):
        sector = str(sec.get("sector") or "").strip()
        industry = str(sec.get("industry") or "").strip()
        if sector and sector != "UNKNOWN":
            return f"{sector} / {industry}".strip(" /")
    return "UNCLASSIFIED"


def sector_pe_map(dataset: Dict[str, Any]) -> Dict[str, float]:
    fundamentals = dataset.get("fundamentals") or {}
    buckets: Dict[str, List[float]] = {}
    for ticker, fund in fundamentals.items() if isinstance(fundamentals, dict) else []:
        if not isinstance(fund, dict):
            continue
        pe = n(fund.get("pe_ttm_ratio") or fund.get("pe_ratio"))
        if pe is None or pe < 3 or pe > 120:
            continue
        buckets.setdefault(sector_for(str(ticker).upper(), dataset), []).append(pe)
    return {sector: float(statistics.median(values)) for sector, values in buckets.items() if values}


def ece_by_theme(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in dataset.get("event_correlations_all") or dataset.get("event_correlations") or []:
        if isinstance(row, dict) and row.get("theme"):
            out[str(row["theme"]).upper()] = row
    return out


def event_adjustment(ticker: str, dataset: Dict[str, Any]) -> Tuple[float, str]:
    theme = theme_for(ticker, dataset).upper()
    hit = None
    for key, row in ece_by_theme(dataset).items():
        if key in theme or theme in key:
            hit = row
            break
    if not hit:
        return 0.0, "no active ECE theme match"
    basket = n(hit.get("basket_move"), 0.0) or 0.0
    conf = n(hit.get("confidence"), 0.0) or 0.0
    adj = clamp((basket / 100.0) * (conf / 100.0), -0.05, 0.05)
    return adj, f"ECE {hit.get('theme')} basket {basket:+.2f}% confidence {conf:.0f}%"


def flow_adjustment(ticker: str, dataset: Dict[str, Any]) -> Tuple[float, str]:
    cf = (dataset.get("capital_flow") or {}).get(ticker, {})
    if not isinstance(cf, dict):
        return 0.0, "no capital flow"
    bias = str(cf.get("institutional_bias") or "").upper()
    main_net = n(cf.get("main_net") or cf.get("in_flow"), 0.0) or 0.0
    if "STRONG" in bias and ("INFLOW" in bias or "BUY" in bias or "BULL" in bias):
        return 0.025, f"capital flow {bias}"
    if "INFLOW" in bias or "BUY" in bias or main_net > 0:
        return 0.015, f"capital flow {bias or 'net positive'}"
    if "OUTFLOW" in bias or "SELL" in bias or main_net < 0:
        return -0.020, f"capital flow {bias or 'net negative'}"
    return 0.0, f"capital flow {bias or 'neutral'}"


def macro_adjustment(ticker: str, dataset: Dict[str, Any]) -> Tuple[float, str]:
    regime = dataset.get("regime") or {}
    state = str(regime.get("regime") or regime.get("regime_short") or "").upper()
    score = n(regime.get("score"), 0.0) or 0.0
    theme = theme_for(ticker, dataset).upper()
    treasury = dataset.get("treasury_yields") or {}
    nim = n(treasury.get("nim_proxy"), 0.0) or 0.0

    adj = 0.0
    reason = f"regime {state or 'UNKNOWN'} score {score:g}"
    if "RISK OFF" in state or score < -3:
        if "GOLD" in theme:
            adj += 0.04
        elif any(x in theme for x in ("UTILITY", "DEFENSE", "PHARMA")):
            adj += 0.01
        elif any(x in theme for x in ("QUANTUM", "SPACE", "SOFTWARE", "AI", "SEMIS", "SOLAR")):
            adj -= 0.06
        else:
            adj -= 0.03
    elif "RISK ON" in state or score > 3:
        adj += 0.03

    if "BANK" in theme and nim > 0:
        adj += 0.025
        reason += f", NIM proxy {nim:+.2f}"
    if "CLEAN ENERGY" in theme or "SOLAR" in theme:
        adj -= 0.025
    return clamp(adj, -0.10, 0.08), reason


def strategic_adjustment(ticker: str, dataset: Dict[str, Any]) -> Tuple[float, str]:
    theme = theme_for(ticker, dataset).upper()
    if "AI" in theme or "SEMI" in theme:
        return 0.025, "strategic AI/semi premium"
    if "GOLD" in theme:
        return 0.020, "safe-haven optionality"
    if "DEFENSE" in theme or "AEROSPACE" in theme:
        return 0.020, "defense backlog/geopolitical premium"
    if "BANK" in theme:
        return 0.015, "bank NIM thesis premium"
    if "QUANTUM" in theme:
        return -0.060, "speculative quantum execution discount"
    if "SPACE" in theme:
        return -0.035, "space execution/financing discount"
    if "SOLAR" in theme or "CLEAN ENERGY" in theme:
        return -0.040, "rate-sensitive clean energy discount"
    return 0.0, "no strategic premium"


def data_quality_penalty(ticker: str, dataset: Dict[str, Any], profitable: bool) -> Tuple[float, List[str]]:
    notes: List[str] = []
    penalty = 0.0
    freshness = (dataset.get("meta") or {}).get("freshness") or {}
    for key in ("live_prices", "fundamentals", "capital_flow"):
        grade = str((freshness.get(key) or {}).get("grade") or "").upper()
        if grade in {"STALE", "BREACH"}:
            penalty += 0.015
            notes.append(f"{key} freshness {grade}")
    if not profitable:
        penalty += 0.035
        notes.append("loss-making or EPS unavailable; revenue/EBITDA valuation unavailable")
    if sector_for(ticker, dataset).upper() == "UNKNOWN":
        penalty += 0.015
        notes.append("unknown sector classification")
    return clamp(penalty, 0.0, 0.10), notes


def analyst_context(ticker: str, dataset: Dict[str, Any], price: float) -> Tuple[Optional[float], Optional[float], str]:
    at = (dataset.get("analyst_targets") or {}).get(ticker, {})
    if not isinstance(at, dict):
        return None, None, "no analyst target"
    target = n(at.get("avg_target") or at.get("average"))
    if not target or price <= 0:
        return None, None, "no analyst target"
    upside = (target - price) / price * 100.0
    return target, upside, f"Moomoo analyst consensus {target:.2f} ({upside:+.1f}%)"


def add_horizon_fields(row: Dict[str, Any], price: float, ret90: float, probability90: float, prob_cap: float) -> None:
    for h in HORIZONS:
        weight = HORIZON_WEIGHTS[h]
        target = price * (1 + ret90 * weight)
        prob = 0.50 + (probability90 - 0.50) * math.sqrt(weight)
        row[f"target_price_{h}d"] = round(target, 6)
        row[f"probability_{h}d"] = round(clamp(prob, 0.32, prob_cap), 4)
        row[f"expected_return_{h}d"] = round((target - price) / price * 100.0, 4)


def bluelotus_valuation(ticker: str, dataset: Dict[str, Any], sector_pes: Dict[str, float]) -> Dict[str, Any]:
    prices = live_prices(dataset)
    price = n((prices.get(ticker) or {}).get("price"))
    if not price or price <= 0:
        raise ValueError(f"{ticker}: missing current price")

    fund = (dataset.get("fundamentals") or {}).get(ticker, {})
    fund = fund if isinstance(fund, dict) else {}
    eps = n(fund.get("earning_per_share"))
    own_pe = n(fund.get("pe_ttm_ratio") or fund.get("pe_ratio"))
    sector = sector_for(ticker, dataset)
    sector_pe = sector_pes.get(sector) or (own_pe if own_pe and 3 <= own_pe <= 120 else 20.0)
    sector_pe = clamp(sector_pe, 5.0, 85.0)
    profitable = bool(eps and eps > 0)

    basis_parts: List[str] = []
    if profitable:
        base = eps * sector_pe
        basis_parts.append(f"BL_base=EPS {eps:.4f} x sector_PE {sector_pe:.2f}")
    else:
        pct_from_low = n(fund.get("pct_from_52w_low"))
        mean_reversion = -0.08 if pct_from_low and pct_from_low > 120 else 0.0
        base = price * (1.0 + mean_reversion)
        basis_parts.append("BL_base=current_price proxy because EPS/revenue valuation unavailable")

    macro_adj, macro_reason = macro_adjustment(ticker, dataset)
    strategic_adj, strategic_reason = strategic_adjustment(ticker, dataset)
    flow_adj, flow_reason = flow_adjustment(ticker, dataset)
    ece_adj, ece_reason = event_adjustment(ticker, dataset)
    quality_penalty, quality_notes = data_quality_penalty(ticker, dataset, profitable)

    adjusted = base * (1 + macro_adj) * (1 + strategic_adj) * (1 + flow_adj) * (1 + ece_adj)
    safety = 0.10 + quality_penalty
    if profitable and sector != "UNKNOWN":
        safety -= 0.015
    safety = clamp(safety, 0.05, 0.18)
    raw_target = adjusted * (1 - safety)
    ret90 = clamp((raw_target - price) / price, -0.35, 0.45)

    analyst_target, analyst_upside, analyst_note = analyst_context(ticker, dataset, price)
    analyst_agreement = None
    if analyst_upside is not None:
        analyst_agreement = (analyst_upside >= 0 and ret90 >= 0) or (analyst_upside < 0 and ret90 < 0)

    probability90 = 0.50
    probability90 += min(0.13, abs(ret90) * 0.35)
    probability90 += 0.025 if flow_adj > 0 else -0.020 if flow_adj < 0 else 0.0
    probability90 += 0.020 if ece_adj > 0 else -0.020 if ece_adj < 0 else 0.0
    probability90 += 0.015 if analyst_agreement else -0.020 if analyst_agreement is False else 0.0
    probability90 -= quality_penalty * 0.70
    probability90 = clamp(probability90, 0.34, 0.72)

    direction = "UP" if ret90 > 0.005 else "DOWN" if ret90 < -0.005 else "NEUTRAL"
    basis_parts.extend([
        macro_reason,
        strategic_reason,
        flow_reason,
        ece_reason,
        f"safety_margin {safety:.2%}",
        analyst_note,
    ])

    row: Dict[str, Any] = {
        "ticker": ticker,
        "current_price": round(price, 6),
        "prediction_method": "BLUELOTUS_CONSERVATIVE",
        "forecast_direction": direction,
        "confidence": round(probability90, 4),
        "bluelotus_score": round((probability90 - 0.50) * 100.0, 4),
        "analyst_target": analyst_target,
        "analyst_upside_pct": round(analyst_upside, 4) if analyst_upside is not None else None,
        "regime": str((dataset.get("regime") or {}).get("regime") or (dataset.get("regime") or {}).get("regime_short") or "UNKNOWN"),
        "sector_theme": theme_for(ticker, dataset),
        "method_basis": " | ".join(basis_parts),
        "risk_notes": "; ".join(quality_notes) if quality_notes else "standard BlueLotus conservative safety margin applied",
        "event_definition": "UP: actual_price >= target_price_h; DOWN: actual_price <= target_price_h; NEUTRAL: actual absolute move <= 2%",
        "created_by": "BlueLotus_Superforecast_Engine",
    }
    add_horizon_fields(row, price, ret90, probability90, 0.72)
    return row


def analyst_forecast(ticker: str, dataset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prices = live_prices(dataset)
    price = n((prices.get(ticker) or {}).get("price"))
    if not price or price <= 0:
        return None
    at = (dataset.get("analyst_targets") or {}).get(ticker, {})
    if not isinstance(at, dict):
        return None
    target90 = n(at.get("avg_target") or at.get("average"))
    if not target90 or target90 <= 0:
        return None

    ret90 = clamp((target90 - price) / price, -0.50, 0.80)
    buy = n(at.get("buy"), 0.0) or 0.0
    sell = n(at.get("sell"), 0.0) or 0.0
    analysts = n(at.get("total_analysts"), 0.0) or 0.0
    sentiment_component = clamp((buy - sell) / 100.0 * 0.10, -0.10, 0.10)
    upside_component = clamp(math.tanh(ret90 * 2.0) * 0.16, -0.16, 0.16)
    coverage_component = 0.015 if analysts >= 10 else -0.015 if analysts < 3 else 0.0
    probability90 = clamp(0.50 + abs(upside_component) + max(sentiment_component, -0.03) + coverage_component, 0.34, 0.76)
    direction = "UP" if ret90 > 0.005 else "DOWN" if ret90 < -0.005 else "NEUTRAL"

    row: Dict[str, Any] = {
        "ticker": ticker,
        "current_price": round(price, 6),
        "prediction_method": "ANALYST_CONSENSUS",
        "forecast_direction": direction,
        "confidence": round(probability90, 4),
        "bluelotus_score": None,
        "analyst_target": round(target90, 6),
        "analyst_upside_pct": round(ret90 * 100.0, 4),
        "regime": str((dataset.get("regime") or {}).get("regime") or (dataset.get("regime") or {}).get("regime_short") or "UNKNOWN"),
        "sector_theme": theme_for(ticker, dataset),
        "method_basis": "Moomoo analyst consensus benchmark; used for accuracy comparison, not as BlueLotus primary anchor",
        "risk_notes": "sell-side benchmark; may reflect consensus herding and target lag",
        "event_definition": "UP: actual_price >= target_price_h; DOWN: actual_price <= target_price_h; NEUTRAL: actual absolute move <= 2%",
        "created_by": "BlueLotus_Superforecast_Engine",
    }
    add_horizon_fields(row, price, ret90, probability90, 0.76)
    return row


def make_forecast_id(snapshot_id: str, ticker: str, method: str) -> str:
    digest = hashlib.sha1(f"{snapshot_id}|{ticker}|{method}".encode("utf-8")).hexdigest()[:10]
    method_code = "BL" if method == "BLUELOTUS_CONSERVATIVE" else "AN"
    compact_ticker = ticker[:5]
    return f"BLF-{compact_ticker}-{method_code}-{digest}"


def generate_forecasts(dataset: Dict[str, Any], dataset_sha: str, dataset_path: Path) -> Dict[str, Any]:
    meta = dataset.get("meta") or {}
    forecast_dt = parse_dt(meta.get("generated_at")) or datetime.now()
    snapshot_seed = f"{forecast_dt.isoformat()}|{dataset_sha[:16]}"
    snapshot_id = f"SF-{forecast_dt.strftime('%Y%m%d-%H%M%S')}-{hashlib.sha1(snapshot_seed.encode('utf-8')).hexdigest()[:8]}"
    sector_pes = sector_pe_map(dataset)
    tickers = get_universe(dataset)

    forecasts: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for ticker in tickers:
        try:
            bl = bluelotus_valuation(ticker, dataset, sector_pes)
            bl["forecast_id"] = make_forecast_id(snapshot_id, ticker, bl["prediction_method"])
            forecasts.append(bl)
        except Exception as exc:
            skipped.append({"ticker": ticker, "reason": str(exc)})

        an = analyst_forecast(ticker, dataset)
        if an:
            an["forecast_id"] = make_forecast_id(snapshot_id, ticker, an["prediction_method"])
            forecasts.append(an)

    for row in forecasts:
        row["snapshot_id"] = snapshot_id
        row["forecast_date"] = forecast_dt.isoformat(sep=" ")
        row["dataset_generated_at"] = meta.get("generated_at")
        row["dataset_sha256"] = dataset_sha
        row["source_dataset_path"] = str(dataset_path)

    methods = sorted({row["prediction_method"] for row in forecasts})
    return {
        "meta": {
            "engine_version": ENGINE_VERSION,
            "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "snapshot_id": snapshot_id,
            "forecast_date": forecast_dt.isoformat(sep=" "),
            "dataset_generated_at": meta.get("generated_at"),
            "dataset_sha256": dataset_sha,
            "ticker_count": len(tickers),
            "forecast_count": len(forecasts),
            "methods": methods,
            "horizons_days": list(HORIZONS),
            "doctrine": "Research-only BlueLotus conservative forecasts; analyst consensus is a benchmark opponent, not the house method.",
        },
        "forecasts": forecasts,
        "skipped": skipped,
    }


INSERT_SQL = """
INSERT INTO ticker_forecasts (
    forecast_id, snapshot_id, forecast_date, dataset_generated_at, dataset_sha256,
    ticker, current_price, prediction_method, forecast_direction,
    target_price_7d, target_price_14d, target_price_30d, target_price_60d, target_price_90d,
    probability_7d, probability_14d, probability_30d, probability_60d, probability_90d,
    expected_return_7d, expected_return_14d, expected_return_30d, expected_return_60d, expected_return_90d,
    confidence, bluelotus_score, analyst_target, analyst_upside_pct,
    regime, sector_theme, method_basis, risk_notes, source_dataset_path, created_by, forecast_json
) VALUES (
    %(forecast_id)s, %(snapshot_id)s, %(forecast_date)s, %(dataset_generated_at)s, %(dataset_sha256)s,
    %(ticker)s, %(current_price)s, %(prediction_method)s, %(forecast_direction)s,
    %(target_price_7d)s, %(target_price_14d)s, %(target_price_30d)s, %(target_price_60d)s, %(target_price_90d)s,
    %(probability_7d)s, %(probability_14d)s, %(probability_30d)s, %(probability_60d)s, %(probability_90d)s,
    %(expected_return_7d)s, %(expected_return_14d)s, %(expected_return_30d)s, %(expected_return_60d)s, %(expected_return_90d)s,
    %(confidence)s, %(bluelotus_score)s, %(analyst_target)s, %(analyst_upside_pct)s,
    %(regime)s, %(sector_theme)s, %(method_basis)s, %(risk_notes)s, %(source_dataset_path)s, %(created_by)s, %(forecast_json)s
)
ON DUPLICATE KEY UPDATE
    snapshot_id = VALUES(snapshot_id),
    forecast_date = VALUES(forecast_date),
    dataset_generated_at = VALUES(dataset_generated_at),
    dataset_sha256 = VALUES(dataset_sha256),
    current_price = VALUES(current_price),
    prediction_method = VALUES(prediction_method),
    forecast_direction = VALUES(forecast_direction),
    target_price_7d = VALUES(target_price_7d),
    target_price_14d = VALUES(target_price_14d),
    target_price_30d = VALUES(target_price_30d),
    target_price_60d = VALUES(target_price_60d),
    target_price_90d = VALUES(target_price_90d),
    probability_7d = VALUES(probability_7d),
    probability_14d = VALUES(probability_14d),
    probability_30d = VALUES(probability_30d),
    probability_60d = VALUES(probability_60d),
    probability_90d = VALUES(probability_90d),
    expected_return_7d = VALUES(expected_return_7d),
    expected_return_14d = VALUES(expected_return_14d),
    expected_return_30d = VALUES(expected_return_30d),
    expected_return_60d = VALUES(expected_return_60d),
    expected_return_90d = VALUES(expected_return_90d),
    confidence = VALUES(confidence),
    bluelotus_score = VALUES(bluelotus_score),
    analyst_target = VALUES(analyst_target),
    analyst_upside_pct = VALUES(analyst_upside_pct),
    regime = VALUES(regime),
    sector_theme = VALUES(sector_theme),
    method_basis = VALUES(method_basis),
    risk_notes = VALUES(risk_notes),
    source_dataset_path = VALUES(source_dataset_path),
    created_by = VALUES(created_by),
    forecast_json = VALUES(forecast_json),
    created_at = CURRENT_TIMESTAMP
"""


def insert_forecasts(package: Dict[str, Any]) -> Dict[str, Any]:
    root = project_root()
    sys.path.insert(0, str(root))

    from dotenv import load_dotenv
    from mid.bluelotus_forecast_tables import create_tables
    from core.db import get_connection

    load_dotenv(root / ".env")
    create_tables()
    conn = get_connection()
    processed = 0
    try:
        cur = conn.cursor()
        for row in package.get("forecasts", []):
            payload = dict(row)
            payload["forecast_json"] = json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True)
            for key in ("forecast_date", "dataset_generated_at"):
                payload[key] = parse_dt(payload.get(key))
            cur.execute(INSERT_SQL, payload)
            processed += 1
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"db_status": "inserted_or_updated", "rows_processed": processed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BlueLotus Superforecast/Brier forecast rows")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--research-output", type=Path, default=DEFAULT_RESEARCH_OUTPUT)
    parser.add_argument("--data-output", type=Path, default=DEFAULT_DATA_OUTPUT)
    parser.add_argument("--skip-db", action="store_true", help="Write JSON only; do not insert into DB")
    args = parser.parse_args()

    dataset, dataset_sha = load_dataset(args.dataset)
    package = generate_forecasts(dataset, dataset_sha, args.dataset)
    db_result = {"db_status": "skipped"}
    if not args.skip_db:
        db_result = insert_forecasts(package)
    package["database"] = db_result

    write_json(args.research_output, package)
    write_json(args.data_output, package)

    meta = package["meta"]
    print("BlueLotus Superforecast generated.")
    print(f"Snapshot : {meta['snapshot_id']}")
    print(f"Tickers  : {meta['ticker_count']}")
    print(f"Forecasts: {meta['forecast_count']} ({', '.join(meta['methods'])})")
    print(f"DB       : {db_result.get('db_status')} rows={db_result.get('rows_processed', 0)}")
    print(f"Output   : {args.research_output}")


if __name__ == "__main__":
    main()

