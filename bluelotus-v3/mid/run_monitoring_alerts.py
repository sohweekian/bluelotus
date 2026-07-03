#!/usr/bin/env python3
"""
BlueLotus MID -- monitoring, alert, and lineage runner.

Reads dataset_raw.json and latest institutional artifacts, writes:
- monitoring_alerts table
- data_lineage_events table
- data/audit/monitoring_alerts_latest.json
- raw_signal_archive source Monitoring_Governance
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(r"C:\bluelotus3")
DATASET_PATH = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
RISK_PATH = PROJECT_ROOT / "data" / "risk" / "risk_model_latest.json"
THESIS_PATH = PROJECT_ROOT / "data" / "thesis" / "thesis_lifecycle_latest.json"
HISTORY_PATH = PROJECT_ROOT / "data" / "history" / "historical_price_coverage_latest.json"
AUDIT_OUTPUT = PROJECT_ROOT / "data" / "audit" / "monitoring_alerts_latest.json"


def n(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(str(value).replace(",", "").replace("N/A", "").replace("--", "").strip() or default)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(sep=" ")
        except TypeError:
            return value.isoformat()
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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def get_connection():
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection as _get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    return _get_connection()


def make_alert(cycle_ts: str, severity: str, layer: str, alert_type: str,
               title: str, message: str, payload: Dict[str, Any] | None = None,
               ticker: str | None = None) -> Dict[str, Any]:
    seed = f"{cycle_ts}|{severity}|{layer}|{alert_type}|{title}|{ticker or ''}|{message}"
    return {
        "alert_id": f"ALERT-{sha256_text(seed)[:20]}",
        "cycle_ts": cycle_ts,
        "severity": severity,
        "layer_name": layer,
        "alert_type": alert_type,
        "title": title,
        "message": message,
        "related_ticker": ticker,
        "payload": payload or {},
        "resolved": False,
    }


def build_alerts(dataset: Dict[str, Any], risk: Dict[str, Any], thesis: Dict[str, Any], history: Dict[str, Any]) -> List[Dict[str, Any]]:
    cycle_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alerts: List[Dict[str, Any]] = []

    freshness = ((dataset.get("meta") or {}).get("freshness") or {})
    for section, row in freshness.items():
        if section == "thresholds" or not isinstance(row, dict):
            continue
        grade = str(row.get("grade") or "UNKNOWN").upper()
        if grade in {"STALE", "UNKNOWN"}:
            sev = "CRITICAL" if section in {"portfolio", "live_prices", "risk_model"} and grade == "STALE" else "WARNING"
            alerts.append(make_alert(
                cycle_ts, sev, "freshness", "section_freshness",
                f"{section} freshness {grade}",
                f"Dataset section {section} is {grade}; age_minutes={row.get('age_minutes')}.",
                {"section": section, **row},
            ))

    sla = dataset.get("data_quality_sla") if isinstance(dataset.get("data_quality_sla"), dict) else {}
    for src in (sla.get("summary") or {}).get("breached_sources") or []:
        alerts.append(make_alert(
            cycle_ts, "WARNING", "data_quality_sla", "source_sla_breach",
            f"SLA breach: {src}",
            f"Source {src} exceeded expected refresh SLA.",
            {"source": src},
        ))

    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    if portfolio.get("integrity_flag"):
        alerts.append(make_alert(
            cycle_ts, "CRITICAL", "portfolio", "integrity_flag",
            "Portfolio integrity flag active",
            str(portfolio.get("integrity_flag_reason") or "Portfolio requires reconciliation."),
            {"portfolio_source": portfolio.get("data_source"), "cycle_ts": portfolio.get("cycle_ts")},
        ))

    risk_breaches = risk.get("constraint_breaches") if isinstance(risk.get("constraint_breaches"), list) else []
    for breach in risk_breaches:
        alerts.append(make_alert(
            cycle_ts, "WARNING", "risk_model", str(breach.get("type") or "constraint_breach"),
            f"Risk constraint breach: {breach.get('type')}",
            f"Risk model reports {breach.get('type')} value={breach.get('value')} limit={breach.get('limit')}.",
            breach,
            ticker=breach.get("ticker"),
        ))
    if risk and n(risk.get("return_observations")) < 20:
        alerts.append(make_alert(
            cycle_ts, "WARNING", "risk_model", "low_history_observations",
            "Risk model has low return observations",
            f"Only {risk.get('return_observations')} return observations are available for portfolio VaR.",
            {"return_observations": risk.get("return_observations")},
        ))

    cm = dataset.get("cross_market_confirmation") if isinstance(dataset.get("cross_market_confirmation"), dict) else {}
    flags = cm.get("interpretation_flags") if isinstance(cm.get("interpretation_flags"), dict) else {}
    active_flags = [k for k, v in flags.items() if v]
    for flag in active_flags:
        sev = "WARNING" if any(token in flag for token in ["risk_off", "stress", "failure", "panic", "pressure"]) else "INFO"
        alerts.append(make_alert(
            cycle_ts, sev, "cross_market", "active_interpretation_flag",
            f"Cross-market flag: {flag}",
            f"Cross-market confirmation flag is active: {flag}.",
            {"flag": flag, "scores": cm.get("derived_scores") or {}},
        ))

    for row in thesis.get("theses") or []:
        if row.get("status") == "CONTRADICTED":
            alerts.append(make_alert(
                cycle_ts, "WARNING", "thesis_lifecycle", "thesis_contradicted",
                f"Thesis contradicted: {row.get('thesis_id')}",
                row.get("thesis_name") or "Thesis contradicted by current evidence.",
                {"probability": row.get("current_probability"), "contradictions": row.get("contradictions")},
            ))
        elif row.get("status") == "CONFIRMED" and row.get("priority") == "P1":
            alerts.append(make_alert(
                cycle_ts, "INFO", "thesis_lifecycle", "p1_thesis_confirmed",
                f"P1 thesis confirmed: {row.get('thesis_id')}",
                row.get("thesis_name") or "P1 thesis confirmed.",
                {"probability": row.get("current_probability"), "evidence": row.get("evidence")},
            ))

    rf = dataset.get("research_forecasting") if isinstance(dataset.get("research_forecasting"), dict) else {}
    if rf.get("status") == "operational" and rf.get("brier_status") == "collecting":
        alerts.append(make_alert(
            cycle_ts, "INFO", "forecasting", "brier_collecting",
            "Brier engine collecting history",
            "Forecast accountability is operational, but no horizon has matured yet.",
            {"forecast_count": rf.get("forecast_count"), "ticker_count": rf.get("ticker_count")},
        ))

    if history:
        cov = n(history.get("coverage_ratio"))
        if cov < 0.80:
            alerts.append(make_alert(
                cycle_ts, "WARNING", "historical_prices", "coverage_low",
                "Historical price coverage below threshold",
                f"Moomoo historical price coverage is {cov:.1%}.",
                {"coverage_ratio": cov, "failed": history.get("failed")},
            ))

    return alerts


def build_lineage(dataset: Dict[str, Any], risk: Dict[str, Any], thesis: Dict[str, Any], history: Dict[str, Any], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    cycle_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dataset_sha = sha256_text(json_dumps(dataset)) if dataset else None
    return {
        "event_id": f"LINEAGE-{sha256_text(cycle_ts + str(dataset_sha))[:20]}",
        "cycle_ts": cycle_ts,
        "stage": "institutional_upgrade_monitoring",
        "dataset_sha256": dataset_sha,
        "input_refs": {
            "dataset_raw": str(DATASET_PATH),
            "risk_model": str(RISK_PATH),
            "thesis_lifecycle": str(THESIS_PATH),
            "historical_price_coverage": str(HISTORY_PATH),
        },
        "output_refs": {
            "monitoring_alerts": str(AUDIT_OUTPUT),
        },
        "metrics": {
            "alerts_count": len(alerts),
            "critical_count": sum(1 for a in alerts if a.get("severity") == "CRITICAL"),
            "warning_count": sum(1 for a in alerts if a.get("severity") == "WARNING"),
            "info_count": sum(1 for a in alerts if a.get("severity") == "INFO"),
        },
        "notes": "Monitoring and lineage are audit outputs only; no execution side effects.",
    }


def write_database(alerts: List[Dict[str, Any]], lineage: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        for alert in alerts:
            cur.execute(
                """
                INSERT INTO monitoring_alerts (
                    alert_id, cycle_ts, severity, layer_name, alert_type,
                    title, message, related_ticker, payload_json, resolved
                ) VALUES (
                    %s,%s,%s,%s,%s, %s,%s,%s,CAST(%s AS JSON),%s
                )
                ON DUPLICATE KEY UPDATE
                    severity = VALUES(severity),
                    title = VALUES(title),
                    message = VALUES(message),
                    payload_json = VALUES(payload_json),
                    resolved = VALUES(resolved)
                """,
                (
                    alert["alert_id"],
                    alert["cycle_ts"],
                    alert["severity"],
                    alert["layer_name"],
                    alert["alert_type"],
                    alert["title"],
                    alert["message"],
                    alert.get("related_ticker"),
                    json_dumps(alert.get("payload") or {}),
                    bool(alert.get("resolved")),
                ),
            )
        cur.execute(
            """
            INSERT INTO data_lineage_events (
                event_id, cycle_ts, stage, input_refs_json, output_refs_json,
                dataset_sha256, notes
            ) VALUES (
                %s,%s,%s,CAST(%s AS JSON),CAST(%s AS JSON),%s,%s
            )
            ON DUPLICATE KEY UPDATE
                input_refs_json = VALUES(input_refs_json),
                output_refs_json = VALUES(output_refs_json),
                dataset_sha256 = VALUES(dataset_sha256),
                notes = VALUES(notes)
            """,
            (
                lineage["event_id"],
                lineage["cycle_ts"],
                lineage["stage"],
                json_dumps(lineage.get("input_refs") or {}),
                json_dumps(lineage.get("output_refs") or {}),
                lineage.get("dataset_sha256"),
                lineage.get("notes"),
            ),
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_outputs(package: Dict[str, Any]) -> None:
    AUDIT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUTPUT.write_text(json.dumps(json_safe(package), ensure_ascii=False, indent=2), encoding="utf-8")


def write_raw_signal(package: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    summary = (
        f"Monitoring governance: alerts {package.get('alert_count')} | "
        f"critical {package.get('severity_counts', {}).get('CRITICAL', 0)} | "
        f"warnings {package.get('severity_counts', {}).get('WARNING', 0)}"
    )
    write_raw_signal(
        source="Monitoring_Governance",
        ingestion_method="dataset_alert_lineage_monitoring",
        raw_payload=json_safe(package),
        raw_text=summary,
        signal_type="governance",
        suspected_category="MONITORING_ALERTS",
        suspected_entities=[a.get("alert_id") for a in package.get("alerts") or []],
        suspected_impact="medium",
        quality_score=0.95,
        quality_flags={"research_only": True, "orders_generated": False},
    )


def run() -> Dict[str, Any]:
    ensure_tables()
    dataset = load_json(DATASET_PATH)
    risk = load_json(RISK_PATH) or (dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {})
    thesis = load_json(THESIS_PATH) or (dataset.get("thesis_lifecycle") if isinstance(dataset.get("thesis_lifecycle"), dict) else {})
    history = load_json(HISTORY_PATH)
    alerts = build_alerts(dataset, risk, thesis, history)
    lineage = build_lineage(dataset, risk, thesis, history, alerts)
    severity_counts: Dict[str, int] = {}
    for alert in alerts:
        severity_counts[alert["severity"]] = severity_counts.get(alert["severity"], 0) + 1
    package = {
        "version": "v1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "operational",
        "alert_count": len(alerts),
        "severity_counts": severity_counts,
        "alerts": alerts,
        "lineage": lineage,
    }
    write_database(alerts, lineage)
    write_outputs(package)
    write_raw_signal(package)
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BlueLotus monitoring and lineage alerts")
    parser.parse_args()
    package = run()
    print("BlueLotus monitoring governance complete.")
    print(f"Alerts: {package['alert_count']} | Severity: {package['severity_counts']}")


if __name__ == "__main__":
    main()

