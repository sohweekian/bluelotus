#!/usr/bin/env python3
"""
BlueLotus forecast method comparison report.

Reads forecast_resolutions and writes:
- research_forecast_accuracy_report.txt
- forecast_method_comparison_latest.json

This is an accuracy/accountability report, not a trade instruction.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_TEXT_OUTPUT = PROJECT_ROOT / "research" / "research_forecast_accuracy_report.txt"
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "data" / "brier" / "forecast_method_comparison_latest.json"


def project_root() -> Path:
    p = Path.cwd()
    if (p / "core").exists() or (p / "mid").exists():
        return p
    if p.name.lower() in {"mid", "research"}:
        return p.parent
    return PROJECT_ROOT


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(sep=" ")
        except Exception:
            return str(value)
    return value


def connect():
    root = project_root()
    sys.path.insert(0, str(root))
    from dotenv import load_dotenv
    from mid.bluelotus_forecast_tables import create_tables
    from core.db import get_connection

    load_dotenv(root / ".env")
    create_tables()
    return get_connection()


def fetch_summary() -> Dict[str, Any]:
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS n FROM ticker_forecasts")
        forecast_count = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute("SELECT COUNT(*) AS n FROM forecast_resolutions")
        resolution_count = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            """
            SELECT prediction_method, horizon_days,
                   COUNT(*) AS n,
                   AVG(brier_score) AS avg_brier,
                   AVG(percentage_error) AS avg_percentage_error,
                   AVG(directional_correct) AS directional_accuracy
            FROM forecast_resolutions
            GROUP BY prediction_method, horizon_days
            ORDER BY horizon_days ASC, avg_brier ASC
            """
        )
        by_method_horizon = cur.fetchall()
        cur.execute(
            """
            SELECT ticker, prediction_method,
                   COUNT(*) AS n,
                   AVG(brier_score) AS avg_brier,
                   AVG(percentage_error) AS avg_percentage_error,
                   AVG(directional_correct) AS directional_accuracy
            FROM forecast_resolutions
            GROUP BY ticker, prediction_method
            HAVING COUNT(*) >= 2
            ORDER BY avg_brier ASC, n DESC
            LIMIT 50
            """
        )
        by_ticker = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return {
        "forecast_count": forecast_count,
        "resolution_count": resolution_count,
        "by_method_horizon": json_safe(by_method_horizon),
        "by_ticker": json_safe(by_ticker),
    }


def fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "N/A"


def build_text(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    L = lines.append
    sep = "=" * 78
    L(sep)
    L("  BLUELOTUS RESEARCH FORECAST ACCURACY REPORT")
    L("  Brier score accountability layer - Research only")
    L(sep)
    L(f"  Generated        : {datetime.now().isoformat(sep=' ', timespec='seconds')}")
    L(f"  Forecast Rows    : {summary.get('forecast_count', 0)}")
    L(f"  Resolved Horizons: {summary.get('resolution_count', 0)}")
    L("")
    if not summary.get("resolution_count"):
        L("  Status           : COLLECTING")
        L("  Interpretation   : Forecast infrastructure is live, but no 7D/14D/30D/60D/90D horizons have matured yet.")
        L("  Doctrine         : Do not claim forecast skill until resolved Brier history exists.")
        L(sep)
        return "\n".join(lines)

    L("  METHOD / HORIZON COMPARISON")
    L("-" * 78)
    L(f"  {'Method':<26} {'H':>4} {'N':>6} {'Brier':>10} {'PriceErr':>10} {'DirAcc':>10}")
    for row in summary.get("by_method_horizon") or []:
        L(
            f"  {str(row.get('prediction_method')):<26} {int(row.get('horizon_days') or 0):>4} "
            f"{int(row.get('n') or 0):>6} {fmt(row.get('avg_brier')):>10} "
            f"{fmt(row.get('avg_percentage_error')):>10} {fmt(row.get('directional_accuracy')):>10}"
        )

    L("")
    L("  BEST TICKER/METHOD PAIRS WITH AT LEAST TWO RESOLUTIONS")
    L("-" * 78)
    L(f"  {'Ticker':<8} {'Method':<26} {'N':>6} {'Brier':>10} {'PriceErr':>10} {'DirAcc':>10}")
    for row in summary.get("by_ticker") or []:
        L(
            f"  {str(row.get('ticker')):<8} {str(row.get('prediction_method')):<26} "
            f"{int(row.get('n') or 0):>6} {fmt(row.get('avg_brier')):>10} "
            f"{fmt(row.get('avg_percentage_error')):>10} {fmt(row.get('directional_accuracy')):>10}"
        )
    L(sep)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare BlueLotus forecast methods after resolutions mature")
    parser.add_argument("--text-output", type=Path, default=DEFAULT_TEXT_OUTPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    args = parser.parse_args()

    summary = fetch_summary()
    package = {
        "meta": {
            "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "status": "resolved_history_available" if summary.get("resolution_count") else "collecting",
        },
        **summary,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(json_safe(package), indent=2, ensure_ascii=False), encoding="utf-8")
    args.text_output.write_text(build_text(package), encoding="utf-8")
    print(f"Forecast comparison: forecasts={summary.get('forecast_count')} resolutions={summary.get('resolution_count')}")
    print(f"Output: {args.text_output}")


if __name__ == "__main__":
    main()

