from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Tuple

from canonical.target_usd_vector import build_target_usd_vector

from .cash_overlay import build_cash_overlay
from .concentration_overlay import build_concentration_overlay
from .hedge_overlay import build_hedge_overlay
from .liquidity_overlay import build_liquidity_overlay
from .open_order_overlay import build_open_order_overlay
from .risk_overlay_schema import DEFAULT_MAX_TICKER_USD, HEDGE_TICKERS, RISK_OVERLAY_VERSION


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _position_items(positions: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(positions, dict):
        for ticker, row in positions.items():
            if isinstance(row, dict):
                yield str(row.get("ticker") or ticker).replace("US.", "").upper(), row
    elif isinstance(positions, list):
        for row in positions:
            if isinstance(row, dict):
                yield str(row.get("ticker") or row.get("symbol") or row.get("code") or "").replace("US.", "").upper(), row


def _market_value(row: Dict[str, Any]) -> float:
    for key in ("market_value", "market_val", "mkt_val", "value", "position_value"):
        if row.get(key) not in (None, ""):
            return _num(row.get(key))
    return _num(row.get("qty") or row.get("quantity")) * _num(row.get("price") or row.get("last_price"))


def _positions(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    out: Dict[str, Dict[str, Any]] = {}
    for ticker, row in _position_items(portfolio.get("positions")):
        clone = dict(row)
        clone["market_value"] = _market_value(row)
        out[ticker] = clone
    return out


def _risk_adjust_row(row: Dict[str, Any], cash: Dict[str, Any], concentration: Dict[str, Any]) -> Dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    current = _num(row.get("current_usd"))
    raw_target = _num(row.get("target_usd_after_gate") or row.get("target_usd_before_gate"))
    cio_cap = _num(row.get("cio_cap_usd"), DEFAULT_MAX_TICKER_USD)
    cash_available = _num(cash.get("cash_available_after_open_orders"))
    cap_reason = []
    if ticker in HEDGE_TICKERS:
        adjusted = current
        status = "HEDGE_EXCLUDED_FROM_EQUITY_RISK_CAP"
        cap_reason.append("hedge_excluded_from_equity_kelly")
    else:
        adjusted = min(raw_target, cio_cap, current + max(0.0, cash_available))
        status = "RISK_ADJUSTED"
    if cash.get("cash_overlay_status") == "CASH_CONSTRAINED" and adjusted > current:
        adjusted = current
        cap_reason.append("cash_constrained")
    if concentration.get("concentration_overlay_status") == "CONCENTRATION_REVIEW" and adjusted > max(current, cio_cap):
        adjusted = max(current, cio_cap)
        cap_reason.append("concentration_cap")
    max_add = max(0.0, adjusted - current)
    return {
        "ticker": ticker,
        "current_usd": round(current, 2),
        "raw_target_usd": round(raw_target, 2),
        "cio_cap_usd": round(cio_cap, 2),
        "cash_available_cap_usd": round(cash_available, 2),
        "risk_adjusted_target_usd": round(adjusted, 2),
        "max_allowed_add_usd": round(max_add, 2),
        "risk_block_reason": ", ".join(cap_reason) if cap_reason else "NONE",
        "risk_overlay_status": status,
        "advisory_only": True,
        "orders_generated": 0,
        "order_routing_enabled": False,
    }


def build_risk_overlay(dataset: Dict[str, Any], target_vector: Dict[str, Any] | None = None) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    total_assets = _num(portfolio.get("total_assets", portfolio.get("total_value")))
    positions = _positions(dataset)
    cash = build_cash_overlay(portfolio, orders)
    concentration = build_concentration_overlay(positions, total_assets)
    hedge = build_hedge_overlay(positions, total_assets)
    liquidity = build_liquidity_overlay(positions)
    open_orders = build_open_order_overlay(orders)
    vector = target_vector or build_target_usd_vector(dataset, {})
    ticker_outputs = [_risk_adjust_row(row, cash, concentration) for row in vector.get("rows") or [] if isinstance(row, dict)]
    beta_proxy = min(2.5, 0.65 + concentration.get("cluster_concentration", 0.0))
    var_proxy = total_assets * 0.08 * beta_proxy
    overlay_status = "RISK_REVIEW" if any(
        item.get("risk_overlay_status") not in {"RISK_ADJUSTED", "HEDGE_EXCLUDED_FROM_EQUITY_RISK_CAP"} for item in ticker_outputs
    ) else "PASS"
    if concentration.get("concentration_overlay_status") != "PASS" or liquidity.get("position_risk_telemetry_status") != "PASS":
        overlay_status = "RISK_REVIEW"
    return {
        "version": RISK_OVERLAY_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "portfolio": {
            "total_assets": round(total_assets, 2),
            "portfolio_beta_estimate": round(beta_proxy, 4),
            "portfolio_var_status": "PROXY_AVAILABLE" if total_assets else "INSUFFICIENT_DATA",
            "position_risk_telemetry_status": liquidity.get("position_risk_telemetry_status"),
            "VaR95_display": f"${var_proxy:,.2f} proxy",
            "beta_display": f"{beta_proxy:.2f} proxy",
            "max_drawdown_proxy": round(var_proxy * 1.75, 2),
            **cash,
            **hedge,
            **concentration,
            **open_orders,
        },
        "ticker_outputs": ticker_outputs,
        "risk_overlay_status": overlay_status,
        "advisory_only": True,
    }
