from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from acms_cop.common import first_dict, first_list, parse_dt


def _event(issue_type: str, severity: str, description: str, component: str = "ACMS-COP", ticker: str | None = None, theme: str | None = None) -> Dict[str, Any]:
    return {
        "issue_time": parse_dt(datetime.now()),
        "issue_type": issue_type,
        "severity": severity,
        "affected_ticker": ticker,
        "affected_theme": theme,
        "affected_component": component,
        "issue_description": description,
        "detected_by": "acms_cop.data_quality_extractor",
        "resolved": False,
        "resolved_at": None,
        "resolution_notes": None,
    }


def extract_data_quality_events(
    cycle_row: Dict[str, Any],
    ticker_rows: List[Dict[str, Any]],
    theme_rows: List[Dict[str, Any]],
    dataset: Dict[str, Any],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if str(cycle_row.get("execution_authority", "")).upper() != "CIO_ONLY_MANUAL":
        events.append(_event("EXECUTION_SAFETY_CONFLICT", "CRITICAL", "Execution authority is not CIO_ONLY_MANUAL.", "execution"))
    if bool(cycle_row.get("order_routing_enabled")):
        events.append(_event("EXECUTION_SAFETY_CONFLICT", "CRITICAL", "Order routing enabled.", "execution"))
    if bool(cycle_row.get("llm_order_generation_enabled")):
        events.append(_event("EXECUTION_SAFETY_CONFLICT", "CRITICAL", "LLM order generation enabled.", "execution"))
    if int(cycle_row.get("system_generated_orders") or 0) > 0:
        events.append(_event("EXECUTION_SAFETY_CONFLICT", "CRITICAL", "System generated orders are non-zero.", "execution"))

    portfolio = first_dict(dataset.get("portfolio"), dataset.get("portfolio_readonly"))
    positions = first_dict(portfolio.get("positions"))
    for ticker, pos in positions.items():
        status = str(first_dict(pos).get("pnl_integrity_status", "")).upper()
        if status.startswith("BROKER_PNL"):
            events.append(_event("PNL_CONFLICT", "WARNING", f"{ticker} P/L status {status}.", "portfolio", ticker=str(ticker)))

    seen_themes: set[str] = set()
    for row in theme_rows:
        theme = str(row.get("theme") or "")
        key = theme.upper()
        if key in seen_themes:
            events.append(_event("DUPLICATE_THEME", "WARNING", f"Duplicate ACMS theme row detected: {theme}.", "theme", theme=theme))
        seen_themes.add(key)

    for src in first_list(dataset.get("source_health")):
        if isinstance(src, dict) and src.get("active") is False:
            events.append(_event("STALE_SOURCE", "INFO", f"Source inactive: {src.get('source')}.", "source_health"))
    for row in ticker_rows:
        if not row.get("flow_bias"):
            events.append(_event("MISSING_FIELD", "WARNING", "Ticker row missing flow bias.", "ticker_cycle", ticker=str(row.get("ticker") or "")))
    return events

