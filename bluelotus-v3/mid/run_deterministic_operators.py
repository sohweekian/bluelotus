#!/usr/bin/env python3
"""
BlueLotus deterministic operator pack.

Reads dataset_raw.json and emits rules-based operator findings for downstream
Chief Strategist / CIO synthesis. This layer must never call an LLM or broker
execution API.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "audit" / "deterministic_operators_latest.json"

VERSION = "v0.3"

CLUSTER_TICKERS = {
    "GOLD_MINERS": {"AU", "NEM", "PAAS", "HL", "CDE", "AG", "GDX", "GDXJ"},
    "GOLD_SAFE_HAVEN": {"GLD", "SLV"},
    "SPACE_DEFENSE": {"ASTS", "RKLB", "LUNR", "BKSY", "SATS", "RDW", "SIDU", "IRDM", "VSAT", "SPIR", "PL", "SPCE"},
    "QUANTUM": {"IONQ", "RGTI", "QUBT", "QBTS", "ARQQ", "QMCO"},
    "AI_SEMIS": {"NVDA", "AMD", "AVGO", "MRVL", "MU", "TSM", "AMAT", "ARM", "ASML", "QCOM", "INTC"},
    "MAG7_BIG_TECH": {"MSFT", "AAPL", "GOOGL", "META", "AMZN", "TSLA", "NFLX", "UBER"},
}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _weight_from_position(pos: Dict[str, Any], total_assets: float) -> float:
    if not total_assets:
        return 0.0
    value = _num(pos.get("mkt_val"), None)
    if value is None:
        value = _num(pos.get("market_value"), 0.0) or 0.0
    return value / total_assets


def _portfolio_positions(dataset: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], float, float]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), dict) else {}
    total_assets = _num(portfolio.get("total_assets"), None)
    if total_assets is None:
        total_assets = _num(portfolio.get("total_value"), 0.0) or 0.0
    cash = _num(portfolio.get("cash"), 0.0) or 0.0
    return positions, total_assets, cash


def _ticker_theme(ticker: str, dataset: Dict[str, Any]) -> str:
    t = str(ticker).upper()
    for cluster, tickers in CLUSTER_TICKERS.items():
        if t in tickers:
            return cluster
    security_master = dataset.get("security_master") if isinstance(dataset.get("security_master"), dict) else {}
    row = security_master.get(t) if isinstance(security_master, dict) else {}
    if isinstance(row, dict):
        return str(row.get("theme") or row.get("sector") or "UNKNOWN").upper().replace(" ", "_").replace("/", "_")
    return "UNKNOWN"


def _live_row(dataset: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    prices = dataset.get("live_prices") if isinstance(dataset.get("live_prices"), dict) else {}
    row = prices.get(str(ticker).upper()) if isinstance(prices, dict) else {}
    return row if isinstance(row, dict) else {}


def _chg(dataset: Dict[str, Any], ticker: str) -> float | None:
    return _num(_live_row(dataset, ticker).get("chg_pct"), None)


def _price(dataset: Dict[str, Any], ticker: str) -> float | None:
    return _num(_live_row(dataset, ticker).get("price"), None)


def _status_score(status: str) -> float:
    return {
        "PASS": 1.0,
        "CLEAR": 1.0,
        "WATCH": 0.75,
        "NEUTRAL": 0.65,
        "WARNING": 0.5,
        "REVIEW": 0.45,
        "HIGH": 0.35,
        "CRITICAL": 0.2,
        "FAIL": 0.0,
    }.get(str(status).upper(), 0.5)


def macro_regime_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    cross = dataset.get("cross_market_confirmation") if isinstance(dataset.get("cross_market_confirmation"), dict) else {}
    derived = cross.get("derived_scores") if isinstance(cross.get("derived_scores"), dict) else {}
    ece_rows = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    ece_rows = ece_rows if isinstance(ece_rows, list) else []

    vix = _num(regime.get("vix_level"), None)
    yield_10y = _num(((dataset.get("treasury_yields") or {}).get("yield_10y") if isinstance(dataset.get("treasury_yields"), dict) else None), None)
    uup = _chg(dataset, "UUP")
    spy = _chg(dataset, "SPY")
    positive_sectors = sum(1 for r in ece_rows if isinstance(r, dict) and (_num(r.get("basket_move"), 0) or 0) > 0.10)
    negative_sectors = sum(1 for r in ece_rows if isinstance(r, dict) and (_num(r.get("basket_move"), 0) or 0) < -0.10)
    breadth = positive_sectors - negative_sectors
    credit_stress = _num(derived.get("credit_stress_score"), 0.0) or 0.0
    risk_appetite = _num(derived.get("risk_appetite_score"), 0.0) or 0.0
    dollar_pressure = _num(derived.get("dollar_pressure_score"), 0.0) or 0.0
    yield_pressure = _num(derived.get("yield_pressure_score"), 0.0) or 0.0

    risk_off_points = 0
    risk_on_points = 0
    if vix is not None:
        if vix >= 25:
            risk_off_points += 2
        elif vix >= 20:
            risk_off_points += 1
        elif vix < 16:
            risk_on_points += 1
    if spy is not None:
        if spy <= -1.0:
            risk_off_points += 2
        elif spy < -0.25:
            risk_off_points += 1
        elif spy >= 0.5:
            risk_on_points += 1
    if uup is not None and uup >= 0.5:
        risk_off_points += 1
    if yield_10y is not None and yield_10y >= 4.75:
        risk_off_points += 1
    if credit_stress >= 0.45:
        risk_off_points += 1
    if risk_appetite >= 0.55:
        risk_on_points += 1
    if breadth >= 5:
        risk_on_points += 1
    elif breadth <= -5:
        risk_off_points += 1
    if dollar_pressure >= 0.50 or yield_pressure >= 0.50:
        risk_off_points += 1

    raw_regime = str(regime.get("regime") or regime.get("regime_short") or "UNKNOWN").upper()
    if risk_off_points >= 4:
        status = "RISK_OFF"
    elif risk_on_points >= 3 and risk_off_points <= 1:
        status = "RISK_ON"
    elif risk_off_points >= 2:
        status = "WATCH"
    else:
        status = "NEUTRAL" if raw_regime == "NEUTRAL" else raw_regime

    tactical_overlay = "RISK_ON" if risk_on_points >= 3 and risk_appetite >= 0.55 else "NEUTRAL"
    if raw_regime == "RISK OFF" and status == "RISK_ON":
        status = "RISK_OFF"
        risk_off_points = max(risk_off_points, 2)

    blocked = ["ADD_HIGH_BETA_RISK"] if status in {"RISK_OFF", "WATCH"} else []
    evidence = [
        f"regime={raw_regime} score={regime.get('score')}",
        f"vix={vix}",
        f"10y_yield={yield_10y}",
        f"uup_change_pct={uup}",
        f"spy_change_pct={spy}",
        f"sector_breadth={breadth} ({positive_sectors} positive / {negative_sectors} negative)",
        f"credit_stress_score={credit_stress:.3f}",
        f"risk_appetite_score={risk_appetite:.3f}",
    ]
    return {
        "operator": "macro_regime",
        "status": status,
        "score": round(max(0.0, min(1.0, 0.5 + 0.12 * risk_on_points - 0.10 * risk_off_points)), 4),
        "evidence": evidence,
        "blocked_actions": blocked,
        "metrics": {
            "risk_off_points": risk_off_points,
            "risk_on_points": risk_on_points,
            "raw_regime": raw_regime,
            "tactical_risk_appetite_overlay": tactical_overlay,
            "sector_breadth": breadth,
            "credit_stress_score": round(credit_stress, 4),
            "risk_appetite_score": round(risk_appetite, 4),
        },
        "confidence": "DATA_CONFIRMED",
    }


def gold_thesis_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    checks = []

    gld = _chg(dataset, "GLD")
    slv = _chg(dataset, "SLV")
    gdx = _chg(dataset, "GDX")
    gdxj = _chg(dataset, "GDXJ")
    au = _chg(dataset, "AU")
    nem = _chg(dataset, "NEM")
    uup = _chg(dataset, "UUP")
    tlt = _chg(dataset, "TLT")
    ief = _chg(dataset, "IEF")
    xle = _chg(dataset, "XLE")
    spy = _chg(dataset, "SPY")
    vxx = _chg(dataset, "VXX")

    def add(name: str, passed: bool, available: bool, evidence: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "WATCH" if available else "MISSING", "evidence": evidence})

    add("gold_stabilizes", gld is not None and gld >= 0.0, gld is not None, f"GLD {gld}")
    add("silver_confirms", slv is not None and gld is not None and slv >= gld - 0.25, slv is not None and gld is not None, f"SLV {slv} vs GLD {gld}")
    add("miners_vs_gold", gdx is not None and gld is not None and gdx >= gld + 0.25, gdx is not None and gld is not None, f"GDX {gdx} vs GLD {gld}")
    add("junior_miners_confirm", gdxj is not None and gld is not None and gdxj >= gld, gdxj is not None and gld is not None, f"GDXJ {gdxj} vs GLD {gld}")
    au_nem_confirm = any(x is not None and gdx is not None and x >= gdx - 0.25 for x in (au, nem))
    add("au_nem_vs_gdx", au_nem_confirm, gdx is not None and (au is not None or nem is not None), f"AU {au}, NEM {nem}, GDX {gdx}")
    add("dxy_not_surging", uup is not None and uup < 0.50, uup is not None, f"UUP {uup}")
    add("rates_not_spiking", (tlt is not None and tlt > -0.75) or (ief is not None and ief > -0.50), tlt is not None or ief is not None, f"TLT {tlt}, IEF {ief}")
    add("miner_liquidation_risk", gdx is not None and spy is not None and vxx is not None and gdx >= spy - 1.0 and vxx < 5.0, gdx is not None and spy is not None, f"GDX {gdx}, SPY {spy}, VXX {vxx}")
    add("oil_risk_premium", xle is not None and xle >= 0.0, xle is not None, f"XLE {xle}")

    available = [c for c in checks if c["status"] != "MISSING"]
    passed = [c for c in checks if c["status"] == "PASS"]
    score = len(passed) / len(available) if available else 0.0
    if score >= 0.75:
        status = "CONFIRMED"
    elif score >= 0.50:
        status = "WATCH"
    else:
        status = "FAIL"

    conc = concentration_operator(dataset)
    concentration_blocks = "ADD_TO_GOLD_MINERS" in conc.get("blocked_actions", [])
    blocked = []
    if concentration_blocks:
        blocked.extend(["ADD_GOLD_MINERS", "ADD_AU", "ADD_NEM"])
    if status != "CONFIRMED":
        blocked.append("INCREASE_GOLD_THESIS_RISK")

    return {
        "operator": "gold_thesis",
        "status": status,
        "score": round(score, 4),
        "evidence": [f"{c['name']}={c['status']} ({c['evidence']})" for c in checks],
        "blocked_actions": sorted(set(blocked)),
        "metrics": {
            "available_checks": len(available),
            "pass_count": len(passed),
            "watch_count": sum(1 for c in checks if c["status"] == "WATCH"),
            "missing_count": sum(1 for c in checks if c["status"] == "MISSING"),
            "concentration_blocks_adds": concentration_blocks,
        },
        "confidence": "DATA_CONFIRMED",
        "checks": checks,
    }


def concentration_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    positions, total_assets, cash = _portfolio_positions(dataset)
    weights: List[Tuple[str, float]] = []
    clusters: Dict[str, float] = {}
    for ticker, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        t = str(ticker).upper()
        w = _weight_from_position(pos, total_assets)
        weights.append((t, w))
        theme = _ticker_theme(t, dataset)
        clusters[theme] = clusters.get(theme, 0.0) + w

    weights_sorted = sorted(weights, key=lambda x: x[1], reverse=True)
    largest_ticker, largest_weight = weights_sorted[0] if weights_sorted else ("", 0.0)
    top3_weight = sum(w for _, w in weights_sorted[:3])
    hhi = sum(w * w for _, w in weights_sorted)
    largest_cluster, largest_cluster_weight = ("", 0.0)
    if clusters:
        largest_cluster, largest_cluster_weight = max(clusters.items(), key=lambda x: x[1])

    status = "CLEAR"
    if largest_weight >= 0.33 or largest_cluster_weight >= 0.65 or top3_weight >= 0.80:
        status = "CRITICAL"
    elif largest_weight >= 0.30 or largest_cluster_weight >= 0.50 or top3_weight >= 0.70 or hhi >= 0.20:
        status = "HIGH"
    elif largest_weight >= 0.20 or largest_cluster_weight >= 0.35 or hhi >= 0.12:
        status = "WATCH"

    blocked = []
    if largest_ticker and largest_weight >= 0.30:
        blocked.append(f"ADD_{largest_ticker}")
    if largest_cluster and largest_cluster_weight >= 0.50:
        safe_cluster = largest_cluster.upper().replace(" ", "_").replace("/", "_")
        blocked.extend([f"ADD_TO_{safe_cluster}", f"INCREASE_{safe_cluster}_EXPOSURE"])

    cash_weight = cash / total_assets if total_assets else None
    if cash_weight is not None and cash_weight < 0.05:
        blocked.append("LOWER_CASH")

    evidence = [
        f"largest_position={largest_ticker or 'NONE'} weight={largest_weight:.1%}",
        f"top3_weight={top3_weight:.1%}",
        f"hhi={hhi:.3f}",
        f"largest_cluster={largest_cluster or 'NONE'} weight={largest_cluster_weight:.1%}",
    ]
    if cash_weight is not None:
        evidence.append(f"cash_weight={cash_weight:.1%}")

    return {
        "operator": "concentration_risk",
        "status": status,
        "score": round(min(1.0, max(largest_weight, largest_cluster_weight, top3_weight, hhi)), 4),
        "evidence": evidence,
        "blocked_actions": sorted(set(blocked)),
        "metrics": {
            "largest_ticker": largest_ticker or None,
            "largest_weight": round(largest_weight, 4),
            "top3_weight": round(top3_weight, 4),
            "hhi": round(hhi, 4),
            "largest_cluster": largest_cluster or None,
            "largest_cluster_weight": round(largest_cluster_weight, 4),
            "cash_weight": round(cash_weight, 4) if cash_weight is not None else None,
        },
        "confidence": "DATA_CONFIRMED",
    }


def freshness_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    freshness = (dataset.get("meta") or {}).get("freshness") if isinstance(dataset.get("meta"), dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    critical = {
        "portfolio",
        "live_prices",
        "treasury_yields",
        "cross_market_confirmation",
        "risk_model",
        "portfolio_targets",
        "execution",
    }
    stale: List[str] = []
    critical_stale: List[str] = []
    warnings: List[str] = []
    rows = []
    for name, info in freshness.items():
        if name == "thresholds" or not isinstance(info, dict):
            continue
        grade = str(info.get("grade") or "UNKNOWN").upper()
        age = info.get("age_minutes")
        row = {"section": name, "grade": grade, "age_minutes": age, "critical": name in critical}
        rows.append(row)
        if grade in {"STALE", "BREACH", "ERROR"}:
            stale.append(name)
            if name in critical:
                critical_stale.append(name)
        elif grade in {"SAME_DAY_STALE", "MARKET_CLOSED_OK"}:
            warnings.append(name)

    status = "PASS"
    if critical_stale:
        status = "FAIL"
    elif stale or warnings:
        status = "WARNING"

    return {
        "operator": "freshness_governor",
        "status": status,
        "score": round(max(0.0, 1.0 - 0.20 * len(critical_stale) - 0.08 * len(stale) - 0.01 * len(warnings)), 4),
        "evidence": [
            f"sections_checked={len(rows)}",
            f"critical_stale={len(critical_stale)}",
            f"stale={len(stale)}",
            f"warnings={len(warnings)}",
        ],
        "blocked_actions": ["ADD_RISK"] if critical_stale else [],
        "metrics": {
            "critical_stale_sections": critical_stale,
            "stale_sections": stale,
            "warning_sections": warnings,
        },
        "confidence": "DATA_CONFIRMED",
        "rows": rows,
    }


def execution_safety_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    execution = dataset.get("execution") if isinstance(dataset.get("execution"), dict) else {}
    cio_decisions = dataset.get("cio_decisions") if isinstance(dataset.get("cio_decisions"), dict) else {}
    order_routing = bool(execution.get("order_routing_enabled"))
    generated = int(_num(execution.get("orders_generated_by_pipeline"), 0) or 0)
    generated_alt = int(_num(execution.get("orders_generated"), 0) or 0)
    decision_generated = int(_num(cio_decisions.get("orders_generated"), 0) or 0)
    authority = str(execution.get("execution_authority") or cio_decisions.get("execution_authority") or "")
    read_only = bool(execution.get("broker_extract_only", True))

    failures = []
    if order_routing:
        failures.append("order_routing_enabled=True")
    if generated or generated_alt or decision_generated:
        failures.append("orders_generated_nonzero")
    if authority and authority != "CIO_ONLY_MANUAL":
        failures.append(f"unexpected_authority={authority}")
    if not read_only:
        failures.append("broker_extract_only=False")

    return {
        "operator": "execution_safety",
        "status": "FAIL" if failures else "PASS",
        "score": 0.0 if failures else 1.0,
        "evidence": [
            f"execution_authority={authority or 'UNKNOWN'}",
            f"order_routing_enabled={order_routing}",
            f"orders_generated_by_pipeline={generated}",
            f"orders_generated={generated_alt}",
            f"cio_decision_orders_generated={decision_generated}",
            f"broker_extract_only={read_only}",
        ],
        "blocked_actions": ["SYSTEM_ORDER_ROUTING", "AUTO_EXECUTION"] if failures else [],
        "metrics": {
            "failures": failures,
            "manual_execution_required": bool(execution.get("manual_execution_required", True)),
        },
        "confidence": "DATA_CONFIRMED",
    }


def catalyst_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    calendar = dataset.get("catalyst_calendar") if isinstance(dataset.get("catalyst_calendar"), dict) else {}
    all_events = calendar.get("all") if isinstance(calendar.get("all"), list) else []
    portfolio_events = calendar.get("portfolio_only") if isinstance(calendar.get("portfolio_only"), list) else []
    ece_rows = dataset.get("event_correlations_all") or dataset.get("event_correlations") or []
    ece_rows = ece_rows if isinstance(ece_rows, list) else []
    priority = dataset.get("priority_intelligence") if isinstance(dataset.get("priority_intelligence"), dict) else {}
    p1 = priority.get("P1") if isinstance(priority.get("P1"), dict) else {}
    p1_catalysts = p1.get("catalysts") if isinstance(p1.get("catalysts"), list) else []

    imminent = []
    active = []
    past_recent = []
    for row in all_events:
        if not isinstance(row, dict):
            continue
        days = _num(row.get("days_until_catalyst"), None)
        if days is None:
            continue
        if 0 <= days <= 14:
            imminent.append(row)
        elif days < 0 and days >= -3:
            past_recent.append(row)
        if str(row.get("alert_flag") or "").upper() in {"ACTIVE", "IMMINENT"}:
            active.append(row)

    direct_support = [r for r in ece_rows if isinstance(r, dict) and str(r.get("theme_catalyst_quality") or "").upper() == "DIRECT_CAUSAL_SUPPORT"]
    review_flags = [r for r in ece_rows if isinstance(r, dict) and r.get("review_flags")]
    portfolio_imminent = [r for r in portfolio_events if isinstance(r, dict) and 0 <= (_num(r.get("days_until_catalyst"), 9999) or 9999) <= 14]

    status = "PASS"
    if review_flags:
        status = "WARNING"
    if portfolio_imminent:
        status = "REVIEW"
    if not all_events and not direct_support:
        status = "FAIL"

    blocked = []
    if status in {"WARNING", "REVIEW", "FAIL"}:
        blocked.append("ADD_RISK_WITHOUT_CATALYST_REVIEW")

    evidence = [
        f"events_total={len(all_events)}",
        f"portfolio_events={len(portfolio_events)}",
        f"imminent_14d={len(imminent)}",
        f"portfolio_imminent_14d={len(portfolio_imminent)}",
        f"active_flags={len(active)}",
        f"recent_past_3d={len(past_recent)}",
        f"ece_direct_causal_support={len(direct_support)}",
        f"ece_review_flags={len(review_flags)}",
        f"p1_catalysts={len(p1_catalysts)}",
    ]
    return {
        "operator": "catalyst_intelligence",
        "status": status,
        "score": round(max(0.35 if all_events else 0.0, min(1.0, 0.70 + 0.02 * len(direct_support) - 0.025 * len(review_flags) - 0.04 * len(portfolio_imminent))), 4),
        "evidence": evidence,
        "blocked_actions": blocked,
        "metrics": {
            "imminent_tickers": sorted({str(r.get("ticker", "")).upper() for r in imminent if r.get("ticker")}),
            "portfolio_imminent_tickers": sorted({str(r.get("ticker", "")).upper() for r in portfolio_imminent if r.get("ticker")}),
            "review_flag_themes": sorted({str(r.get("theme", "")) for r in review_flags if r.get("theme")}),
        },
        "confidence": "DATA_CONFIRMED",
    }


def thesis_lifecycle_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    thesis = dataset.get("thesis_lifecycle") if isinstance(dataset.get("thesis_lifecycle"), dict) else {}
    theses = thesis.get("theses") if isinstance(thesis.get("theses"), list) else []
    review_required = []
    contradictions = 0
    evidence_items = 0
    low_confidence = []
    inactive = []
    for row in theses:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("thesis_id") or row.get("thesis_name") or "UNKNOWN")
        status = str(row.get("status") or "UNKNOWN").upper()
        conf = _num(row.get("confidence"), None)
        ev = row.get("evidence") if isinstance(row.get("evidence"), list) else []
        contra = row.get("contradictions") if isinstance(row.get("contradictions"), list) else []
        evidence_items += len(ev)
        contradictions += len(contra)
        if status not in {"ACTIVE", "WATCH"}:
            inactive.append(tid)
        if conf is not None and conf < 0.50:
            low_confidence.append(tid)
        if len(contra) >= 2 or (conf is not None and conf < 0.45):
            review_required.append(tid)

    status = "PASS"
    if low_confidence or contradictions:
        status = "WARNING"
    if review_required:
        status = "REVIEW"
    if not theses:
        status = "FAIL"

    blocked = ["ADD_WITHOUT_THESIS_REVIEW"] if status in {"REVIEW", "FAIL"} else []
    return {
        "operator": "thesis_lifecycle",
        "status": status,
        "score": round(max(0.0, 1.0 - 0.04 * contradictions - 0.08 * len(low_confidence) - 0.12 * len(review_required)), 4),
        "evidence": [
            f"thesis_count={len(theses)}",
            f"evidence_items={evidence_items}",
            f"contradictions={contradictions}",
            f"low_confidence={len(low_confidence)}",
            f"review_required={len(review_required)}",
        ],
        "blocked_actions": blocked,
        "metrics": {
            "review_required": review_required,
            "low_confidence": low_confidence,
            "inactive": inactive,
            "status_counts": thesis.get("status_counts", {}),
        },
        "confidence": "DATA_CONFIRMED",
    }


def archive_mismatch_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    archive = dataset.get("report_archive") if isinstance(dataset.get("report_archive"), dict) else {}
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    mismatches = []

    comparisons = [
        ("dataset_generated_at", archive.get("dataset_generated_at"), meta.get("generated_at")),
        ("export_version", archive.get("export_version"), meta.get("export_version")),
        ("ingest_version", archive.get("ingest_version"), meta.get("ingest_version")),
        ("regime", archive.get("regime"), regime.get("regime")),
        ("regime_score", archive.get("regime_score"), regime.get("score")),
        ("latest_signal_at", archive.get("latest_signal_at"), meta.get("latest_signal_at")),
        ("total_signals", archive.get("total_signals"), meta.get("total_signals")),
    ]
    for field, archived, live in comparisons:
        if archived is None or live is None:
            continue
        if str(archived) != str(live):
            mismatches.append({"field": field, "archived": archived, "live": live})

    status = "PASS"
    if mismatches:
        status = "WARNING"
    if archive.get("status") in {"not_configured", "extract_error"}:
        status = "FAIL"

    return {
        "operator": "archive_mismatch",
        "status": status,
        "score": round(max(0.0, 1.0 - 0.08 * len(mismatches)), 4),
        "evidence": [
            f"archive_status={archive.get('status', 'UNKNOWN')}",
            f"archive_id={archive.get('id')}",
            f"mismatch_count={len(mismatches)}",
        ],
        "blocked_actions": ["USE_ARCHIVE_AS_LIVE_TRUTH"] if mismatches else [],
        "metrics": {
            "mismatches": mismatches,
        },
        "confidence": "DATA_CONFIRMED",
    }


def portfolio_mandate_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    positions, total_assets, cash = _portfolio_positions(dataset)
    constraints = dataset.get("portfolio_constraints") if isinstance(dataset.get("portfolio_constraints"), dict) else {}
    mandates = dataset.get("portfolio_mandates") if isinstance(dataset.get("portfolio_mandates"), dict) else {}
    targets = dataset.get("portfolio_targets") if isinstance(dataset.get("portfolio_targets"), dict) else {}
    target_actions = targets.get("actions") if isinstance(targets.get("actions"), list) else []
    risk_metrics = dataset.get("risk_metrics") if isinstance(dataset.get("risk_metrics"), dict) else {}

    min_cash = _num(constraints.get("min_cash_weight"), 0.05) or 0.05
    max_single = _num(constraints.get("max_single_name_weight"), 0.30) or 0.30
    max_cluster = _num(constraints.get("max_theme_weight"), 0.45) or 0.45
    cash_weight = cash / total_assets if total_assets else 0.0

    breaches = []
    blocked = []
    if cash_weight < min_cash:
        breaches.append("min_cash_weight")
        blocked.append("LOWER_CASH")
    for ticker, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        w = _weight_from_position(pos, total_assets)
        if w > max_single:
            t = str(ticker).upper()
            breaches.append(f"max_single_name_weight:{t}")
            blocked.append(f"ADD_{t}")

    cluster_weights: Dict[str, float] = {}
    for ticker, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        cluster = _ticker_theme(str(ticker), dataset)
        cluster_weights[cluster] = cluster_weights.get(cluster, 0.0) + _weight_from_position(pos, total_assets)
    for cluster, weight in cluster_weights.items():
        if weight > max_cluster:
            safe_cluster = cluster.upper().replace(" ", "_").replace("/", "_")
            breaches.append(f"max_cluster_weight:{safe_cluster}")
            blocked.extend([f"ADD_TO_{safe_cluster}", f"INCREASE_{safe_cluster}_EXPOSURE"])

    non_research_only = [
        t for t, row in mandates.items()
        if isinstance(row, dict) and row.get("research_only") is not True
    ]
    if non_research_only:
        breaches.append("mandate_research_only_missing")
        blocked.append("AUTO_EXECUTION")

    status = "PASS"
    if breaches:
        status = "REVIEW"
    if any(b.startswith("min_cash") for b in breaches):
        status = "FAIL"

    return {
        "operator": "portfolio_mandate",
        "status": status,
        "score": round(max(0.0, 1.0 - 0.07 * len(breaches)), 4),
        "evidence": [
            f"cash_weight={cash_weight:.1%} min_cash={min_cash:.1%}",
            f"max_single_name={max_single:.1%}",
            f"max_cluster={max_cluster:.1%}",
            f"target_actions={len(target_actions)}",
            f"risk_metric_breaches={len(risk_metrics.get('constraint_breaches') or [])}",
            f"breaches={len(breaches)}",
        ],
        "blocked_actions": sorted(set(blocked)),
        "metrics": {
            "breaches": breaches,
            "cluster_weights": {k: round(v, 4) for k, v in sorted(cluster_weights.items())},
            "target_actions": target_actions,
            "non_research_only": non_research_only,
        },
        "confidence": "DATA_CONFIRMED",
    }


def cash_fortress_mode_operator(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect CIO cash-fortress / scout-mode posture.

    Derives four mode flags from portfolio structure and macro context:
      cash_fortress_mode    — high cash is intentional defensive posture, not a defect
      scout_mode            — active book is small initial tranches only
      second_tranche_blocked — scaling blocked pending macro confirmation
      deployment_floor_active — floor breach is meaningful (False in cash-fortress mode)

    These flags are passed to agents to distinguish defensive posture from portfolio defects.
    NO execution authority. CIO_ONLY_MANUAL.
    """
    positions, total_assets, cash = _portfolio_positions(dataset)
    portfolio_readonly = dataset.get("portfolio_readonly") or {}
    risk_metrics       = dataset.get("risk_metrics") or {}
    macro_regime       = (dataset.get("macro_regime") or {}).get("regime", "UNKNOWN")
    cio_action         = (dataset.get("cio_action") or {}).get("action", "UNKNOWN")
    thesis_widgets     = dataset.get("thesis_widgets") or {}

    cash_weight = cash / total_assets if total_assets else 0.0
    market_value = total_assets - cash if total_assets else 0.0

    # ── Cash weight thresholds ────────────────────────────────────────────────
    CASH_FORTRESS_THRESHOLD = 0.70   # >= 70% cash → fortress candidate

    # ── CIO actions that indicate defensive / wait posture ────────────────────
    DEFENSIVE_ACTIONS = {
        "WAIT", "HOLD", "WATCH", "REVIEW", "MANUAL_REVIEW_REQUIRED",
        "CIO_VERIFICATION_REQUIRED", "RISK_REVIEW", "HEDGE_REVIEW",
        "NO_ADD", "HOLD_REVIEW",
    }
    DEFENSIVE_REGIMES = {
        "RISK_OFF", "MILD_RISK_OFF", "NEUTRAL", "WATCH",
    }

    # ── Compute cash_fortress_mode ────────────────────────────────────────────
    cash_fortress_mode = (
        cash_weight >= CASH_FORTRESS_THRESHOLD
        and (
            any(d in str(cio_action).upper() for d in DEFENSIVE_ACTIONS)
            or any(d in str(macro_regime).upper() for d in DEFENSIVE_REGIMES)
            or str(macro_regime).upper() == "UNKNOWN"   # no regime = conservative
        )
    )

    # ── Compute scout_mode ────────────────────────────────────────────────────
    # Scout: small positions (each < $1,000) or very small total market value
    SCOUT_TOTAL_MV_THRESHOLD = 5_000.0
    SCOUT_MAX_POSITION_VALUE = 1_500.0
    position_values = []
    for ticker, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        mv = _num(pos.get("mkt_val") or pos.get("market_value"), 0.0) or 0.0
        position_values.append(mv)

    all_small = all(v <= SCOUT_MAX_POSITION_VALUE for v in position_values) if position_values else True
    scout_mode = cash_fortress_mode and (market_value <= SCOUT_TOTAL_MV_THRESHOLD or all_small)

    # ── Compute second_tranche_blocked ────────────────────────────────────────
    # Blocked until: Warsh/FOMC confirmed, BOJ stable, regime risk-on confirmed
    boj_status   = str((thesis_widgets.get("boj_yen_watcher") or {}).get("status", "UNKNOWN")).upper()
    s8_status    = str((thesis_widgets.get("global_leverage_unwind") or {}).get("status", "UNKNOWN")).upper()

    second_tranche_blocked = (
        scout_mode
        or boj_status in {"WATCH", "ACTIVE_UNWIND", "SEVERE_UNWIND", "UNKNOWN"}
        or s8_status  in {"WATCH", "ACTIVE_UNWIND", "SEVERE_UNWIND", "UNKNOWN"}
        or macro_regime.upper() in {"RISK_OFF", "MILD_RISK_OFF", "UNKNOWN"}
    )

    # ── Compute deployment_floor_active ───────────────────────────────────────
    # Floor is meaningful only when CIO intends to deploy capital
    DEPLOY_ACTIONS = {"BUY", "ADD", "DEPLOY", "ACCUMULATE", "SCALE_IN"}
    deployment_floor_active = (
        not cash_fortress_mode
        and not scout_mode
        and any(d in str(cio_action).upper() for d in DEPLOY_ACTIONS)
    )

    # ── Evidence ──────────────────────────────────────────────────────────────
    evidence = [
        f"cash_weight={cash_weight:.1%}",
        f"market_value=${market_value:,.0f}",
        f"cash_fortress_threshold={CASH_FORTRESS_THRESHOLD:.0%}",
        f"macro_regime={macro_regime}",
        f"cio_action={cio_action}",
        f"boj_status={boj_status}",
        f"s8_leverage_status={s8_status}",
        f"position_count={len(positions)}",
    ]

    status = "PASS"  # cash_fortress_mode is not a failure — it is an interpretation flag

    return {
        "operator":                "cash_fortress_mode",
        "status":                  status,
        "score":                   1.0,
        "evidence":                evidence,
        "blocked_actions":         (
            ["SECOND_TRANCHE_ADD", "SCALE_IN_ADD"] if second_tranche_blocked else []
        ),
        "metrics": {
            "cash_fortress_mode":       cash_fortress_mode,
            "scout_mode":               scout_mode,
            "second_tranche_blocked":   second_tranche_blocked,
            "deployment_floor_active":  deployment_floor_active,
            "cash_weight":              round(cash_weight, 4),
            "market_value":             round(market_value, 2),
            "position_count":           len(positions),
        },
        "confidence": "DATA_CONFIRMED",
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
    }


