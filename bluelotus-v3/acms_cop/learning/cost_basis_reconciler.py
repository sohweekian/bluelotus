from __future__ import annotations

from typing import Any, Dict, Iterable, List


DEFAULT_CONFLICT_TICKERS = ("ASTS", "QUBT", "LUNR", "QBTS")


def _num(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def reconcile_cost_basis(
    ticker: str,
    broker_unrealized: Any,
    computed_unrealized: Any,
    third_witness_unrealized: Any = None,
    tolerance: float = 5.0,
    governance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    broker = _num(broker_unrealized)
    computed = _num(computed_unrealized)
    third = _num(third_witness_unrealized)
    delta_bc = None if broker is None or computed is None else round(broker - computed, 4)
    delta_bt = None if broker is None or third is None else round(broker - third, 4)
    delta_ct = None if computed is None or third is None else round(computed - third, 4)

    if broker is not None and computed is not None and abs(broker - computed) <= tolerance:
        status = "RESOLVED_HIGH_CONFIDENCE"
        selected = "BROKER_AND_PIPELINE_AGREE"
        review = False
        reliability = "broker_api_and_pipeline_confirmed"
    elif third is not None and broker is not None and computed is not None:
        broker_ok = abs(broker - third) <= tolerance
        computed_ok = abs(computed - third) <= tolerance
        if broker_ok and not computed_ok:
            status = "RESOLVED_WITH_THIRD_WITNESS"
            selected = "BROKER_REPORTED"
            review = False
            reliability = "broker_api_confirmed_by_third_witness"
        elif computed_ok and not broker_ok:
            status = "RESOLVED_WITH_THIRD_WITNESS"
            selected = "PIPELINE_COMPUTED"
            review = False
            reliability = "pipeline_computed_confirmed_by_third_witness"
        else:
            status = "MANUAL_REVIEW_REQUIRED"
            selected = "NO_SOURCE_SELECTED"
            review = True
            reliability = "third_witness_disagrees_with_broker_and_pipeline"
    else:
        status = "UNRESOLVED_AWAITING_THIRD_SOURCE"
        selected = "BROKER_REPORTED"
        review = True
        reliability = "awaiting_independent_third_witness"

    record = {
        "ticker": str(ticker).upper(),
        "broker_unrealized": broker,
        "computed_unrealized": computed,
        "third_witness_unrealized": third,
        "delta_broker_vs_computed": delta_bc,
        "delta_broker_vs_third": delta_bt,
        "delta_computed_vs_third": delta_ct,
        "selected_source": selected,
        "resolution_status": status,
        "source_reliability_update": reliability,
        "cio_review_required": review,
    }
    if governance:
        record.update(governance)
    return record


def build_cost_basis_reconciliation(
    dataset: Dict[str, Any],
    governance: Dict[str, Any] | None = None,
    tickers: Iterable[str] = DEFAULT_CONFLICT_TICKERS,
) -> List[Dict[str, Any]]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), dict) else {}
    third_map = dataset.get("cost_basis_third_witness") if isinstance(dataset.get("cost_basis_third_witness"), dict) else {}
    if not third_map and isinstance(dataset.get("third_witness_cost_basis"), dict):
        third_map = dataset.get("third_witness_cost_basis") or {}
    records: List[Dict[str, Any]] = []
    for ticker in tickers:
        pos = positions.get(ticker, {}) if isinstance(positions.get(ticker), dict) else {}
        third_row = third_map.get(ticker) if isinstance(third_map, dict) else None
        third = third_row.get("unrealized", third_row.get("unrealized_pnl")) if isinstance(third_row, dict) else None
        records.append(reconcile_cost_basis(
            ticker,
            pos.get("unrealized", pos.get("unrealized_pnl")),
            pos.get("computed_unrealized"),
            third,
            governance=governance,
        ))
    return records
