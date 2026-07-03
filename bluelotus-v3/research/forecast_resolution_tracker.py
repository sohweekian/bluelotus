#!/usr/bin/env python3
"""
BlueLotus forecast resolution tracker.

Research-only:
- Reads due ticker_forecasts rows
- Compares forecast targets with current actual prices from dataset_raw.json
- Writes forecast_resolution_results.json
- Inserts resolved horizons into forecast_resolutions
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_RESEARCH_OUTPUT = PROJECT_ROOT / "research" / "forecast_resolution_results.json"
DEFAULT_DATA_OUTPUT = PROJECT_ROOT / "data" / "brier" / "forecast_resolution_results_latest.json"
HORIZONS = (7, 14, 30, 60, 90)


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


def parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    s = str(value).replace("SGT", "").replace("Z", "").strip()
    s = s.replace("T", " ").split("+")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    return None


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def load_dataset(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def connect():
    root = project_root()
    sys.path.insert(0, str(root))
    from dotenv import load_dotenv
    from mid.bluelotus_forecast_tables import create_tables
    from core.db import get_connection

    load_dotenv(root / ".env")
    create_tables()
    return get_connection()


def fetch_due_forecasts(conn, now: datetime, limit: int) -> List[Tuple[Dict[str, Any], int]]:
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT *
        FROM ticker_forecasts
        WHERE forecast_date <= %s
        ORDER BY forecast_date ASC, ticker ASC, prediction_method ASC
        LIMIT %s
        """,
        (now - timedelta(days=min(HORIZONS)), limit * len(HORIZONS)),
    )
    rows = cur.fetchall()
    cur.close()

    due: List[Tuple[Dict[str, Any], int]] = []
    cur = conn.cursor(dictionary=True)
    for row in rows:
        fdt = parse_dt(row.get("forecast_date"))
        if not fdt:
            continue
        for h in HORIZONS:
            if fdt + timedelta(days=h) > now:
                continue
            cur.execute(
                "SELECT id FROM forecast_resolutions WHERE forecast_id=%s AND horizon_days=%s LIMIT 1",
                (row["forecast_id"], h),
            )
            if not cur.fetchone():
                due.append((row, h))
                if len(due) >= limit:
                    cur.close()
                    return due
    cur.close()
    return due


def resolve_one(row: Dict[str, Any], horizon: int, prices: Dict[str, Dict[str, Any]], now: datetime) -> Optional[Dict[str, Any]]:
    ticker = str(row.get("ticker") or "").upper()
    actual = n((prices.get(ticker) or {}).get("price"))
    current = n(row.get("current_price"))
    predicted = n(row.get(f"target_price_{horizon}d"))
    probability = n(row.get(f"probability_{horizon}d"))
    expected_return = n(row.get(f"expected_return_{horizon}d"))
    direction = str(row.get("forecast_direction") or "NEUTRAL").upper()
    if actual is None or current is None or predicted is None or probability is None:
        return None

    if direction == "UP":
        outcome = 1 if actual >= predicted else 0
    elif direction == "DOWN":
        outcome = 1 if actual <= predicted else 0
    else:
        outcome = 1 if abs((actual - current) / current) <= 0.02 else 0

    actual_return = (actual - current) / current * 100.0 if current else None
    abs_error = abs(predicted - actual)
    pct_error = abs_error / actual if actual else None
    brier = (probability - outcome) ** 2
    directional_correct = None
    if expected_return is not None and actual_return is not None:
        if abs(expected_return) < 0.01:
            directional_correct = 1 if abs(actual_return) <= 2 else 0
        else:
            directional_correct = 1 if (expected_return >= 0 and actual_return >= 0) or (expected_return < 0 and actual_return < 0) else 0

    return {
        "forecast_id": row.get("forecast_id"),
        "snapshot_id": row.get("snapshot_id"),
        "ticker": ticker,
        "prediction_method": row.get("prediction_method"),
        "horizon_days": horizon,
        "forecast_date": row.get("forecast_date"),
        "resolution_date": now,
        "current_price": current,
        "predicted_price": predicted,
        "actual_price": actual,
        "forecast_direction": direction,
        "forecast_probability": probability,
        "actual_outcome": outcome,
        "brier_score": round(brier, 8),
        "absolute_error": round(abs_error, 6),
        "percentage_error": round(pct_error, 8) if pct_error is not None else None,
        "expected_return_pct": expected_return,
        "actual_return_pct": round(actual_return, 4) if actual_return is not None else None,
        "directional_correct": directional_correct,
    }


INSERT_SQL = """
INSERT INTO forecast_resolutions (
    forecast_id, snapshot_id, ticker, prediction_method, horizon_days,
    forecast_date, resolution_date, current_price, predicted_price, actual_price,
    forecast_direction, forecast_probability, actual_outcome, brier_score,
    absolute_error, percentage_error, expected_return_pct, actual_return_pct,
    directional_correct, resolution_json
) VALUES (
    %(forecast_id)s, %(snapshot_id)s, %(ticker)s, %(prediction_method)s, %(horizon_days)s,
    %(forecast_date)s, %(resolution_date)s, %(current_price)s, %(predicted_price)s, %(actual_price)s,
    %(forecast_direction)s, %(forecast_probability)s, %(actual_outcome)s, %(brier_score)s,
    %(absolute_error)s, %(percentage_error)s, %(expected_return_pct)s, %(actual_return_pct)s,
    %(directional_correct)s, %(resolution_json)s
)
ON DUPLICATE KEY UPDATE
    actual_price = VALUES(actual_price),
    brier_score = VALUES(brier_score),
    resolution_json = VALUES(resolution_json)
"""


def insert_resolutions(conn, rows: List[Dict[str, Any]]) -> int:
    cur = conn.cursor()
    count = 0
    try:
        for row in rows:
            payload = dict(row)
            payload["forecast_date"] = parse_dt(payload.get("forecast_date"))
            payload["resolution_date"] = parse_dt(payload.get("resolution_date")) or datetime.now()
            payload["resolution_json"] = json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True)
            cur.execute(INSERT_SQL, payload)
            count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return count


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve due BlueLotus forecast horizons")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--research-output", type=Path, default=DEFAULT_RESEARCH_OUTPUT)
    parser.add_argument("--data-output", type=Path, default=DEFAULT_DATA_OUTPUT)
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()

    now = datetime.now()
    dataset = load_dataset(args.dataset)
    prices = live_prices(dataset)
    conn = connect()
    try:
        due = fetch_due_forecasts(conn, now, args.limit)
        resolved = [r for row, h in due if (r := resolve_one(row, h, prices, now))]
        inserted = insert_resolutions(conn, resolved) if resolved else 0
    finally:
        conn.close()

    package = {
        "meta": {
            "generated_at": now.isoformat(sep=" ", timespec="seconds"),
            "due_count": len(due),
            "resolved_count": len(resolved),
            "inserted_or_updated": inserted,
            "status": "resolved" if resolved else "no_due_forecasts",
        },
        "resolutions": resolved,
    }
    write_json(args.research_output, package)
    write_json(args.data_output, package)
    print(f"Forecast resolutions: due={len(due)} resolved={len(resolved)} inserted={inserted}")
    print(f"Output: {args.research_output}")


if __name__ == "__main__":
    main()

