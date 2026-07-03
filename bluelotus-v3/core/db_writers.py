"""
BlueLotus Digital Institution -- V2.0
core/db_writers.py

Departmental MySQL write functions.
Each department imports only their own function.

    Research Department:   from core.db_writers import write_research_report
    Risk Department:       from core.db_writers import write_risk_report
    CIO Layer:             from core.db_writers import write_cio_decision

All functions:
  - Accept a plain Python dict matching the table schema
  - Validate required fields before attempting any DB write
  - Return the inserted row id on success
  - Raise a clear ValueError or RuntimeError on failure
  - Are safe to call multiple times per day (UNIQUE constraint on report_date
    triggers an UPDATE rather than a second INSERT for research and risk)

Environment variables (inherited from .env via python-dotenv):
  MYSQL_HOST     / DB_HOST      (default: 127.0.0.1)
  MYSQL_PORT     / DB_PORT      (default: 3306)
  MYSQL_USER     / DB_USER      (required)
  MYSQL_PASSWORD / DB_PASSWORD  (default: "")
  MYSQL_DATABASE / DB_NAME      (default: bluelotus2)

CIO:    Kian Soh
Author: Claude -- Frontend / Publishing Department
Date:   June 2026
"""

from __future__ import annotations

import json
import hashlib
import os
import logging
from datetime import datetime, date
from typing import Any, Dict, Optional

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("bluelotus.core.db_writers")

# ─────────────────────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────────────────────

def _get_connection():
    """Open and return a fresh MySQL connection from .env credentials."""
    return mysql.connector.connect(
        host     = os.getenv("MYSQL_HOST")     or os.getenv("DB_HOST",     "127.0.0.1"),
        port     = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT",     "3306")),
        user     = os.getenv("MYSQL_USER")     or os.getenv("DB_USER",     ""),
        password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", ""),
        database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME",     "bluelotus2"),
        charset  = "utf8mb4",
        autocommit = False,
    )


