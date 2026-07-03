from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


HEDGE_INSTRUMENTS = {"VXX", "VIXY", "UVXY", "SVXY"}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _num_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _kelly_inputs(analyst_consensus_upside: Any, probability: Any, portfolio_assets: Any) -> Tuple[float | None, float | None, float | None, List[str]]:
    upside = _num_or_none(analyst_consensus_upside)
    prob = _num_or_none(probability)
    assets = _num_or_none(portfolio_assets)
    missing: List[str] = []
    if upside is None or upside == 0:
        missing.append("analyst_consensus_upside")
    if prob is None or prob <= 0 or prob >= 1:
        missing.append("probability")
    if assets is None or assets <= 0:
        missing.append("portfolio_assets")
    b = upside / 100.0 if upside is not None else None
    p = max(0.0, min(1.0, prob)) if prob is not None else None
    q = 1.0 - p if p is not None else None
    return b, p, q, missing


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


def resolve_portfolio_position(dataset: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    ticker_u = str(ticker).upper()
    sources = [
        ("dataset.portfolio.positions", (dataset.get("portfolio") or {}).get("positions") if isinstance(dataset.get("portfolio"), dict) else None),
        ("dataset.portfolio_readonly.positions", (dataset.get("portfolio_readonly") or {}).get("positions") if isinstance(dataset.get("portfolio_readonly"), dict) else None),
        ("dataset.moomoo_readonly_dedicated_table.positions", (dataset.get("moomoo_readonly_dedicated_table") or {}).get("positions") if isinstance(dataset.get("moomoo_readonly_dedicated_table"), dict) else None),
        ("dataset.broker_portfolio_snapshot.positions", (dataset.get("broker_portfolio_snapshot") or {}).get("positions") if isinstance(dataset.get("broker_portfolio_snapshot"), dict) else None),
    ]
    for source_name, positions in sources:
        for found, row in _position_items(positions):
            if found == ticker_u:
                return {
                    "ticker": ticker_u,
                    "current_qty": _num(row.get("qty", row.get("quantity"))),
                    "current_price": _num(row.get("price", row.get("last_price"))),
                    "current_cost_basis": _num(row.get("cost_basis", row.get("total_cost", row.get("cost")))),
                    "current_position_usd": _position_market_value(row),
                    "position_source": source_name,
                    "holding_status": "HELD_HEDGE_INSTRUMENT" if ticker_u in HEDGE_INSTRUMENTS else "HELD",
                }
    return {
        "ticker": ticker_u,
        "current_qty": 0.0,
        "current_price": 0.0,
        "current_cost_basis": 0.0,
        "current_position_usd": 0.0,
        "position_source": "NO_LIVE_POSITION",
        "holding_status": "NOT_HELD",
    }


def classify_kelly(full_fraction: float, quarter_usd: float, scout_usd: float, half_load_usd: float, input_status: str = "OK") -> str:
    if input_status == "INSUFFICIENT_DATA":
        return "KELLY_INSUFFICIENT_DATA / CIO_REVIEW_REQUIRED"
    if full_fraction <= 0:
        return "KELLY_NO_SIZE / SCOUT_ONLY_IF_CIO_APPROVES"
    if quarter_usd <= scout_usd:
        return "KELLY_SUPPORTS_SCOUT_ONLY"
    if quarter_usd <= half_load_usd:
        return "KELLY_SUPPORTS_HALF_LOAD_REVIEW"
    return "KELLY_SUPPORTS_SIZE_REVIEW_BUT_CIO_ONLY"


def _sleeve_descriptor(ticker: str, constraints: Dict[str, Any]) -> Dict[str, Any]:
    ticker_u = str(ticker or "").upper()
    if not isinstance(constraints, dict):
        constraints = {}
    for sleeve_id, rule in constraints.items():
        if not isinstance(rule, dict):
            continue
        tickers = {str(t).upper() for t in (rule.get("tickers") or [])}
        if ticker_u in tickers:
            return {
                "sleeve_id": sleeve_id,
                "sleeve_role": rule.get("role") or "",
                "sleeve_policy": rule.get("current_policy") or rule.get("allowed") or "",
                "sleeve_limit_usd": rule.get("max_capital_per_ticker_usd"),
                "kill_condition_refs": rule.get("kill_conditions") or [],
            }
    return {
        "sleeve_id": "unmapped",
        "sleeve_role": "",
        "sleeve_policy": "",
        "sleeve_limit_usd": None,
        "kill_condition_refs": [],
    }


def compute_kelly_advisory(
    ticker: str,
    analyst_consensus_upside: Any,
    probability: Any,
    portfolio_assets: Any,
    current_position_value: Any = 0.0,
    max_capital_per_ticker_usd: Any = 4000.0,
    initial_scout_usd: Any = 1000.0,
    half_load_usd: Any = 2000.0,
    active_sleeve_rule: str = "",
    sleeve_id: str = "",
    sleeve_role: str = "",
    sleeve_policy: str = "",
    sleeve_limit_usd: Any = None,
    kill_condition_refs: Any = None,
    eight_lens_score: Any = None,
    current_qty: Any = 0.0,
    current_price: Any = 0.0,
    current_cost_basis: Any = 0.0,
    holding_status: str = "",
    position_source: str = "",
    governance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ticker_u = str(ticker).upper()
    is_hedge = ticker_u in HEDGE_INSTRUMENTS
    b, p, q, missing = _kelly_inputs(analyst_consensus_upside, probability, portfolio_assets)
    if is_hedge:
        input_status = "HEDGE_INSTRUMENT_EXCLUDED"
        full = None
        edge = None
    elif missing:
        input_status = "INSUFFICIENT_DATA"
        full = None
        edge = None
    elif b is not None and b < 0:
        input_status = "NEGATIVE_EXPECTED_RETURN"
        edge = (b * p) - q  # Negative-edge sentinel; Kelly formula requires positive payoff odds.
        full = edge
    else:
        input_status = "OK"
        edge = (b * p) - q
        full = edge / b if b and b > 0 else None
    display_full = full if full is not None else 0.0
    quarter = full * 0.25 if full is not None else 0.0
    assets = _num(portfolio_assets)
    quarter_usd = max(0.0, quarter * assets) if full is not None else 0.0
    cap = _num(max_capital_per_ticker_usd, 4000.0)
    capped = min(quarter_usd, cap)
    current = _num(current_position_value)
    scout = _num(initial_scout_usd, 1000.0)
    half = _num(half_load_usd, 2000.0)
    status = "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY" if is_hedge else classify_kelly(display_full, quarter_usd, scout, half, input_status)
    delta = capped - current
    delta_pct = (delta / current) if current else None
    record = {
        "ticker": ticker_u,
        "analyst_consensus_upside": round((b or 0.0) * 100.0, 4),
        "8_lens_score": eight_lens_score,
        "8_lens_confidence": p,
        "thesis_probability": p,
        "portfolio_assets": assets,
        "max_capital_per_ticker_usd": cap,
        "active_sleeve_rule": active_sleeve_rule,
        "sleeve_id": sleeve_id,
        "sleeve_role": sleeve_role,
        "sleeve_policy": sleeve_policy,
        "sleeve_limit_usd": _num(sleeve_limit_usd, cap) if sleeve_limit_usd is not None else cap,
        "kill_condition_refs": kill_condition_refs or [],
        "kelly_b": round(b, 6) if b is not None else None,
        "kelly_p": round(p, 6) if p is not None else None,
        "kelly_q": round(q, 6) if q is not None else None,
        "kelly_input_status": input_status,
        "kelly_missing_inputs": ",".join(missing),
        "edge_estimate": round(edge, 6) if edge is not None else None,
        "full_kelly_fraction": round(display_full, 6) if full is not None else None,
        "quarter_kelly_fraction": round(quarter, 6),
        "quarter_kelly_usd": round(quarter_usd, 2),
        "capped_advisory_size_usd": round(capped, 2),
        "capped_advisory_usd": round(capped, 2),
        "current_qty": round(_num(current_qty), 6),
        "current_price": round(_num(current_price), 6),
        "current_cost_basis": round(_num(current_cost_basis), 2),
        "current_position_usd": round(current, 2),
        "current_vs_advisory_delta": round(delta, 2),
        "current_vs_advisory_pct": round(delta_pct, 6) if delta_pct is not None else None,
        "current_vs_advisory_status": "NO_LIVE_HOLDING" if current <= 0 else ("ABOVE_ADVISORY_CAP" if delta < 0 else "BELOW_ADVISORY_CAP"),
        "holding_status": holding_status or ("HEDGE_INSTRUMENT" if is_hedge else ("HELD" if current > 0 else "NOT_HELD")),
        "position_source": position_source or "",
        "kelly_status": status,
        "cio_override_required": True,
        "advisory_only": True,
        "orders_generated": 0,
        "order_routing_enabled": False,
        "warning": "Kelly output is advisory only. It is not an order. It does not override CIO manual sizing.",
    }
    if governance:
        record.update(governance)
    return record


def build_kelly_sizing_advisory(
    dataset: Dict[str, Any],
    governance: Dict[str, Any] | None = None,
    tickers: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    primary_positions = portfolio.get("positions")
    forecasts = (dataset.get("research_forecasting") or {}).get("forecasts_by_ticker") if isinstance(dataset.get("research_forecasting"), dict) else {}
    constraints = dataset.get("cio_context_capsule", {}).get("active_sleeve_rules", {}) if isinstance(dataset.get("cio_context_capsule"), dict) else {}
    if not constraints and isinstance(dataset.get("active_sleeve_rules"), dict):
        constraints = dataset.get("active_sleeve_rules") or {}
    assets = portfolio.get("total_assets") or portfolio.get("total_value") or 0
    position_names = {ticker for ticker, _ in _position_items(primary_positions)}
    names = list(tickers) if tickers else sorted(position_names | set((forecasts or {}).keys()))
    records: List[Dict[str, Any]] = []
    for ticker in names:
        fset = forecasts.get(ticker, {}) if isinstance(forecasts, dict) else {}
        analyst = fset.get("ANALYST_CONSENSUS", {}) if isinstance(fset.get("ANALYST_CONSENSUS"), dict) else {}
        bl = fset.get("BLUELOTUS_CONSERVATIVE", {}) if isinstance(fset.get("BLUELOTUS_CONSERVATIVE"), dict) else {}
        pos = resolve_portfolio_position(dataset, ticker)
        upside = analyst.get("analyst_upside_pct", analyst.get("expected_return_90d", 0))
        probability = analyst.get("probability_90d", analyst.get("confidence", bl.get("confidence", 0.5)))
        sleeve = _sleeve_descriptor(ticker, constraints)
        records.append(compute_kelly_advisory(
            ticker,
            upside,
            probability,
            assets,
            pos["current_position_usd"],
            max_capital_per_ticker_usd=4000.0,
            active_sleeve_rule=sleeve["sleeve_id"],
            sleeve_id=sleeve["sleeve_id"],
            sleeve_role=sleeve["sleeve_role"],
            sleeve_policy=sleeve["sleeve_policy"],
            sleeve_limit_usd=sleeve["sleeve_limit_usd"],
            kill_condition_refs=sleeve["kill_condition_refs"],
            eight_lens_score=bl.get("bluelotus_score"),
            current_qty=pos["current_qty"],
            current_price=pos["current_price"],
            current_cost_basis=pos["current_cost_basis"],
            holding_status=pos["holding_status"],
            position_source=pos["position_source"],
            governance=governance,
        ))
    return records
