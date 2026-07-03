from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from acms_cop.db.acms_db import get_connection, insert_row
from acms_cop.db.migrations import run_migrations
from acms_cop.common import json_dumps, parse_dt
from acms_cop.extractors.agent_extractor import extract_agent_cycles
from acms_cop.extractors.cycle_extractor import extract_cycle
from acms_cop.extractors.data_quality_extractor import extract_data_quality_events
from acms_cop.extractors.forecast_extractor import extract_forecasts
from acms_cop.extractors.theme_cycle_extractor import extract_theme_cycles
from acms_cop.extractors.ticker_cycle_extractor import extract_ticker_cycles
from acms_cop.reports.strategic_thinking_report import render_acms_cop_report
from acms_cop.reports.signal_edge_dashboard_renderer import build_shannon_thorp_refinement


TABLE_ORDER = [
    "acms_cycle",
    "acms_ticker_cycle",
    "acms_theme_cycle",
    "acms_forecast",
    "acms_agent_cycle",
    "acms_data_quality_event",
]

STR_TABLE_ORDER = [
    "acms_signal_entropy",
    "acms_source_capacity",
    "acms_cost_basis_reconciliation",
    "acms_kelly_sizing_advisory",
    "acms_hedge_ratio_review",
    "acms_str_cycle_summary",
]


def _common(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": row.get("run_id"),
        "cycle_timestamp": parse_dt(row.get("cycle_timestamp")),
        "dataset_timestamp": parse_dt(row.get("dataset_timestamp")),
        "report_binding_id": row.get("report_binding_id"),
        "governance_pack_id": row.get("governance_pack_id"),
        "execution_authority": row.get("execution_authority", "CIO_ONLY_MANUAL"),
        "order_routing_enabled": bool(row.get("order_routing_enabled", False)),
        "system_orders_generated": int(row.get("system_orders_generated") or 0),
    }


