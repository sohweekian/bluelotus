#!/usr/bin/env python3
"""
BlueLotus MID -- Moomoo historical price backfill.

Moomoo read-only:
- Uses OpenQuoteContext.request_history_kline().
- Does not import trade contexts.
- Does not create, modify, cancel, or route orders.

Outputs:
- historical_prices table
- data/history/historical_price_coverage_latest.json
- raw_signal_archive source Historical_Prices_Moomoo
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
OPEND_HOST = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
OPEND_PORT = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))
OUTPUT_PATH = PROJECT_ROOT / "data" / "history" / "historical_price_coverage_latest.json"

FACTOR_TICKERS = [
    "SPY", "QQQ", "IWM", "RSP",
    "XLK", "XLF", "XLE", "XLU", "XLP", "XLI", "XLY", "XLV", "XLB", "XLC",
    "TLT", "IEF", "SHY", "HYG", "JNK", "LQD", "AGG",
    "GLD", "SLV", "GDX", "GDXJ", "UUP", "VXX", "UVXY",
    "VUG", "VTV", "MTUM", "QUAL", "USMV", "VLUE",
    "EFA", "EEM", "FXI", "KWEB", "EWJ", "EWZ", "INDA",
    "MBB", "TIP", "BIL", "IAU", "SIL", "SILJ", "UNG", "DBA", "CPER", "URA", "DBC", "XME", "USO",
]


def n(value: Any, default: float | None = None) -> float | None:
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


def normalize_tickers(tickers: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for ticker in tickers:
        t = str(ticker or "").strip().upper().replace("US.", "")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def get_tickers(limit: int | None, include_factors: bool) -> List[str]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.ticker_universe import get_universe

    base = get_universe(limit=limit)
    return normalize_tickers([*base, *(FACTOR_TICKERS if include_factors else [])])


def latest_portfolio_tickers() -> List[str]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT p.ticker
            FROM portfolio_readonly_positions p
            JOIN (
                SELECT snapshot_id
                FROM portfolio_readonly_snapshots
                ORDER BY cycle_ts DESC, id DESC
                LIMIT 1
            ) s ON s.snapshot_id = p.snapshot_id
            ORDER BY p.ticker
        """)
        rows = [str(r.get("ticker") or "").upper() for r in cur.fetchall()]
        cur.close()
        return normalize_tickers(rows)
    except Exception:
        return []
    finally:
        conn.close()


def parse_ticker_arg(value: str) -> List[str]:
    return normalize_tickers(x.strip() for x in str(value or "").split(",") if x.strip())


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def fetch_one(ctx: Any, ft: Any, ticker: str, start: str, end: str, ktype: str, autype: str, frequency_wait_sec: float = 31.0) -> Tuple[List[Dict[str, Any]], str | None]:
    code = f"US.{ticker}"
    page_req_key = None
    rows: List[Dict[str, Any]] = []
    error = None
    frequency_retries = 0

    while True:
        ret, data, page_req_key = ctx.request_history_kline(
            code,
            start=start,
            end=end,
            ktype=ktype,
            autype=autype,
            fields=[""],
            max_count=1000,
            page_req_key=page_req_key,
        )
        if ret != ft.RET_OK:
            error_text = str(data)
            if "high frequency" in error_text.lower() and frequency_retries < 3:
                frequency_retries += 1
                print(f"  rate limit hit; sleeping {frequency_wait_sec:.0f}s before retry {frequency_retries}/3")
                time.sleep(frequency_wait_sec)
                continue
            error = error_text
            break
        if data is not None:
            try:
                rows.extend(json_safe(data.to_dict(orient="records")))
            except Exception as exc:
                error = f"DataFrame parse failed: {exc}"
                break
        if not page_req_key:
            break
    return rows, error


