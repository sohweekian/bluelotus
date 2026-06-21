#!/usr/bin/env python3
"""
BlueLotus MID -- freshness recovery operator.

Reads dataset_raw.json, identifies stale sections, executes the smallest mapped
refresh set, and writes an auditable recovery run. Market-data staleness during
closed/weekend windows is recorded as deferred rather than treated as a failed
refresh.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(r"C:\bluelotus3")
MID_DIR = PROJECT_ROOT / "mid"
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "audit" / "freshness_recovery_latest.json"

MARKET_DATA_SECTIONS = {"live_prices", "fear_greed", "ticker_sentiment", "capital_flow"}
MARKET_CLOSED_GRACE_MINUTES = 72 * 60

SECTION_REFRESHERS = {
    "live_prices": "ingest_core",
    "fear_greed": "ingest_core",
    "ticker_sentiment": "ingest_core",
    "capital_flow": "fetch_capital_flow",
    "fundamentals": "fetch_fundamentals",
    "treasury_yields": "fetch_treasury_yields",
    "cross_market_confirmation": "fetch_cross_market_confirmation",
    "portfolio_readonly": "fetch_portfolio_readonly",
    "corporate_actions": "fetch_corporate_actions",
    "delistings": "fetch_corporate_actions",
    "conference_calendar": "fetch_conference_calendar",
    "ceo_appearances": "fetch_ceo_appearances",
    "tech_pub_signals": "fetch_tech_publications",
}

REFRESHER_COMMANDS = {
    "ingest_core": [sys.executable, "-m", "mid.ingest"],
    "fetch_capital_flow": [sys.executable, "fetch_capital_flow.py"],
    "fetch_fundamentals": [sys.executable, "fetch_fundamentals.py"],
    "fetch_treasury_yields": [sys.executable, "fetch_treasury_yields.py"],
    "fetch_cross_market_confirmation": [sys.executable, "fetch_cross_market_confirmation.py"],
    "fetch_portfolio_readonly": [sys.executable, "fetch_portfolio_readonly.py"],
    "fetch_corporate_actions": [sys.executable, "fetch_corporate_actions.py", "--limit", "200", "--sleep-sec", "0.02"],
    "fetch_conference_calendar": [sys.executable, "fetch_conference_calendar.py", "--rss-scan"],
    "fetch_ceo_appearances": [sys.executable, "fetch_ceo_appearances.py"],
    "fetch_tech_publications": [sys.executable, "fetch_tech_publications.py"],
}


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


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "").replace("+00:00", "")[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load_dataset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("dataset_raw.json must be a JSON object")
    return data


def is_market_closed_deferred(section: str, item: Dict[str, Any], market_session: str) -> bool:
    if section not in MARKET_DATA_SECTIONS:
        return False
    age = item.get("age_minutes")
    try:
        age_m = int(age)
    except Exception:
        return False
    weekend = datetime.now().weekday() >= 5
    market_closed = str(market_session or "").upper() in {"CLOSED", "UNKNOWN"}
    return (weekend or market_closed) and age_m <= MARKET_CLOSED_GRACE_MINUTES


def stale_sections(dataset: Dict[str, Any]) -> tuple[List[str], List[str]]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    freshness = meta.get("freshness") if isinstance(meta.get("freshness"), dict) else {}
    market_session = str(meta.get("market_session") or "UNKNOWN")
    actionable: List[str] = []
    deferred: List[str] = []
    for section, item in freshness.items():
        if section == "thresholds" or not isinstance(item, dict):
            continue
        if str(item.get("grade") or "").upper() != "STALE":
            continue
        if is_market_closed_deferred(section, item, market_session):
            deferred.append(section)
        else:
            actionable.append(section)
    return actionable, deferred


def run_command(command: List[str], cwd: Path, timeout_sec: int) -> Dict[str, Any]:
    started = datetime.now()
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "started_at": started.isoformat(sep=" "),
        "finished_at": datetime.now().isoformat(sep=" "),
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def insert_run(summary: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))

    from dotenv import load_dotenv
    from core.db import close_cycle_conn, get_connection, write_raw_signal
    from mid.institutional_upgrade_tables import create_tables

    load_dotenv(PROJECT_ROOT / ".env")
    create_tables()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO freshness_recovery_runs (
                run_id, cycle_ts, dataset_generated_at, market_session,
                stale_sections_json, market_closed_deferred_json,
                attempted_modules_json, command_results_json,
                unresolved_sections_json, status, summary_json
            ) VALUES (%s,%s,%s,%s,CAST(%s AS JSON),CAST(%s AS JSON),
                      CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),%s,CAST(%s AS JSON))
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                command_results_json = VALUES(command_results_json),
                unresolved_sections_json = VALUES(unresolved_sections_json),
                summary_json = VALUES(summary_json)
            """,
            (
                summary["run_id"],
                summary["cycle_ts"],
                parse_dt(summary.get("dataset_generated_at")),
                summary.get("market_session"),
                json_dumps(summary.get("stale_sections", [])),
                json_dumps(summary.get("market_closed_deferred", [])),
                json_dumps(summary.get("attempted_modules", [])),
                json_dumps(summary.get("command_results", [])),
                json_dumps(summary.get("unresolved_sections", [])),
                summary["status"],
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

    try:
        write_raw_signal(
            source="Freshness_Recovery",
            ingestion_method="freshness_recovery_operator",
            raw_payload=summary,
            raw_text=(
                f"Freshness recovery {summary['status']}: "
                f"attempted {len(summary.get('attempted_modules', []))} modules | "
                f"deferred {len(summary.get('market_closed_deferred', []))}"
            ),
            signal_type="governance",
            suspected_category="DATA_FRESHNESS_RECOVERY",
            suspected_entities=summary.get("stale_sections", []),
            suspected_impact="medium",
            quality_score=1.0 if summary["status"] in {"NO_ACTION_REQUIRED", "RECOVERY_ATTEMPTED"} else 0.5,
            quality_flags={"market_closed_deferred": summary.get("market_closed_deferred", [])},
        )
    finally:
        close_cycle_conn()


def run_recovery(args: argparse.Namespace) -> Dict[str, Any]:
    dataset = load_dataset(args.dataset)
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    actionable, deferred = stale_sections(dataset)
    modules = sorted({
        SECTION_REFRESHERS[section]
        for section in actionable
        if section in SECTION_REFRESHERS
    })

    command_results: List[Dict[str, Any]] = []
    if args.execute:
        for module in modules:
            command = REFRESHER_COMMANDS.get(module)
            if not command:
                command_results.append({"module": module, "exit_code": None, "error": "no command mapped"})
                continue
            cwd = PROJECT_ROOT if module == "ingest_core" else MID_DIR
            try:
                result = run_command(command, cwd, args.timeout_sec)
            except subprocess.TimeoutExpired as exc:
                result = {
                    "command": command,
                    "cwd": str(cwd),
                    "exit_code": -1,
                    "error": f"timeout after {args.timeout_sec}s",
                    "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                    "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                }
            result["module"] = module
            command_results.append(result)

    failed_modules = [r.get("module") for r in command_results if r.get("exit_code") not in (0, None)]
    unmapped = [section for section in actionable if section not in SECTION_REFRESHERS]
    status = "NO_ACTION_REQUIRED"
    if actionable and not args.execute:
        status = "PLAN_ONLY"
    elif failed_modules:
        status = "RECOVERY_PARTIAL"
    elif modules:
        status = "RECOVERY_ATTEMPTED"
    elif actionable:
        status = "UNMAPPED_STALE_SECTIONS"

    run_id = f"FRESH-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    summary = {
        "run_id": run_id,
        "cycle_ts": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "dataset_generated_at": meta.get("generated_at"),
        "market_session": meta.get("market_session"),
        "status": status,
        "execute": bool(args.execute),
        "stale_sections": actionable,
        "market_closed_deferred": deferred,
        "attempted_modules": modules,
        "failed_modules": failed_modules,
        "unmapped_sections": unmapped,
        "unresolved_sections": sorted(set(unmapped + failed_modules)),
        "command_results": command_results,
        "policy": {
            "market_data_sections": sorted(MARKET_DATA_SECTIONS),
            "market_closed_grace_minutes": MARKET_CLOSED_GRACE_MINUTES,
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(summary), indent=2, ensure_ascii=False), encoding="utf-8")
    insert_run(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BlueLotus freshness recovery")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--execute", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout-sec", type=int, default=900)
    args = parser.parse_args()

    summary = run_recovery(args)
    print("Freshness recovery complete.")
    print(f"Status   : {summary['status']}")
    print(f"Stale    : {summary['stale_sections']}")
    print(f"Deferred : {summary['market_closed_deferred']}")
    print(f"Modules  : {summary['attempted_modules']}")


if __name__ == "__main__":
    main()

