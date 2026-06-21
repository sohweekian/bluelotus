#!/usr/bin/env python3
"""
BlueLotus MID -- staged historical price backfill scheduler.

Maintains a queue for the capped research universe and refreshes a small batch
per cycle through fetch_historical_prices.py. This respects Moomoo quota limits
and gradually moves every ticker toward institutional backtest coverage.
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
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(r"C:\bluelotus3")
MID_DIR = PROJECT_ROOT / "mid"
COVERAGE_PATH = PROJECT_ROOT / "data" / "history" / "historical_price_coverage_latest.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "history" / "historical_backfill_latest.json"


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


def normalize_tickers(tickers: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for ticker in tickers:
        t = str(ticker or "").strip().upper().replace("US.", "")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def load_tickers(limit: int | None) -> tuple[List[str], List[str], List[str]]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection
    from mid.fetch_historical_prices import FACTOR_TICKERS
    from mid.ticker_universe import get_universe

    load_dotenv(PROJECT_ROOT / ".env")
    universe = normalize_tickers(get_universe(limit=limit))
    factors = normalize_tickers(FACTOR_TICKERS)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT p.ticker
            FROM portfolio_readonly_positions p
            JOIN (
                SELECT snapshot_id
                FROM portfolio_readonly_snapshots
                ORDER BY cycle_ts DESC, id DESC
                LIMIT 1
            ) s ON s.snapshot_id = p.snapshot_id
            ORDER BY p.ticker
            """
        )
        portfolio = normalize_tickers(r.get("ticker") for r in cur.fetchall())
        cur.close()
    except Exception:
        portfolio = []
    finally:
        conn.close()
    return universe, factors, portfolio


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def connect_db():
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    return get_connection()


def priority_for(ticker: str, portfolio: set[str], factors: set[str]) -> tuple[int, str]:
    if ticker in portfolio:
        return 1, "portfolio"
    if ticker in factors:
        return 2, "factor"
    return 5, "grand_universe_200"


def refresh_queue_stats(cur, tickers: List[str], portfolio: set[str], factors: set[str], days: int, min_rows: int) -> None:
    for ticker in tickers:
        priority, source = priority_for(ticker, portfolio, factors)
        cur.execute(
            """
            INSERT INTO historical_backfill_queue (
                ticker, universe_source, priority, desired_days, min_rows
            ) VALUES (%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                universe_source = VALUES(universe_source),
                priority = LEAST(priority, VALUES(priority)),
                desired_days = VALUES(desired_days),
                min_rows = VALUES(min_rows)
            """,
            (ticker, source, priority, days, min_rows),
        )

    cur.execute(
        """
        SELECT ticker, COUNT(*) AS row_count, MIN(bar_date) AS first_bar_date,
               MAX(bar_date) AS latest_bar_date, MAX(fetched_at) AS latest_fetch_at
        FROM historical_prices
        GROUP BY ticker
        """
    )
    stats = {str(r["ticker"]).upper(): r for r in cur.fetchall()}
    today = datetime.now().date()
    for ticker in tickers:
        row = stats.get(ticker, {})
        row_count = int(row.get("row_count") or 0)
        latest = row.get("latest_bar_date")
        latest_date = latest if isinstance(latest, date) else None
        complete = row_count >= min_rows
        stale = bool(latest_date and (today - latest_date).days > 10)
        status = "COMPLETE" if complete and not stale else ("STALE" if row_count else "PENDING")
        cur.execute(
            """
            UPDATE historical_backfill_queue
            SET row_count=%s, first_bar_date=%s, latest_bar_date=%s,
                latest_fetch_at=%s, status=%s
            WHERE ticker=%s
            """,
            (
                row_count,
                row.get("first_bar_date"),
                row.get("latest_bar_date"),
                row.get("latest_fetch_at"),
                status,
                ticker,
            ),
        )


def select_batch(cur, batch_size: int) -> List[str]:
    cur.execute(
        """
        SELECT ticker
        FROM historical_backfill_queue
        WHERE status IN ('PENDING','STALE')
        ORDER BY priority ASC, COALESCE(last_attempt_at, '1970-01-01') ASC, attempt_count ASC, ticker ASC
        LIMIT %s
        """,
        (batch_size,),
    )
    return [str(r["ticker"]).upper() for r in cur.fetchall()]


def mark_attempt(cur, tickers: List[str]) -> None:
    if not tickers:
        return
    placeholders = ",".join(["%s"] * len(tickers))
    cur.execute(
        f"""
        UPDATE historical_backfill_queue
        SET attempt_count = attempt_count + 1, last_attempt_at = NOW()
        WHERE ticker IN ({placeholders})
        """,
        tuple(tickers),
    )


def load_coverage() -> Dict[str, Any]:
    if not COVERAGE_PATH.exists():
        return {}
    try:
        with COVERAGE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def update_selected_errors(cur, tickers: List[str], coverage: Dict[str, Any]) -> None:
    rows = coverage.get("tickers") if isinstance(coverage.get("tickers"), dict) else {}
    for ticker in tickers:
        result = rows.get(ticker) if isinstance(rows, dict) else {}
        error = result.get("error") if isinstance(result, dict) else None
        row_count = int(result.get("rows") or 0) if isinstance(result, dict) else 0
        if row_count > 0 and not error:
            cur.execute(
                """
                UPDATE historical_backfill_queue
                SET last_success_at = NOW(), last_error = NULL
                WHERE ticker = %s
                """,
                (ticker,),
            )
        elif error:
            cur.execute(
                """
                UPDATE historical_backfill_queue
                SET last_error = %s
                WHERE ticker = %s
                """,
                (str(error)[:4000], ticker),
            )


