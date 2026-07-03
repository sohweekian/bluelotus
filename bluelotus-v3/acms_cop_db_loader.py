#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from acms_cop.db.acms_loader import build_payload, insert_payload, payload_counts
from acms_cop.reports.acms_summary_renderer import build_acms_summary


PROJECT_ROOT = Path(__file__).resolve().parent
ACMS_DATA_DIR = PROJECT_ROOT / "data" / "acms_cop"
ACMS_REPORT_DIR = PROJECT_ROOT / "reports"


def write_outputs(payload: dict) -> None:
    ACMS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ACMS_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    cycle = payload["acms_cycle"][0]
    summary = build_acms_summary(
        cycle,
        payload["acms_ticker_cycle"],
        payload["acms_theme_cycle"],
        payload["acms_forecast"],
        payload["acms_agent_cycle"],
        payload["acms_data_quality_event"],
    )
    (ACMS_DATA_DIR / "acms_cop_latest.json").write_text(json.dumps({
        "summary": summary,
        "counts": payload_counts(payload),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (ACMS_REPORT_DIR / "acms_cop_latest.txt").write_text(payload["report_text"], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load ACMS-COP records from V3 artifacts.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--mode", required=True, choices=["live", "dry-run"])
    parser.add_argument("--skip-forecast", action="store_true")
    parser.add_argument("--skip-agent", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    payload = build_payload(args.dataset, args.workbook, args.skip_forecast, args.skip_agent)
    counts = payload_counts(payload)
    write_outputs(payload)
    print("ACMS-COP loader counts")
    for table, count in counts.items():
        print(f"{table}: {count} pending row{'s' if count != 1 else ''}")
    print("Safety: CIO_ONLY_MANUAL preserved; no broker execution; no generated orders.")

    if args.mode == "dry-run":
        print("Mode: dry-run. No rows inserted.")
        return 0

    inserted = insert_payload(args.database, payload)
    print(f"Mode: live. Inserted rows: {inserted}")
    if args.verbose:
        print(f"Report: {ACMS_REPORT_DIR / 'acms_cop_latest.txt'}")
        print(f"Summary: {ACMS_DATA_DIR / 'acms_cop_latest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