def fetch_cur_kline_one(ctx: Any, ft: Any, ticker: str, num: int, ktype: str, autype: str) -> Tuple[List[Dict[str, Any]], str | None]:
    """Fallback recent-bar fetch. Quote subscription only; no trade context."""
    code = f"US.{ticker}"
    try:
        ret_sub, data_sub = ctx.subscribe([code], [ft.SubType.K_DAY], subscribe_push=False)
        if ret_sub != ft.RET_OK:
            return [], f"subscribe K_DAY failed: {data_sub}"
        ret, data = ctx.get_cur_kline(code, num, ktype=ktype, autype=autype)
        if ret != ft.RET_OK:
            return [], str(data)
        try:
            return json_safe(data.to_dict(orient="records")), None
        except Exception as exc:
            return [], f"cur_kline DataFrame parse failed: {exc}"
    finally:
        try:
            ctx.unsubscribe([code], [ft.SubType.K_DAY])
        except Exception:
            pass


def parse_bar(row: Dict[str, Any], ticker: str, ktype: str, autype: str, fetched_at: str) -> Dict[str, Any] | None:
    time_key = str(row.get("time_key") or row.get("date") or "").strip()
    if not time_key:
        return None
    bar_date = time_key[:10]
    close_price = n(row.get("close"))
    if close_price is None:
        return None
    return {
        "ticker": ticker,
        "code": row.get("code") or f"US.{ticker}",
        "bar_date": bar_date,
        "time_key": time_key,
        "ktype": ktype,
        "autype": autype,
        "open_price": n(row.get("open")),
        "high_price": n(row.get("high")),
        "low_price": n(row.get("low")),
        "close_price": close_price,
        "volume": int(n(row.get("volume"), 0) or 0),
        "turnover": n(row.get("turnover")),
        "change_rate": n(row.get("change_rate")),
        "raw_bar": row,
        "fetched_at": fetched_at,
    }


def write_bars(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    conn = get_connection()
    try:
        cur = conn.cursor()
        written = 0
        for row in rows:
            cur.execute(
                """
                INSERT INTO historical_prices (
                    ticker, code, bar_date, time_key, ktype, autype,
                    open_price, high_price, low_price, close_price,
                    volume, turnover, change_rate, raw_bar_json, fetched_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,CAST(%s AS JSON),%s
                )
                ON DUPLICATE KEY UPDATE
                    code = VALUES(code),
                    time_key = VALUES(time_key),
                    open_price = VALUES(open_price),
                    high_price = VALUES(high_price),
                    low_price = VALUES(low_price),
                    close_price = VALUES(close_price),
                    volume = VALUES(volume),
                    turnover = VALUES(turnover),
                    change_rate = VALUES(change_rate),
                    raw_bar_json = VALUES(raw_bar_json),
                    fetched_at = VALUES(fetched_at)
                """,
                (
                    row["ticker"],
                    row["code"],
                    row["bar_date"],
                    row["time_key"],
                    row["ktype"],
                    row["autype"],
                    row["open_price"],
                    row["high_price"],
                    row["low_price"],
                    row["close_price"],
                    row["volume"],
                    row["turnover"],
                    row["change_rate"],
                    json.dumps(row["raw_bar"], ensure_ascii=False, default=str),
                    row["fetched_at"],
                ),
            )
            written += 1
        conn.commit()
        cur.close()
        return written
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_coverage(results: Dict[str, Any], start: str, end: str, ktype: str, autype: str) -> Dict[str, Any]:
    filled = [t for t, r in results.items() if r.get("rows", 0) > 0]
    failed = {t: r.get("error") for t, r in results.items() if r.get("error")}
    return {
        "cycle_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Historical_Prices_Moomoo",
        "method": "OpenQuoteContext.request_history_kline",
        "read_only_protocol": True,
        "start": start,
        "end": end,
        "ktype": ktype,
        "autype": autype,
        "ticker_count": len(results),
        "filled_count": len(filled),
        "coverage_ratio": round(len(filled) / len(results), 4) if results else 0.0,
        "total_rows_written": sum(int(r.get("written", 0) or 0) for r in results.values()),
        "failed_count": len(failed),
        "failed": failed,
        "tickers": results,
    }


def write_outputs(coverage: Dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(coverage), ensure_ascii=False, indent=2), encoding="utf-8")


