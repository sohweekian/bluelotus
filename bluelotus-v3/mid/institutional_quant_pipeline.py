#!/usr/bin/env python3
"""
BlueLotus MID -- Institutional Quant process runner.

This script turns the institutional quant requirements into an auditable
database-backed process layer:

1. Read data/frontend/dataset_raw.json.
2. Run readiness processes over the current dataset snapshot.
3. Store the input snapshot, run summary, process metrics, and warnings in MySQL.
4. Let mid/export_dataset_raw.py extract the latest completed run into the next
   dataset_raw.json under the "institutional_quant" key.

This is a foundation layer, not a full quant engine. It makes gaps visible and
machine-readable so future backtesting, risk, execution, and governance modules
can attach to the same database contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

RUN_VERSION = "v0.1"
DEFAULT_DATASET = Path(r"C:\bluelotus3\data\frontend\dataset_raw.json")

REQUIRED_TOP_LEVEL_SECTIONS = [
    "meta",
    "source_health",
    "regime",
    "portfolio",
    "live_prices",
    "fear_greed",
    "analyst_targets",
    "event_correlations",
    "ticker_sentiment",
    "fundamentals",
    "capital_flow",
    "treasury_yields",
    "signals",
    "signals_latest",
]

INSTITUTIONAL_TARGETS = [
    "point_in_time_history",
    "bias_controls",
    "feature_registry",
    "backtesting",
    "statistical_validation",
    "risk_model",
    "portfolio_construction",
    "execution_records",
    "monitoring",
    "governance_audit",
]

THEME_MAP = {
    "AU": "GOLD / SAFE HAVEN",
    "NEM": "GOLD / SAFE HAVEN",
    "NVDA": "AI / SEMIS",
    "AMD": "AI / SEMIS",
    "AVGO": "AI / SEMIS",
    "MRVL": "AI / SEMIS",
    "MU": "AI / SEMIS",
    "QBTS": "QUANTUM",
    "QUBT": "QUANTUM",
    "RGTI": "QUANTUM",
    "IONQ": "QUANTUM",
    "BAC": "BANKS / LIQUIDITY",
    "WFC": "BANKS / LIQUIDITY",
    "JPM": "BANKS / LIQUIDITY",
    "FCX": "COPPER / INDUSTRIAL METALS",
    "CCJ": "ENERGY / URANIUM",
}


@dataclass
class ProcessResult:
    name: str
    score: float
    status: str
    label: str
    result: Dict[str, Any]
    metrics: Dict[str, Any]
    warnings: List[str]
    version: str = RUN_VERSION


def project_root() -> Path:
    p = Path.cwd()
    if (p / "core").exists() or (p / "mid").exists():
        return p
    if p.name.lower() == "mid":
        return p.parent
    return Path(r"C:\bluelotus3")


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip().replace("SGT", "").replace("Z", "")
    if s.endswith("+00:00"):
        s = s[:-6]
    s = s[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def sha256_dataset(dataset: Dict[str, Any]) -> str:
    return hashlib.sha256(json_dumps(dataset).encode("utf-8", errors="replace")).hexdigest()


def readiness_label(score: float) -> str:
    if score >= 85:
        return "INSTITUTIONAL_READY"
    if score >= 70:
        return "ADVANCED"
    if score >= 50:
        return "DEVELOPING"
    return "FOUNDATION"


def status_from_score(score: float) -> str:
    if score >= 80:
        return "PASS"
    if score >= 50:
        return "WARNING"
    return "FAIL"


def clamp_score(score: float) -> float:
    return round(max(0.0, min(100.0, float(score))), 3)


def result(name: str, score: float, result_body: Dict[str, Any],
           metrics: Dict[str, Any], warnings: Iterable[str]) -> ProcessResult:
    s = clamp_score(score)
    return ProcessResult(
        name=name,
        score=s,
        status=status_from_score(s),
        label=readiness_label(s),
        result=result_body,
        metrics=metrics,
        warnings=[w for w in warnings if w],
    )


def load_dataset(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("dataset_raw.json must contain a top-level JSON object")
    return data


def strip_prior_process_layer(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Remove this runner's previous export block before hashing/analyzing input."""
    clean = dict(dataset)
    clean.pop("institutional_quant", None)
    return clean


