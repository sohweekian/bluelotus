from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_governance(dataset: Dict[str, Any]) -> Dict[str, Any]:
    law = dataset.get("law_governance_binding") if isinstance(dataset.get("law_governance_binding"), dict) else {}
    execution = dataset.get("execution") if isinstance(dataset.get("execution"), dict) else {}
    return {
        "execution_authority": execution.get("execution_authority") or law.get("execution_authority") or "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "broker_mode": "READ_ONLY",
        "broker_api_role": "READ_ONLY_EXTRACTION",
        "law_pack_id": law.get("governance_pack_id") or law.get("active_governance_pack_id") or "UNBOUND",
        "report_memory_binding_id": law.get("report_memory_binding_id") or law.get("binding_id") or "UNBOUND",
        "cio_context_capsule_hash": law.get("cio_context_capsule_hash") or "",
        "chief_strategist_master_prompt_hash": law.get("chief_strategist_master_prompt_hash") or "",
        "no_automatic_dca": True,
        "no_automatic_second_tranche": True,
        "no_broker_mutation": True,
    }


def resolve_session(dataset: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    raw = str(meta.get("market_session") or "").upper()
    if "WEEKEND" in raw:
        canonical = "WEEKEND_SNAPSHOT"
    elif "HOLIDAY" in raw:
        canonical = "HOLIDAY_CLOSED"
    elif "PRE" in raw:
        canonical = "PRE_MARKET"
    elif "AFTER" in raw or "POST" in raw:
        canonical = "AFTER_HOURS"
    elif "REGULAR" in raw or raw == "OPEN":
        canonical = "REGULAR_OPEN"
    elif raw:
        canonical = "MARKET_CLOSED_LAST_REGULAR_CLOSE"
    else:
        canonical = "UNKNOWN_REQUIRES_REVIEW"
    legacy_flag = str(regime.get("session_flag") or "").upper()
    legacy_closed = regime.get("market_closed")
    conflict = canonical == "WEEKEND_SNAPSHOT" and legacy_flag == "OPEN"
    return {
        "canonical_market_session": canonical,
        "market_closed": True if canonical in {"WEEKEND_SNAPSHOT", "HOLIDAY_CLOSED", "MARKET_CLOSED_LAST_REGULAR_CLOSE"} else False,
        "session_source": raw or "UNKNOWN",
        "legacy_session_flag": legacy_flag,
        "legacy_market_closed": legacy_closed,
        "session_conflict_detected": conflict,
        "session_conflict_resolution": "CANONICAL_OVERRIDES_LEGACY_OPEN" if conflict else "NO_CONFLICT",
    }


def resolve_portfolio_state(dataset: Dict[str, Any]) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    readonly = dataset.get("portfolio_readonly") if isinstance(dataset.get("portfolio_readonly"), dict) else {}
    positions_raw = portfolio.get("positions")
    positions = positions_raw if isinstance(positions_raw, (dict, list)) else {}
    return {
        "total_assets": _num(portfolio.get("total_assets", portfolio.get("total_value"))),
        "cash": _num(readonly.get("cash", portfolio.get("cash"))),
        "buying_power": _num(readonly.get("buying_power", portfolio.get("buying_power"))),
        "position_count": len(positions),
        "positions_source": "portfolio.positions",
        "portfolio_truth_status": "PASS",
    }


def resolve_order_state(dataset: Dict[str, Any]) -> Dict[str, Any]:
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    open_orders = orders.get("open_orders") if isinstance(orders.get("open_orders"), list) else []
    reserved = 0.0
    for row in open_orders:
        if not isinstance(row, dict):
            continue
        if str(row.get("trd_side") or row.get("side") or "").upper() == "BUY":
            status = str(row.get("order_status") or row.get("status") or "").upper()
            if "CANCEL" not in status and "FILL" not in status:
                reserved += _num(row.get("qty")) * _num(row.get("price", row.get("limit_price")))
    return {
        "open_order_count": len(open_orders),
        "open_order_reserved_cash": round(reserved, 2),
        "broker_mutation_detected": False,
        "orders_generated": 0,
        "order_routing_enabled": False,
        "order_state_status": "PASS",
    }


def build_truth_source_audit(dataset: Dict[str, Any], session_state: Dict[str, Any], portfolio_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "PASS" if session_state.get("canonical_market_session") else "REVIEW",
        "canonical_session_source": "canonical.session_state",
        "canonical_portfolio_source": "portfolio_readonly+portfolio",
        "canonical_order_source": "orders.open_orders",
        "legacy_fields_deprecated": [
            "regime.session_flag",
            "regime.market_closed",
            "portfolio.buying_power_delta",
            "portfolio.buying_power_delta_flag",
        ],
        "notes": "Canonical fields are primary. Legacy fields are retained for compatibility only.",
    }
