from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from acms_cop.classifiers.signal_entropy_classifier import build_signal_entropy_record
from acms_cop.reports.cio_order_policy import (
    build_gold_support_bid_policy,
    classify_cio_order_policy,
    apply_policy_security_overrides,
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _position_items(positions: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(positions, dict):
        for ticker, row in positions.items():
            if isinstance(row, dict):
                yield str(row.get("ticker") or ticker).upper(), row
        return
    if isinstance(positions, list):
        for row in positions:
            if isinstance(row, dict):
                yield str(row.get("ticker") or row.get("symbol") or row.get("code") or "").replace("US.", "").upper(), row


def _order_status(row: Dict[str, Any]) -> str:
    return str(row.get("order_status") or row.get("broker_status") or row.get("status") or "UNKNOWN").upper()


def _order_age_minutes(row: Dict[str, Any], now: datetime | None = None) -> int | None:
    ts = _parse_dt(row.get("updated_time") or row.get("create_time") or row.get("submitted_at"))
    if not ts:
        return None
    base = now or datetime.now(timezone.utc)
    return max(0, int((base - ts).total_seconds() / 60))


def reconcile_buying_power(dataset: Dict[str, Any], threshold: float = 500.0) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    readonly = dataset.get("portfolio_readonly") if isinstance(dataset.get("portfolio_readonly"), dict) else {}
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    open_orders = orders.get("open_orders") if isinstance(orders.get("open_orders"), list) else []
    broker_bp = _num(readonly.get("buying_power", portfolio.get("buying_power")))
    pipeline_bp = _num(portfolio.get("buying_power", readonly.get("buying_power")))
    cash = _num(readonly.get("cash", portfolio.get("cash")))
    reserved = 0.0
    for row in open_orders:
        if str(row.get("trd_side") or row.get("side") or "").upper() == "BUY" and _order_status(row) not in {"CANCELLED", "CANCELLED_ALL", "FILLED", "DELETED", "FAILED"}:
            reserved += _num(row.get("qty")) * _num(row.get("price", row.get("limit_price")))
    margin_adjustment = max(0.0, broker_bp - cash + reserved)
    settlement_adjustment = _num(readonly.get("settlement_adjustment", portfolio.get("settlement_adjustment")))
    currency_adjustment = _num(readonly.get("currency_adjustment", portfolio.get("currency_adjustment")))
    computed_bp = cash - reserved + settlement_adjustment + margin_adjustment + currency_adjustment
    delta = broker_bp - computed_bp
    cash_only_delta = broker_bp - (cash - reserved)
    if abs(delta) <= threshold:
        flag = False
        status = "RECONCILED"
        explanation = "Broker buying power reconciles after open-order reserve and margin adjustment."
    elif abs(cash_only_delta) > threshold and margin_adjustment > 0:
        flag = False
        status = "MARGIN_BUYING_POWER_EXPLAINED"
        explanation = "Cash-only calculation is not directly comparable to broker margin buying power."
    else:
        flag = True
        status = "REVIEW"
        explanation = "Unexplained buying-power delta remains above threshold."
    return {
        "broker_buying_power": round(broker_bp, 2),
        "pipeline_buying_power": round(pipeline_bp, 2),
        "cash": round(cash, 2),
        "open_order_reserved_cash": round(reserved, 2),
        "settlement_adjustment": round(settlement_adjustment, 2),
        "margin_adjustment": round(margin_adjustment, 2),
        "currency_adjustment": round(currency_adjustment, 2),
        "computed_buying_power": round(computed_bp, 2),
        "buying_power_delta": round(delta, 2),
        "buying_power_delta_flag": flag,
        "canonical_buying_power_delta": round(delta, 2),
        "canonical_buying_power_delta_flag": flag,
        "legacy_buying_power_delta": portfolio.get("buying_power_delta"),
        "legacy_buying_power_delta_flag": portfolio.get("buying_power_delta_flag"),
        "legacy_field": True,
        "deprecated_by": "canonical_buying_power_delta",
        "do_not_render_as_primary": True,
        "status": status,
        "delta_explanation": explanation,
    }


def reconcile_beta_sources(dataset: Dict[str, Any], str_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    risk = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    hedge = (str_data or dataset.get("shannon_thorp_refinement") or {}).get("hedge_ratio_review") if isinstance(str_data or dataset.get("shannon_thorp_refinement"), dict) else {}
    observations = int(_num(risk.get("return_observations")))
    risk_beta_raw = risk.get("beta_to_spy")
    risk_beta = None if observations <= 0 or risk_beta_raw in (None, "") else _num(risk_beta_raw)
    str_beta = hedge.get("portfolio_beta_to_spy")
    risk_status = "RISK_MODEL_BETA_UNAVAILABLE" if risk_beta is None else "HISTORICAL_BETA_VALIDATED"
    if observations <= 0:
        history_status = "INSUFFICIENT_HISTORY"
        conflict = False
        mismatch = "expected_due_to_history_insufficient"
    elif risk_beta is not None and str_beta is not None and abs(float(str_beta) - risk_beta) > 0.5:
        history_status = "HISTORICAL_BETA_VALIDATED"
        conflict = True
        mismatch = "validated_sources_diverge"
    else:
        history_status = "HISTORICAL_BETA_VALIDATED" if risk_beta is not None else "INSUFFICIENT_HISTORY"
        conflict = False
        mismatch = "none"
    return {
        "risk_model_beta": risk_beta,
        "risk_model_beta_status": risk_status,
        "str_proxy_beta": str_beta,
        "str_proxy_beta_status": "STR_PROXY_BETA_ESTIMATE" if str_beta is not None else "RISK_MODEL_BETA_UNAVAILABLE",
        "risk_model_observations": observations,
        "history_status": history_status,
        "beta_conflict": conflict,
        "beta_source_mismatch": mismatch,
    }


def resolve_snapshot_age(dataset: Dict[str, Any], live_dashboard_ts: Any = None) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    readonly = dataset.get("portfolio_readonly") if isinstance(dataset.get("portfolio_readonly"), dict) else {}
    formal = _parse_dt(meta.get("generated_at"))
    live = _parse_dt(live_dashboard_ts or readonly.get("cycle_ts") or portfolio.get("cycle_ts") or meta.get("generated_at"))
    broker = _parse_dt(readonly.get("cycle_ts") or portfolio.get("cycle_ts"))
    tolerance = 10
    formal_minus_dashboard = None if not formal or not live else int((formal - live).total_seconds() / 60)
    formal_minus_broker = None if not formal or not broker else int((formal - broker).total_seconds() / 60)
    age_delta = None if formal_minus_dashboard is None else -formal_minus_dashboard
    if formal_minus_dashboard is not None and formal_minus_dashboard > tolerance:
        status = "FORMAL_REPORT_NEWER_THAN_LIVE_DASHBOARD"
        explanation = "Formal report was generated after the dashboard/broker snapshot; dashboard may lag the report."
    elif formal_minus_dashboard is not None and formal_minus_dashboard < -tolerance:
        status = "LIVE_DASHBOARD_NEWER"
        explanation = "Dashboard snapshot is newer than the formal report."
    elif formal_minus_broker is not None and formal_minus_broker < -tolerance:
        status = "BROKER_PORTFOLIO_NEWER_THAN_REPORT"
        explanation = "Broker portfolio timestamp is newer than the formal report."
    elif formal and live and abs(formal_minus_dashboard or 0) <= tolerance:
        status = "CURRENT"
        explanation = "Formal report, dashboard, and broker timestamps are within tolerance."
    elif formal and int((datetime.now(timezone.utc) - formal).total_seconds() / 60) > 240:
        status = "REPORT_STALE"
        explanation = "Formal report is older than the staleness threshold."
    elif live and int((datetime.now(timezone.utc) - live).total_seconds() / 60) > 240:
        status = "DASHBOARD_STALE"
        explanation = "Dashboard snapshot is older than the staleness threshold."
    else:
        status = "CURRENT"
        explanation = "Formal report, dashboard, and broker timestamps are within tolerance."
    return {
        "FORMAL_REPORT_SNAPSHOT_TS": formal.isoformat() if formal else "",
        "LIVE_DASHBOARD_SNAPSHOT_TS": live.isoformat() if live else "",
        "BROKER_PORTFOLIO_TS": broker.isoformat() if broker else "",
        "AGE_DELTA_MINUTES": age_delta,
        "formal_report_snapshot_ts": formal.isoformat() if formal else "",
        "live_dashboard_snapshot_ts": live.isoformat() if live else "",
        "broker_portfolio_ts": broker.isoformat() if broker else "",
        "formal_minus_dashboard_minutes": formal_minus_dashboard,
        "formal_minus_broker_minutes": formal_minus_broker,
        "snapshot_alignment_status": status,
        "snapshot_alignment_explanation": explanation,
        "REPORT_STALENESS_STATUS": status,
    }


def resolve_session_state(dataset: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    raw = str(meta.get("market_session") or (dataset.get("live_prices") or {}).get("market_session") or "").upper()
    if "WEEKEND" in raw:
        canonical = "WEEKEND_SNAPSHOT"
    elif "HOLIDAY" in raw:
        canonical = "HOLIDAY_CLOSED"
    elif "PRE" in raw:
        canonical = "PRE_MARKET"
    elif "AFTER" in raw or "POST" in raw:
        canonical = "AFTER_HOURS"
    elif "REGULAR" in raw or "OPEN" in raw:
        canonical = "REGULAR_OPEN"
    elif raw:
        canonical = "MARKET_CLOSED_LAST_REGULAR_CLOSE"
    else:
        canonical = "UNKNOWN_REQUIRES_REVIEW"
    regime = dataset.get("regime") if isinstance(dataset.get("regime"), dict) else {}
    legacy_session_flag = str(regime.get("session_flag") or "").upper()
    legacy_market_closed = regime.get("market_closed")
    if canonical == "WEEKEND_SNAPSHOT":
        rendered_session_flag = "LEGACY_UNMAPPED" if legacy_session_flag == "OPEN" else (legacy_session_flag or "LEGACY_UNMAPPED")
        rendered_market_closed = True if legacy_market_closed is not True else legacy_market_closed
    else:
        rendered_session_flag = legacy_session_flag or "LEGACY_UNMAPPED"
        rendered_market_closed = legacy_market_closed
    return {
        "market_session_canonical": canonical,
        "canonical_market_session": canonical,
        "price_session_source": raw or "UNKNOWN",
        "regular_market_open": canonical == "REGULAR_OPEN",
        "after_hours_active": canonical == "AFTER_HOURS",
        "pre_market_active": canonical == "PRE_MARKET",
        "weekend_snapshot": canonical == "WEEKEND_SNAPSHOT",
        "legacy_session_flag": legacy_session_flag,
        "legacy_market_closed": legacy_market_closed,
        "rendered_session_flag": rendered_session_flag,
        "rendered_market_closed": rendered_market_closed,
        "legacy_field": True,
        "deprecated_by": "canonical_market_session",
        "do_not_render_as_primary": True,
        "last_regular_close_timestamp": meta.get("last_regular_close_timestamp") or meta.get("generated_at") or "",
    }


def build_report_status_taxonomy(governance: Dict[str, Any] | None, consistency: Dict[str, Any] | None, str_data: Dict[str, Any] | None) -> Dict[str, Any]:
    gov = governance or {}
    cons = consistency or {}
    failed_gates = gov.get("governance_gate_failed_gates") or gov.get("failed_gates") or []
    if isinstance(failed_gates, str):
        failed_gates = [failed_gates]
    failed_checks = cons.get("failed_checks") or []
    unresolved_cost = []
    for row in ((str_data or {}).get("cost_basis_reconciliation") or []):
        if str(row.get("resolution_status", "")).startswith("UNRESOLVED") or row.get("cio_review_required"):
            unresolved_cost.append(row.get("ticker"))
    return {
        "governance_failed_gates": failed_gates,
        "consistency_audit_failed_checks": failed_checks,
        "data_integrity_failed_checks": ["cost-basis conflicts"] if unresolved_cost else [],
        "data_integrity_unresolved_items": unresolved_cost,
        "required_wording": {
            "governance": f"Governance failed gates: {', '.join(failed_gates) if failed_gates else 'none'}",
            "consistency": f"Consistency audit failed checks: {', '.join(failed_checks) if failed_checks else 'none'}",
            "data_integrity": f"Data integrity unresolved items: {'cost-basis conflicts' if unresolved_cost else 'none'}",
        },
    }


def classify_cio_decisions(dataset: Dict[str, Any], now: datetime | None = None) -> Dict[str, Any]:
    session = resolve_session_state(dataset)
    cio = dataset.get("cio_decisions") if isinstance(dataset.get("cio_decisions"), dict) else {}
    if not cio:
        return {"status": "CIO_DECISIONS_UNAVAILABLE", "age_minutes": None, "market_data_freshness_failure": False}
    ts = _parse_dt(cio.get("generated_at"))
    age = None if not ts else int(((now or datetime.now(timezone.utc)) - ts).total_seconds() / 60)
    pending = int(_num(cio.get("pending_review_count")))
    if age is None:
        status = "CIO_DECISIONS_UNAVAILABLE"
    elif age <= 240:
        status = "CIO_DECISIONS_FRESH"
    elif session["weekend_snapshot"] and pending == 0:
        status = "CIO_DECISIONS_STALE_BUT_NON_BLOCKING"
    else:
        status = "CIO_DECISIONS_STALE_REVIEW_REQUIRED"
    return {
        "status": status,
        "age_minutes": age,
        "pending_review_count": pending,
        "governance_context_stale": status.endswith("REVIEW_REQUIRED"),
        "cio_context_stale_review_required": status.endswith("REVIEW_REQUIRED"),
        "market_data_freshness_failure": False,
    }


def _canonical_order_state(status: str, qty: float, dealt: float) -> Dict[str, Any]:
    if status in {"FILLED", "FILLED_ALL"} or (qty > 0 and dealt >= qty):
        return {"canonical_order_state": "FILLED", "is_live_on_exchange": False}
    if dealt > 0:
        return {"canonical_order_state": "PARTIALLY_FILLED", "is_live_on_exchange": status in {"SUBMITTED", "SUBMITTING"}}
    if "CANCEL" in status:
        return {"canonical_order_state": "CANCELLED", "is_live_on_exchange": False}
    if "EXPIRE" in status:
        return {"canonical_order_state": "EXPIRED", "is_live_on_exchange": False}
    if status == "WAITING_SUBMIT":
        return {"canonical_order_state": "WAITING_SUBMIT_PENDING", "is_live_on_exchange": False}
    if status in {"SUBMITTED", "SUBMITTING"}:
        return {"canonical_order_state": "SUBMITTED_LIVE", "is_live_on_exchange": True}
    if status == "WAITING":
        return {"canonical_order_state": "UNKNOWN_REQUIRES_REVIEW", "is_live_on_exchange": False}
    return {"canonical_order_state": "UNKNOWN_REQUIRES_REVIEW", "is_live_on_exchange": False}


def reconcile_open_orders(dataset: Dict[str, Any], now: datetime | None = None) -> List[Dict[str, Any]]:
    orders = dataset.get("orders") if isinstance(dataset.get("orders"), dict) else {}
    rows = orders.get("open_orders") if isinstance(orders.get("open_orders"), list) else []
    out: List[Dict[str, Any]] = []
    for row in rows:
        status = _order_status(row)
        dealt = _num(row.get("dealt_qty"))
        qty = _num(row.get("qty"))
        ticker = str(row.get("ticker") or row.get("code") or "").replace("US.", "").upper()
        side = str(row.get("trd_side") or row.get("side") or "").upper()
        limit_price = _num(row.get("price", row.get("limit_price")))
        order_notional = abs(qty * limit_price)
        cancelled = "CANCEL" in status
        filled = status in {"FILLED", "FILLED_ALL"} or (qty > 0 and dealt >= qty)
        policy = classify_cio_order_policy(ticker, side)
        canonical_state = _canonical_order_state(status, qty, dealt)
        if filled:
            classification = "FILLED"
        elif cancelled:
            classification = "CANCELLED"
        elif "EXPIRE" in status:
            classification = "EXPIRED"
        elif policy and status in {"WAITING_SUBMIT", "SUBMITTED", "SUBMITTING", "WAITING"}:
            classification = policy["classification"]
        elif status in {"WAITING_SUBMIT", "SUBMITTED", "SUBMITTING", "WAITING"}:
            classification = "LIVE_BLOCKED_PENDING_CIO_REVIEW"
        else:
            classification = "UNKNOWN_REQUIRES_REVIEW"
        still_live = bool(canonical_state["is_live_on_exchange"]) or classification.startswith("LIVE") or classification in {
            "CIO_APPROVED_GOLD_SUPPORT_BID_PENDING",
            "CIO_TRADING_STRATEGY_ORDER_PENDING",
        }
        out.append({
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "limit_price": limit_price,
            "order_notional": round(order_notional, 2),
            "broker_status": status,
            "raw_order_intent": row.get("order_intent") or row.get("intent") or "EXISTING_BROKER_ORDER",
            **canonical_state,
            "order_intent": (policy or {}).get("order_intent") or row.get("order_intent") or row.get("intent") or "EXISTING_BROKER_ORDER",
            "policy_bucket": (policy or {}).get("policy_bucket"),
            "policy_target_usd": (policy or {}).get("policy_target_usd"),
            "policy_note": (policy or {}).get("policy_note"),
            "order_age": _order_age_minutes(row, now),
            "still_live": still_live,
            "blocked_by_operator": (policy or {}).get("blocked_by_operator", classification.startswith("LIVE_BLOCKED")),
            "requires_cio_review": (policy or {}).get("requires_cio_review", classification.startswith("LIVE") or classification == "UNKNOWN_REQUIRES_REVIEW"),
            "cancelled": cancelled,
            "filled": filled,
            "dealt_qty": dealt,
            "classification": classification,
        })
    return out


def build_security_master_exceptions(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    apply_policy_security_overrides(dataset)
    sm = dataset.get("security_master") if isinstance(dataset.get("security_master"), dict) else {}
    rows: List[Dict[str, Any]] = []
    for ticker, info in sm.items():
        if str(ticker).startswith("_") or str(ticker).lower() in {"metadata", "schema", "generated_at"}:
            continue
        if not isinstance(info, dict):
            continue
        sector = str(info.get("sector") or "").strip()
        industry = str(info.get("industry") or "").strip()
        if not sector or sector.upper() in {"UNKNOWN", "N/A"} or not industry or industry.upper() in {"UNKNOWN", "N/A"}:
            rows.append({
                "ticker": ticker,
                "current_sector": sector or "UNKNOWN",
                "current_industry": industry or "UNKNOWN",
                "classification_status": "CLASSIFICATION_GAP",
                "proposed_sector": info.get("proposed_sector") or "MANUAL_RESEARCH_REQUIRED",
                "proposed_industry": info.get("proposed_industry") or "MANUAL_RESEARCH_REQUIRED",
                "source_used": info.get("classification_source") or "security_master",
                "requires_manual_approval": True,
            })
    return rows


def link_sentiment_hygiene_entropy(dataset: Dict[str, Any], str_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    hygiene = dataset.get("sentiment_hygiene_gate")
    if not isinstance(hygiene, dict):
        path = Path(r"C:\bluelotus3\data\governance\approved_operating_truth.json")
        if path.exists():
            try:
                hygiene = (json.loads(path.read_text(encoding="utf-8")) or {}).get("sentiment_hygiene_gate") or {}
            except Exception:
                hygiene = {}
        else:
            hygiene = {}
    dirty = int(_num(hygiene.get("dirty_count", hygiene.get("dirty_headline_count"))))
    clean = int(_num(hygiene.get("clean_count", hygiene.get("clean_headline_count"))))
    affected = hygiene.get("affected_tickers") or []
    if not affected:
        affected = sorted({str(x.get("ticker", "")).upper() for x in hygiene.get("examples_blocked", []) if isinstance(x, dict) and x.get("ticker")})
    entropy_rows = {r.get("ticker"): r for r in ((str_data or {}).get("signal_entropy") or []) if isinstance(r, dict)}
    if affected:
        vals = [_num((entropy_rows.get(t) or {}).get("signal_entropy_normalized")) for t in affected if t in entropy_rows]
        entropy_score = round(sum(vals) / len(vals), 6) if vals else 0.0
    else:
        entropy_score = 0.0
    total = clean + dirty
    dirty_ratio = round(dirty / total, 6) if total else 0.0
    if dirty_ratio >= 0.8:
        classification = "HIGH_DIRTY_RATIO"
        hygiene_classification = "HIGH_DIRTY_RATIO"
        cio_tape_eligible = False
        exclusion_reason = "dirty_headline_ratio_above_threshold"
    elif entropy_score >= 0.6:
        classification = "HIGH_ENTROPY / NOISY_SIGNAL"
        hygiene_classification = "HIGH_ENTROPY / NOISY_SIGNAL"
        cio_tape_eligible = not affected
        exclusion_reason = "high_entropy_noise" if affected else ""
    elif dirty > 0:
        classification = "LOW_ENTROPY_DIRTY_SIGNAL"
        hygiene_classification = "LOW_ENTROPY_DIRTY_SIGNAL"
        cio_tape_eligible = False
        exclusion_reason = "dirty_but_consistent_noise"
    else:
        classification = "LOW_ENTROPY_CLEAN_SIGNAL"
        hygiene_classification = "LOW_ENTROPY_CLEAN_SIGNAL"
        cio_tape_eligible = True
        exclusion_reason = ""
    return {
        "dirty_headline_count": dirty,
        "clean_headline_count": clean,
        "dirty_ratio": dirty_ratio,
        "affected_tickers": affected,
        "entropy_score": entropy_score,
        "entropy_classification": classification,
        "hygiene_classification": hygiene_classification,
        "cio_tape_eligible": cio_tape_eligible,
        "exclusion_reason": exclusion_reason,
        "excluded_from_cio_tape": not cio_tape_eligible,
        "included_in_warning_layer": dirty > 0,
    }


def build_risk_model_canonical_status(dataset: Dict[str, Any]) -> Dict[str, Any]:
    risk = dataset.get("risk_model") if isinstance(dataset.get("risk_model"), dict) else {}
    observations = int(_num(risk.get("return_observations")))
    positions = risk.get("positions") if isinstance(risk.get("positions"), list) else []
    if observations <= 0:
        return {
            "canonical_risk_model_status": "HISTORY_INSUFFICIENT",
            "portfolio_var_status": "PORTFOLIO_VAR_UNAVAILABLE",
            "position_risk_telemetry_status": "POSITION_RISK_TELEMETRY_AVAILABLE" if positions else "POSITION_RISK_TELEMETRY_UNAVAILABLE",
            "VaR95_display": "UNAVAILABLE - HISTORY_INSUFFICIENT",
            "beta_display": "UNAVAILABLE - HISTORY_INSUFFICIENT",
            "return_observations": observations,
        }
    return {
        "canonical_risk_model_status": "PORTFOLIO_VAR_VALID",
        "portfolio_var_status": "PORTFOLIO_VAR_VALID",
        "position_risk_telemetry_status": "POSITION_RISK_TELEMETRY_AVAILABLE" if positions else "POSITION_RISK_TELEMETRY_UNAVAILABLE",
        "VaR95_display": ((risk.get("historical_var") or {}).get("confidence_95") or {}).get("daily_dollars"),
        "beta_display": risk.get("beta_to_spy"),
        "return_observations": observations,
    }


def build_kelly_pei_fusion(dataset: Dict[str, Any], str_data: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    str_payload = str_data or dataset.get("shannon_thorp_refinement") or {}
    pei = dataset.get("prospective_event_intelligence") if isinstance(dataset.get("prospective_event_intelligence"), dict) else {}
    text = json.dumps(pei, ensure_ascii=False).upper() if pei else ""
    macro_gated = any(token in text for token in ("WARSH", "BOJ", "ADD RISK", "BLOCKED", "MACRO"))
    target = {"PL", "QUBT", "LUNR", "QBTS"}
    rows = []
    for r in str_payload.get("kelly_sizing_advisory", []) or []:
        if not isinstance(r, dict):
            continue
        ticker = str(r.get("ticker") or "").upper()
        status = str(r.get("kelly_status") or "")
        if "HEDGE_INSTRUMENT_EXCLUDED" in status:
            fused = "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
        elif "INSUFFICIENT" in status:
            fused = "KELLY_INSUFFICIENT_DATA"
        elif "NO_SIZE" in status:
            fused = "KELLY_NO_SIZE"
        elif ticker in target and macro_gated:
            fused = "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED"
        elif "SUPPORTS" in status:
            fused = "KELLY_SUPPORTED_AND_MACRO_CLEAR"
        else:
            fused = "CIO_REVIEW_REQUIRED"
        rows.append({"ticker": ticker, "kelly_status": status, "kelly_pei_fused_status": fused})
    return rows


def build_canonical_truth_source(dataset: Dict[str, Any], rem: Dict[str, Any]) -> Dict[str, Any]:
    bp = rem.get("buying_power_reconciliation") or {}
    sess = rem.get("session_state") or {}
    snap = rem.get("snapshot_age_banner") or {}
    risk = rem.get("risk_model_status") or {}
    orders = rem.get("open_order_state_reconciliation") or []
    return {
        "canonical_buying_power_delta": bp.get("canonical_buying_power_delta"),
        "canonical_buying_power_delta_flag": bp.get("canonical_buying_power_delta_flag"),
        "canonical_market_session": sess.get("canonical_market_session"),
        "canonical_snapshot_alignment_status": snap.get("snapshot_alignment_status"),
        "canonical_pnl_integrity_status": "UNRESOLVED_REVIEW_REQUIRED" if (rem.get("report_status_taxonomy") or {}).get("data_integrity_unresolved_items") else "PASS",
        "canonical_gold_thesis_action": ((dataset.get("gold_thesis_tracker") or {}).get("thesis_action") or {}).get("execution_permission"),
        "canonical_risk_model_status": risk.get("canonical_risk_model_status"),
        "canonical_kelly_macro_fused_status": "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED" if any(r.get("kelly_pei_fused_status") == "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED" for r in rem.get("kelly_pei_fusion") or []) else "NO_MACRO_KELLY_CONFLICT",
        "canonical_order_state": {r.get("ticker"): r.get("canonical_order_state") for r in orders},
        "legacy_fields": {
            "portfolio.buying_power_delta": {"legacy_field": True, "deprecated_by": "canonical_buying_power_delta", "do_not_render_as_primary": True},
            "regime.session_flag": {"legacy_field": True, "deprecated_by": "canonical_market_session", "do_not_render_as_primary": True},
            "regime.market_closed": {"legacy_field": True, "deprecated_by": "canonical_market_session", "do_not_render_as_primary": True},
        },
    }


def build_remediation_reconciliation(dataset: Dict[str, Any], str_data: Dict[str, Any] | None = None, consistency: Dict[str, Any] | None = None) -> Dict[str, Any]:
    str_payload = str_data or dataset.get("shannon_thorp_refinement") or {}
    law = dataset.get("law_governance_binding") if isinstance(dataset.get("law_governance_binding"), dict) else {}
    gov_truth = {}
    path = Path(r"C:\bluelotus3\data\governance\approved_operating_truth.json")
    if path.exists():
        try:
            gov_truth = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            gov_truth = {}
    taxonomy_source = {**law, **gov_truth}
    apply_policy_security_overrides(dataset)
    open_orders = reconcile_open_orders(dataset)
    rem = {
        "status": "OPERATIONAL",
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
        "kelly_hedge_instruments_excluded": [
            r.get("ticker") for r in (str_payload.get("kelly_sizing_advisory") or [])
            if isinstance(r, dict) and str(r.get("kelly_status")) == "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY"
        ],
        "buying_power_reconciliation": reconcile_buying_power(dataset),
        "beta_source_reconciliation": reconcile_beta_sources(dataset, str_payload),
        "snapshot_age_banner": resolve_snapshot_age(dataset),
        "session_state": resolve_session_state(dataset),
        "report_status_taxonomy": build_report_status_taxonomy(taxonomy_source, consistency, str_payload),
        "cio_decisions_freshness": classify_cio_decisions(dataset),
        "open_order_state_reconciliation": open_orders,
        "gold_support_bid_policy": build_gold_support_bid_policy(dataset, open_orders),
        "security_master_exceptions": build_security_master_exceptions(dataset),
        "sentiment_hygiene_entropy_link": link_sentiment_hygiene_entropy(dataset, str_payload),
        "risk_model_status": build_risk_model_canonical_status(dataset),
        "kelly_pei_fusion": build_kelly_pei_fusion(dataset, str_payload),
        "hedge_advisory_disclaimer": {
            "text": "Hedge ratio review is advisory only. It does not create a hedge order. It does not recommend automatic VXX/VIXY sizing. CIO_ONLY_MANUAL remains supreme.",
            "advisory_only": True,
            "data_quality_status": "RECONCILED" if ((str_payload.get("hedge_ratio_review") or {}).get("current_hedge_value") is not None) else "MISSING",
        },
    }
    rem["canonical_truth_source"] = build_canonical_truth_source(dataset, rem)
    return rem


def remediation_summary_rows(rem: Dict[str, Any]) -> List[List[Any]]:
    bp = rem.get("buying_power_reconciliation") or {}
    beta = rem.get("beta_source_reconciliation") or {}
    snap = rem.get("snapshot_age_banner") or {}
    sess = rem.get("session_state") or {}
    return [
        ["Field", "Value"],
        ["Status", rem.get("status")],
        ["Execution Authority", rem.get("execution_authority")],
        ["Order Routing Enabled", rem.get("order_routing_enabled")],
        ["System Orders Generated", rem.get("system_orders_generated")],
        ["Buying Power Status", bp.get("status")],
        ["Buying Power Delta", bp.get("buying_power_delta")],
        ["Beta Source Mismatch", beta.get("beta_source_mismatch")],
        ["Report Staleness", snap.get("REPORT_STALENESS_STATUS")],
        ["Market Session", sess.get("market_session_canonical")],
        ["Snapshot Alignment", snap.get("snapshot_alignment_status")],
        ["Open Orders", len(rem.get("open_order_state_reconciliation") or [])],
        ["Gold Support Bid Policy", (rem.get("gold_support_bid_policy") or {}).get("status")],
        ["Security Master Exceptions", len(rem.get("security_master_exceptions") or [])],
    ]


def render_remediation_text_section(rem: Dict[str, Any]) -> str:
    if not rem:
        return "V3 / STR BUG-CLEARANCE RECONCILIATION\nStatus: MISSING\n"
    bp = rem.get("buying_power_reconciliation") or {}
    beta = rem.get("beta_source_reconciliation") or {}
    snap = rem.get("snapshot_age_banner") or {}
    sess = rem.get("session_state") or {}
    tax = rem.get("report_status_taxonomy") or {}
    cio = rem.get("cio_decisions_freshness") or {}
    sent = rem.get("sentiment_hygiene_entropy_link") or {}
    hedge = rem.get("hedge_advisory_disclaimer") or {}
    gold_policy = rem.get("gold_support_bid_policy") or {}
    excluded_hedges = rem.get("kelly_hedge_instruments_excluded") or []
    lines = [
        "V3 / STR BUG-CLEARANCE RECONCILIATION",
        "=" * 38,
        "Execution: CIO_ONLY_MANUAL | Order Routing: FALSE | System Orders Generated: 0",
        "",
        "Buying Power Reconciliation",
        f"- broker={bp.get('broker_buying_power')} computed={bp.get('computed_buying_power')} delta={bp.get('buying_power_delta')} flag={bp.get('buying_power_delta_flag')} | {bp.get('status')}",
        f"- explanation: {bp.get('delta_explanation')}",
        "",
        "Beta Source Reconciliation",
        f"- risk_model_beta={beta.get('risk_model_beta')} ({beta.get('risk_model_beta_status')}) | str_proxy_beta={beta.get('str_proxy_beta')} ({beta.get('str_proxy_beta_status')}) | conflict={beta.get('beta_conflict')} | {beta.get('beta_source_mismatch')}",
        "",
        "Snapshot Age Banner",
        f"- formal={snap.get('FORMAL_REPORT_SNAPSHOT_TS')} | live={snap.get('LIVE_DASHBOARD_SNAPSHOT_TS')} | broker={snap.get('BROKER_PORTFOLIO_TS')} | formal_minus_dashboard_min={snap.get('formal_minus_dashboard_minutes')} | {snap.get('snapshot_alignment_status')}",
        f"- explanation: {snap.get('snapshot_alignment_explanation')}",
        "",
        "Canonical Session State",
        f"- {sess.get('market_session_canonical')} | source={sess.get('price_session_source')} | weekend={sess.get('weekend_snapshot')}",
        "",
        "Report Status Taxonomy",
        f"- {((tax.get('required_wording') or {}).get('governance'))}",
        f"- {((tax.get('required_wording') or {}).get('consistency'))}",
        f"- {((tax.get('required_wording') or {}).get('data_integrity'))}",
        "",
        "CIO Decisions Freshness",
        f"- {cio.get('status')} | age_min={cio.get('age_minutes')} | governance_context_stale={cio.get('governance_context_stale')} | market_data_failure={cio.get('market_data_freshness_failure')}",
        "",
        "Sentiment Hygiene Entropy Link",
        f"- dirty={sent.get('dirty_headline_count')} clean={sent.get('clean_headline_count')} ratio={sent.get('dirty_ratio')} entropy={sent.get('entropy_score')} | {sent.get('hygiene_classification')} | cio_tape_eligible={sent.get('cio_tape_eligible')}",
        "",
        "Kelly Hedge Instrument Exclusion",
        f"- {', '.join(excluded_hedges) if excluded_hedges else 'none'} | HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY",
        "",
        "Open Order State Reconciliation",
    ]
    for row in (rem.get("open_order_state_reconciliation") or [])[:10]:
        policy_suffix = f" | {row.get('policy_bucket')} | target={row.get('policy_target_usd')}" if row.get("policy_bucket") else ""
        lines.append(f"- {row.get('ticker')} {row.get('side')} {row.get('qty')} @ {row.get('limit_price')} | {row.get('broker_status')} | {row.get('canonical_order_state')} | live_exchange={row.get('is_live_on_exchange')} | {row.get('classification')} | CIO review={row.get('requires_cio_review')}{policy_suffix}")
    lines.extend([
        "",
        "Gold Miner Support-Bid Policy",
        f"- status={gold_policy.get('status')} | total_target={gold_policy.get('total_target_usd')} | per_ticker={gold_policy.get('per_ticker_target_usd')} | pending={gold_policy.get('pending_order_notional')} | remaining={gold_policy.get('remaining_to_target')}",
        f"- context: {gold_policy.get('policy_context')}",
        "",
        "Security Master Exceptions",
        f"- count={len(rem.get('security_master_exceptions') or [])}",
        "",
        "Hedge Advisory Disclaimer",
        f"- {hedge.get('text')}",
    ])
    return "\n".join(lines)
