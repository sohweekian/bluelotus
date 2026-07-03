from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from acms_cop.reports.acms_summary_renderer import build_acms_summary
from acms_cop.reports.planning_dossier_renderer import render_planning_dossier


def _top_counter(rows: List[Dict[str, Any]], key: str, n: int = 8) -> str:
    counts = Counter(str(row.get(key) or "UNCLASSIFIED") for row in rows)
    if not counts:
        return "- None"
    return "\n".join(f"- {name}: {count}" for name, count in counts.most_common(n))


def render_acms_cop_report(
    cycle_row: Dict[str, Any],
    ticker_rows: List[Dict[str, Any]],
    theme_rows: List[Dict[str, Any]],
    forecast_rows: List[Dict[str, Any]],
    agent_rows: List[Dict[str, Any]],
    dq_rows: List[Dict[str, Any]],
) -> str:
    summary = build_acms_summary(cycle_row, ticker_rows, theme_rows, forecast_rows, agent_rows, dq_rows)
    flow_counts = Counter(str(row.get("flow_bias") or "UNKNOWN") for row in ticker_rows)
    portfolio_tickers = [r for r in ticker_rows if r.get("ticker") in {"VXX", "VIXY", "PL", "LUNR", "QBTS", "QUBT"}]
    theme_lines = [
        f"- {r.get('theme')}: {r.get('acms_state')} | {r.get('theme_direction')} | confidence {r.get('confidence')}"
        for r in theme_rows[:12]
    ]
    ticker_lines = [
        f"- {r.get('ticker')}: {r.get('acms_state')} | flow {r.get('flow_bias')} | price {r.get('price_direction')}"
        for r in portfolio_tickers[:12]
    ]
    forecast_lines = [
        f"- {round(float(r.get('forecast_probability') or 0) * 100, 1)}% / {r.get('horizon_sessions')} sessions: {r.get('forecast_question')} | outcome: {r.get('outcome_definition')}"
        for r in forecast_rows
    ]
    dq_lines = [
        f"- {r.get('severity')} {r.get('issue_type')}: {r.get('issue_description')}"
        for r in dq_rows[:20]
    ] or ["- No ACMS data-quality issues detected."]
    agent_lines = [
        f"- {r.get('agent_name')}: {r.get('recommendation')} | confidence {r.get('confidence')} | path {r.get('raw_output_path')}"
        for r in agent_rows[:12]
    ] or ["- No agent cycle rows available for this extraction."]

    ten_questions = [
        ("What is the market primarily afraid of?", "Regime and hedging signals still point to macro/event uncertainty rather than pure earnings risk."),
        ("What information is the market actively pricing?", "Capital flow, cross-market confirmation, event windows, and source-verified catalysts."),
        ("Which agent types are most active?", "Risk, macro, portfolio structure, data integrity, and thesis agents are accountable through acms_agent_cycle."),
        ("Are institutions accumulating or distributing?", ", ".join(f"{k}:{v}" for k, v in flow_counts.most_common())),
        ("Is the move causal or behavioral?", "Theme rows separate causal_status from price action so behavioral moves do not masquerade as confirmed catalysts."),
        ("Is strength short-covering or institutional sponsorship?", "ACMS states distinguish CLEAN_ACCUMULATION from SHORT_COVERING_RALLY and DISTRIBUTION_INTO_STRENGTH."),
        ("Is liquidity improving or only price improving?", "Execution gate requires credit calm, hedge demand cooling, and flow confirmation before scaling."),
        ("What would prove the thesis wrong?", "Failed execution safety, worsening P/L truth conflict, causal invalidation, or regime deterioration."),
        ("What would confirm the thesis?", "Causal confirmation plus flow confirmation plus regime and high-beta/banks confirmation."),
        ("What is the cost of waiting versus acting?", "Waiting preserves cash fortress and avoids false sponsorship; acting early risks chasing unconfirmed behavior."),
    ]

    return "\n".join([
        "ACMS-COP Strategic Thinking",
        "",
        "1. Dominant ACMS Market State",
        f"- Dominant state: {summary['dominant_acms_state']}",
        f"- Regime: {summary['regime_label']}",
        f"- CIO posture: {summary['cio_posture']}",
        "",
        "2. Seven-Layer Evidence Summary",
        f"- Dataset / cycle: {cycle_row.get('dataset_ts')}",
        f"- Regime score: {cycle_row.get('regime_score')}",
        f"- VIX: {cycle_row.get('vix')}",
        f"- Fear & Greed: {cycle_row.get('fear_greed')} {cycle_row.get('fear_greed_status')}",
        f"- Cash weight: {cycle_row.get('cash_weight')}",
        f"- Portfolio market value: {cycle_row.get('market_value')}",
        f"- Execution authority: {cycle_row.get('execution_authority')}",
        "",
        "3. Flow Collision Summary",
        _top_counter(ticker_rows, "flow_bias"),
        "",
        "4. Behavioral State by Theme",
        "\n".join(theme_lines) if theme_lines else "- No theme states available.",
        "",
        "5. Behavioral State by Portfolio Ticker",
        "\n".join(ticker_lines) if ticker_lines else "- No portfolio ticker states mapped.",
        "",
        "6. CIO Planning Dossier",
        render_planning_dossier(portfolio_tickers or ticker_rows[:6], cycle_row),
        "",
        "7. Execution Gate",
        f"- Second tranche: {cycle_row.get('second_tranche_status')}",
        f"- Scale-in: {cycle_row.get('scale_in_status')}",
        f"- Order routing enabled: {cycle_row.get('order_routing_enabled')}",
        f"- LLM order generation enabled: {cycle_row.get('llm_order_generation_enabled')}",
        f"- System generated orders: {cycle_row.get('system_generated_orders')}",
        "",
        "8. Forecasts Opened This Cycle",
        "\n".join(forecast_lines) if forecast_lines else "- Forecast generation skipped.",
        "",
        "9. Learning Records Pending",
        f"- Open forecasts pending outcome: {len(forecast_rows)}",
        f"- Agent accountability rows: {len(agent_rows)}",
        f"- Data-quality events: {len(dq_rows)}",
        "\n".join(dq_lines),
        "",
        "10 Strategic Questions",
        "\n".join(f"{idx}. {q}\n   {a}" for idx, (q, a) in enumerate(ten_questions, start=1)),
        "",
        "Agent Accountability",
        "\n".join(agent_lines),
        "",
        "Doctrine",
        "- CIO_ONLY_MANUAL remains the only execution authority.",
        "- ACMS-COP records planning, blocked actions, forecasts, decisions, outcomes, and learning memory.",
        "- ACMS-COP does not route, place, cancel, modify, or generate broker orders.",
    ])

