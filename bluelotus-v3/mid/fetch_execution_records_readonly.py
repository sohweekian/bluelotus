#!/usr/bin/env python3
"""
BlueLotus MID -- Moomoo read-only execution records extractor.

Protocol:
- Extract open orders, historical orders, open deals, and historical deals only.
- Uses Moomoo read/query methods.
- Does not unlock trading.
- Does not create, modify, cancel, or route orders.

Outputs:
- execution_readonly_snapshots / execution_readonly_orders /
  execution_readonly_deals / execution_readonly_fees tables
- data/execution/execution_readonly_latest.json
- raw_signal_archive source Execution_ReadOnly_Moomoo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
OPEND_HOST = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
OPEND_PORT = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))
OUTPUT_PATH = PROJECT_ROOT / "data" / "execution" / "execution_readonly_latest.json"

READ_ONLY_PROTOCOL = {
    "read_only": True,
    "allowed_methods_called": [
        "OpenSecTradeContext.order_list_query",
        "OpenSecTradeContext.history_order_list_query",
        "OpenSecTradeContext.deal_list_query",
        "OpenSecTradeContext.history_deal_list_query",
        "OpenSecTradeContext.order_fee_query",
    ],
    "prohibited_methods_called": [],
    "execution_authority": "CIO_ONLY",
    "order_routing": "DISABLED_BY_DESIGN",
    "orders_generated_by_pipeline": False,
    "doctrine": "Broker API is used for extraction only. CIO owns all execution.",
}


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


def df_records(df: Any) -> List[Dict[str, Any]]:
    if df is None:
        return []
    try:
        return [json_safe(r) for r in df.to_dict(orient="records")]
    except Exception:
        return []


def n(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("N/A", "").replace("--", "").strip()
        if not text:
            return default
        out = float(text)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def dt(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).replace("T", " ").split(".")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text[:19], fmt)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
    return None


def clean_ticker(code: Any) -> str:
    return str(code or "").replace("US.", "").strip().upper()


def stable_id(prefix: str, row: Dict[str, Any]) -> str:
    raw = json.dumps(json_safe(row), sort_keys=True, ensure_ascii=False, default=str)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()[:24]}"


def first_present(row: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def fetch_moomoo_execution(days: int) -> Dict[str, Any]:
    import moomoo as ft
    import moomoo.common.ft_logger as ft_logger

    ft_logger.logger.enable_console_log(False)
    end_date = date.today()
    start_date = end_date - timedelta(days=max(1, int(days)))
    query_errors: Dict[str, str] = {}
    rows: Dict[str, List[Dict[str, Any]]] = {
        "open_orders": [],
        "historical_orders": [],
        "open_deals": [],
        "historical_deals": [],
        "fees": [],
    }

    ctx = ft.OpenSecTradeContext(
        filter_trdmarket=ft.TrdMarket.US,
        host=OPEND_HOST,
        port=OPEND_PORT,
        security_firm=ft.SecurityFirm.FUTUSG,
    )
    try:
        ret, data = ctx.order_list_query(
            trd_env=ft.TrdEnv.REAL,
            acc_id=0,
            refresh_cache=True,
            order_market=ft.TrdMarket.US,
        )
        if ret == ft.RET_OK:
            rows["open_orders"] = df_records(data)
        else:
            query_errors["order_list_query"] = str(data)

        ret, data = ctx.history_order_list_query(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            trd_env=ft.TrdEnv.REAL,
            acc_id=0,
            order_market=ft.TrdMarket.US,
        )
        if ret == ft.RET_OK:
            rows["historical_orders"] = df_records(data)
        else:
            query_errors["history_order_list_query"] = str(data)

        ret, data = ctx.deal_list_query(
            trd_env=ft.TrdEnv.REAL,
            acc_id=0,
            refresh_cache=True,
            deal_market=ft.TrdMarket.US,
        )
        if ret == ft.RET_OK:
            rows["open_deals"] = df_records(data)
        else:
            query_errors["deal_list_query"] = str(data)

        ret, data = ctx.history_deal_list_query(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            trd_env=ft.TrdEnv.REAL,
            acc_id=0,
            deal_market=ft.TrdMarket.US,
        )
        if ret == ft.RET_OK:
            rows["historical_deals"] = df_records(data)
        else:
            query_errors["history_deal_list_query"] = str(data)

        order_ids = []
        for row in rows["open_orders"] + rows["historical_orders"]:
            order_id = first_present(row, ["order_id", "orderID", "id"])
            if order_id:
                order_ids.append(str(order_id))
        order_ids = sorted(set(order_ids))[:50]
        if order_ids:
            ret, data = ctx.order_fee_query(order_id_list=order_ids, trd_env=ft.TrdEnv.REAL, acc_id=0)
            if ret == ft.RET_OK:
                rows["fees"] = df_records(data)
            else:
                query_errors["order_fee_query"] = str(data)
    finally:
        ctx.close()

    rows["start_date"] = start_date.isoformat()  # type: ignore[assignment]
    rows["end_date"] = end_date.isoformat()  # type: ignore[assignment]
    rows["query_errors"] = query_errors  # type: ignore[assignment]
    return rows


def build_snapshot(raw: Dict[str, Any], days: int) -> Dict[str, Any]:
    cycle_ts = datetime.now()
    snapshot_id = f"EXRO-{cycle_ts.strftime('%Y%m%d%H%M%S')}"
    query_errors = raw.get("query_errors") if isinstance(raw.get("query_errors"), dict) else {}
    open_orders = raw.get("open_orders") if isinstance(raw.get("open_orders"), list) else []
    historical_orders = raw.get("historical_orders") if isinstance(raw.get("historical_orders"), list) else []
    open_deals = raw.get("open_deals") if isinstance(raw.get("open_deals"), list) else []
    historical_deals = raw.get("historical_deals") if isinstance(raw.get("historical_deals"), list) else []
    fees = raw.get("fees") if isinstance(raw.get("fees"), list) else []

    status = "operational" if not query_errors else "partial_error"
    return {
        "status": status,
        "snapshot_id": snapshot_id,
        "cycle_ts": cycle_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "broker": "moomoo",
        "data_source": "OpenSecTradeContext",
        "trd_env": "REAL",
        "market": "US",
        "lookback_days": int(days),
        "start_date": raw.get("start_date"),
        "end_date": raw.get("end_date"),
        "open_order_count": len(open_orders),
        "historical_order_count": len(historical_orders),
        "open_deal_count": len(open_deals),
        "historical_deal_count": len(historical_deals),
        "fee_record_count": len(fees),
        "query_errors": query_errors,
        "read_only_protocol": READ_ONLY_PROTOCOL,
        "open_orders": open_orders,
        "historical_orders": historical_orders,
        "open_deals": open_deals,
        "historical_deals": historical_deals,
        "fees": fees,
        "summary": {
            "orders_generated_by_pipeline": False,
            "order_routing_enabled": False,
            "execution_authority": "CIO_ONLY",
            "has_order_history_extraction": True,
            "has_deal_history_extraction": True,
            "query_error_count": len(query_errors),
        },
    }


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def write_database(snapshot: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO execution_readonly_snapshots (
                snapshot_id, cycle_ts, broker, data_source, trd_env, market,
                start_date, end_date, open_order_count, historical_order_count,
                open_deal_count, historical_deal_count, fee_record_count,
                query_errors_json, read_only_protocol_json, summary_json
            ) VALUES (
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,
                CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON)
            )
            """,
            (
                snapshot["snapshot_id"],
                snapshot["cycle_ts"],
                snapshot["broker"],
                snapshot["data_source"],
                snapshot["trd_env"],
                snapshot["market"],
                snapshot["start_date"],
                snapshot["end_date"],
                snapshot["open_order_count"],
                snapshot["historical_order_count"],
                snapshot["open_deal_count"],
                snapshot["historical_deal_count"],
                snapshot["fee_record_count"],
                json.dumps(snapshot.get("query_errors") or {}, ensure_ascii=False, default=str),
                json.dumps(snapshot["read_only_protocol"], ensure_ascii=False, default=str),
                json.dumps(snapshot["summary"], ensure_ascii=False, default=str),
            ),
        )

        for scope, collection in (("OPEN", snapshot.get("open_orders") or []), ("HISTORICAL", snapshot.get("historical_orders") or [])):
            for row in collection:
                if not isinstance(row, dict):
                    continue
                order_id = str(first_present(row, ["order_id", "orderID", "id"]) or stable_id("ORD", row))
                code = first_present(row, ["code", "stock_code"])
                cur.execute(
                    """
                    INSERT INTO execution_readonly_orders (
                        snapshot_id, order_scope, order_id, code, ticker,
                        trd_side, order_type, order_status, qty, price,
                        dealt_qty, dealt_avg_price, create_time, updated_time,
                        raw_order_json
                    ) VALUES (
                        %s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,
                        %s,%s,%s,%s,
                        CAST(%s AS JSON)
                    )
                    ON DUPLICATE KEY UPDATE raw_order_json = VALUES(raw_order_json)
                    """,
                    (
                        snapshot["snapshot_id"],
                        scope,
                        order_id,
                        code,
                        clean_ticker(code),
                        first_present(row, ["trd_side", "side"]),
                        first_present(row, ["order_type", "orderType"]),
                        first_present(row, ["order_status", "status", "orderStatus"]),
                        n(first_present(row, ["qty", "quantity"])),
                        n(first_present(row, ["price", "order_price"])),
                        n(first_present(row, ["dealt_qty", "filled_qty"])),
                        n(first_present(row, ["dealt_avg_price", "filled_avg_price", "avg_price"])),
                        dt(first_present(row, ["create_time", "createTime", "created_time"])),
                        dt(first_present(row, ["updated_time", "update_time", "updatedTime"])),
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )

        for scope, collection in (("OPEN", snapshot.get("open_deals") or []), ("HISTORICAL", snapshot.get("historical_deals") or [])):
            for row in collection:
                if not isinstance(row, dict):
                    continue
                deal_id = str(first_present(row, ["deal_id", "dealID", "id"]) or stable_id("DEAL", row))
                order_id = first_present(row, ["order_id", "orderID"])
                code = first_present(row, ["code", "stock_code"])
                cur.execute(
                    """
                    INSERT INTO execution_readonly_deals (
                        snapshot_id, deal_scope, deal_id, order_id, code, ticker,
                        trd_side, qty, price, deal_time, raw_deal_json
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,CAST(%s AS JSON)
                    )
                    ON DUPLICATE KEY UPDATE raw_deal_json = VALUES(raw_deal_json)
                    """,
                    (
                        snapshot["snapshot_id"],
                        scope,
                        deal_id,
                        str(order_id) if order_id else None,
                        code,
                        clean_ticker(code),
                        first_present(row, ["trd_side", "side"]),
                        n(first_present(row, ["qty", "quantity"])),
                        n(first_present(row, ["price", "deal_price"])),
                        dt(first_present(row, ["deal_time", "create_time", "time"])),
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )

        for row in snapshot.get("fees") or []:
            if not isinstance(row, dict):
                continue
            order_id = str(first_present(row, ["order_id", "orderID", "id"]) or stable_id("FEE", row))
            cur.execute(
                """
                INSERT INTO execution_readonly_fees (
                    snapshot_id, order_id, fee_record_json
                ) VALUES (%s,%s,CAST(%s AS JSON))
                ON DUPLICATE KEY UPDATE fee_record_json = VALUES(fee_record_json)
                """,
                (
                    snapshot["snapshot_id"],
                    order_id,
                    json.dumps(row, ensure_ascii=False, default=str),
                ),
            )

        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_outputs(snapshot: Dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")


def write_raw_signal(snapshot: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    summary = (
        f"Execution readonly: open_orders {snapshot.get('open_order_count')} | "
        f"historical_orders {snapshot.get('historical_order_count')} | "
        f"historical_deals {snapshot.get('historical_deal_count')} | "
        f"read_only=True | errors {len(snapshot.get('query_errors') or {})}"
    )
    write_raw_signal(
        source="Execution_ReadOnly_Moomoo",
        ingestion_method="moomoo_readonly_order_deal_history_query",
        raw_payload=json_safe(snapshot),
        raw_text=summary,
        signal_type="execution",
        suspected_category="BROKER_EXECUTION_READONLY",
        suspected_entities=[],
        suspected_impact="medium",
        quality_score=1.0 if not snapshot.get("query_errors") else 0.75,
        quality_flags={
            "read_only_protocol": True,
            "orders_generated_by_pipeline": False,
            "execution_methods_called": [],
            "query_errors": snapshot.get("query_errors") or {},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Moomoo read-only order/deal execution records")
    parser.add_argument("--days", type=int, default=180, help="Historical order/deal lookback days.")
    parser.add_argument("--no-db", action="store_true", help="Write JSON only.")
    args = parser.parse_args()

    ensure_tables()
    raw = fetch_moomoo_execution(args.days)
    snapshot = build_snapshot(raw, args.days)
    if not args.no_db:
        write_database(snapshot)
        write_raw_signal(snapshot)
    write_outputs(snapshot)

    print("BlueLotus read-only execution records snapshot generated.")
    print(f"Snapshot: {snapshot['snapshot_id']} | status: {snapshot['status']}")
    print(
        "Open orders: {open_order_count} | Historical orders: {historical_order_count} | "
        "Historical deals: {historical_deal_count}".format(**snapshot)
    )
    print("Protocol: EXTRACT ONLY, no unlock/order mutation methods called.")


if __name__ == "__main__":
    main()

