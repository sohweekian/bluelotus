#!/usr/bin/env python3
"""
BlueLotus MID -- Moomoo read-only portfolio extractor.

Protocol:
- Extract portfolio and account data only.
- Uses position_list_query() and accinfo_query().
- Does not unlock trading.
- Does not create, modify, cancel, or route orders.

Outputs:
- portfolio_readonly_snapshots / portfolio_readonly_positions tables
- data/portfolio/portfolio_readonly_latest.json
- raw_signal_archive source Portfolio_ReadOnly_Moomoo
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
OPEND_HOST = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
OPEND_PORT = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))
OUTPUT_PATH = PROJECT_ROOT / "data" / "portfolio" / "portfolio_readonly_latest.json"

READ_ONLY_PROTOCOL = {
    "read_only": True,
    "allowed_methods_called": [
        "OpenSecTradeContext.position_list_query",
        "OpenSecTradeContext.accinfo_query",
    ],
    "prohibited_methods_called": [],
    "execution_authority": "CIO_ONLY",
    "order_routing": "DISABLED_BY_DESIGN",
    "doctrine": "Broker API is used for extraction only. CIO owns all execution.",
}


def n(value: Any, default: float = 0.0) -> float:
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


def df_records(df: Any) -> List[Dict[str, Any]]:
    if df is None:
        return []
    try:
        return [json_safe(r) for r in df.to_dict(orient="records")]
    except Exception:
        return []


def clean_ticker(code: Any) -> str:
    return str(code or "").replace("US.", "").strip().upper()


def fetch_moomoo_portfolio() -> Dict[str, Any]:
    import moomoo as ft
    import moomoo.common.ft_logger as ft_logger

    ft_logger.logger.enable_console_log(False)
    ctx = ft.OpenSecTradeContext(
        filter_trdmarket=ft.TrdMarket.US,
        host=OPEND_HOST,
        port=OPEND_PORT,
        security_firm=ft.SecurityFirm.FUTUSG,
    )
    try:
        ret_pos, pos_df = ctx.position_list_query(
            trd_env=ft.TrdEnv.REAL,
            acc_id=0,
            refresh_cache=True,
            position_market=ft.TrdMarket.US,
            currency=ft.Currency.USD,
        )
        ret_acct, acct_df = ctx.accinfo_query(
            trd_env=ft.TrdEnv.REAL,
            acc_id=0,
            refresh_cache=True,
            currency=ft.Currency.USD,
        )
    finally:
        ctx.close()

    if ret_pos != ft.RET_OK:
        raise RuntimeError(f"position_list_query failed: {pos_df}")
    if ret_acct != ft.RET_OK:
        raise RuntimeError(f"accinfo_query failed: {acct_df}")

    return {
        "positions_raw": df_records(pos_df),
        "account_raw": df_records(acct_df),
    }


def build_snapshot(raw: Dict[str, Any]) -> Dict[str, Any]:
    cycle_ts = datetime.now()
    snapshot_id = f"PFRO-{cycle_ts.strftime('%Y%m%d%H%M%S')}"
    account_rows = raw.get("account_raw") or []
    account = account_rows[0] if account_rows else {}

    positions: Dict[str, Any] = {}
    total_market_value = 0.0
    total_cost = 0.0
    total_pnl = 0.0

    for row in raw.get("positions_raw") or []:
        ticker = clean_ticker(row.get("code"))
        if not ticker:
            continue
        qty = n(row.get("qty"))
        if qty <= 0:
            continue
        average_cost = n(row.get("average_cost"))
        cost_price = n(row.get("cost_price"))
        diluted_cost = n(row.get("diluted_cost"))
        if average_cost <= 0:
            average_cost = cost_price if cost_price > 0 else diluted_cost

        market_value = n(row.get("market_val") or row.get("market_value"))
        price = n(row.get("nominal_price") or row.get("price") or row.get("last_price"))
        if price <= 0 and market_value > 0 and qty > 0:
            price = market_value / qty
        if market_value <= 0 and price > 0:
            market_value = price * qty

        cost_basis = average_cost * qty if average_cost > 0 else n(row.get("cost_basis"))
        unrealized_pnl = n(row.get("pl_val") or row.get("unrealized_pl") or row.get("unrealized_pnl"))
        if unrealized_pnl == 0 and market_value and cost_basis:
            unrealized_pnl = market_value - cost_basis
        unrealized_pnl_pct = n(row.get("pl_ratio") or row.get("pl_ratio_pct"))
        if unrealized_pnl_pct == 0 and cost_basis:
            unrealized_pnl_pct = unrealized_pnl / cost_basis * 100.0
        day_change_pct = n(row.get("today_pl_ratio") or row.get("today_pl_ratio_pct"))

        total_market_value += market_value
        total_cost += cost_basis
        total_pnl += unrealized_pnl
        positions[ticker] = {
            "ticker": ticker,
            "code": row.get("code"),
            "qty": round(qty, 6),
            "average_cost": round(average_cost, 6) if average_cost else None,
            "cost_price": round(cost_price, 6) if cost_price else None,
            "diluted_cost": round(diluted_cost, 6) if diluted_cost else None,
            "price": round(price, 6) if price else None,
            "market_value": round(market_value, 4),
            "cost_basis": round(cost_basis, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 6),
            "day_change_pct": round(day_change_pct, 6),
            "raw_position": row,
        }

    cash = n(account.get("us_cash") or account.get("cash"))
    buying_power = n(account.get("usd_net_cash_power") or account.get("power") or account.get("max_power_short"))
    account_market_value = n(account.get("market_val"))
    usd_assets = n(account.get("usd_assets") or account.get("total_assets") or account.get("total_asset"))
    total_assets = usd_assets if usd_assets > 0 else cash + total_market_value

    integrity_flag = False
    integrity_reasons = []
    if not positions:
        integrity_flag = True
        integrity_reasons.append("No live positions returned by read-only broker query.")
    if total_assets <= 0:
        integrity_flag = True
        integrity_reasons.append("Total assets could not be reconciled from account info.")
    if account_market_value > 0 and total_market_value > 0:
        diff = abs(account_market_value - total_market_value)
        if diff > max(100.0, account_market_value * 0.05):
            integrity_flag = True
            integrity_reasons.append(
                f"Account market_val differs from summed positions by ${diff:,.2f}."
            )

    return {
        "snapshot_id": snapshot_id,
        "cycle_ts": cycle_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "broker": "moomoo",
        "data_source": "OpenSecTradeContext",
        "account_currency": "USD",
        "read_only_protocol": READ_ONLY_PROTOCOL,
        "position_count": len(positions),
        "cash": round(cash, 4),
        "buying_power": round(buying_power, 4),
        "market_value": round(total_market_value, 4),
        "account_market_value": round(account_market_value, 4),
        "total_assets": round(total_assets, 4),
        "total_cost": round(total_cost, 4),
        "total_pnl": round(total_pnl, 4),
        "total_pnl_pct": round(total_pnl / total_cost * 100.0, 6) if total_cost else None,
        "integrity_flag": integrity_flag,
        "integrity_reason": "; ".join(integrity_reasons) if integrity_reasons else None,
        "positions": positions,
        "account_raw": account,
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
            INSERT INTO portfolio_readonly_snapshots (
                snapshot_id, cycle_ts, broker, data_source, account_currency,
                position_count, total_assets, cash, buying_power, market_value,
                total_cost, total_pnl, total_pnl_pct, integrity_flag,
                integrity_reason, read_only_protocol_json, account_raw_json
            ) VALUES (
                %s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,
                %s,CAST(%s AS JSON),CAST(%s AS JSON)
            )
            """,
            (
                snapshot["snapshot_id"],
                snapshot["cycle_ts"],
                snapshot["broker"],
                snapshot["data_source"],
                snapshot["account_currency"],
                snapshot["position_count"],
                snapshot["total_assets"],
                snapshot["cash"],
                snapshot["buying_power"],
                snapshot["market_value"],
                snapshot["total_cost"],
                snapshot["total_pnl"],
                snapshot["total_pnl_pct"],
                bool(snapshot["integrity_flag"]),
                snapshot["integrity_reason"],
                json.dumps(snapshot["read_only_protocol"], ensure_ascii=False, default=str),
                json.dumps(snapshot.get("account_raw") or {}, ensure_ascii=False, default=str),
            ),
        )

        for ticker, pos in (snapshot.get("positions") or {}).items():
            cur.execute(
                """
                INSERT INTO portfolio_readonly_positions (
                    snapshot_id, ticker, code, qty, average_cost, cost_price,
                    diluted_cost, price, market_value, cost_basis,
                    unrealized_pnl, unrealized_pnl_pct, day_change_pct,
                    raw_position_json
                ) VALUES (
                    %s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,CAST(%s AS JSON)
                )
                """,
                (
                    snapshot["snapshot_id"],
                    ticker,
                    pos.get("code"),
                    pos.get("qty"),
                    pos.get("average_cost"),
                    pos.get("cost_price"),
                    pos.get("diluted_cost"),
                    pos.get("price"),
                    pos.get("market_value"),
                    pos.get("cost_basis"),
                    pos.get("unrealized_pnl"),
                    pos.get("unrealized_pnl_pct"),
                    pos.get("day_change_pct"),
                    json.dumps(pos.get("raw_position") or {}, ensure_ascii=False, default=str),
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
        f"Portfolio readonly: {snapshot.get('position_count')} positions | "
        f"assets ${snapshot.get('total_assets'):,.2f} | cash ${snapshot.get('cash'):,.2f} | "
        f"read_only=True | integrity={snapshot.get('integrity_flag')}"
    )
    write_raw_signal(
        source="Portfolio_ReadOnly_Moomoo",
        ingestion_method="moomoo_readonly_position_account_query",
        raw_payload=json_safe(snapshot),
        raw_text=summary,
        signal_type="portfolio",
        suspected_category="BROKER_PORTFOLIO_READONLY",
        suspected_entities=sorted((snapshot.get("positions") or {}).keys()),
        suspected_impact="medium",
        quality_score=1.0 if not snapshot.get("integrity_flag") else 0.75,
        quality_flags={
            "read_only_protocol": True,
            "execution_methods_called": [],
            "integrity_flag": snapshot.get("integrity_flag"),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Moomoo read-only portfolio state")
    parser.add_argument("--no-db", action="store_true", help="Write JSON only")
    args = parser.parse_args()

    ensure_tables()
    raw = fetch_moomoo_portfolio()
    snapshot = build_snapshot(raw)
    if not args.no_db:
        write_database(snapshot)
        write_raw_signal(snapshot)
    write_outputs(snapshot)

    print("BlueLotus read-only portfolio snapshot generated.")
    print(f"Snapshot: {snapshot['snapshot_id']}")
    print(f"Positions: {snapshot['position_count']} | Assets: ${snapshot['total_assets']:,.2f}")
    print("Protocol: EXTRACT ONLY, no execution methods called.")


if __name__ == "__main__":
    main()

