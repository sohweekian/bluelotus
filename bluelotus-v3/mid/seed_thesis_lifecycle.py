#!/usr/bin/env python3
"""
BlueLotus MID -- thesis lifecycle updater.

This module seeds and updates the core investment theses as database records.
It reads the current dataset and converts cross-market flags, regime evidence,
forecast state, and risk telemetry into conservative thesis probabilities.

The output is a research accountability layer, not an execution layer.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
DATASET_PATH = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "thesis" / "thesis_lifecycle_latest.json"


def n(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(str(value).replace(",", "").replace("N/A", "").replace("--", "").strip() or default)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def clamp(value: float, low: float = 0.25, high: float = 0.80) -> float:
    return max(low, min(high, value))


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


def load_dataset() -> Dict[str, Any]:
    if not DATASET_PATH.exists():
        return {}
    try:
        return json.loads(DATASET_PATH.read_text(encoding="utf-8"))
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


THESIS_TEMPLATES = [
    {
        "thesis_id": "THESIS-GOLD-SAFE-HAVEN",
        "thesis_name": "Gold and Miners as Safe-Haven Stress Beneficiaries",
        "priority": "P1",
        "base_probability": 0.55,
        "direction": "BULLISH_GOLD_MINERS",
        "horizon_days": 90,
        "tickers": [("GLD", "proxy", 0.15), ("SLV", "proxy", 0.10), ("GDX", "miner_basket", 0.12), ("GDXJ", "miner_basket", 0.10), ("AU", "portfolio_or_watch", 0.20), ("NEM", "large_cap_miner", 0.15)],
        "kill_condition": "Gold and miners both underperform SPY while real-rate/dollar pressure remains high for multiple cycles.",
    },
    {
        "thesis_id": "THESIS-AI-SEMIS-RISK",
        "thesis_name": "AI Semis Fragility Under Risk-Off and Valuation Compression",
        "priority": "P1",
        "base_probability": 0.52,
        "direction": "RISK_REDUCTION_AI_SEMIS",
        "horizon_days": 60,
        "tickers": [("NVDA", "leader", 0.18), ("AMD", "beta", 0.14), ("AVGO", "quality", 0.12), ("MRVL", "beta", 0.10), ("MU", "memory_cycle", 0.10), ("QQQ", "proxy", 0.10), ("XLK", "proxy", 0.10)],
        "kill_condition": "QQQ/XLK regain leadership with positive breadth, no credit stress, and semis outperform for multiple cycles.",
    },
    {
        "thesis_id": "THESIS-BANKS-NIM-LIQUIDITY",
        "thesis_name": "Banks Benefit From NIM and Liquidity Rotation Only If Credit Stress Is Contained",
        "priority": "P2",
        "base_probability": 0.50,
        "direction": "SELECTIVE_BANKS",
        "horizon_days": 90,
        "tickers": [("BAC", "portfolio_or_watch", 0.18), ("WFC", "portfolio_or_watch", 0.18), ("JPM", "quality_bank", 0.15), ("XLF", "proxy", 0.12), ("GS", "capital_markets", 0.08), ("MS", "capital_markets", 0.08)],
        "kill_condition": "Credit stress rises while XLF underperforms SPY and yield curve/NIM proxy deteriorates.",
    },
    {
        "thesis_id": "THESIS-QUANTUM-PANIC",
        "thesis_name": "Quantum Speculative Beta Requires Panic-Control and Evidence Discipline",
        "priority": "P2",
        "base_probability": 0.54,
        "direction": "REDUCE_SPECULATIVE_BETA_UNLESS_CONFIRMED",
        "horizon_days": 45,
        "tickers": [("IONQ", "quality_beta", 0.16), ("QBTS", "speculative_beta", 0.16), ("QUBT", "speculative_beta", 0.14), ("RGTI", "speculative_beta", 0.14), ("QTUM", "proxy", 0.10)],
        "kill_condition": "Quantum names regain strength with confirmed catalyst and no broad speculative risk-off.",
    },
    {
        "thesis_id": "THESIS-CLEAN-ENERGY-RATES",
        "thesis_name": "Clean Energy Remains Rate-Sensitive Until Yield Pressure Eases",
        "priority": "P3",
        "base_probability": 0.50,
        "direction": "RATE_PRESSURE_ON_CLEAN_ENERGY",
        "horizon_days": 90,
        "tickers": [("ENPH", "leader", 0.16), ("FSLR", "quality", 0.14), ("SEDG", "turnaround", 0.10), ("RUN", "rate_beta", 0.10), ("PLUG", "speculative_beta", 0.08), ("BE", "industrial_clean", 0.08)],
        "kill_condition": "Yields fall, credit stress eases, and clean-energy basket outperforms cyclicals for multiple cycles.",
    },
    {
        "thesis_id": "THESIS-BROAD-RISK-OFF",
        "thesis_name": "Broad Market Risk-Off Overrides Single-Name Optimism",
        "priority": "P1",
        "base_probability": 0.50,
        "direction": "CAPITAL_PRESERVATION",
        "horizon_days": 30,
        "tickers": [("SPY", "market", 0.15), ("QQQ", "growth", 0.15), ("IWM", "small_cap", 0.12), ("HYG", "credit", 0.12), ("TLT", "rates", 0.10), ("VXX", "vol_proxy", 0.08)],
        "kill_condition": "Risk appetite, credit, breadth, and factor rotation all recover together.",
    },
]


def evaluate_template(template: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
    cm = dataset.get("cross_market_confirmation") if isinstance(dataset.get("cross_market_confirmation"), dict) else {}
    flags = cm.get("interpretation_flags") if isinstance(cm.get("interpretation_flags"), dict) else {}
    scores = cm.get("derived_scores") if isinstance(cm.get("derived_scores"), dict) else {}
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    risk = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    rf = dataset.get("research_forecasting") if isinstance(dataset.get("research_forecasting"), dict) else {}

    p = float(template["base_probability"])
    evidence = []
    contradictions = []
    tid = template["thesis_id"]

    def add(flag: bool, delta: float, text: str) -> None:
        nonlocal p
        if flag:
            p += delta
            evidence.append({"delta": round(delta, 4), "evidence": text})

    def contra(flag: bool, delta: float, text: str) -> None:
        nonlocal p
        if flag:
            p -= abs(delta)
            contradictions.append({"delta": round(-abs(delta), 4), "contradiction": text})

    if tid == "THESIS-GOLD-SAFE-HAVEN":
        add(bool(flags.get("gold_thesis_confirmed")), 0.08, "Gold/miner cross-market flag confirmed.")
        add(bool(flags.get("commodity_safe_haven_stress")), 0.04, "Commodity safe-haven stress flag active.")
        add(bool(flags.get("broad_market_risk_off")), 0.04, "Broad market risk-off supports safe-haven thesis.")
        contra(bool(flags.get("gold_thesis_tactical_pressure")), 0.05, "Gold positive but miners under tactical pressure.")
        contra(n(scores.get("dollar_pressure_score")) > 0.50, 0.03, "Dollar pressure can cap gold upside.")
    elif tid == "THESIS-AI-SEMIS-RISK":
        add(bool(flags.get("ai_thesis_failure")), 0.09, "AI/tech failure flag active.")
        add(bool(flags.get("tech_led_selloff")), 0.06, "Tech-led selloff confirmed.")
        add(bool(flags.get("growth_factor_under_pressure")), 0.04, "Growth factor under pressure.")
        contra(n(scores.get("risk_appetite_score")) > 0.50, 0.05, "Risk appetite score is positive.")
    elif tid == "THESIS-BANKS-NIM-LIQUIDITY":
        add(bool(flags.get("bank_thesis_confirmed")), 0.08, "XLF relative strength confirms bank thesis.")
        add(n((dataset.get("treasury_yields") or {}).get("nim_proxy")) > 0, 0.03, "NIM proxy is positive.")
        contra(bool(flags.get("credit_stress_active")), 0.08, "Credit stress is active.")
        contra(n(scores.get("bond_quality_vs_credit_score")) > 0.75, 0.04, "Quality bonds outperform credit.")
    elif tid == "THESIS-QUANTUM-PANIC":
        add(bool(flags.get("quantum_panic_liquidation")), 0.10, "Quantum panic liquidation flag active.")
        add(bool(flags.get("small_cap_risk_off")), 0.04, "Small-cap risk-off pressures speculative beta.")
        contra(n(scores.get("risk_appetite_score")) > 0.50, 0.04, "Risk appetite positive.")
    elif tid == "THESIS-CLEAN-ENERGY-RATES":
        add(bool(flags.get("yield_pressure_active")), 0.07, "Yield pressure active.")
        add(bool(flags.get("credit_stress_active")), 0.04, "Credit stress raises financing pressure.")
        contra(n(scores.get("yield_pressure_score")) < -0.25, 0.05, "Yield pressure easing.")
    elif tid == "THESIS-BROAD-RISK-OFF":
        add(bool(flags.get("broad_market_risk_off")), 0.10, "Broad market risk-off active.")
        add(bool(flags.get("credit_stress_active")), 0.06, "Credit stress active.")
        add(bool(flags.get("global_ex_us_risk_off")), 0.04, "Global ex-US risk-off active.")
        contra(n(scores.get("risk_appetite_score")) > 0.50, 0.06, "Risk appetite is positive.")

    if str(regime.get("regime") or "").upper().find("RISK") >= 0:
        p += 0.02
        evidence.append({"delta": 0.02, "evidence": f"Regime context: {regime.get('regime')}"})

    risk_breaches = risk.get("constraint_breaches") if isinstance(risk.get("constraint_breaches"), list) else []
    if risk_breaches and template["priority"] == "P1":
        p += 0.02
        evidence.append({"delta": 0.02, "evidence": "Portfolio risk constraints have active breaches."})

    forecast_status = rf.get("brier_status") or "collecting"
    confidence = 0.60 if evidence else 0.45
    if contradictions:
        confidence -= 0.08
    if forecast_status == "collecting":
        confidence -= 0.03

    current = clamp(p)
    status = "CONFIRMED" if current >= 0.62 and evidence else "CONTRADICTED" if current <= 0.42 and contradictions else "ACTIVE"
    return {
        **template,
        "version": "v1.0",
        "status": status,
        "current_probability": round(current, 6),
        "confidence": round(clamp(confidence, 0.25, 0.80), 6),
        "evidence": evidence,
        "contradictions": contradictions,
        "last_evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "doctrine": "Thesis probabilities are conservative research probabilities, not trade instructions.",
    }


def build_thesis_package(dataset: Dict[str, Any]) -> Dict[str, Any]:
    theses = [evaluate_template(t, dataset) for t in THESIS_TEMPLATES]
    counts: Dict[str, int] = {}
    for row in theses:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "version": "v1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "seed_thesis_lifecycle.py",
        "status": "operational",
        "thesis_count": len(theses),
        "status_counts": counts,
        "theses": theses,
    }


def write_database(package: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        for thesis in package.get("theses") or []:
            cur.execute(
                """
                INSERT INTO thesis_lifecycle (
                    thesis_id, thesis_name, version, status, priority,
                    base_probability, current_probability, confidence,
                    direction, horizon_days, thesis_json, evidence_json,
                    contradiction_json, kill_condition
                ) VALUES (
                    %s,%s,%s,%s,%s, %s,%s,%s, %s,%s, CAST(%s AS JSON),
                    CAST(%s AS JSON),CAST(%s AS JSON),%s
                )
                ON DUPLICATE KEY UPDATE
                    thesis_name = VALUES(thesis_name),
                    version = VALUES(version),
                    status = VALUES(status),
                    priority = VALUES(priority),
                    base_probability = VALUES(base_probability),
                    current_probability = VALUES(current_probability),
                    confidence = VALUES(confidence),
                    direction = VALUES(direction),
                    horizon_days = VALUES(horizon_days),
                    thesis_json = VALUES(thesis_json),
                    evidence_json = VALUES(evidence_json),
                    contradiction_json = VALUES(contradiction_json),
                    kill_condition = VALUES(kill_condition)
                """,
                (
                    thesis["thesis_id"],
                    thesis["thesis_name"],
                    thesis["version"],
                    thesis["status"],
                    thesis["priority"],
                    thesis["base_probability"],
                    thesis["current_probability"],
                    thesis["confidence"],
                    thesis["direction"],
                    thesis["horizon_days"],
                    json_dumps(thesis),
                    json_dumps(thesis.get("evidence") or []),
                    json_dumps(thesis.get("contradictions") or []),
                    thesis.get("kill_condition"),
                ),
            )
            for ticker, role, weight in thesis.get("tickers") or []:
                cur.execute(
                    """
                    INSERT INTO thesis_ticker_links (
                        thesis_id, ticker, role, weight, rationale
                    ) VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        role = VALUES(role),
                        weight = VALUES(weight),
                        rationale = VALUES(rationale)
                    """,
                    (
                        thesis["thesis_id"],
                        ticker,
                        role,
                        weight,
                        f"{thesis['thesis_name']} / {role}",
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
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(package), ensure_ascii=False, indent=2), encoding="utf-8")


def write_raw_signal(package: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    summary = (
        f"Thesis lifecycle: {package.get('thesis_count')} theses | "
        f"counts {package.get('status_counts')}"
    )
    write_raw_signal(
        source="Thesis_Lifecycle",
        ingestion_method="dataset_cross_market_thesis_update",
        raw_payload=json_safe(package),
        raw_text=summary,
        signal_type="research",
        suspected_category="THESIS_CONFIRMATION",
        suspected_entities=[t.get("thesis_id") for t in package.get("theses") or []],
        suspected_impact="medium",
        quality_score=0.90,
        quality_flags={"research_only": True, "orders_generated": False},
    )


def main() -> None:
    ensure_tables()
    dataset = load_dataset()
    package = build_thesis_package(dataset)
    write_database(package)
    write_outputs(package)
    write_raw_signal(package)
    print("BlueLotus thesis lifecycle updated.")
    print(f"Theses: {package['thesis_count']} | Status counts: {package['status_counts']}")


if __name__ == "__main__":
    main()