def run_fetch(tickers: List[str], args: argparse.Namespace) -> Dict[str, Any]:
    command = [
        sys.executable,
        "fetch_historical_prices.py",
        "--tickers",
        ",".join(tickers),
        "--days",
        str(args.days),
        "--sleep-sec",
        str(args.sleep_sec),
        "--cur-kline-num",
        str(args.cur_kline_num),
    ]
    started = datetime.now()
    proc = subprocess.run(
        command,
        cwd=str(MID_DIR),
        text=True,
        capture_output=True,
        timeout=args.timeout_sec,
    )
    return {
        "command": command,
        "cwd": str(MID_DIR),
        "started_at": started.isoformat(sep=" "),
        "finished_at": datetime.now().isoformat(sep=" "),
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def queue_counts(cur) -> Dict[str, int]:
    cur.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM historical_backfill_queue
        GROUP BY status
        """
    )
    return {str(r["status"]): int(r["n"] or 0) for r in cur.fetchall()}


def insert_run(summary: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from core.db import close_cycle_conn, write_raw_signal

    conn = connect_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO historical_backfill_runs (
                run_id, cycle_ts, status, batch_size, selected_tickers_json,
                command_json, command_exit_code, coverage_json, summary_json
            ) VALUES (%s,%s,%s,%s,CAST(%s AS JSON),CAST(%s AS JSON),%s,CAST(%s AS JSON),CAST(%s AS JSON))
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                command_json = VALUES(command_json),
                command_exit_code = VALUES(command_exit_code),
                coverage_json = VALUES(coverage_json),
                summary_json = VALUES(summary_json)
            """,
            (
                summary["run_id"],
                summary["cycle_ts"],
                summary["status"],
                int(summary.get("batch_size") or 0),
                json_dumps(summary.get("selected_tickers", [])),
                json_dumps(summary.get("command_result")),
                summary.get("command_exit_code"),
                json_dumps(summary.get("coverage", {})),
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
            source="Historical_Backfill_Scheduler",
            ingestion_method="historical_backfill_queue",
            raw_payload=summary,
            raw_text=(
                f"Historical backfill {summary['status']}: selected "
                f"{len(summary.get('selected_tickers', []))} | queue {summary.get('queue_counts')}"
            ),
            signal_type="market_data",
            suspected_category="HISTORICAL_BACKFILL_SCHEDULER",
            suspected_entities=summary.get("selected_tickers", []),
            suspected_impact="medium",
            quality_score=summary.get("coverage_ratio", 0.0),
            quality_flags={"read_only_protocol": True, "queue_counts": summary.get("queue_counts")},
        )
    finally:
        close_cycle_conn()


def run_scheduler(args: argparse.Namespace) -> Dict[str, Any]:
    ensure_tables()
    universe, factors, portfolio = load_tickers(args.limit)
    tickers = normalize_tickers([*portfolio, *factors, *universe])
    portfolio_set = set(portfolio)
    factor_set = set(factors)

    conn = connect_db()
    command_result: Dict[str, Any] | None = None
    coverage: Dict[str, Any] = {}
    selected: List[str] = []
    try:
        cur = conn.cursor(dictionary=True)
        refresh_queue_stats(cur, tickers, portfolio_set, factor_set, args.days, args.min_rows)
        conn.commit()
        selected = select_batch(cur, args.batch_size)
        if selected and args.execute:
            mark_attempt(cur, selected)
            conn.commit()
            command_result = run_fetch(selected, args)
            coverage = load_coverage()
            refresh_queue_stats(cur, tickers, portfolio_set, factor_set, args.days, args.min_rows)
            update_selected_errors(cur, selected, coverage)
            conn.commit()
        counts = queue_counts(cur)
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    exit_code = command_result.get("exit_code") if command_result else None
    filled_count = int(coverage.get("filled_count") or 0) if coverage else 0
    coverage_ratio = round(filled_count / len(selected), 4) if selected else 1.0
    status = "QUEUE_COMPLETE" if not selected else "PLAN_ONLY"
    if selected and args.execute:
        status = "BATCH_COMPLETE" if exit_code == 0 else "BATCH_WARNING"
    run_id = f"HBF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    summary = {
        "run_id": run_id,
        "cycle_ts": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "status": status,
        "execute": bool(args.execute),
        "universe_count": len(universe),
        "factor_count": len(factors),
        "portfolio_count": len(portfolio),
        "queue_ticker_count": len(tickers),
        "queue_counts": counts,
        "batch_size": len(selected),
        "selected_tickers": selected,
        "command_result": command_result,
        "command_exit_code": exit_code,
        "coverage_ratio": coverage_ratio,
        "coverage": coverage,
        "policy": {
            "days": args.days,
            "min_rows": args.min_rows,
            "scheduler_batch_size": args.batch_size,
            "read_only_protocol": True,
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(summary), indent=2, ensure_ascii=False), encoding="utf-8")
    insert_run(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run staged historical backfill scheduler")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--min-rows", type=int, default=90)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--sleep-sec", type=float, default=0.55)
    parser.add_argument("--cur-kline-num", type=int, default=180)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--execute", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    summary = run_scheduler(args)
    print("Historical backfill scheduler complete.")
    print(f"Status  : {summary['status']}")
    print(f"Queue   : {summary['queue_counts']}")
    print(f"Selected: {summary['selected_tickers']}")


if __name__ == "__main__":
    main()