def write_raw_signal(coverage: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    summary = (
        f"Historical prices Moomoo: coverage {coverage.get('filled_count')}/{coverage.get('ticker_count')} | "
        f"rows {coverage.get('total_rows_written')} | {coverage.get('start')} to {coverage.get('end')}"
    )
    write_raw_signal(
        source="Historical_Prices_Moomoo",
        ingestion_method="moomoo_request_history_kline",
        raw_payload=json_safe(coverage),
        raw_text=summary,
        signal_type="market_data",
        suspected_category="HISTORICAL_PRICE_BARS",
        suspected_entities=list((coverage.get("tickers") or {}).keys())[:250],
        suspected_impact="medium",
        quality_score=float(coverage.get("coverage_ratio") or 0),
        quality_flags={
            "read_only_protocol": True,
            "failed_count": coverage.get("failed_count"),
            "ktype": coverage.get("ktype"),
        },
    )


def fetch_all(args: argparse.Namespace) -> Dict[str, Any]:
    import moomoo as ft
    import moomoo.common.ft_logger as ft_logger

    ft_logger.logger.enable_console_log(False)
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=args.days)
    start = args.start or start_dt.strftime("%Y-%m-%d")
    end = args.end or end_dt.strftime("%Y-%m-%d")
    if args.tickers:
        tickers = parse_ticker_arg(args.tickers)
    elif args.portfolio_and_factors:
        tickers = normalize_tickers([*latest_portfolio_tickers(), *FACTOR_TICKERS])
    else:
        tickers = get_tickers(args.limit, args.include_factors)
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
    results: Dict[str, Any] = {}
    try:
        for idx, ticker in enumerate(tickers, 1):
            raw_rows, error = fetch_one(ctx, ft, ticker, start, end, args.ktype, args.autype, args.frequency_wait_sec)
            used_method = "request_history_kline"
            if error and args.quota_fallback_cur_kline and "insufficient historical candlestick quota" in error.lower():
                raw_rows, fallback_error = fetch_cur_kline_one(ctx, ft, ticker, args.cur_kline_num, args.ktype, args.autype)
                if raw_rows:
                    error = None
                    used_method = "get_cur_kline_after_quote_subscribe"
                else:
                    error = f"{error}; fallback_error={fallback_error}"
            bars = [
                bar for bar in (
                    parse_bar(row, ticker, args.ktype, args.autype, fetched_at)
                    for row in raw_rows
                )
                if bar is not None
            ]
            written = write_bars(bars)
            results[ticker] = {
                "rows": len(bars),
                "written": written,
                "first_date": bars[0]["bar_date"] if bars else None,
                "last_date": bars[-1]["bar_date"] if bars else None,
                "method": used_method,
                "error": error,
            }
            print(f"[{idx:03d}/{len(tickers):03d}] {ticker:<6} rows={len(bars):4d} written={written:4d}" + (f" ERROR={error}" if error else ""))
            if args.sleep_sec > 0:
                time.sleep(args.sleep_sec)
    finally:
        ctx.close()

    return build_coverage(results, start, end, args.ktype, args.autype)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Moomoo historical kline bars")
    parser.add_argument("--days", type=int, default=180, help="Lookback calendar days when --start is omitted")
    parser.add_argument("--start", default="", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="", help="End date YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=None, help="Universe ticker limit before factors are added")
    parser.add_argument("--tickers", default="", help="Comma-separated explicit ticker list; overrides --limit/--include-factors")
    parser.add_argument("--portfolio-and-factors", action="store_true", help="Use latest read-only portfolio tickers plus core factor proxies")
    parser.add_argument("--ktype", default="K_DAY")
    parser.add_argument("--autype", default="qfq")
    parser.add_argument("--sleep-sec", type=float, default=0.55)
    parser.add_argument("--frequency-wait-sec", type=float, default=31.0)
    parser.add_argument("--include-factors", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--quota-fallback-cur-kline", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--cur-kline-num", type=int, default=180)
    parser.add_argument("--no-db", action="store_true", help="Skip raw_signal write only; bar table still required for risk model")
    args = parser.parse_args()

    ensure_tables()
    coverage = fetch_all(args)
    write_outputs(coverage)
    if not args.no_db:
        write_raw_signal(coverage)

    print("BlueLotus historical price backfill complete.")
    print(f"Coverage: {coverage['filled_count']}/{coverage['ticker_count']} ({coverage['coverage_ratio']:.1%})")
    print(f"Rows written: {coverage['total_rows_written']}")


if __name__ == "__main__":
    main()

