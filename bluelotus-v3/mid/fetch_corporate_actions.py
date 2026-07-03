#!/usr/bin/env python3
"""
BlueLotus MID -- Moomoo corporate actions and listing-status fetcher.

Read-only quote endpoints:
- get_stock_basicinfo()
- get_corporate_actions_stock_splits()
- get_corporate_actions_dividends()

No trade context is opened. No orders are generated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(r"C:\bluelotus3")
OUTPUT_PATH = PROJECT_ROOT / "data" / "reference" / "corporate_actions_latest.json"
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111


def n(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("N/A", "").replace("--", "").strip()
        if text == "":
            return default
        out = float(text)
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


def clean_ticker(code: Any) -> str:
    return str(code or "").replace("US.", "").strip().upper()


def parse_date(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if not text or text in {"--", "N/A"}:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def action_id(ticker: str, action_type: str, row: Dict[str, Any]) -> str:
    seed = f"{ticker}|{action_type}|{json_dumps(row)}"
    return f"CA-{hashlib.sha256(seed.encode('utf-8', errors='replace')).hexdigest()[:40]}"


def chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def get_tickers(limit: Optional[int], explicit: str = "") -> List[str]:
    if explicit:
        raw = [x.strip().upper() for x in explicit.split(",") if x.strip()]
    else:
        sys.path.insert(0, str(PROJECT_ROOT))
        from mid.ticker_universe import get_universe
        raw = get_universe(limit=limit)
    seen = set()
    out = []
    for ticker in raw:
        t = clean_ticker(ticker)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def fetch_basic_info(ctx: Any, ft: Any, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for batch in chunks(tickers, 80):
        codes = [f"US.{t}" for t in batch]
        ret, data = ctx.get_stock_basicinfo(ft.Market.US, stock_type=ft.SecurityType.STOCK, code_list=codes)
        if ret != ft.RET_OK or data is None:
            for t in batch:
                rows[t] = {"ticker": t, "error": str(data)}
            continue
        for row in json_safe(data.to_dict(orient="records")):
            ticker = clean_ticker(row.get("code"))
            if ticker:
                rows[ticker] = row
    return rows


def fetch_actions_for_ticker(ctx: Any, ticker: str) -> Dict[str, List[Dict[str, Any]]]:
    code = f"US.{ticker}"
    out = {"splits": [], "dividends": []}
    ret, data = ctx.get_corporate_actions_stock_splits(code)
    if ret == 0 and isinstance(data, dict):
        out["splits"] = json_safe(data.get("split_list") or [])
    else:
        out["splits_error"] = str(data)
    ret, data = ctx.get_corporate_actions_dividends(code)
    if ret == 0 and isinstance(data, dict):
        out["dividends"] = json_safe(data.get("dividend_list") or [])
    else:
        out["dividends_error"] = str(data)
    return out


def normalize_action(ticker: str, action_type: str, row: Dict[str, Any], fetched_at: str) -> Dict[str, Any]:
    code = f"US.{ticker}"
    if action_type == "SPLIT":
        event_date = parse_date(row.get("dir_deci_pub_date_str") or row.get("pub_date"))
        return {
            "action_id": action_id(ticker, action_type, row),
            "ticker": ticker,
            "code": code,
            "action_type": action_type,
            "event_date": event_date,
            "ex_date": None,
            "record_date": None,
            "pay_date": None,
            "statement": row.get("reform_type"),
            "ratio_text": row.get("rate"),
            "amount": None,
            "currency": None,
            "raw": row,
            "fetched_at": fetched_at,
        }
    statement = str(row.get("statement") or "")
    amount = None
    currency = None
    parts = statement.replace(":", " ").split()
    for i, token in enumerate(parts):
        val = n(token)
        if val is not None and i + 1 < len(parts):
            amount = val
            currency = parts[i + 1] if parts[i + 1].isalpha() else None
            break
    return {
        "action_id": action_id(ticker, action_type, row),
        "ticker": ticker,
        "code": code,
        "action_type": action_type,
        "event_date": parse_date(row.get("pub_date") or row.get("ex_date")),
        "ex_date": parse_date(row.get("ex_date")),
        "record_date": parse_date(row.get("record_date")),
        "pay_date": parse_date(row.get("dividend_date") or row.get("pay_date")),
        "statement": statement,
        "ratio_text": None,
        "amount": amount,
        "currency": currency,
        "raw": row,
        "fetched_at": fetched_at,
    }


def write_database(basic: Dict[str, Dict[str, Any]], actions: List[Dict[str, Any]], fetched_at: str) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    conn = get_connection()
    snapshot_date = fetched_at[:10]
    try:
        cur = conn.cursor()
        for ticker, row in basic.items():
            code = row.get("code") or f"US.{ticker}"
            listing_status = str(row.get("listing_status") or row.get("status") or "ACTIVE")
            delisting = any(x in listing_status.upper() for x in ("DELIST", "SUSPEND", "HALT"))
            cur.execute(
                """
                INSERT INTO security_listing_status (
                    ticker, code, snapshot_date, name, security_type,
                    exchange_type, owner_market, listing_date, delisting_flag,
                    listing_status, raw_json, fetched_at
                ) VALUES (
                    %s,%s,%s,%s,%s, %s,%s,%s,%s, %s,CAST(%s AS JSON),%s
                )
                ON DUPLICATE KEY UPDATE
                    code = VALUES(code),
                    name = VALUES(name),
                    security_type = VALUES(security_type),
                    exchange_type = VALUES(exchange_type),
                    owner_market = VALUES(owner_market),
                    listing_date = VALUES(listing_date),
                    delisting_flag = VALUES(delisting_flag),
                    listing_status = VALUES(listing_status),
                    raw_json = VALUES(raw_json),
                    fetched_at = VALUES(fetched_at)
                """,
                (
                    ticker,
                    code,
                    snapshot_date,
                    row.get("name") or row.get("stock_name"),
                    row.get("stock_type") or row.get("security_type"),
                    row.get("exchange_type"),
                    row.get("owner_market"),
                    row.get("listing_date") or row.get("list_time"),
                    delisting,
                    listing_status,
                    json_dumps(row),
                    fetched_at,
                ),
            )
        for row in actions:
            cur.execute(
                """
                INSERT INTO corporate_actions (
                    action_id, ticker, code, action_type, event_date, ex_date,
                    record_date, pay_date, statement, ratio_text, amount,
                    currency, raw_json, fetched_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,CAST(%s AS JSON),%s
                )
                ON DUPLICATE KEY UPDATE
                    event_date = VALUES(event_date),
                    ex_date = VALUES(ex_date),
                    record_date = VALUES(record_date),
                    pay_date = VALUES(pay_date),
                    statement = VALUES(statement),
                    ratio_text = VALUES(ratio_text),
                    amount = VALUES(amount),
                    currency = VALUES(currency),
                    raw_json = VALUES(raw_json),
                    fetched_at = VALUES(fetched_at)
                """,
                (
                    row["action_id"],
                    row["ticker"],
                    row["code"],
                    row["action_type"],
                    row["event_date"],
                    row["ex_date"],
                    row["record_date"],
                    row["pay_date"],
                    row["statement"],
                    row["ratio_text"],
                    row["amount"],
                    row["currency"],
                    json_dumps(row["raw"]),
                    row["fetched_at"],
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
    OUTPUT_PATH.write_text(json.dumps(json_safe(package), indent=2, ensure_ascii=False), encoding="utf-8")


def write_raw_signal(package: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    write_raw_signal(
        source="Corporate_Actions_Moomoo",
        ingestion_method="moomoo_corporate_actions_basicinfo",
        raw_payload=json_safe(package),
        raw_text=(
            f"Corporate actions/listing status: tickers {package.get('ticker_count')} | "
            f"actions {package.get('action_count')} | delisting flags {package.get('delisting_flag_count')}"
        ),
        signal_type="reference",
        suspected_category="CORPORATE_ACTIONS_LISTING_STATUS",
        suspected_entities=package.get("tickers") or [],
        suspected_impact="medium",
        quality_score=package.get("coverage_ratio") or 0,
        quality_flags={"read_only_protocol": True, "orders_generated": False},
    )


def run(args: argparse.Namespace) -> Dict[str, Any]:
    import moomoo as ft
    import moomoo.common.ft_logger as ft_logger

    ft_logger.logger.enable_console_log(False)
    ensure_tables()
    tickers = get_tickers(args.limit, args.tickers)
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
    try:
        basic = fetch_basic_info(ctx, ft, tickers)
        actions: List[Dict[str, Any]] = []
        errors: Dict[str, Any] = {}
        for i, ticker in enumerate(tickers, 1):
            raw = fetch_actions_for_ticker(ctx, ticker)
            for row in raw.get("splits") or []:
                actions.append(normalize_action(ticker, "SPLIT", row, fetched_at))
            for row in raw.get("dividends") or []:
                actions.append(normalize_action(ticker, "DIVIDEND", row, fetched_at))
            if raw.get("splits_error") or raw.get("dividends_error"):
                errors[ticker] = {
                    "splits_error": raw.get("splits_error"),
                    "dividends_error": raw.get("dividends_error"),
                }
            print(f"[{i:03d}/{len(tickers):03d}] {ticker:<6} splits={len(raw.get('splits') or [])} dividends={len(raw.get('dividends') or [])}")
            if args.sleep_sec:
                time.sleep(args.sleep_sec)
    finally:
        ctx.close()

    delisting_count = sum(
        1 for row in basic.values()
        if any(x in str(row.get("listing_status") or row.get("status") or "").upper() for x in ("DELIST", "SUSPEND", "HALT"))
    )
    package = {
        "version": "v1.0",
        "generated_at": fetched_at,
        "source": "Corporate_Actions_Moomoo",
        "method": "OpenQuoteContext get_stock_basicinfo/get_corporate_actions_stock_splits/get_corporate_actions_dividends",
        "read_only_protocol": True,
        "ticker_count": len(tickers),
        "basic_info_count": len([r for r in basic.values() if not r.get("error")]),
        "coverage_ratio": round(len([r for r in basic.values() if not r.get("error")]) / len(tickers), 4) if tickers else 0,
        "action_count": len(actions),
        "split_count": sum(1 for a in actions if a.get("action_type") == "SPLIT"),
        "dividend_count": sum(1 for a in actions if a.get("action_type") == "DIVIDEND"),
        "delisting_flag_count": delisting_count,
        "tickers": tickers,
        "basic_info": basic,
        "recent_actions": actions[:500],
        "errors": errors,
    }
    write_database(basic, actions, fetched_at)
    write_outputs(package)
    write_raw_signal(package)
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Moomoo corporate actions and listing status")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--tickers", default="")
    parser.add_argument("--sleep-sec", type=float, default=0.05)
    args = parser.parse_args()
    package = run(args)
    print("BlueLotus corporate actions/listing status complete.")
    print(f"Coverage: {package['basic_info_count']}/{package['ticker_count']} | actions {package['action_count']}")


if __name__ == "__main__":
    main()

