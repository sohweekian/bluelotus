from __future__ import annotations

from typing import Any, Dict


GOLD_SUPPORT_BID_TICKERS = {"AU", "NEM", "AEM", "B"}
TRADING_STRATEGY_TICKERS = {"BKSY", "NVDA"}

GOLD_SUPPORT_TOTAL_TARGET_USD = 16000.0
GOLD_SUPPORT_PER_TICKER_TARGET_USD = 4000.0

GOLD_SUPPORT_BID_CLASSIFICATION = "CIO_APPROVED_GOLD_SUPPORT_BID_PENDING"
TRADING_STRATEGY_CLASSIFICATION = "CIO_TRADING_STRATEGY_ORDER_PENDING"

GOLD_MINER_SECURITY_PROFILE: Dict[str, Dict[str, str]] = {
    ticker: {
        "sector": "Basic Materials",
        "industry": "Gold",
        "classification_source": "cio_gold_support_bid_policy",
    }
    for ticker in GOLD_SUPPORT_BID_TICKERS
}

HEDGE_SECURITY_PROFILE: Dict[str, Dict[str, Any]] = {
    "VIXY": {
        "sector": "VOLATILITY",
        "industry": "VOLATILITY_ETP",
        "instrument_role": "HEDGE_INSTRUMENT",
        "equity_kelly_eligible": False,
        "classification_source": "cio_volatility_hedge_policy",
    }
}


def normalize_ticker(value: Any) -> str:
    return str(value or "").replace("US.", "").strip().upper()


def classify_cio_order_policy(ticker: Any, side: Any) -> Dict[str, Any] | None:
    ticker_norm = normalize_ticker(ticker)
    side_norm = str(side or "").strip().upper()
    if side_norm != "BUY":
        return None
    if ticker_norm in GOLD_SUPPORT_BID_TICKERS:
        return {
            "classification": GOLD_SUPPORT_BID_CLASSIFICATION,
            "order_intent": "GOLD_MINER_5D_SUPPORT_BID",
            "policy_bucket": "gold_miners",
            "policy_target_usd": GOLD_SUPPORT_PER_TICKER_TARGET_USD,
            "blocked_by_operator": False,
            "requires_cio_review": True,
            "policy_note": (
                "CIO-defined 5D support bid. Warsh-hawkish/gold-weakness context is "
                "entry logic, not automatic thesis invalidation."
            ),
        }
    if ticker_norm in TRADING_STRATEGY_TICKERS:
        return {
            "classification": TRADING_STRATEGY_CLASSIFICATION,
            "order_intent": "CIO_TRADING_STRATEGY_ORDER",
            "policy_bucket": "trading_strategy",
            "policy_target_usd": None,
            "blocked_by_operator": False,
            "requires_cio_review": True,
            "policy_note": "CIO-defined trading strategy order. Execution remains manual.",
        }
    return None


def apply_policy_security_overrides(dataset: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(dataset, dict):
        return {}
    sm = dataset.setdefault("security_master", {})
    if not isinstance(sm, dict):
        sm = {}
        dataset["security_master"] = sm
    for ticker, override in GOLD_MINER_SECURITY_PROFILE.items():
        row = sm.get(ticker)
        if not isinstance(row, dict):
            row = {"ticker": ticker}
            sm[ticker] = row
        if not row.get("sector") or str(row.get("sector")).upper() in {"UNKNOWN", "N/A"}:
            row["sector"] = override["sector"]
        if not row.get("industry") or str(row.get("industry")).upper() in {"UNKNOWN", "N/A"}:
            row["industry"] = override["industry"]
        row.setdefault("classification_source", override["classification_source"])
    for ticker, override in HEDGE_SECURITY_PROFILE.items():
        row = sm.get(ticker)
        if not isinstance(row, dict):
            row = {"ticker": ticker}
            sm[ticker] = row
        row.update(override)
    return sm


def build_gold_support_bid_policy(dataset: Dict[str, Any], open_order_rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), dict) else {}

    current_by_ticker: Dict[str, float] = {ticker: 0.0 for ticker in sorted(GOLD_SUPPORT_BID_TICKERS)}
    for ticker, row in positions.items():
        ticker_norm = normalize_ticker(ticker)
        if ticker_norm not in current_by_ticker or not isinstance(row, dict):
            continue
        current_by_ticker[ticker_norm] = float(row.get("market_val") or row.get("market_value") or row.get("value") or 0.0)

    pending_by_ticker: Dict[str, float] = {ticker: 0.0 for ticker in sorted(GOLD_SUPPORT_BID_TICKERS)}
    for row in open_order_rows:
        ticker = normalize_ticker(row.get("ticker"))
        if ticker in pending_by_ticker and row.get("classification") == GOLD_SUPPORT_BID_CLASSIFICATION:
            pending_by_ticker[ticker] += float(row.get("order_notional") or 0.0)

    rows = []
    for ticker in sorted(GOLD_SUPPORT_BID_TICKERS):
        current = current_by_ticker.get(ticker, 0.0)
        pending = pending_by_ticker.get(ticker, 0.0)
        committed = current + pending
        rows.append({
            "ticker": ticker,
            "target_usd": GOLD_SUPPORT_PER_TICKER_TARGET_USD,
            "current_market_value": round(current, 2),
            "pending_order_notional": round(pending, 2),
            "committed_value": round(committed, 2),
            "remaining_to_target": round(max(0.0, GOLD_SUPPORT_PER_TICKER_TARGET_USD - committed), 2),
            "policy": "5D_SUPPORT_BID_ONLY",
        })

    total_current = sum(current_by_ticker.values())
    total_pending = sum(pending_by_ticker.values())
    total_committed = total_current + total_pending
    return {
        "status": "ACTIVE",
        "tickers": sorted(GOLD_SUPPORT_BID_TICKERS),
        "total_target_usd": GOLD_SUPPORT_TOTAL_TARGET_USD,
        "per_ticker_target_usd": GOLD_SUPPORT_PER_TICKER_TARGET_USD,
        "current_market_value": round(total_current, 2),
        "pending_order_notional": round(total_pending, 2),
        "committed_value": round(total_committed, 2),
        "remaining_to_target": round(max(0.0, GOLD_SUPPORT_TOTAL_TARGET_USD - total_committed), 2),
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "policy_context": (
            "AU/NEM/AEM/B are CIO-defined gold-miner 5D support bids. "
            "Temporary miner weakness from hawkish-rate or peace-deal gold pressure is the support-bid setup."
        ),
        "rows": rows,
    }
