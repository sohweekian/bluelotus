from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


HEDGE_TICKERS = {"VXX", "VIXY", "UVXY", "SVXY"}
MACRO_GATED_TICKERS = {"PL", "QUBT", "LUNR", "QBTS"}


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


def _price_for(dataset: Dict[str, Any], ticker: str, row: Dict[str, Any] | None = None) -> float:
    if row:
        for key in ("price", "last_price", "current_price"):
            if row.get(key) not in (None, ""):
                return _num(row.get(key))
    live = dataset.get("live_prices") if isinstance(dataset.get("live_prices"), dict) else {}
    rec = live.get(ticker) if isinstance(live.get(ticker), dict) else {}
    return _num(rec.get("price") or rec.get("last_price"))


def _position_value(dataset: Dict[str, Any], ticker: str, row: Dict[str, Any]) -> float:
    for key in ("mkt_val", "market_val", "market_value", "value", "position_value"):
        if row.get(key) not in (None, ""):
            return _num(row.get(key))
    return _num(row.get("qty")) * _price_for(dataset, ticker, row)


def _sleeve_rules(dataset: Dict[str, Any]) -> Dict[str, Any]:
    capsule = dataset.get("cio_context_capsule") if isinstance(dataset.get("cio_context_capsule"), dict) else {}
    rules = capsule.get("active_sleeve_rules") if isinstance(capsule.get("active_sleeve_rules"), dict) else {}
    if not rules and isinstance(dataset.get("active_sleeve_rules"), dict):
        rules = dataset.get("active_sleeve_rules") or {}
    return rules or {}


def _sleeve_for(ticker: str, rules: Dict[str, Any]) -> Dict[str, Any]:
    for sleeve_id, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        if ticker in {str(t).upper() for t in (rule.get("tickers") or [])}:
            return {"sleeve_id": sleeve_id, **rule}
    if ticker in HEDGE_TICKERS:
        return {"sleeve_id": "volatility_hedge", "role": "EVENT_HEDGE", "current_policy": "KEEP_UNTIL_RELIEF_CONFIRMED"}
    return {"sleeve_id": "unmapped", "role": "", "current_policy": ""}