def build_operator_pack(dataset: Dict[str, Any]) -> Dict[str, Any]:
    operators = [
        macro_regime_operator(dataset),
        gold_thesis_operator(dataset),
        concentration_operator(dataset),
        freshness_operator(dataset),
        execution_safety_operator(dataset),
        catalyst_operator(dataset),
        thesis_lifecycle_operator(dataset),
        archive_mismatch_operator(dataset),
        portfolio_mandate_operator(dataset),
        cash_fortress_mode_operator(dataset),
    ]
    fail_count = sum(1 for op in operators if op["status"] == "FAIL")
    review_count = sum(1 for op in operators if op["status"] in {"WARNING", "REVIEW", "HIGH", "CRITICAL", "WATCH", "RISK_OFF"})
    blocked_actions = sorted({a for op in operators for a in op.get("blocked_actions", [])})
    readiness = "FAIL" if fail_count else "REVIEW_REQUIRED" if review_count else "PASS"
    doctrine = (
        "Deterministic operators calculate and block unsafe actions. "
        "Chief Strategist may synthesize. CIO decides and executes manually."
    )
    return {
        "status": "operational",
        "version": VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dataset_generated_at": (dataset.get("meta") or {}).get("generated_at") if isinstance(dataset.get("meta"), dict) else None,
        "execution_authority": "CIO_ONLY_MANUAL",
        "llm_used": False,
        "order_routing_enabled": False,
        "orders_generated": 0,
        "readiness": readiness,
        "summary": {
            "operator_count": len(operators),
            "fail_count": fail_count,
            "review_count": review_count,
            "blocked_actions": blocked_actions,
        },
        "operators": {op["operator"]: op for op in operators},
        "doctrine": doctrine,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BlueLotus deterministic operator pack")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    if not isinstance(dataset, dict):
        raise ValueError("dataset_raw.json must contain a JSON object")
    result = build_operator_pack(dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Deterministic operators: {result['readiness']} | {args.output}")
    print(f"Operators: {', '.join(result['operators'].keys())}")
    print(f"Blocked actions: {', '.join(result['summary']['blocked_actions']) or 'none'}")


if __name__ == "__main__":
    main()