def _to_json(value: Any) -> Optional[str]:
    """Serialize a dict/list to JSON string, or pass through None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value  # already serialized
    return json.dumps(value, ensure_ascii=False, default=str)


def _require(data: dict, fields: list[str], context: str):
    """Raise ValueError if any required field is missing or empty."""
    missing = [f for f in fields if not data.get(f)]
    if missing:
        raise ValueError(f"[{context}] Missing required fields: {missing}")


# ─────────────────────────────────────────────────────────────
# RESEARCH DEPARTMENT
# write_research_report()
# ─────────────────────────────────────────────────────────────

def write_research_report(report: dict) -> int:
    """
    Write a research report to the research_reports table.

    Required fields in report dict:
        report_date              str or date  e.g. "2026-06-01"
        report_id                str          e.g. "research_20260601_150000"
        model_name               str          e.g. "grok-4"
        prompt_hash              str          SHA256 of the prompt sent to model
        dataset_snapshot_id      str          e.g. "snapshot_20260601_150000"
        regime_at_generation     str          "RISK_ON" | "RISK_OFF" | "NEUTRAL"
        market_outlook           str          Narrative text
        sector_outlook           dict         {sector: {direction, rationale, confidence}}
        ticker_recommendations   dict         {ticker: {action, thesis, probability, ...}}
        top_conviction_tickers   list         [{ticker, rationale, conviction_fi}]
        probability_assessments  dict         {event: probability}
        forecasts                list         [{ticker, target, horizon_days, conviction_fi}]

    Optional fields:
        key_catalysts            str
        risk_flags               str
        confidence_overall       float        0.0 to 1.0  (default 0.0)
        model_version            str
        schema_version           str          (default "1.0")

    Returns:
        int — the inserted or updated row id

    Behaviour:
        If a record for report_date already exists (agent re-runs same day),
        this function UPDATES the existing record rather than raising a
        duplicate key error. Only one research report per trading date.
    """
    _require(report, [
        "report_date", "report_id", "model_name", "prompt_hash",
        "dataset_snapshot_id", "regime_at_generation", "market_outlook",
        "sector_outlook", "ticker_recommendations", "top_conviction_tickers",
        "probability_assessments", "forecasts",
    ], "write_research_report")

    conn = _get_connection()
    try:
        cur = conn.cursor()

        sql = """
            INSERT INTO research_reports (
                report_date, report_id, generated_at,
                model_name, model_version, prompt_hash,
                dataset_snapshot_id, regime_at_generation,
                market_outlook, sector_outlook,
                ticker_recommendations, top_conviction_tickers,
                probability_assessments, forecasts,
                key_catalysts, risk_flags,
                confidence_overall, delivered_to_publishing, schema_version
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, 0, %s
            )
            ON DUPLICATE KEY UPDATE
                report_id              = VALUES(report_id),
                generated_at           = VALUES(generated_at),
                model_name             = VALUES(model_name),
                model_version          = VALUES(model_version),
                prompt_hash            = VALUES(prompt_hash),
                dataset_snapshot_id    = VALUES(dataset_snapshot_id),
                regime_at_generation   = VALUES(regime_at_generation),
                market_outlook         = VALUES(market_outlook),
                sector_outlook         = VALUES(sector_outlook),
                ticker_recommendations = VALUES(ticker_recommendations),
                top_conviction_tickers = VALUES(top_conviction_tickers),
                probability_assessments= VALUES(probability_assessments),
                forecasts              = VALUES(forecasts),
                key_catalysts          = VALUES(key_catalysts),
                risk_flags             = VALUES(risk_flags),
                confidence_overall     = VALUES(confidence_overall),
                schema_version         = VALUES(schema_version)
        """

        params = (
            str(report["report_date"]),
            report["report_id"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            report["model_name"],
            report.get("model_version"),
            report["prompt_hash"],
            report["dataset_snapshot_id"],
            report["regime_at_generation"],
            report["market_outlook"],
            _to_json(report["sector_outlook"]),
            _to_json(report["ticker_recommendations"]),
            _to_json(report["top_conviction_tickers"]),
            _to_json(report["probability_assessments"]),
            _to_json(report["forecasts"]),
            report.get("key_catalysts"),
            report.get("risk_flags"),
            float(report.get("confidence_overall", 0.0)),
            report.get("schema_version", "1.0"),
        )

        cur.execute(sql, params)
        conn.commit()

        # Fetch the row id (INSERT or UPDATE)
        cur.execute(
            "SELECT id FROM research_reports WHERE report_date = %s",
            (str(report["report_date"]),)
        )
        row = cur.fetchone()
        row_id = row[0] if row else cur.lastrowid
        cur.close()

        logger.info(
            "[Research] Written report_id=%s  date=%s  regime=%s  confidence=%.3f  row_id=%d",
            report["report_id"], report["report_date"],
            report["regime_at_generation"],
            float(report.get("confidence_overall", 0.0)),
            row_id,
        )
        return row_id

    except Exception as e:
        conn.rollback()
        logger.error("[Research] write_research_report FAILED: %s", e)
        raise RuntimeError(f"write_research_report failed: {e}") from e
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# RISK DEPARTMENT
# write_risk_report()
# ─────────────────────────────────────────────────────────────

def write_risk_report(report: dict) -> int:
    """
    Write a risk report to the risk_reports table.

    Required fields in report dict:
        report_date              str or date  e.g. "2026-06-01"
        report_id                str          e.g. "risk_20260601_150200"
        model_name               str          e.g. "grok-4"
        prompt_hash              str          SHA256 of the prompt sent to model
        dataset_snapshot_id      str          e.g. "snapshot_20260601_150000"
        regime_at_generation     str          "RISK_ON" | "RISK_OFF" | "NEUTRAL"
        portfolio_risk_summary   str          Narrative text
        regime_risk_score        int          -12 to +12
        risk_assessments         dict         {ticker: {risk_score, risk_summary, key_risks}}
        counterarguments         dict         {ticker: {bull_thesis, bear_thesis, key_risk}}
        scenario_risks           dict         {bull, base, bear, black_swan} each with
                                              {probability, description, portfolio_impact}
        macro_risks              list         [{risk_type, description, severity, lens}]
        sector_exposure_risk     dict         {sector: {exposure_pct, risk_rating, comment}}
        overall_risk_rating      str          "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

    Optional fields:
        geopolitical_risks       list
        recommended_actions      list
        model_version            str
        schema_version           str          (default "1.0")

    Returns:
        int — the inserted or updated row id

    Behaviour:
        Same as write_research_report — UPDATE on duplicate report_date.
    """
    _require(report, [
        "report_date", "report_id", "model_name", "prompt_hash",
        "dataset_snapshot_id", "regime_at_generation",
        "portfolio_risk_summary", "risk_assessments", "counterarguments",
        "scenario_risks", "macro_risks", "sector_exposure_risk",
        "overall_risk_rating",
    ], "write_risk_report")

    # Validate scenario_risks has all four required keys
    sr = report.get("scenario_risks", {})
    if isinstance(sr, str):
        sr = json.loads(sr)
    missing_scenarios = [k for k in ("bull", "base", "bear", "black_swan") if k not in sr]
    if missing_scenarios:
        raise ValueError(
            f"[write_risk_report] scenario_risks missing keys: {missing_scenarios}. "
            "All four scenarios (bull, base, bear, black_swan) are mandatory."
        )

    conn = _get_connection()
    try:
        cur = conn.cursor()

        sql = """
            INSERT INTO risk_reports (
                report_date, report_id, generated_at,
                model_name, model_version, prompt_hash,
                dataset_snapshot_id, regime_at_generation,
                portfolio_risk_summary, regime_risk_score,
                risk_assessments, counterarguments,
                scenario_risks, macro_risks,
                geopolitical_risks, sector_exposure_risk,
                recommended_actions, overall_risk_rating,
                delivered_to_publishing, schema_version
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                0, %s
            )
            ON DUPLICATE KEY UPDATE
                report_id              = VALUES(report_id),
                generated_at           = VALUES(generated_at),
                model_name             = VALUES(model_name),
                model_version          = VALUES(model_version),
                prompt_hash            = VALUES(prompt_hash),
                dataset_snapshot_id    = VALUES(dataset_snapshot_id),
                regime_at_generation   = VALUES(regime_at_generation),
                portfolio_risk_summary = VALUES(portfolio_risk_summary),
                regime_risk_score      = VALUES(regime_risk_score),
                risk_assessments       = VALUES(risk_assessments),
                counterarguments       = VALUES(counterarguments),
                scenario_risks         = VALUES(scenario_risks),
                macro_risks            = VALUES(macro_risks),
                geopolitical_risks     = VALUES(geopolitical_risks),
                sector_exposure_risk   = VALUES(sector_exposure_risk),
                recommended_actions    = VALUES(recommended_actions),
                overall_risk_rating    = VALUES(overall_risk_rating),
                schema_version         = VALUES(schema_version)
        """

        params = (
            str(report["report_date"]),
            report["report_id"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            report["model_name"],
            report.get("model_version"),
            report["prompt_hash"],
            report["dataset_snapshot_id"],
            report["regime_at_generation"],
            report["portfolio_risk_summary"],
            int(report.get("regime_risk_score", 0)),
            _to_json(report["risk_assessments"]),
            _to_json(report["counterarguments"]),
            _to_json(report["scenario_risks"]),
            _to_json(report["macro_risks"]),
            _to_json(report.get("geopolitical_risks")),
            _to_json(report["sector_exposure_risk"]),
            _to_json(report.get("recommended_actions")),
            report["overall_risk_rating"],
            report.get("schema_version", "1.0"),
        )

        cur.execute(sql, params)
        conn.commit()

        cur.execute(
            "SELECT id FROM risk_reports WHERE report_date = %s",
            (str(report["report_date"]),)
        )
        row = cur.fetchone()
        row_id = row[0] if row else cur.lastrowid
        cur.close()

        logger.info(
            "[Risk] Written report_id=%s  date=%s  rating=%s  regime_score=%d  row_id=%d",
            report["report_id"], report["report_date"],
            report["overall_risk_rating"],
            int(report.get("regime_risk_score", 0)),
            row_id,
        )
        return row_id

    except Exception as e:
        conn.rollback()
        logger.error("[Risk] write_risk_report FAILED: %s", e)
        raise RuntimeError(f"write_risk_report failed: {e}") from e
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# CIO LAYER
# write_cio_decision()
# ─────────────────────────────────────────────────────────────

def write_cio_decision(decision: dict) -> int:
    """
    Write a CIO decision to the cio_decisions table.

    Required fields in decision dict:
        decision_id            str   e.g. "cio_20260601_152300_001"
        decision_date          str   e.g. "2026-06-01"
        decision_time          str   e.g. "15:23:00"
        action                 str   "BUY"|"SELL"|"HOLD"|"ALLOCATE"|"REDUCE"|"STRATEGIC_NOTE"
        regime_at_decision     str   "RISK_ON" | "RISK_OFF" | "NEUTRAL"
        rationale              str   Mandatory. Why this decision was made.
        confidence             float 0.0 to 1.0

    Optional fields:
        ticker                 str
        quantity               int
        price_at_decision      float
        size_usd               float
        thesis_reference       str   Links to research_reports.report_id
        risk_reference         str   Links to risk_reports.report_id
        portfolio_pct_before   float
        portfolio_pct_after    float
        entry_type             str   "L1_ENTRY"|"L2_ADD"|"FULL_EXIT"|"PARTIAL_EXIT"|"FREE_RIDER"
        working_order_placed   int   1 or 0
        order_price            float
        strategic_note         str
        outcome_review_date    str   e.g. "2026-09-01"  (90 days for positions)
        schema_version         str   (default "1.0")

    Returns:
        int — the inserted row id

    Behaviour:
        CIO decisions are INSERT ONLY. No update on duplicate.
        Each decision gets its own unique decision_id.
        If you need to amend a decision, insert a new record with
        action="STRATEGIC_NOTE" and reference the original decision_id
        in the rationale field.
    """
    _require(decision, [
        "decision_id", "decision_date", "decision_time",
        "action", "regime_at_decision", "rationale", "confidence",
    ], "write_cio_decision")

    # Validate action value
    valid_actions = {"BUY", "SELL", "HOLD", "ALLOCATE", "REDUCE", "STRATEGIC_NOTE"}
    if decision["action"].upper() not in valid_actions:
        raise ValueError(
            f"[write_cio_decision] Invalid action '{decision['action']}'. "
            f"Must be one of: {valid_actions}"
        )

    # Validate rationale is not empty
    if not str(decision.get("rationale", "")).strip():
        raise ValueError(
            "[write_cio_decision] rationale is mandatory and cannot be empty. "
            "An undocumented CIO decision is not an institutional decision."
        )

    conn = _get_connection()
    try:
        cur = conn.cursor()

        sql = """
            INSERT INTO cio_decisions (
                decision_id, decision_date, decision_time, recorded_at,
                action, ticker, quantity,
                price_at_decision, size_usd, confidence,
                rationale, thesis_reference, risk_reference,
                regime_at_decision,
                portfolio_pct_before, portfolio_pct_after,
                entry_type, working_order_placed, order_price,
                strategic_note, outcome_review_date,
                outcome_recorded, schema_version
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                0, %s
            )
        """

        params = (
            decision["decision_id"],
            str(decision["decision_date"]),
            str(decision["decision_time"]),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            decision["action"].upper(),
            decision.get("ticker"),
            decision.get("quantity"),
            decision.get("price_at_decision"),
            decision.get("size_usd"),
            float(decision["confidence"]),
            str(decision["rationale"]).strip(),
            decision.get("thesis_reference"),
            decision.get("risk_reference"),
            decision["regime_at_decision"],
            decision.get("portfolio_pct_before"),
            decision.get("portfolio_pct_after"),
            decision.get("entry_type"),
            int(decision.get("working_order_placed", 0)),
            decision.get("order_price"),
            decision.get("strategic_note"),
            decision.get("outcome_review_date"),
            decision.get("schema_version", "1.0"),
        )

        cur.execute(sql, params)
        conn.commit()
        row_id = cur.lastrowid
        cur.close()

        logger.info(
            "[CIO] Written decision_id=%s  action=%s  ticker=%s  confidence=%.3f  row_id=%d",
            decision["decision_id"],
            decision["action"].upper(),
            decision.get("ticker", "N/A"),
            float(decision["confidence"]),
            row_id,
        )
        return row_id

    except mysql.connector.IntegrityError as e:
        conn.rollback()
        raise RuntimeError(
            f"[write_cio_decision] Duplicate decision_id '{decision['decision_id']}'. "
            "Generate a unique decision_id for each decision."
        ) from e
    except Exception as e:
        conn.rollback()
        logger.error("[CIO] write_cio_decision FAILED: %s", e)
        raise RuntimeError(f"write_cio_decision failed: {e}") from e
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# UTILITY — prompt hash helper
# ─────────────────────────────────────────────────────────────

def hash_prompt(prompt: str) -> str:
    """
    Return SHA256 hex digest of a prompt string.
    Use this to populate the prompt_hash field before calling write functions.

    Example:
        from core.db_writers import hash_prompt
        prompt_hash = hash_prompt(my_prompt_string)
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def make_report_id(department: str) -> str:
    """
    Generate a standard report_id for research or risk reports.
    department: "research" or "risk"

    Example:
        report_id = make_report_id("research")
        # -> "research_20260601_150000"
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{department}_{ts}"


def make_decision_id(seq: int = 1) -> str:
    """
    Generate a standard decision_id for CIO decisions.
    seq: sequence number if multiple decisions in the same second.

    Example:
        decision_id = make_decision_id(seq=1)
        # -> "cio_20260601_152300_001"
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"cio_{ts}_{seq:03d}"