def _kelly_map(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    str_data = dataset.get("shannon_thorp_refinement") if isinstance(dataset.get("shannon_thorp_refinement"), dict) else {}
    return {
        str(row.get("ticker") or "").upper(): row
        for row in (str_data.get("kelly_sizing_advisory") or [])
        if isinstance(row, dict)
    }


def _all_vector_tickers(dataset: Dict[str, Any]) -> List[str]:
    out = set()
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    for ticker, _ in _position_items(portfolio.get("positions")):
        out.add(ticker)
    for ticker in _kelly_map(dataset):
        out.add(ticker)
    for sleeve in _sleeve_rules(dataset).values():
        if isinstance(sleeve, dict):
            out.update(str(t).upper() for t in (sleeve.get("tickers") or []))
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    for row in orders.get("open_orders") or []:
        if isinstance(row, dict):
            out.add(str(row.get("ticker") or row.get("code") or "").replace("US.", "").upper())
    return sorted(t for t in out if t)


def build_target_usd_vector(dataset: Dict[str, Any], risk_overlay: Dict[str, Any] | None = None) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions = {ticker: row for ticker, row in _position_items(portfolio.get("positions"))}
    total_assets = _num(portfolio.get("total_assets", portfolio.get("total_value")))
    rules = _sleeve_rules(dataset)
    kelly = _kelly_map(dataset)
    risk_rows = {
        str(row.get("ticker") or "").upper(): row
        for row in ((risk_overlay or {}).get("ticker_outputs") or [])
        if isinstance(row, dict)
    }
    pei = dataset.get("prospective_event_intelligence") if isinstance(dataset.get("prospective_event_intelligence"), dict) else {}
    pei_text = str(pei).upper()
    macro_gate = any(token in pei_text for token in ("WARSH", "BOJ", "BLOCKED", "ADD RISK"))
    rows: List[Dict[str, Any]] = []
    for ticker in _all_vector_tickers(dataset):
        pos = positions.get(ticker, {})
        qty = _num(pos.get("qty", pos.get("quantity")))
        price = _price_for(dataset, ticker, pos)
        current_usd = _position_value(dataset, ticker, pos) if pos else 0.0
        current_weight = current_usd / total_assets if total_assets else 0.0
        sleeve = _sleeve_for(ticker, rules)
        cio_cap = _num(sleeve.get("max_capital_per_ticker_usd"), 4000.0)
        if sleeve.get("sleeve_id") == "volatility_hedge":
            cio_cap = max(current_usd, cio_cap)
        initial_scout = _num(sleeve.get("initial_scout_usd"), 1000.0)
        half_load = _num(sleeve.get("half_load_usd"), 2000.0)
        max_load = _num(sleeve.get("max_load_usd"), cio_cap)
        krow = kelly.get(ticker, {})
        str_kelly = _num(krow.get("capped_advisory_usd", krow.get("capped_advisory_size_usd")), current_usd)
        rrow = risk_rows.get(ticker, {})
        risk_cap = _num(rrow.get("risk_adjusted_target_usd"), cio_cap)
        before_gate = min(cio_cap, max_load, str_kelly if str_kelly > 0 else cio_cap, risk_cap if risk_cap > 0 else cio_cap)
        pei_gate = "PEI_MACRO_GATED" if ticker in MACRO_GATED_TICKERS and macro_gate else "PEI_CLEAR"
        operator_gate = "OPERATOR_CLEAR"
        cash_weight = (_num(portfolio.get("cash")) / total_assets) if total_assets else 0.0
        cash_constraint = "CASH_FORTRESS_ACTIVE" if cash_weight >= 0.7 else "CASH_AVAILABLE"
        if ticker in HEDGE_TICKERS:
            after_gate = current_usd
            action = "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
            explanation = "Volatility hedge excluded from equity Kelly sizing; retain/trim remains CIO manual."
        elif pei_gate != "PEI_CLEAR" and before_gate > current_usd:
            after_gate = current_usd
            action = "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED"
            explanation = "Kelly/risk may support sizing, but PEI macro gate blocks add-risk."
        elif operator_gate != "OPERATOR_CLEAR":
            after_gate = current_usd
            action = "ADD_BLOCKED"
            explanation = "Deterministic operator blocks scale-in."
        else:
            after_gate = before_gate
            if after_gate > current_usd and after_gate <= half_load:
                action = "HALF_LOAD_ONLY"
            elif after_gate > current_usd:
                action = "LOAD_ALLOWED"
            elif after_gate < current_usd * 0.8:
                action = "TRIM_REVIEW"
            else:
                action = "HOLD_OBSERVE"
            explanation = "Advisory target generated for CIO manual review only."
        delta = max(0.0, after_gate - current_usd)
        rows.append({
            "ticker": ticker,
            "current_qty": round(qty, 6),
            "current_price": round(price, 6),
            "current_usd": round(current_usd, 2),
            "current_weight": round(current_weight, 6),
            "cio_sleeve": sleeve.get("sleeve_id"),
            "cio_cap_usd": round(cio_cap, 2),
            "initial_scout_usd": round(initial_scout, 2),
            "half_load_usd": round(half_load, 2),
            "max_load_usd": round(max_load, 2),
            "str_kelly_advisory_usd": round(str_kelly, 2),
            "risk_overlay_cap_usd": round(risk_cap, 2),
            "pei_gate_status": pei_gate,
            "operator_gate_status": operator_gate,
            "cash_fortress_constraint": cash_constraint,
            "target_usd_before_gate": round(before_gate, 2),
            "target_usd_after_gate": round(after_gate, 2),
            "manual_delta_usd": round(delta, 2),
            "manual_delta_qty_estimate": round(delta / price, 6) if price else 0.0,
            "action_classification": action,
            "explanation": explanation,
            "advisory_only": True,
            "orders_generated": 0,
            "order_routing_enabled": False,
        })
    return {
        "version": "v3.1-target-usd-vector",
        "row_count": len(rows),
        "advisory_only": True,
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "rows": rows,
    }
