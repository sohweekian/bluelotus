from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from acms_cop.classifiers.confirmation_gate_classifier import classify_confirmation_gate
from acms_cop.common import first_dict, json_dumps, parse_dt, safe_float, sha256_file


def _return_from_live(ds: Dict[str, Any], ticker: str) -> float | None:
    live = first_dict(ds.get("live_prices"))
    row = live.get(ticker) if isinstance(live.get(ticker), dict) else {}
    for key in ("chg_pct", "change_pct", "day_return", "return_pct"):
        if key in row:
            return safe_float(row.get(key))
    return None


def extract_cycle(dataset: Dict[str, Any], dataset_path: str | Path) -> Dict[str, Any]:
    meta = first_dict(dataset.get("meta"))
    regime = first_dict(dataset.get("regime"))
    portfolio = first_dict(dataset.get("portfolio"), dataset.get("portfolio_readonly"))
    deterministic = first_dict(dataset.get("deterministic_operators"))
    execution = first_dict(dataset.get("execution"))
    fear = first_dict(dataset.get("fear_greed"))
    treasury = first_dict(dataset.get("treasury_yields"))
    cross = first_dict(dataset.get("cross_market_confirmation"))
    fx_pressure = first_dict(cross.get("dollar_rates_pressure"))
    risk_metrics = first_dict(dataset.get("risk_metrics"))

    total_assets = safe_float(portfolio.get("total_assets"), 0.0) or 0.0
    cash_value = safe_float(portfolio.get("cash"), 0.0) or 0.0
    market_value = safe_float(portfolio.get("market_val") or portfolio.get("market_value") or portfolio.get("total_value"), 0.0) or 0.0
    cash_weight = (cash_value / total_assets) if total_assets else safe_float(risk_metrics.get("cash_weight"), 0.0)
    blocked_actions = first_dict(deterministic.get("summary")).get("blocked_actions", [])
    positions = first_dict(portfolio.get("positions"))
    pnl_status = "OK"
    if any(str(first_dict(pos).get("pnl_integrity_status", "")).upper().startswith("BROKER_PNL") for pos in positions.values()):
        pnl_status = "P/L_CONFLICT_REVIEW_REQUIRED"

    row: Dict[str, Any] = {
        "dataset_ts": parse_dt(meta.get("generated_at") or regime.get("cycle_ts")),
        "generated_at": parse_dt(meta.get("generated_at") or deterministic.get("generated_at")),
        "pipeline_version": str(meta.get("export_version") or deterministic.get("version") or "V3"),
        "dataset_hash": str(meta.get("dataset_sha256") or sha256_file(dataset_path)),
        "dataset_path": str(Path(dataset_path)),
        "market_session": str(meta.get("market_session") or regime.get("session_flag") or ""),
        "regime_label": str(regime.get("regime_short") or regime.get("regime") or ""),
        "regime_score": safe_float(regime.get("score")),
        "cio_posture": str(regime.get("action") or deterministic.get("readiness") or "REVIEW"),
        "confidence": safe_float(dataset.get("report_archive", {}).get("confidence") if isinstance(dataset.get("report_archive"), dict) else None),
        "vix": safe_float(regime.get("vix_level")),
        "fear_greed": safe_float(fear.get("score") or regime.get("fg_score")),
        "fear_greed_status": str(fear.get("label") or fear.get("rating") or ""),
        "usd_jpy": safe_float(fx_pressure.get("usd_jpy") or dataset.get("usd_jpy")),
        "uup_return": _return_from_live(dataset, "UUP"),
        "spy_return": _return_from_live(dataset, "SPY"),
        "qqq_return": _return_from_live(dataset, "QQQ"),
        "iwm_return": _return_from_live(dataset, "IWM"),
        "total_assets": total_assets,
        "cash_value": cash_value,
        "cash_weight": cash_weight,
        "market_value": market_value,
        "total_pnl": safe_float(portfolio.get("total_pnl")),
        "cash_fortress_mode": bool(cash_weight and cash_weight >= 0.70),
        "scout_mode": bool(market_value and market_value <= 5000 and cash_weight and cash_weight >= 0.70),
        "second_tranche_status": "",
        "scale_in_status": "",
        "execution_authority": str(deterministic.get("execution_authority") or execution.get("execution_authority") or "CIO_ONLY_MANUAL"),
        "order_routing_enabled": bool(deterministic.get("order_routing_enabled") or execution.get("order_routing_enabled")),
        "llm_order_generation_enabled": bool(execution.get("order_generation_enabled") or dataset.get("llm_order_generation_enabled", False)),
        "system_generated_orders": int(deterministic.get("orders_generated") or execution.get("orders_generated") or execution.get("orders_generated_by_pipeline") or 0),
        "data_integrity_status": str(portfolio.get("integrity_flag_reason") or portfolio.get("integrity_reason") or "OK"),
        "pnl_integrity_status": pnl_status,
        "blocked_actions_json": json_dumps(blocked_actions),
        "notes": "ACMS-COP v1 cycle extracted from V3 deterministic artifacts. Advisory only.",
    }
    gate = classify_confirmation_gate(row, {"regime_confirmed": "RISK_OFF" not in row["regime_label"].upper()})
    row["second_tranche_status"] = gate["second_tranche_status"]
    row["scale_in_status"] = gate["scale_in_status"]
    row["blocked_actions_json"] = json_dumps(gate["blocked_actions"])
    return row

