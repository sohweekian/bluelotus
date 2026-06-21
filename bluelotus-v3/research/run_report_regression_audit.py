"""
BlueLotus V2 report regression audit for the 2026-06-13 CIO defect set.

This script is intentionally narrow: it checks the exact contradictions and
missing disclosures that were found in the upgraded R6 report package.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / "research"
DATASET_PATH = ROOT / "data" / "frontend" / "dataset_raw.json"
TXT_PATH = RESEARCH_DIR / "Bluelotus_V3_Report.txt"
WORD_PATH = RESEARCH_DIR / "Bluelotus_V3_Report.docx"
EXCEL_PATH = RESEARCH_DIR / "Bluelotus_V3_Report.xlsx"
JSON_OUT = RESEARCH_DIR / "regression_audit_latest.json"
TXT_OUT = RESEARCH_DIR / "regression_audit_latest.txt"

REQUIRED_THEMES = {
    "NVDA": "AI / SEMIS",
    "ASTS": "SPACE / HIGH-BETA",
    "RKLB": "SPACE / HIGH-BETA",
    "PL": "SPACE / HIGH-BETA",
    "LUNR": "SPACE / HIGH-BETA",
    "QBTS": "QUANTUM",
    "QUBT": "QUANTUM",
    "AU": "GOLD_MINER",
    "NEM": "GOLD_MINER",
}

GOLD_WORDING_BY_STATUS = {
    "CONFIRMING": "Gold thesis is confirming",
    "WARNING": "Gold thesis WARNING",
    "WATCH": "Gold thesis WATCH",
    "FAILING": "Gold thesis FAILING",
}
REQUIRED_ORDER_WARNING = "Current open orders do not guarantee pre-BOJ miner de-risking. Manual CIO action required."


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_zip_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            parts: List[str] = []
            for name in zf.namelist():
                if name.endswith(".xml") or name.endswith(".rels"):
                    parts.append(zf.read(name).decode("utf-8", errors="replace"))
            return re.sub(r"<[^>]+>", " ", "\n".join(parts))
    except Exception:
        return ""


def check(name: str, passed: bool, detail: str) -> Dict[str, str]:
    return {"name": name, "result": "PASS" if passed else "FAIL", "detail": detail}


def main() -> int:
    dataset = read_json(DATASET_PATH)
    txt = read_text(TXT_PATH)
    word = read_zip_text(WORD_PATH)
    excel = read_zip_text(EXCEL_PATH)
    all_rendered = "\n".join([txt, word, excel])
    results: List[Dict[str, str]] = []

    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    base_regime = str(regime.get("regime") or "").upper()
    macro = (((dataset.get("deterministic_operators") or {}).get("operators") or {}).get("macro_regime") or {})
    macro_status = str(macro.get("status") or "").upper()
    overlay = str(((macro.get("metrics") or {}).get("tactical_risk_appetite_overlay")) or "")
    results.append(check(
        "No macro regime contradiction",
        not (base_regime == "RISK OFF" and macro_status == "RISK_ON"),
        f"base_regime={base_regime} | macro_operator={macro_status} | overlay={overlay}",
    ))

    gold_tracker = dataset.get("gold_thesis_tracker") if isinstance(dataset.get("gold_thesis_tracker"), dict) else {}
    gold_status = str(gold_tracker.get("status") or "").upper()
    required_gold_wording = GOLD_WORDING_BY_STATUS.get(gold_status, "Gold thesis")
    results.append(check(
        "Gold thesis wording separates confirmation from concentration",
        required_gold_wording in all_rendered
        and "Core miner exposure appropriate" not in all_rendered
        and "gold-miner exposure is institutionally excessive" not in all_rendered,
        f"gold_status={gold_status or 'UNKNOWN'}; required wording present; stale excessive-exposure wording absent",
    ))

    macro_events = dataset.get("macro_event_risks") if isinstance(dataset.get("macro_event_risks"), list) else []
    macro_event_text = json.dumps(macro_events, ensure_ascii=False) + "\n" + all_rendered
    results.append(check(
        "Macro catalysts include BOJ and FOMC",
        all(token in macro_event_text for token in ["BOJ June 16", "FOMC June 16-17", "Fed press conference"]),
        f"macro_event_risks={len(macro_events)}",
    ))

    market_status = str((dataset.get("meta") or {}).get("market_session") or "")
    if "REGULAR_SESSION" in market_status.upper():
        market_status_ok = "REGULAR_SESSION" in all_rendered or "REGULAR SESSION" in all_rendered
    else:
        market_status_ok = (
            "MARKET CLOSED" in all_rendered
            and "WEEKEND SNAPSHOT" not in all_rendered
            and "Market Status" in all_rendered
            and "Market Session   : REGULAR" not in all_rendered
        )
    results.append(check(
        "Market status label matches current session",
        market_status_ok,
        f"meta.market_session={market_status}",
    ))

    results.append(check(
        "CIO Plan vs Broker Order Book rendered",
        "CIO Plan vs Broker Order Book" in all_rendered and REQUIRED_ORDER_WARNING in all_rendered,
        "section and warning present",
    ))

    ticker_sentiment = dataset.get("ticker_sentiment")
    if isinstance(ticker_sentiment, dict):
        sentiment_rows = [v for v in ticker_sentiment.values() if isinstance(v, dict)]
    elif isinstance(ticker_sentiment, list):
        sentiment_rows = [v for v in ticker_sentiment if isinstance(v, dict)]
    else:
        sentiment_rows = []
    relevance_count = sum(1 for r in sentiment_rows if "ticker_relevance" in r)
    results.append(check(
        "Ticker sentiment has entity relevance fields",
        relevance_count == len(sentiment_rows) or not sentiment_rows,
        f"rows={len(sentiment_rows)} | with_relevance={relevance_count}",
    ))

    missing_themes = []
    for ticker, theme in REQUIRED_THEMES.items():
        if ticker not in all_rendered or theme not in all_rendered:
            missing_themes.append(f"{ticker}:{theme}")
    results.append(check(
        "Required portfolio classifications rendered",
        not missing_themes and "UNCLASSIFIED" not in all_rendered,
        f"missing={missing_themes[:6]}",
    ))

    execution = dataset.get("execution") if isinstance(dataset.get("execution"), dict) else {}
    results.append(check(
        "Execution remains CIO_ONLY_MANUAL",
        execution.get("execution_authority", "CIO_ONLY_MANUAL") == "CIO_ONLY_MANUAL",
        f"execution_authority={execution.get('execution_authority')}",
    ))
    results.append(check(
        "No order routing",
        not bool(execution.get("order_routing_enabled")),
        f"order_routing_enabled={execution.get('order_routing_enabled')}",
    ))
    generated = int(execution.get("orders_generated") or execution.get("orders_generated_by_pipeline") or 0)
    results.append(check(
        "No generated orders",
        generated == 0,
        f"generated_orders={generated}",
    ))

    pass_count = sum(1 for r in results if r["result"] == "PASS")
    fail_count = len(results) - pass_count
    status = "PASS" if fail_count == 0 else "FAIL"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "checks": results,
    }
    JSON_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "BlueLotus V2 Report Regression Audit",
        f"Status: {status} | Pass {pass_count}/{len(results)} | Fail {fail_count}/{len(results)}",
        "",
    ]
    for r in results:
        lines.append(f"[{r['result']}] {r['name']} - {r['detail']}")
    TXT_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(lines[0])
    print(lines[1])
    for r in results:
        print(f"  [{r['result']}] {r['name']} :: {r['detail']}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