# ─────────────────────────────────────────────────────────────
# QUICK SMOKE TEST
# Run: python core/db_writers.py
# Inserts one test record per table and immediately deletes them.
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)s  %(message)s")

    print("=" * 60)
    print("  BlueLotus db_writers.py — smoke test")
    print("=" * 60)

    today = date.today().isoformat()
    errors = []

    # ── Test 1: research_reports ─────────────────────────────
    print("\n[1] Testing write_research_report...")
    try:
        test_research = {
            "report_date":             today,
            "report_id":               f"research_TEST_{datetime.now().strftime('%H%M%S')}",
            "model_name":              "test_model",
            "model_version":           "0.0",
            "prompt_hash":             hash_prompt("test prompt research"),
            "dataset_snapshot_id":     f"snapshot_TEST_{today}",
            "regime_at_generation":    "NEUTRAL",
            "market_outlook":          "TEST RECORD — smoke test only. Do not act on this.",
            "sector_outlook":          {"SEMICONDUCTORS": {"direction": "NEUTRAL", "rationale": "test", "confidence": 0.5}},
            "ticker_recommendations":  {"BAC": {"action": "HOLD", "thesis": "test", "probability": 0.5, "target_price": 52.0, "catalysts": []}},
            "top_conviction_tickers":  [{"ticker": "BAC", "rationale": "test", "conviction_fi": 0.5}],
            "probability_assessments": {"TEST_EVENT": 0.5},
            "forecasts":               [{"ticker": "BAC", "target": 54.0, "horizon_days": 90, "conviction_fi": 0.5}],
            "key_catalysts":           "Test catalyst",
            "risk_flags":              "Test risk flag",
            "confidence_overall":      0.500,
        }
        row_id = write_research_report(test_research)
        print(f"  OK — row_id={row_id}")

        # Clean up test record
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM research_reports WHERE report_date = %s AND market_outlook LIKE 'TEST RECORD%'", (today,))
        conn.commit(); conn.close()
        print("  Cleaned up test record.")
    except Exception as e:
        print(f"  FAILED: {e}")
        errors.append(f"research_reports: {e}")

    # ── Test 2: risk_reports ─────────────────────────────────
    print("\n[2] Testing write_risk_report...")
    try:
        test_risk = {
            "report_date":           today,
            "report_id":             f"risk_TEST_{datetime.now().strftime('%H%M%S')}",
            "model_name":            "test_model",
            "model_version":         "0.0",
            "prompt_hash":           hash_prompt("test prompt risk"),
            "dataset_snapshot_id":   f"snapshot_TEST_{today}",
            "regime_at_generation":  "NEUTRAL",
            "portfolio_risk_summary":"TEST RECORD — smoke test only.",
            "regime_risk_score":     0,
            "risk_assessments":      {"BAC": {"risk_score": 3, "risk_summary": "test", "key_risks": ["test"]}},
            "counterarguments":      {"BAC": {"bull_thesis": "test bull", "bear_thesis": "test bear", "key_risk": "test"}},
            "scenario_risks":        {
                "bull":       {"probability": 0.20, "description": "test", "portfolio_impact": "+$100"},
                "base":       {"probability": 0.50, "description": "test", "portfolio_impact": "+$0"},
                "bear":       {"probability": 0.25, "description": "test", "portfolio_impact": "-$100"},
                "black_swan": {"probability": 0.05, "description": "test", "portfolio_impact": "-$500"},
            },
            "macro_risks":           [{"risk_type": "TEST", "description": "test", "severity": "LOW", "lens": "L3"}],
            "sector_exposure_risk":  {"FINANCIALS": {"exposure_pct": 24.3, "risk_rating": "MEDIUM", "comment": "test"}},
            "overall_risk_rating":   "LOW",
        }
        row_id = write_risk_report(test_risk)
        print(f"  OK — row_id={row_id}")

        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM risk_reports WHERE report_date = %s AND portfolio_risk_summary LIKE 'TEST RECORD%'", (today,))
        conn.commit(); conn.close()
        print("  Cleaned up test record.")
    except Exception as e:
        print(f"  FAILED: {e}")
        errors.append(f"risk_reports: {e}")

    # ── Test 3: cio_decisions ────────────────────────────────
    print("\n[3] Testing write_cio_decision...")
    try:
        test_decision = {
            "decision_id":         make_decision_id(seq=999),
            "decision_date":       today,
            "decision_time":       datetime.now().strftime("%H:%M:%S"),
            "action":              "STRATEGIC_NOTE",
            "regime_at_decision":  "NEUTRAL",
            "confidence":          1.0,
            "rationale":           "TEST RECORD — smoke test only. db_writers.py connectivity confirmed.",
            "strategic_note":      "Smoke test. Delete after verification.",
        }
        row_id = write_cio_decision(test_decision)
        print(f"  OK — row_id={row_id}")

        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM cio_decisions WHERE rationale LIKE 'TEST RECORD%'")
        conn.commit(); conn.close()
        print("  Cleaned up test record.")
    except Exception as e:
        print(f"  FAILED: {e}")
        errors.append(f"cio_decisions: {e}")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"  SMOKE TEST FAILED — {len(errors)} error(s):")
        for err in errors:
            print(f"    {err}")
        sys.exit(1)
    else:
        print("  ALL TESTS PASSED")
        print("  research_reports  — write confirmed")
        print("  risk_reports      — write confirmed")
        print("  cio_decisions     — write confirmed")
        print("  Departments can now write to MySQL.")
    print("=" * 60)