def extract_str_tables(dataset: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    str_data = dataset.get("shannon_thorp_refinement")
    if not isinstance(str_data, dict) or not str_data:
        str_data = build_shannon_thorp_refinement(dataset)

    entropy_rows = []
    for r in str_data.get("signal_entropy", []):
        entropy_rows.append({
            **_common(r),
            "ticker": r.get("ticker"),
            "old_label": r.get("old_label"),
            "signal_entropy_raw": r.get("signal_entropy_raw"),
            "signal_entropy_normalized": r.get("signal_entropy_normalized"),
            "evidence_category_count": r.get("evidence_category_count"),
            "clean_signal_weight": r.get("clean_signal_weight"),
            "dirty_signal_weight": r.get("dirty_signal_weight"),
            "source_tier_weighted_entropy": r.get("source_tier_weighted_entropy"),
            "classification": r.get("classification"),
            "evidence_categories_json": json_dumps(r.get("evidence_categories") or {}),
        })

    source_rows = []
    for r in str_data.get("source_capacity", []):
        source_rows.append({
            **_common(r),
            "source_name": r.get("source_name"),
            "source_tier": r.get("source_tier"),
            "signal_count": r.get("signal_count"),
            "confirmed_count": r.get("confirmed_count"),
            "contradicted_count": r.get("contradicted_count"),
            "unresolved_count": r.get("unresolved_count"),
            "estimated_mutual_information": r.get("estimated_mutual_information"),
            "estimated_channel_capacity": r.get("estimated_channel_capacity"),
            "capacity_confidence": r.get("capacity_confidence"),
            "tier_upgrade_candidate": bool(r.get("tier_upgrade_candidate", False)),
            "tier_downgrade_candidate": bool(r.get("tier_downgrade_candidate", False)),
            "status": r.get("status"),
        })

    cost_rows = []
    for r in str_data.get("cost_basis_reconciliation", []):
        cost_rows.append({
            **_common(r),
            "ticker": r.get("ticker"),
            "broker_unrealized": r.get("broker_unrealized"),
            "computed_unrealized": r.get("computed_unrealized"),
            "third_witness_unrealized": r.get("third_witness_unrealized"),
            "delta_broker_vs_computed": r.get("delta_broker_vs_computed"),
            "delta_broker_vs_third": r.get("delta_broker_vs_third"),
            "delta_computed_vs_third": r.get("delta_computed_vs_third"),
            "selected_source": r.get("selected_source"),
            "resolution_status": r.get("resolution_status"),
            "source_reliability_update": r.get("source_reliability_update"),
            "cio_review_required": bool(r.get("cio_review_required", True)),
        })

    kelly_rows = []
    for r in str_data.get("kelly_sizing_advisory", []):
        kelly_rows.append({
            **_common(r),
            "ticker": r.get("ticker"),
            "edge_estimate": r.get("edge_estimate"),
            "full_kelly_fraction": r.get("full_kelly_fraction"),
            "quarter_kelly_fraction": r.get("quarter_kelly_fraction"),
            "quarter_kelly_usd": r.get("quarter_kelly_usd"),
            "capped_advisory_size_usd": r.get("capped_advisory_size_usd"),
            "current_position_usd": r.get("current_position_usd"),
            "current_vs_advisory_delta": r.get("current_vs_advisory_delta"),
            "kelly_status": r.get("kelly_status"),
            "cio_override_required": bool(r.get("cio_override_required", True)),
        })

    hedge = str_data.get("hedge_ratio_review") if isinstance(str_data.get("hedge_ratio_review"), dict) else {}
    hedge_rows = [{
        **_common(str_data),
        "current_hedge_value": hedge.get("current_hedge_value"),
        "current_hedge_pct_of_market_value": hedge.get("current_hedge_pct_of_market_value"),
        "implied_full_hedge_value": hedge.get("implied_full_hedge_value"),
        "fractional_hedge_value": hedge.get("fractional_hedge_value"),
        "hedge_gap_usd": hedge.get("hedge_gap_usd"),
        "hedge_status": hedge.get("hedge_status"),
        "raw_review_json": json_dumps(hedge),
    }]

    summary = str_data.get("cycle_summary") if isinstance(str_data.get("cycle_summary"), dict) else {}
    summary_rows = [{
        **_common(str_data),
        "status": str_data.get("status"),
        "version": str_data.get("version"),
        "signal_entropy_count": summary.get("signal_entropy_count"),
        "source_capacity_count": summary.get("source_capacity_count"),
        "cost_basis_conflict_count": summary.get("cost_basis_conflict_count"),
        "kelly_advisory_count": summary.get("kelly_advisory_count"),
        "hedge_status": summary.get("hedge_status"),
        "brier_logging_status": str_data.get("brier_logging_status"),
    }]

    return {
        "acms_signal_entropy": entropy_rows,
        "acms_source_capacity": source_rows,
        "acms_cost_basis_reconciliation": cost_rows,
        "acms_kelly_sizing_advisory": kelly_rows,
        "acms_hedge_ratio_review": hedge_rows,
        "acms_str_cycle_summary": summary_rows,
    }


def load_dataset(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_payload(
    dataset_path: str | Path,
    workbook_path: str | Path,
    skip_forecast: bool = False,
    skip_agent: bool = False,
) -> Dict[str, Any]:
    dataset = load_dataset(dataset_path)
    cycle = extract_cycle(dataset, dataset_path)
    ticker_rows = extract_ticker_cycles(dataset, workbook_path)
    theme_rows = extract_theme_cycles(dataset, ticker_rows)
    forecast_rows = [] if skip_forecast else extract_forecasts(dataset)
    agent_rows = [] if skip_agent else extract_agent_cycles()
    dq_rows = extract_data_quality_events(cycle, ticker_rows, theme_rows, dataset)
    report = render_acms_cop_report(cycle, ticker_rows, theme_rows, forecast_rows, agent_rows, dq_rows)
    str_tables = extract_str_tables(dataset)
    return {
        "acms_cycle": [cycle],
        "acms_ticker_cycle": ticker_rows,
        "acms_theme_cycle": theme_rows,
        "acms_forecast": forecast_rows,
        "acms_agent_cycle": agent_rows,
        "acms_data_quality_event": dq_rows,
        **str_tables,
        "report_text": report,
    }


def payload_counts(payload: Dict[str, Any]) -> Dict[str, int]:
    return {table: len(payload.get(table, [])) for table in TABLE_ORDER + STR_TABLE_ORDER}


def insert_payload(database: str, payload: Dict[str, Any]) -> int:
    run_migrations(database)
    conn = get_connection(database=database)
    try:
        cursor = conn.cursor()
        cycle_rows = payload["acms_cycle"]
        if len(cycle_rows) != 1:
            raise ValueError("ACMS live insert requires exactly one cycle row.")
        cycle_id = insert_row(cursor, "acms_cycle", cycle_rows[0])
        inserted = 1
        for table in TABLE_ORDER[1:]:
            for row in payload.get(table, []):
                insert_row(cursor, table, {"cycle_id": cycle_id, **row})
                inserted += 1
        for table in STR_TABLE_ORDER:
            for row in payload.get(table, []):
                insert_row(cursor, table, row)
                inserted += 1
        conn.commit()
        cursor.close()
        return inserted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
