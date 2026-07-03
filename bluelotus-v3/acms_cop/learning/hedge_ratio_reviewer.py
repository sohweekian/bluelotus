from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_hedge(current: float, target: float) -> str:
    if target <= 0:
        return "HEDGE_DATA_INSUFFICIENT"
    ratio = current / target
    if ratio < 0.70:
        return "UNDER_HEDGED"
    if ratio <= 1.30:
        return "ROUGHLY_HEDGED"
    return "OVER_HEDGED"


def _position_items(positions: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(positions, dict):
        for ticker, row in positions.items():
            if isinstance(row, dict):
                yield str(row.get("ticker") or ticker).upper(), row
        return
    if isinstance(positions, list):
        for row in positions:
            if isinstance(row, dict):
                yield str(row.get("ticker") or row.get("symbol") or "").upper(), row


def _position_market_value(row: Dict[str, Any]) -> float:
    for key in ("mkt_val", "market_val", "market_value", "value", "position_value"):
        if key in row:
            return _num(row.get(key))
    qty = _num(row.get("qty", row.get("quantity")))
    price = _num(row.get("price", row.get("last_price")))
    return qty * price if qty and price else 0.0


def _portfolio_positions(dataset: Dict[str, Any]) -> Tuple[Any, str]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions = portfolio.get("positions")
    if positions:
        return positions, "dataset.portfolio.positions[*].mkt_val"
    readonly = dataset.get("portfolio_readonly") if isinstance(dataset.get("portfolio_readonly"), dict) else {}
    positions = readonly.get("positions")
    if positions:
        return positions, "dataset.portfolio_readonly.positions[*].market_value"
    return {}, "NO_PORTFOLIO_POSITIONS_FOUND"


def review_hedge_ratio(
    portfolio_beta_to_spy: Any,
    portfolio_market_value: Any,
    current_vxx_value: Any,
    current_vixy_value: Any,
    hedge_effectiveness: Any = 3.6,
    event_failure_probability: Any = 0.25,
    cross_asset_stress_score: Any = 0.0,
    governance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    beta = _num(portfolio_beta_to_spy)
    market_value = _num(portfolio_market_value)
    vxx = _num(current_vxx_value)
    vixy = _num(current_vixy_value)
    effectiveness = max(0.01, abs(_num(hedge_effectiveness, 3.6)))
    hedge_ratio = abs(beta) / effectiveness if beta else 0.0
    implied = market_value * hedge_ratio
    event_p = max(0.0, min(1.0, _num(event_failure_probability, 0.25)))
    fractional = implied * max(0.25, event_p)
    current = vxx + vixy
    status = classify_hedge(current, fractional)
    record = {
        "portfolio_beta_to_spy": round(beta, 6),
        "hedge_effectiveness": round(effectiveness, 6),
        "hedge_ratio": round(hedge_ratio, 6),
        "portfolio_market_value": round(market_value, 2),
        "current_vxx_value": round(vxx, 2),
        "current_vixy_value": round(vixy, 2),
        "current_hedge_value": round(current, 2),
        "current_hedge_pct_of_market_value": round(current / market_value, 6) if market_value else 0.0,
        "implied_full_hedge_value": round(implied, 2),
        "fractional_hedge_value": round(fractional, 2),
        "hedge_gap_usd": round(fractional - current, 2),
        "cross_asset_stress_score": _num(cross_asset_stress_score),
        "event_failure_probability": event_p,
        "hedge_status": status,
        "advisory_only": True,
        "data_quality_status": "RECONCILED" if current > 0 else "NO_HEDGE_POSITION_VALUE_FOUND",
        "disclaimer": "Hedge ratio review is advisory only. It does not create a hedge order. It does not recommend automatic VXX/VIXY sizing. CIO_ONLY_MANUAL remains supreme.",
        "orders_generated": 0,
        "order_routing_enabled": False,
    }
    if governance:
        record.update(governance)
    return record


def build_hedge_ratio_review(dataset: Dict[str, Any], governance: Dict[str, Any] | None = None) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions, hedge_source = _portfolio_positions(dataset)
    risk_model = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    risk_positions = risk_model.get("positions") if isinstance(risk_model.get("positions"), list) else []

    market_value = _num(portfolio.get("market_val", portfolio.get("total_value")))
    weighted_beta = 0.0
    hedge_effectiveness_values: List[float] = []
    for item in risk_positions:
        ticker = str(item.get("ticker", "")).upper()
        value = _num(item.get("market_value"))
        beta = _num(item.get("beta_to_spy"))
        if ticker in {"VXX", "VIXY"} and beta:
            hedge_effectiveness_values.append(abs(beta))
        elif value and beta:
            weighted_beta += (value / market_value) * beta if market_value else 0.0

    hedge_values: Dict[str, float] = {"VXX": 0.0, "VIXY": 0.0}
    matched_tickers: List[str] = []
    for ticker, row in _position_items(positions):
        if ticker in hedge_values:
            hedge_values[ticker] += _position_market_value(row)
            matched_tickers.append(ticker)
    effectiveness = sum(hedge_effectiveness_values) / len(hedge_effectiveness_values) if hedge_effectiveness_values else 3.6
    stress = ((dataset.get("regime") or {}).get("score") if isinstance(dataset.get("regime"), dict) else 0) or 0
    record = review_hedge_ratio(
        weighted_beta,
        market_value,
        hedge_values["VXX"],
        hedge_values["VIXY"],
        effectiveness,
        0.25,
        stress,
        governance,
    )
    record.update({
        "hedge_value_source": hedge_source,
        "hedge_tickers_expected": ["VXX", "VIXY"],
        "hedge_tickers_matched": sorted(set(matched_tickers)),
    })
    return record