def prices_map(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    live = dataset.get("live_prices") or {}
    if not isinstance(live, dict):
        return {}
    if isinstance(live.get("prices"), dict):
        live = live["prices"]
    skip = {"vix", "market_session", "top_movers", "cycle_ts", "ticker_count", "source"}
    return {
        str(k).upper(): v
        for k, v in live.items()
        if k not in skip and isinstance(v, dict) and "price" in v
    }


def top_movers(dataset: Dict[str, Any], limit: int = 15) -> List[Dict[str, Any]]:
    live = dataset.get("live_prices") or {}
    if isinstance(live, dict) and isinstance(live.get("top_movers"), list):
        return live["top_movers"][:limit]
    rows = []
    for ticker, data in prices_map(dataset).items():
        try:
            move = float(data.get("chg_pct") or 0)
        except Exception:
            move = 0.0
        rows.append({
            "ticker": ticker,
            "price": data.get("price"),
            "chg_pct": move,
            "volume": data.get("volume"),
        })
    rows.sort(key=lambda r: abs(float(r.get("chg_pct") or 0)), reverse=True)
    return rows[:limit]


def portfolio_positions(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    portfolio = dataset.get("portfolio") or {}
    if not isinstance(portfolio, dict):
        return {}
    positions = portfolio.get("positions") or {}
    return positions if isinstance(positions, dict) else {}


def freshness_summary(dataset: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    freshness = ((dataset.get("meta") or {}).get("freshness") or {})
    stale = []
    unknown = []
    for section, item in freshness.items():
        if section == "thresholds" or not isinstance(item, dict):
            continue
        grade = str(item.get("grade") or "UNKNOWN").upper()
        if grade == "STALE":
            stale.append(section)
        elif grade == "UNKNOWN":
            unknown.append(section)
    metrics = {
        "sections_tracked": len([k for k in freshness if k != "thresholds"]),
        "fresh_sections": len([
            k for k, v in freshness.items()
            if k != "thresholds" and isinstance(v, dict) and v.get("grade") == "FRESH"
        ]),
        "stale_sections": stale,
        "unknown_sections": unknown,
    }
    warnings = []
    if stale:
        warnings.append("Stale dataset sections: " + ", ".join(stale))
    if unknown:
        warnings.append("Unknown freshness sections: " + ", ".join(unknown))
    return metrics, warnings


def process_data_quality(dataset: Dict[str, Any]) -> ProcessResult:
    missing = [s for s in REQUIRED_TOP_LEVEL_SECTIONS if s not in dataset or dataset.get(s) in (None, {}, [])]
    source_health = dataset.get("source_health") or []
    meta = dataset.get("meta") or {}
    freshness, freshness_warnings = freshness_summary(dataset)

    sources_expected = int(meta.get("sources_expected") or len(source_health) or 0)
    external_active = int(meta.get("external_sources_active") or 0)
    total_signals = int(meta.get("total_signals") or 0)
    source_coverage = (external_active / sources_expected * 100.0) if sources_expected else 0.0
    section_score = (1.0 - len(missing) / max(1, len(REQUIRED_TOP_LEVEL_SECTIONS))) * 35.0
    freshness_score = (
        freshness["fresh_sections"] / max(1, freshness["sections_tracked"]) * 25.0
        if freshness["sections_tracked"] else 0.0
    )
    source_score = min(25.0, source_coverage / 100.0 * 25.0)
    signal_score = 15.0 if total_signals >= 1000 else 8.0 if total_signals else 0.0
    score = section_score + freshness_score + source_score + signal_score

    warnings = list(freshness_warnings)
    if missing:
        warnings.append("Missing or empty required sections: " + ", ".join(missing))

    return result(
        "data_quality",
        score,
        {
            "purpose": "Validate current dataset completeness, freshness, source coverage, and signal depth.",
            "coverage_status": "usable" if score >= 70 else "needs_attention",
            "required_sections_missing": missing,
        },
        {
            "top_level_sections": len(dataset),
            "required_sections": len(REQUIRED_TOP_LEVEL_SECTIONS),
            "missing_required_sections": len(missing),
            "sources_expected": sources_expected,
            "external_sources_active": external_active,
            "source_coverage_pct": round(source_coverage, 2),
            "total_signals": total_signals,
            **freshness,
        },
        warnings,
    )


def process_point_in_time(dataset: Dict[str, Any]) -> ProcessResult:
    meta = dataset.get("meta") or {}
    latest = dataset.get("signals_latest") or []
    generated_at = parse_dt(meta.get("generated_at"))
    latest_signal_at = parse_dt(meta.get("latest_signal_at"))
    timestamped = 0
    future_rows = 0
    for row in latest:
        if not isinstance(row, dict):
            continue
        dt = parse_dt(row.get("received_at"))
        if dt:
            timestamped += 1
            if generated_at and dt > generated_at:
                future_rows += 1

    timestamp_score = 35.0 if generated_at and latest_signal_at else 10.0
    signal_ts_score = (timestamped / max(1, len(latest))) * 25.0 if latest else 0.0
    future_score = 20.0 if future_rows == 0 else max(0.0, 20.0 - future_rows)
    snapshot_score = 15.0
    event_time_score = 5.0
    score = timestamp_score + signal_ts_score + future_score + snapshot_score + event_time_score

    warnings = [
        "This validates the current snapshot only; full point-in-time history requires storing every export.",
        "Event time, publication time, and ingestion time are not separated for every section.",
    ]
    if future_rows:
        warnings.append(f"{future_rows} latest signal rows appear newer than dataset meta.generated_at.")

    return result(
        "point_in_time_readiness",
        score,
        {
            "purpose": "Check whether the current dataset can support point-in-time reconstruction.",
            "current_snapshot_is_hashable": True,
            "full_history_required": True,
        },
        {
            "dataset_generated_at": meta.get("generated_at"),
            "latest_signal_at": meta.get("latest_signal_at"),
            "signals_latest_count": len(latest) if isinstance(latest, list) else 0,
            "signals_with_received_at": timestamped,
            "future_timestamp_rows": future_rows,
        },
        warnings,
    )


def process_bias_controls(dataset: Dict[str, Any]) -> ProcessResult:
    signals = dataset.get("signals_latest") or []
    security_master = dataset.get("security_master") if isinstance(dataset.get("security_master"), dict) else {}
    security_meta = security_master.get("_meta", {}) if isinstance(security_master, dict) else {}
    raw_with_urls = 0
    raw_with_payload = 0
    raw_with_received_at = 0
    if isinstance(signals, list):
        for row in signals:
            if not isinstance(row, dict):
                continue
            raw_with_urls += 1 if row.get("source_url") else 0
            raw_with_payload += 1 if row.get("raw_payload") else 0
            raw_with_received_at += 1 if row.get("received_at") else 0

    has_corporate_actions = "corporate_actions" in dataset
    has_identifier_master = bool(security_master) or "ticker_mapping" in dataset
    has_delisting_data = "delistings" in dataset
    provenance_score = min(30.0, (raw_with_received_at / max(1, len(signals))) * 20.0 + (raw_with_payload / max(1, len(signals))) * 10.0)
    identifier_score = 20.0 if has_identifier_master else 4.0
    corp_action_score = 20.0 if has_corporate_actions else 4.0
    delisting_score = 15.0 if has_delisting_data else 2.0
    source_url_score = min(15.0, (raw_with_urls / max(1, len(signals))) * 15.0)
    score = provenance_score + identifier_score + corp_action_score + delisting_score + source_url_score

    warnings = []
    if not has_identifier_master:
        warnings.append("No security master or ticker mapping section found.")
    if not has_corporate_actions:
        warnings.append("No corporate action adjustment layer found.")
    if not has_delisting_data:
        warnings.append("No delisting/survivorship-bias control layer found.")

    return result(
        "bias_controls",
        score,
        {
            "purpose": "Identify bias-control readiness for quant research and backtesting.",
            "bias_controls_are_partial": True,
        },
        {
            "latest_signals": len(signals) if isinstance(signals, list) else 0,
            "signals_with_received_at": raw_with_received_at,
            "signals_with_raw_payload": raw_with_payload,
            "signals_with_source_url": raw_with_urls,
            "has_security_master": has_identifier_master,
            "security_master_ticker_count": security_meta.get("ticker_count"),
            "security_master_unknown_sector_count": security_meta.get("unknown_sector_count"),
            "has_corporate_actions": has_corporate_actions,
            "has_delistings": has_delisting_data,
        },
        warnings,
    )


def process_signal_validation(dataset: Dict[str, Any]) -> ProcessResult:
    signals_by_source = dataset.get("signals") or {}
    source_health = dataset.get("source_health") or []
    latest = dataset.get("signals_latest") or []
    active_sources = [s for s in source_health if isinstance(s, dict) and s.get("active")]
    quality_scores = []
    for rows in signals_by_source.values() if isinstance(signals_by_source, dict) else []:
        for row in rows if isinstance(rows, list) else []:
            q = row.get("quality_score") if isinstance(row, dict) else None
            if q is not None:
                try:
                    quality_scores.append(float(q))
                except Exception:
                    pass
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    source_score = min(35.0, len(active_sources) / max(1, len(source_health)) * 35.0)
    quality_score = min(25.0, avg_quality * 25.0)
    latest_score = 20.0 if len(latest) >= 100 else 10.0 if latest else 0.0
    validation_score = 10.0 if "signal_validation" in dataset else 0.0
    backtest_score = 10.0 if "backtests" in dataset or "backtest_results" in dataset else 0.0
    score = source_score + quality_score + latest_score + validation_score + backtest_score

    warnings = []
    if validation_score == 0.0:
        warnings.append("No historical signal validation metrics found in dataset.")
    if backtest_score == 0.0:
        warnings.append("No backtest results found in dataset.")

    return result(
        "signal_validation",
        score,
        {
            "purpose": "Measure whether current signals have statistical validation and historical evidence.",
            "current_signal_tape_is_available": bool(latest),
            "historical_validation_required": True,
        },
        {
            "sources_active": len(active_sources),
            "source_health_rows": len(source_health) if isinstance(source_health, list) else 0,
            "latest_signal_rows": len(latest) if isinstance(latest, list) else 0,
            "quality_score_count": len(quality_scores),
            "average_quality_score": round(avg_quality, 4),
            "has_backtest_results": backtest_score > 0,
            "has_signal_validation_section": validation_score > 0,
        },
        warnings,
    )


def process_risk_model(dataset: Dict[str, Any]) -> ProcessResult:
    portfolio = dataset.get("portfolio") or {}
    positions = portfolio_positions(dataset)
    risk_metrics = dataset.get("risk_metrics") if isinstance(dataset.get("risk_metrics"), dict) else {}
    total_assets = float(portfolio.get("total_assets") or portfolio.get("total_value") or 0) if isinstance(portfolio, dict) else 0.0
    cash = float(portfolio.get("cash") or 0) if isinstance(portfolio, dict) else 0.0
    exposures = {}
    largest_position = None
    largest_weight = 0.0
    for ticker, pos in positions.items():
        value = float((pos or {}).get("mkt_val") or 0)
        weight = value / total_assets if total_assets else 0.0
        theme = THEME_MAP.get(str(ticker).upper(), "UNCLASSIFIED")
        exposures[theme] = exposures.get(theme, 0.0) + weight
        if weight > largest_weight:
            largest_weight = weight
            largest_position = str(ticker).upper()

    regime = dataset.get("regime") or {}
    vix_level = regime.get("vix_level") if isinstance(regime, dict) else None
    event_correlations = dataset.get("event_correlations") or []
    has_theme_stress = isinstance(event_correlations, list) and len(event_correlations) >= 10
    has_risk_metrics = bool(risk_metrics)
    has_var_proxy = bool(risk_metrics.get("var_proxy")) if has_risk_metrics else False
    has_formal_var = "var" in dataset or "risk_model" in dataset or bool(risk_metrics.get("historical_var"))
    has_factor_model = "factor_exposures" in dataset or "risk_model" in dataset
    has_beta = risk_metrics.get("weighted_beta") is not None if has_risk_metrics else False
    if has_risk_metrics:
        largest_metric = risk_metrics.get("largest_position") or {}
        largest_weight = float(largest_metric.get("weight") or largest_weight or 0)
        largest_position = largest_metric.get("ticker") or largest_position
        exposures = risk_metrics.get("sector_exposure") or exposures
    concentration_score = 20.0 if largest_weight <= 0.30 else 12.0 if largest_weight <= 0.45 else 4.0
    cash_score = 10.0 if total_assets and cash / total_assets >= 0.05 else 4.0
    regime_score = 20.0 if isinstance(regime, dict) and regime.get("regime") else 5.0
    theme_score = 15.0 if has_theme_stress else 5.0
    telemetry_score = 20.0 if has_risk_metrics else 4.0
    beta_score = 10.0 if has_beta else 2.0
    var_score = 15.0 if has_formal_var else 10.0 if has_var_proxy else 3.0
    factor_score = 10.0 if has_factor_model else 3.0
    score = concentration_score + cash_score + regime_score + theme_score + telemetry_score + beta_score + var_score + factor_score
    if not has_formal_var:
        score = min(score, 78.0)

    warnings = []
    if largest_weight > 0.30:
        warnings.append(f"Largest position weight is high: {largest_position} at {largest_weight:.1%}.")
    if not has_factor_model:
        warnings.append("No formal factor exposure model found.")
    if has_var_proxy and not has_formal_var:
        warnings.append("Only interim var_proxy is present; historical VaR/CVaR still required.")
    elif not has_formal_var:
        warnings.append("No VaR/CVaR risk model output found.")

    return result(
        "risk_model",
        score,
        {
            "purpose": "Assess current portfolio and market risk observability.",
            "portfolio_risk_observable": bool(positions),
            "formal_risk_model_required": True,
        },
        {
            "position_count": len(positions),
            "total_assets": total_assets,
            "cash": cash,
            "cash_weight": round(cash / total_assets, 4) if total_assets else None,
            "largest_position": largest_position,
            "largest_position_weight": round(largest_weight, 4),
            "theme_exposures": {k: round(v, 4) for k, v in sorted(exposures.items())},
            "regime": regime.get("regime") if isinstance(regime, dict) else None,
            "regime_score": regime.get("score") if isinstance(regime, dict) else None,
            "vix_level": vix_level,
            "has_event_correlation_stress": has_theme_stress,
            "has_risk_metrics": has_risk_metrics,
            "has_var_proxy": has_var_proxy,
            "has_factor_model": has_factor_model,
            "has_formal_var": has_formal_var,
            "weighted_beta": risk_metrics.get("weighted_beta") if has_risk_metrics else None,
            "constraint_breaches": risk_metrics.get("constraint_breaches") if has_risk_metrics else [],
        },
        warnings,
    )


def process_portfolio_construction(dataset: Dict[str, Any]) -> ProcessResult:
    positions = portfolio_positions(dataset)
    has_target_weights = "target_weights" in dataset or "portfolio_targets" in dataset
    has_optimizer = "optimizer" in dataset or "portfolio_optimizer" in dataset
    has_constraints = "portfolio_constraints" in dataset or "risk_limits" in dataset
    has_mandates = "portfolio_mandates" in dataset
    has_catalysts = bool((dataset.get("catalyst_calendar") or {}).get("portfolio_only")) if isinstance(dataset.get("catalyst_calendar"), dict) else False
    score = 20.0 if positions else 0.0
    score += 20.0 if has_constraints else 5.0
    score += 20.0 if has_target_weights else 3.0
    score += 20.0 if has_optimizer else 2.0
    score += 10.0 if has_mandates else 2.0
    score += 10.0 if has_catalysts else 4.0

    warnings = []
    if not has_target_weights:
        warnings.append("No target-weight generation found.")
    if not has_optimizer:
        warnings.append("No constraint-aware optimizer output found.")
    if not has_constraints:
        warnings.append("No formal portfolio constraints or risk limits found.")

    return result(
        "portfolio_construction",
        score,
        {
            "purpose": "Check whether research signals can become target positions under constraints.",
            "position_state_available": bool(positions),
            "optimizer_required": True,
        },
        {
            "position_count": len(positions),
            "has_target_weights": has_target_weights,
            "has_optimizer": has_optimizer,
            "has_constraints": has_constraints,
            "has_portfolio_mandates": has_mandates,
            "has_portfolio_catalysts": has_catalysts,
        },
        warnings,
    )


def process_execution_readiness(dataset: Dict[str, Any]) -> ProcessResult:
    execution_keys = ["orders", "fills", "trade_lifecycle", "execution", "transaction_cost_analysis"]
    present = [k for k in execution_keys if k in dataset and isinstance(dataset.get(k), dict)]
    cio_layer = dataset.get("cio_decisions") if isinstance(dataset.get("cio_decisions"), dict) else {}
    orders_layer = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    fills_layer = dataset.get("fills") if isinstance(dataset.get("fills"), dict) else {}
    execution_layer = dataset.get("execution") if isinstance(dataset.get("execution"), dict) else {}
    lifecycle_layer = dataset.get("trade_lifecycle") if isinstance(dataset.get("trade_lifecycle"), dict) else {}
    tca_layer = dataset.get("transaction_cost_analysis") if isinstance(dataset.get("transaction_cost_analysis"), dict) else {}
    has_cio = bool(cio_layer) or "cio_action" in dataset
    cio_only = str((cio_layer or {}).get("execution_authority") or "").upper().startswith("CIO_ONLY")
    orders_generated = bool((cio_layer or {}).get("orders_generated"))
    orders_generated = orders_generated or bool(orders_layer.get("orders_generated_by_pipeline"))
    orders_generated = orders_generated or bool(execution_layer.get("orders_generated_by_pipeline"))
    pending_review_count = int((cio_layer or {}).get("pending_review_count") or 0) if cio_layer else 0

    read_only_order_history = orders_layer.get("status") in {"operational", "partial_error", "no_records"}
    read_only_deal_history = fills_layer.get("status") in {"operational", "partial_error", "no_records"}
    read_only_order_history = read_only_order_history or bool(execution_layer.get("read_only_order_history_extraction"))
    read_only_deal_history = read_only_deal_history or bool(execution_layer.get("read_only_deal_history_extraction"))
    has_lifecycle = bool(lifecycle_layer)
    has_tca = bool(tca_layer)
    has_manual_fill_import_contract = bool(
        (execution_layer.get("manual_fill_import_contract") or {}).get("status")
        or lifecycle_layer.get("manual_fill_import_contract")
        or tca_layer.get("manual_fill_import_required")
    )
    open_order_count = int(orders_layer.get("open_order_count") or 0)
    historical_order_count = int(orders_layer.get("historical_order_count") or 0)
    open_deal_count = int(fills_layer.get("open_deal_count") or 0)
    historical_deal_count = int(fills_layer.get("historical_deal_count") or 0)
    actual_order_records = open_order_count + historical_order_count
    actual_deal_records = open_deal_count + historical_deal_count

    score = 10.0
    if has_cio:
        score += 20.0
    if cio_only and not orders_generated:
        score += 20.0
    if execution_layer:
        score += 15.0
    if read_only_order_history:
        score += 10.0
    if read_only_deal_history:
        score += 10.0
    if has_lifecycle:
        score += 10.0
    if has_tca:
        score += 10.0
    if has_manual_fill_import_contract:
        score += 5.0
    if actual_order_records and actual_deal_records:
        score += 5.0
    if has_cio and cio_only and not present:
        score = min(max(score, 70.0), 75.0)
    if has_cio and cio_only and present and not actual_order_records and not actual_deal_records:
        score = min(max(score, 85.0), 90.0)

    warnings = []
    if orders_generated:
        warnings.append("Pipeline reports generated orders; this violates the CIO-only execution doctrine.")
        score = min(score, 49.0)
    elif has_cio and cio_only and read_only_order_history and read_only_deal_history:
        warnings.append("CIO-only manual execution doctrine active; Moomoo order/deal history is extracted read-only and broker routing remains disabled.")
    elif has_cio and cio_only:
        warnings.append("CIO-only manual execution doctrine active; manual control layer exists but broker order/deal history extraction is incomplete.")
    else:
        if "orders" not in present:
            warnings.append("No order-generation records found.")
        if "fills" not in present:
            warnings.append("No fill records found.")
        if "transaction_cost_analysis" not in present:
            warnings.append("No transaction-cost analysis output found.")

    return result(
        "execution_readiness",
        score,
        {
            "purpose": "Check whether portfolio decisions are linked to orders, fills, slippage, and TCA.",
            "execution_layer_present": bool(present),
            "cio_only_manual_doctrine": bool(cio_only),
            "broker_execution_is_out_of_scope": bool(cio_only),
            "read_only_broker_history_extraction": bool(read_only_order_history or read_only_deal_history),
        },
        {
            "execution_sections_present": present,
            "has_cio_decision_context": has_cio,
            "pending_cio_review_count": pending_review_count,
            "orders_generated_by_pipeline": orders_generated,
            "execution_authority": (cio_layer or {}).get("execution_authority"),
            "read_only_order_history_extraction": read_only_order_history,
            "read_only_deal_history_extraction": read_only_deal_history,
            "open_order_count": open_order_count,
            "historical_order_count": historical_order_count,
            "open_deal_count": open_deal_count,
            "historical_deal_count": historical_deal_count,
            "has_trade_lifecycle": has_lifecycle,
            "has_transaction_cost_analysis": has_tca,
            "has_manual_fill_import_contract": has_manual_fill_import_contract,
        },
        warnings,
    )


def process_monitoring_governance(dataset: Dict[str, Any], dataset_sha: str) -> ProcessResult:
    meta = dataset.get("meta") or {}
    source_health = dataset.get("source_health") or []
    freshness, freshness_warnings = freshness_summary(dataset)
    data_quality_sla = dataset.get("data_quality_sla") if isinstance(dataset.get("data_quality_sla"), dict) else {}
    has_archive = "research_archive" in dataset or "report_archive" in dataset
    has_audit = "audit" in dataset or "decision_audit" in dataset
    has_lineage = "lineage" in dataset or "data_lineage" in dataset
    has_sla = bool(data_quality_sla)
    hash_score = 20.0
    source_score = 20.0 if source_health else 5.0
    freshness_score = 20.0 if freshness["sections_tracked"] else 5.0
    sla_score = 10.0 if has_sla else 0.0
    archive_score = 15.0 if has_archive else 4.0
    audit_score = 15.0 if has_audit else 4.0
    lineage_score = 10.0 if has_lineage else 2.0
    score = hash_score + source_score + freshness_score + sla_score + archive_score + audit_score + lineage_score
    if not has_audit or not has_lineage:
        score = min(score, 78.0)

    warnings = list(freshness_warnings)
    sla_summary = data_quality_sla.get("summary", {}) if has_sla else {}
    if has_sla and sla_summary.get("breach"):
        warnings.append(f"Data-quality SLA breaches: {sla_summary.get('breach')}")
    if not has_audit:
        warnings.append("No explicit audit-log section found in dataset output.")
    if not has_lineage:
        warnings.append("No field-level lineage section found in dataset output.")

    return result(
        "monitoring_governance",
        score,
        {
            "purpose": "Check monitorability, auditability, and reproducibility of the current export.",
            "dataset_hash": dataset_sha,
            "reproducible_snapshot": True,
        },
        {
            "dataset_generated_at": meta.get("generated_at"),
            "dataset_sha256": dataset_sha,
            "source_health_rows": len(source_health) if isinstance(source_health, list) else 0,
            "freshness_sections": freshness["sections_tracked"],
            "has_data_quality_sla": has_sla,
            "data_quality_sla_summary": sla_summary if has_sla else None,
            "has_report_archive_section": has_archive,
            "has_audit_section": has_audit,
            "has_lineage_section": has_lineage,
        },
        warnings,
    )


def run_processes(dataset: Dict[str, Any], dataset_sha: str) -> List[ProcessResult]:
    return [
        process_data_quality(dataset),
        process_point_in_time(dataset),
        process_bias_controls(dataset),
        process_signal_validation(dataset),
        process_risk_model(dataset),
        process_portfolio_construction(dataset),
        process_execution_readiness(dataset),
        process_monitoring_governance(dataset, dataset_sha),
    ]


def aggregate_results(results: List[ProcessResult]) -> Dict[str, Any]:
    if not results:
        return {
            "readiness_score": 0.0,
            "readiness_label": "FOUNDATION",
            "status": "NO_RESULTS",
        }
    avg = clamp_score(sum(r.score for r in results) / len(results))
    counts = {
        "PASS": sum(1 for r in results if r.status == "PASS"),
        "WARNING": sum(1 for r in results if r.status == "WARNING"),
        "FAIL": sum(1 for r in results if r.status == "FAIL"),
    }
    top_gaps = []
    for r in sorted(results, key=lambda x: x.score):
        if r.warnings:
            top_gaps.append({
                "process": r.name,
                "score": r.score,
                "warning": r.warnings[0],
            })
        if len(top_gaps) >= 8:
            break
    return {
        "readiness_score": avg,
        "readiness_label": readiness_label(avg),
        "status": "COMPLETED" if counts["WARNING"] == 0 and counts["FAIL"] == 0 else "COMPLETED_WITH_GAPS",
        "process_count": len(results),
        "status_counts": counts,
        "top_gaps": top_gaps,
        "institutional_targets": INSTITUTIONAL_TARGETS,
    }


def connect_db():
    root = project_root()
    sys.path.insert(0, str(root))

    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(root / ".env")
    return get_connection()


def ensure_tables() -> None:
    root = project_root()
    sys.path.insert(0, str(root))
    from mid.institutional_quant_tables import create_tables

    create_tables()


def insert_run(dataset: Dict[str, Any], dataset_path: Path, dataset_sha: str,
               results: List[ProcessResult]) -> Dict[str, Any]:
    ensure_tables()
    meta = dataset.get("meta") or {}
    started_at = datetime.now()
    completed_at = datetime.now()
    snapshot_id = f"dataset_{dataset_sha[:20]}"
    run_id = f"iq_{completed_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    dataset_generated_at = parse_dt(meta.get("generated_at"))
    summary = aggregate_results(results)

    conn = connect_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO institutional_dataset_snapshots (
                snapshot_id, captured_at, dataset_generated_at, export_version,
                ingest_version, dataset_sha256, dataset_path, dataset_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                dataset_path = VALUES(dataset_path),
                dataset_json = VALUES(dataset_json)
            """,
            (
                snapshot_id,
                started_at,
                dataset_generated_at,
                meta.get("export_version"),
                meta.get("ingest_version"),
                dataset_sha,
                str(dataset_path),
                json_dumps(dataset),
            ),
        )
        cur.execute(
            """
            INSERT INTO institutional_quant_runs (
                run_id, run_version, run_status, started_at, completed_at,
                snapshot_id, dataset_generated_at, dataset_export_version,
                dataset_ingest_version, dataset_sha256, dataset_snapshot_path,
                total_processes, passed_processes, warning_processes,
                failed_processes, readiness_score, readiness_label, summary_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                run_id,
                RUN_VERSION,
                summary["status"],
                started_at,
                completed_at,
                snapshot_id,
                dataset_generated_at,
                meta.get("export_version"),
                meta.get("ingest_version"),
                dataset_sha,
                str(dataset_path),
                len(results),
                summary["status_counts"]["PASS"],
                summary["status_counts"]["WARNING"],
                summary["status_counts"]["FAIL"],
                summary["readiness_score"],
                summary["readiness_label"],
                json_dumps(summary),
            ),
        )
        for item in results:
            cur.execute(
                """
                INSERT INTO institutional_quant_process_results (
                    run_id, process_name, process_version, process_status,
                    readiness_score, readiness_label,
                    result_json, metrics_json, warnings_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    process_version = VALUES(process_version),
                    process_status = VALUES(process_status),
                    readiness_score = VALUES(readiness_score),
                    readiness_label = VALUES(readiness_label),
                    result_json = VALUES(result_json),
                    metrics_json = VALUES(metrics_json),
                    warnings_json = VALUES(warnings_json)
                """,
                (
                    run_id,
                    item.name,
                    item.version,
                    item.status,
                    item.score,
                    item.label,
                    json_dumps(item.result),
                    json_dumps(item.metrics),
                    json_dumps(item.warnings),
                ),
            )
        cur.execute(
            """
            INSERT INTO institutional_quant_audit_events (
                run_id, event_type, severity, message, payload_json
            ) VALUES (%s,%s,%s,%s,%s)
            """,
            (
                run_id,
                "RUN_COMPLETED",
                "INFO" if summary["status_counts"]["FAIL"] == 0 else "WARNING",
                "Institutional quant process run completed.",
                json_dumps(summary),
            ),
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "dataset_sha256": dataset_sha,
        **summary,
    }


def build_summary(dataset_path: Path, dataset: Dict[str, Any],
                  dataset_sha: str, results: List[ProcessResult]) -> Dict[str, Any]:
    summary = aggregate_results(results)
    meta = dataset.get("meta") or {}
    return {
        "run_version": RUN_VERSION,
        "dataset_path": str(dataset_path),
        "dataset_generated_at": meta.get("generated_at"),
        "dataset_export_version": meta.get("export_version"),
        "dataset_ingest_version": meta.get("ingest_version"),
        "dataset_sha256": dataset_sha,
        **summary,
        "processes": {
            r.name: {
                "status": r.status,
                "readiness_score": r.score,
                "readiness_label": r.label,
                "metrics": r.metrics,
                "warnings": r.warnings,
            }
            for r in results
        },
    }


def write_summary(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json_safe(summary), f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BlueLotus institutional quant readiness processes.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Path to dataset_raw.json.")
    parser.add_argument("--dry-run", action="store_true", help="Run processes without writing to MySQL.")
    parser.add_argument("--init-db-only", action="store_true", help="Create/update tables and exit.")
    parser.add_argument("--summary-out", type=Path, default=None, help="Optional JSON summary output path.")
    args = parser.parse_args()

    if args.init_db_only:
        ensure_tables()
        print("Institutional quant tables are ready.")
        return

    dataset = strip_prior_process_layer(load_dataset(args.dataset))
    dataset_sha = sha256_dataset(dataset)
    results = run_processes(dataset, dataset_sha)
    summary = build_summary(args.dataset, dataset, dataset_sha, results)

    if args.dry_run:
        db_summary = {"dry_run": True, **summary}
    else:
        db_result = insert_run(dataset, args.dataset, dataset_sha, results)
        db_summary = {**summary, **db_result}

    if args.summary_out:
        write_summary(args.summary_out, db_summary)

    print()
    print("-" * 62)
    print("  BlueLotus Institutional Quant Process Runner")
    print(f"  version           : {RUN_VERSION}")
    print(f"  dataset           : {args.dataset}")
    print(f"  dataset sha256    : {dataset_sha}")
    print(f"  readiness score   : {db_summary['readiness_score']:.3f}")
    print(f"  readiness label   : {db_summary['readiness_label']}")
    print(f"  status            : {db_summary['status']}")
    if not args.dry_run:
        print(f"  run id            : {db_summary['run_id']}")
        print(f"  snapshot id       : {db_summary['snapshot_id']}")
    print("-" * 62)
    for item in results:
        print(f"  {item.name:<28} {item.status:<8} {item.score:>7.3f} {item.label}")
    print("-" * 62)


if __name__ == "__main__":
    main()

