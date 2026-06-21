#!/usr/bin/env python3
"""
BlueLotus V2 dataset_raw.json contract validator.

This validator is intentionally observational:
- no database writes
- no broker calls
- no pipeline execution
- no order generation

It checks whether the exported dataset keeps the shape, coverage, risk,
forecasting, and CIO read-only doctrine expected by the V2 production
reporting layer.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_BLOCK_TYPES: dict[str, type] = {
    "meta": dict,
    "source_health": list,
    "regime": dict,
    "portfolio": dict,
    "live_prices": dict,
    "analyst_targets": dict,
    "fundamentals": dict,
    "capital_flow": dict,
    "treasury_yields": dict,
    "cross_market_confirmation": dict,
    "security_master": dict,
    "data_quality_sla": dict,
    "portfolio_readonly": dict,
    "historical_price_coverage": dict,
    "risk_model": dict,
    "portfolio_targets": dict,
    "thesis_lifecycle": dict,
    "monitoring": dict,
    "audit": dict,
    "dataset_snapshot_archive": dict,
    "freshness_recovery": dict,
    "historical_backfill": dict,
    "cio_decisions": dict,
    "cio_cognition": dict,
    "orders": dict,
    "fills": dict,
    "execution": dict,
    "trade_lifecycle": dict,
    "transaction_cost_analysis": dict,
    "corporate_actions": dict,
    "institutional_quant": dict,
    "research_forecasting": dict,
    "signals": dict,
    "signals_latest": list,
}

MIN_COVERAGE = {
    "live_prices": 180,
    "analyst_targets": 150,
    "fundamentals": 180,
    "capital_flow": 180,
    "source_health": 50,
    "signals": 50,
    "signals_latest": 100,
}

OPTIONAL_COUNT_BLOCKS = {
    "corporate_actions": 150,
    "historical_price_coverage.coverage_by_ticker": 180,
    "security_master": 180,
}

UNKNOWN_VALUES = {"", "UNKNOWN", "N/A", "NA", "NONE", "NULL"}
REQUIRED_FORECAST_METHODS = {"BLUELOTUS_CONSERVATIVE", "ANALYST_CONSENSUS"}
REQUIRED_CROSS_MARKET_KEYS = {
    "derived_scores",
    "interpretation_flags",
    "sector_etf_rotation",
    "market_index_confirmation",
    "volatility_panic_confirmation",
    "credit_liquidity_stress",
    "dollar_rates_pressure",
}


@dataclass
class Finding:
    status: str
    check: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContractReport:
    dataset_path: str
    generated_at: str
    counts: dict[str, int]
    findings: list[dict[str, Any]]


class Contract:
    def __init__(self, dataset_path: Path, verbose: bool = True) -> None:
        self.dataset_path = dataset_path
        self.verbose = verbose
        self.findings: list[Finding] = []

    def add(self, status: str, check: str, message: str, **detail: Any) -> None:
        self.findings.append(Finding(status=status, check=check, message=message, detail=detail))
        if self.verbose:
            print(f"[{status}] {check}: {message}")

    def ok(self, check: str, message: str, **detail: Any) -> None:
        self.add("PASS", check, message, **detail)

    def warn(self, check: str, message: str, **detail: Any) -> None:
        self.add("WARN", check, message, **detail)

    def fail(self, check: str, message: str, **detail: Any) -> None:
        self.add("FAIL", check, message, **detail)

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for finding in self.findings:
            out[finding.status] = out.get(finding.status, 0) + 1
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "dataset_path": str(self.dataset_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "counts": self.counts(),
            "findings": [
                {
                    "status": f.status,
                    "check": f.check,
                    "message": f.message,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
        }


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    candidates = [
        text,
        text.replace(" ", "T"),
        text.split(".")[0],
        text.replace(" ", "T").split(".")[0],
    ]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).replace(tzinfo=None)
        except Exception:
            continue
    return None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def block_count(value: Any) -> int:
    if isinstance(value, (dict, list)):
        return len(value)
    return 0


def real_security_master_count(security_master: Any) -> int:
    if not isinstance(security_master, dict):
        return 0
    return sum(1 for key, row in security_master.items() if not str(key).startswith("_") and isinstance(row, dict))


def nested_get(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def load_dataset(contract: Contract) -> dict[str, Any] | None:
    path = contract.dataset_path
    if not path.exists():
        contract.fail("dataset_file", "dataset_raw.json is missing", path=str(path))
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        contract.fail("dataset_file", "dataset_raw.json parse failed", error=str(exc))
        return None
    if not isinstance(data, dict):
        contract.fail("dataset_file", "dataset root must be a JSON object", actual_type=type(data).__name__)
        return None
    contract.ok("dataset_file", "dataset_raw.json parses as an object", size=path.stat().st_size, top_level_keys=len(data))
    return data


def check_required_blocks(contract: Contract, data: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_BLOCK_TYPES if key not in data]
    wrong_types: list[dict[str, str]] = []
    for key, expected_type in REQUIRED_BLOCK_TYPES.items():
        if key not in data:
            continue
        if not isinstance(data[key], expected_type):
            wrong_types.append(
                {
                    "block": key,
                    "expected": expected_type.__name__,
                    "actual": type(data[key]).__name__,
                }
            )
    if missing:
        contract.fail("required_blocks", "Required top-level dataset blocks are missing", missing=missing)
    else:
        contract.ok("required_blocks", "Required top-level dataset blocks are present", count=len(REQUIRED_BLOCK_TYPES))
    if wrong_types:
        contract.fail("required_blocks", "Required blocks have incorrect JSON types", wrong_types=wrong_types)
    else:
        contract.ok("required_blocks", "Required block types match contract", count=len(REQUIRED_BLOCK_TYPES))


def check_meta(contract: Contract, data: dict[str, Any]) -> None:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        contract.fail("meta", "meta block is not an object")
        return

    required = {
        "export_version": str,
        "ingest_version": str,
        "generated_at": str,
        "market_session": str,
        "sources_expected": int,
        "sources_active": int,
        "total_signals": int,
        "latest_signal_at": str,
    }
    missing = [key for key in required if key not in meta]
    wrong_types = [
        {"field": key, "expected": expected.__name__, "actual": type(meta.get(key)).__name__}
        for key, expected in required.items()
        if key in meta and not isinstance(meta.get(key), expected)
    ]
    if missing or wrong_types:
        contract.fail("meta", "meta block does not satisfy required field contract", missing=missing, wrong_types=wrong_types)
    else:
        contract.ok("meta", "meta block required fields present", export_version=meta["export_version"], ingest_version=meta["ingest_version"])

    expected = meta.get("sources_expected")
    active = meta.get("sources_active")
    if isinstance(expected, int) and isinstance(active, int):
        if expected >= 50 and active >= expected:
            contract.ok("meta", "source coverage metadata meets production threshold", sources_expected=expected, sources_active=active)
        else:
            contract.warn("meta", "source coverage metadata is below production threshold", sources_expected=expected, sources_active=active)

    total_signals = meta.get("total_signals")
    if isinstance(total_signals, int) and total_signals >= 1_000:
        contract.ok("meta", "signal archive depth is usable", total_signals=total_signals)
    else:
        contract.warn("meta", "signal archive depth is low", total_signals=total_signals)

    generated = parse_datetime(meta.get("generated_at"))
    if generated:
        age_min = max(0.0, (datetime.now() - generated).total_seconds() / 60.0)
        if age_min <= 180:
            contract.ok("freshness", "dataset generated_at is fresh", age_minutes=round(age_min, 2), generated_at=meta.get("generated_at"))
        else:
            contract.warn("freshness", "dataset generated_at is older than 180 minutes", age_minutes=round(age_min, 2), generated_at=meta.get("generated_at"))
    else:
        contract.warn("freshness", "dataset generated_at could not be parsed", generated_at=meta.get("generated_at"))

    latest = parse_datetime(meta.get("latest_signal_at"))
    if latest:
        age_min = max(0.0, (datetime.now() - latest).total_seconds() / 60.0)
        if age_min <= 240:
            contract.ok("freshness", "latest signal timestamp is fresh", age_minutes=round(age_min, 2), latest_signal_at=meta.get("latest_signal_at"))
        else:
            contract.warn("freshness", "latest signal timestamp is older than 240 minutes", age_minutes=round(age_min, 2), latest_signal_at=meta.get("latest_signal_at"))
    else:
        contract.warn("freshness", "latest_signal_at could not be parsed", latest_signal_at=meta.get("latest_signal_at"))


def check_coverage(contract: Contract, data: dict[str, Any]) -> None:
    for block, minimum in MIN_COVERAGE.items():
        count = block_count(data.get(block))
        if count >= minimum:
            contract.ok("coverage", f"{block} coverage meets threshold", count=count, expected_min=minimum)
        else:
            contract.warn("coverage", f"{block} coverage below threshold", count=count, expected_min=minimum)

    security_count = real_security_master_count(data.get("security_master"))
    if security_count >= OPTIONAL_COUNT_BLOCKS["security_master"]:
        contract.ok("coverage", "security_master real ticker coverage meets threshold", count=security_count, expected_min=OPTIONAL_COUNT_BLOCKS["security_master"])
    else:
        contract.warn("coverage", "security_master real ticker coverage below threshold", count=security_count, expected_min=OPTIONAL_COUNT_BLOCKS["security_master"])

    hist_coverage = nested_get(data, "historical_price_coverage.coverage_by_ticker")
    hist_count = block_count(hist_coverage)
    if hist_count >= OPTIONAL_COUNT_BLOCKS["historical_price_coverage.coverage_by_ticker"]:
        contract.ok("coverage", "historical price coverage meets threshold", count=hist_count, expected_min=OPTIONAL_COUNT_BLOCKS["historical_price_coverage.coverage_by_ticker"])
    else:
        contract.warn("coverage", "historical price coverage below threshold", count=hist_count, expected_min=OPTIONAL_COUNT_BLOCKS["historical_price_coverage.coverage_by_ticker"])


def check_security_master(contract: Contract, data: dict[str, Any]) -> None:
    sm = data.get("security_master")
    if not isinstance(sm, dict):
        contract.fail("security_master", "security_master block is not an object")
        return
    unknown_sector: list[str] = []
    missing_exchange: list[str] = []
    missing_asset_type: list[str] = []
    for ticker, row in sm.items():
        if str(ticker).startswith("_") or not isinstance(row, dict):
            continue
        sector = str(row.get("sector", "")).strip().upper()
        exchange = str(row.get("exchange", "")).strip().upper()
        asset_type = str(row.get("asset_type", "")).strip().upper()
        if sector in UNKNOWN_VALUES:
            unknown_sector.append(str(ticker))
        if exchange in UNKNOWN_VALUES:
            missing_exchange.append(str(ticker))
        if asset_type in UNKNOWN_VALUES:
            missing_asset_type.append(str(ticker))
    if not unknown_sector and not missing_exchange and not missing_asset_type:
        contract.ok("security_master", "security master classifications are populated", tickers=real_security_master_count(sm))
    else:
        contract.warn(
            "security_master",
            "security master has incomplete classifications",
            unknown_sector=unknown_sector[:20],
            missing_exchange=missing_exchange[:20],
            missing_asset_type=missing_asset_type[:20],
            counts={
                "unknown_sector": len(unknown_sector),
                "missing_exchange": len(missing_exchange),
                "missing_asset_type": len(missing_asset_type),
            },
        )


def check_cio_doctrine(contract: Contract, data: dict[str, Any]) -> None:
    failures: list[dict[str, Any]] = []

    cio = data.get("cio_decisions") if isinstance(data.get("cio_decisions"), dict) else {}
    if cio.get("orders_generated") not in (0, "0", False, None):
        failures.append({"path": "cio_decisions.orders_generated", "value": cio.get("orders_generated")})
    if cio.get("order_generation_enabled") not in (False, "False", "false", 0, "0", None):
        failures.append({"path": "cio_decisions.order_generation_enabled", "value": cio.get("order_generation_enabled")})
    if cio.get("execution_authority") not in ("CIO_ONLY", "CIO_ONLY_MANUAL", None):
        failures.append({"path": "cio_decisions.execution_authority", "value": cio.get("execution_authority")})

    cognition = data.get("cio_cognition") if isinstance(data.get("cio_cognition"), dict) else {}
    if cognition:
        if cognition.get("orders_generated") not in (0, "0", False, None):
            failures.append({"path": "cio_cognition.orders_generated", "value": cognition.get("orders_generated")})
        if cognition.get("order_generation_enabled") not in (False, "False", "false", 0, "0", None):
            failures.append({"path": "cio_cognition.order_generation_enabled", "value": cognition.get("order_generation_enabled")})
        if cognition.get("execution_authority") not in ("CIO_ONLY", "CIO_ONLY_MANUAL", None):
            failures.append({"path": "cio_cognition.execution_authority", "value": cognition.get("execution_authority")})

    risk_protocol = nested_get(data, "risk_model.execution_protocol")
    if isinstance(risk_protocol, dict):
        if risk_protocol.get("orders_generated") not in (False, 0, "0", "False", "false", None):
            failures.append({"path": "risk_model.execution_protocol.orders_generated", "value": risk_protocol.get("orders_generated")})
        if risk_protocol.get("execution_authority") not in ("CIO_ONLY", "CIO_ONLY_MANUAL", None):
            failures.append({"path": "risk_model.execution_protocol.execution_authority", "value": risk_protocol.get("execution_authority")})
    else:
        contract.warn("cio_doctrine", "risk_model execution_protocol is missing")

    target_protocol = nested_get(data, "portfolio_targets.execution_protocol")
    if isinstance(target_protocol, dict):
        if target_protocol.get("orders_generated") not in (False, 0, "0", "False", "false", None):
            failures.append({"path": "portfolio_targets.execution_protocol.orders_generated", "value": target_protocol.get("orders_generated")})
        if str(target_protocol.get("order_instruction", "NONE")).upper() not in ("NONE", "NO_ORDER", "RESEARCH_ONLY"):
            failures.append({"path": "portfolio_targets.execution_protocol.order_instruction", "value": target_protocol.get("order_instruction")})
        if target_protocol.get("execution_authority") not in ("CIO_ONLY", "CIO_ONLY_MANUAL", None):
            failures.append({"path": "portfolio_targets.execution_protocol.execution_authority", "value": target_protocol.get("execution_authority")})
    else:
        contract.warn("cio_doctrine", "portfolio_targets execution_protocol is missing")

    read_only = nested_get(data, "portfolio_readonly.read_only_protocol")
    if isinstance(read_only, dict):
        if read_only.get("read_only") is not True:
            failures.append({"path": "portfolio_readonly.read_only_protocol.read_only", "value": read_only.get("read_only")})
        if str(read_only.get("order_routing", "")).upper() != "DISABLED_BY_DESIGN":
            failures.append({"path": "portfolio_readonly.read_only_protocol.order_routing", "value": read_only.get("order_routing")})
        if read_only.get("prohibited_methods_called") not in ([], None):
            failures.append({"path": "portfolio_readonly.read_only_protocol.prohibited_methods_called", "value": read_only.get("prohibited_methods_called")})
    else:
        failures.append({"path": "portfolio_readonly.read_only_protocol", "value": None})

    if failures:
        contract.fail("cio_doctrine", "CIO-only read/extract doctrine is violated", failures=failures)
    else:
        contract.ok("cio_doctrine", "CIO-only read/extract doctrine is preserved")


def check_execution_records(contract: Contract, data: dict[str, Any]) -> None:
    orders = data.get("orders") if isinstance(data.get("orders"), dict) else {}
    fills = data.get("fills") if isinstance(data.get("fills"), dict) else {}
    execution = data.get("execution") if isinstance(data.get("execution"), dict) else {}
    tca = data.get("transaction_cost_analysis") if isinstance(data.get("transaction_cost_analysis"), dict) else {}
    lifecycle = data.get("trade_lifecycle") if isinstance(data.get("trade_lifecycle"), dict) else {}

    failures: list[dict[str, Any]] = []
    for name, block in [("orders", orders), ("fills", fills), ("execution", execution), ("transaction_cost_analysis", tca)]:
        if block.get("orders_generated_by_pipeline") not in (False, 0, "0", "False", "false", None):
            failures.append({"path": f"{name}.orders_generated_by_pipeline", "value": block.get("orders_generated_by_pipeline")})
    if orders.get("order_routing_enabled") not in (False, 0, "0", "False", "false", None):
        failures.append({"path": "orders.order_routing_enabled", "value": orders.get("order_routing_enabled")})
    if execution.get("order_routing_enabled") not in (False, 0, "0", "False", "false", None):
        failures.append({"path": "execution.order_routing_enabled", "value": execution.get("order_routing_enabled")})

    protocol = orders.get("read_only_protocol") if isinstance(orders.get("read_only_protocol"), dict) else {}
    if protocol and protocol.get("read_only") is not True:
        failures.append({"path": "orders.read_only_protocol.read_only", "value": protocol.get("read_only")})
    if protocol and protocol.get("prohibited_methods_called") not in ([], None):
        failures.append({"path": "orders.read_only_protocol.prohibited_methods_called", "value": protocol.get("prohibited_methods_called")})

    if failures:
        contract.fail("execution_records", "Read-only execution record doctrine is violated", failures=failures)
        return

    order_status = orders.get("status")
    fill_status = fills.get("status")
    if order_status in {"operational", "partial_error", "no_records"} and fill_status in {"operational", "partial_error", "no_records"}:
        contract.ok(
            "execution_records",
            "Read-only order/deal history extraction is exported",
            orders_status=order_status,
            fills_status=fill_status,
            open_order_count=orders.get("open_order_count"),
            historical_order_count=orders.get("historical_order_count"),
            open_deal_count=fills.get("open_deal_count"),
            historical_deal_count=fills.get("historical_deal_count"),
            fee_record_count=orders.get("fee_record_count"),
        )
    else:
        contract.warn("execution_records", "Read-only order/deal history extraction is not operational", orders_status=order_status, fills_status=fill_status)

    if execution and lifecycle and tca:
        contract.ok("execution_records", "Execution governance, lifecycle, and TCA blocks are present")
    else:
        contract.warn("execution_records", "Execution governance/lifecycle/TCA blocks are incomplete")


def check_cross_market(contract: Contract, data: dict[str, Any]) -> None:
    cm = data.get("cross_market_confirmation")
    if not isinstance(cm, dict):
        contract.fail("cross_market", "cross_market_confirmation block is not an object")
        return
    missing = sorted(REQUIRED_CROSS_MARKET_KEYS - set(cm))
    if missing:
        contract.warn("cross_market", "cross-market confirmation keys are missing", missing=missing)
    else:
        contract.ok("cross_market", "cross-market confirmation blocks are present", keys=len(REQUIRED_CROSS_MARKET_KEYS))
    coverage = cm.get("coverage_ratio")
    filled = cm.get("filled_count")
    ticker_count = cm.get("ticker_count")
    if is_number(coverage) and coverage >= 0.9 and isinstance(filled, int) and isinstance(ticker_count, int) and filled >= int(ticker_count * 0.9):
        contract.ok("cross_market", "cross-market coverage meets threshold", coverage_ratio=coverage, filled_count=filled, ticker_count=ticker_count)
    else:
        contract.warn("cross_market", "cross-market coverage is below threshold", coverage_ratio=coverage, filled_count=filled, ticker_count=ticker_count)
    derived = cm.get("derived_scores")
    flags = cm.get("interpretation_flags")
    if isinstance(derived, dict) and len(derived) >= 6 and isinstance(flags, dict) and len(flags) >= 6:
        contract.ok("cross_market", "cross-market derived scores and flags are populated", scores=len(derived), flags=len(flags))
    else:
        contract.warn("cross_market", "cross-market derived scores or flags are thin", scores=block_count(derived), flags=block_count(flags))


def check_risk_model(contract: Contract, data: dict[str, Any]) -> None:
    risk = data.get("risk_model")
    if not isinstance(risk, dict):
        contract.fail("risk_model", "risk_model block is not an object")
        return
    status = str(risk.get("status", "")).lower()
    if status == "operational":
        contract.ok("risk_model", "risk model status is operational")
    else:
        contract.warn("risk_model", "risk model status is not operational", status=risk.get("status"))
    required_numeric = ["portfolio_value", "cash_weight", "invested_weight", "beta_to_spy", "volatility_annualized", "max_drawdown"]
    missing_numeric = [key for key in required_numeric if not is_number(risk.get(key))]
    if missing_numeric:
        contract.warn("risk_model", "risk model numeric fields are missing or non-numeric", missing=missing_numeric)
    else:
        contract.ok("risk_model", "risk model numeric fields are populated", fields=required_numeric)
    observations = risk.get("return_observations")
    if isinstance(observations, int) and observations >= 90:
        contract.ok("risk_model", "risk model has sufficient return observations", return_observations=observations)
    else:
        contract.warn("risk_model", "risk model return observations are thin", return_observations=observations)
    hv = risk.get("historical_var")
    if isinstance(hv, dict) and "confidence_95" in hv and "confidence_99" in hv:
        contract.ok("risk_model", "historical VaR block is populated")
    else:
        contract.warn("risk_model", "historical VaR block is incomplete")
    exposures = risk.get("factor_exposures")
    if isinstance(exposures, dict) and isinstance(exposures.get("factor_betas"), dict) and len(exposures.get("factor_betas", {})) >= 5:
        contract.ok("risk_model", "factor exposures are populated", factors=len(exposures.get("factor_betas", {})))
    else:
        contract.warn("risk_model", "factor exposures are incomplete")


def check_forecasting(contract: Contract, data: dict[str, Any]) -> None:
    rf = data.get("research_forecasting")
    if not isinstance(rf, dict):
        contract.fail("research_forecasting", "research_forecasting block is not an object")
        return
    if str(rf.get("status", "")).lower() == "operational":
        contract.ok("research_forecasting", "forecasting block is operational")
    else:
        contract.warn("research_forecasting", "forecasting block is not operational", status=rf.get("status"))
    ticker_count = rf.get("ticker_count")
    forecast_count = rf.get("forecast_count")
    if isinstance(ticker_count, int) and ticker_count >= 180 and isinstance(forecast_count, int) and forecast_count >= ticker_count:
        contract.ok("research_forecasting", "forecast coverage meets threshold", ticker_count=ticker_count, forecast_count=forecast_count)
    else:
        contract.warn("research_forecasting", "forecast coverage below threshold", ticker_count=ticker_count, forecast_count=forecast_count)
    methods = set(rf.get("methods") or [])
    missing_methods = sorted(REQUIRED_FORECAST_METHODS - methods)
    if missing_methods:
        contract.fail("research_forecasting", "required forecast methods missing", missing=missing_methods, methods=sorted(methods))
    else:
        contract.ok("research_forecasting", "house and analyst forecast methods are present", methods=sorted(methods))
    if rf.get("brier_status"):
        contract.ok("research_forecasting", "Brier status is exported", brier_status=rf.get("brier_status"))
    else:
        contract.warn("research_forecasting", "Brier status is missing")


def check_institutional_quant(contract: Contract, data: dict[str, Any]) -> None:
    iq = data.get("institutional_quant")
    if not isinstance(iq, dict):
        contract.fail("institutional_quant", "institutional_quant block is not an object")
        return
    score = iq.get("readiness_score")
    if is_number(score):
        if score >= 90:
            contract.ok("institutional_quant", "institutional readiness score is 90+", readiness_score=score, label=iq.get("readiness_label"))
        elif score >= 75:
            contract.warn("institutional_quant", "institutional readiness score is advanced but below 90", readiness_score=score, label=iq.get("readiness_label"))
        else:
            contract.fail("institutional_quant", "institutional readiness score is below advanced threshold", readiness_score=score, label=iq.get("readiness_label"))
    else:
        contract.fail("institutional_quant", "institutional readiness score is missing or non-numeric", readiness_score=score)
    processes = iq.get("processes")
    if isinstance(processes, dict) and processes:
        failed = {name: row.get("status") for name, row in processes.items() if isinstance(row, dict) and str(row.get("status", "")).upper() == "FAIL"}
        if failed:
            contract.fail("institutional_quant", "institutional process failures present", failed=failed)
        else:
            contract.ok("institutional_quant", "institutional process checks have no FAIL status", process_count=len(processes))
    else:
        contract.warn("institutional_quant", "institutional process details are missing")


def check_data_quality_sla(contract: Contract, data: dict[str, Any]) -> None:
    sla = data.get("data_quality_sla")
    if not isinstance(sla, dict):
        contract.fail("data_quality_sla", "data_quality_sla block is not an object")
        return
    summary = sla.get("summary")
    if not isinstance(summary, dict):
        contract.warn("data_quality_sla", "SLA summary is missing")
        return
    sources_checked = summary.get("sources_checked")
    breach = summary.get("breach")
    warn = summary.get("warn")
    if isinstance(sources_checked, int) and sources_checked >= 50:
        contract.ok("data_quality_sla", "SLA source coverage meets threshold", sources_checked=sources_checked)
    else:
        contract.warn("data_quality_sla", "SLA source coverage is low", sources_checked=sources_checked)
    if isinstance(breach, int) and breach == 0:
        contract.ok("data_quality_sla", "No SLA breaches present")
    elif isinstance(breach, int):
        contract.warn("data_quality_sla", "SLA breaches present", breach=breach, warn=warn, breached_sources=summary.get("breached_sources"))
    else:
        contract.warn("data_quality_sla", "SLA breach count is missing", breach=breach)


def validate_dataset(dataset_path: Path | str, verbose: bool = True) -> dict[str, Any]:
    contract = Contract(Path(dataset_path), verbose=verbose)
    data = load_dataset(contract)
    if data is None:
        return contract.to_json()

    check_required_blocks(contract, data)
    check_meta(contract, data)
    check_coverage(contract, data)
    check_security_master(contract, data)
    check_cio_doctrine(contract, data)
    check_execution_records(contract, data)
    check_cross_market(contract, data)
    check_risk_model(contract, data)
    check_forecasting(contract, data)
    check_institutional_quant(contract, data)
    check_data_quality_sla(contract, data)
    return contract.to_json()


def write_report(report: dict[str, Any], output: Path | None, archive: bool = False, label: str = "contract") -> None:
    if not output:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[PASS] output: Wrote dataset contract JSON: {output}")
    if archive:
        safe_label = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (label or "contract"))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = output.parent / "dataset_contract_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"dataset_contract_{safe_label}_{stamp}.json"
        archive_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[PASS] output: Archived dataset contract JSON: {archive_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate BlueLotus V2 dataset_raw.json contract.")
    ap.add_argument("--dataset", default=r"C:\bluelotus3\data\frontend\dataset_raw.json", help="Path to dataset_raw.json.")
    ap.add_argument("--json-output", default="", help="Optional JSON output path.")
    ap.add_argument("--no-json-output", action="store_true", help="Do not write the latest JSON output artifact.")
    ap.add_argument("--archive", action="store_true", help="Archive a timestamped contract report.")
    ap.add_argument("--label", default="contract", help="Archive label.")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as non-zero exit.")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    print("BlueLotus V2 dataset_raw.json Contract Validator")
    print(f"Dataset: {dataset}")
    print(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    print()

    report = validate_dataset(dataset)
    counts = report.get("counts", {})
    print()
    print(f"Summary: PASS {counts.get('PASS', 0)} | WARN {counts.get('WARN', 0)} | FAIL {counts.get('FAIL', 0)}")

    output = None
    if not args.no_json_output:
        output = Path(args.json_output) if args.json_output else dataset.parent.parent / "audit" / "dataset_contract_latest.json"
    write_report(report, output, archive=args.archive, label=args.label)

    if counts.get("FAIL", 0):
        return 1
    if args.strict and counts.get("WARN", 0):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

