from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Tuple


SOURCE_TIER_WEIGHTS = {
    1: 1.00,
    2: 0.85,
    3: 0.65,
    4: 0.40,
}


def shannon_entropy(weights: Iterable[float]) -> Tuple[float, float, int]:
    values = [float(w) for w in weights if w and float(w) > 0]
    k = len(values)
    if k <= 1:
        return 0.0, 0.0, k
    total = sum(values)
    entropy = -sum((v / total) * math.log2(v / total) for v in values)
    normalized = entropy / math.log2(k)
    return round(entropy, 6), round(normalized, 6), k


def classify_entropy(value: float) -> str:
    if value < 0.30:
        return "LOW_ENTROPY / CLEAN_SIGNAL"
    if value < 0.60:
        return "MODERATE_ENTROPY / MIXED_SIGNAL"
    return "HIGH_ENTROPY / NOISY_SIGNAL"


def _add(categories: Dict[str, float], name: str, weight: Any) -> None:
    try:
        value = float(weight)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        categories[name] = categories.get(name, 0.0) + value


def evidence_categories_for_ticker(
    sentiment: Dict[str, Any] | None = None,
    flow: Dict[str, Any] | None = None,
    catalyst: Dict[str, Any] | None = None,
    source_tier: int = 2,
) -> Dict[str, float]:
    categories: Dict[str, float] = {}
    sentiment = sentiment or {}
    flow = flow or {}
    catalyst = catalyst or {}

    clean = sentiment.get("clean_headline_count")
    dirty = sentiment.get("dirty_headline_count")
    _add(categories, "clean_headline", clean)
    _add(categories, "dirty_headline", dirty)

    label = str(sentiment.get("sentiment_label") or sentiment.get("label") or "").upper()
    score = sentiment.get("score", 0)
    if label == "BULLISH" or (isinstance(score, (int, float)) and score > 0.15):
        _add(categories, "bullish_sentiment", abs(float(score)) or 1.0)
    elif label == "BEARISH" or (isinstance(score, (int, float)) and score < -0.15):
        _add(categories, "bearish_sentiment", abs(float(score)) or 1.0)
    elif label:
        _add(categories, "neutral_sentiment", 1.0)

    bias = str(flow.get("institutional_bias") or flow.get("flow_bias") or "").upper()
    net = flow.get("main_net", flow.get("in_flow", 0))
    try:
        flow_weight = max(1.0, min(10.0, abs(float(net)) / 1_000_000.0))
    except (TypeError, ValueError):
        flow_weight = 1.0
    if bias in {"INFLOW", "ACCUMULATE"} or (isinstance(net, (int, float)) and net > 0):
        _add(categories, "institutional_inflow", flow_weight)
    elif bias in {"OUTFLOW", "DISTRIBUTE"} or (isinstance(net, (int, float)) and net < 0):
        _add(categories, "institutional_outflow", flow_weight)

    status = str(catalyst.get("status") or catalyst.get("confirmation_status") or "").upper()
    if status in {"CONFIRMED", "PASS", "ACTIVE"}:
        _add(categories, "catalyst_confirmed", 1.0)
    elif status:
        _add(categories, "catalyst_unconfirmed", 1.0)

    freshness = str(sentiment.get("freshness_status") or flow.get("freshness_status") or "").upper()
    if "STALE" in freshness:
        _add(categories, "source_stale", 1.0)
    elif freshness:
        _add(categories, "source_fresh", 1.0)

    tier_weight = SOURCE_TIER_WEIGHTS.get(int(source_tier or 2), 0.85)
    return {key: round(value * tier_weight, 6) for key, value in categories.items()}


def build_signal_entropy_record(
    ticker: str,
    old_label: str = "UNKNOWN",
    sentiment: Dict[str, Any] | None = None,
    flow: Dict[str, Any] | None = None,
    catalyst: Dict[str, Any] | None = None,
    source_tier: int = 2,
    governance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    categories = evidence_categories_for_ticker(sentiment, flow, catalyst, source_tier)
    raw, normalized, count = shannon_entropy(categories.values())
    clean_weight = categories.get("clean_headline", 0.0) + categories.get("source_fresh", 0.0)
    dirty_weight = categories.get("dirty_headline", 0.0) + categories.get("source_stale", 0.0)
    record = {
        "ticker": str(ticker).upper(),
        "old_label": old_label,
        "signal_entropy_raw": raw,
        "signal_entropy_normalized": normalized,
        "evidence_category_count": count,
        "evidence_categories": categories,
        "clean_signal_weight": round(clean_weight, 6),
        "dirty_signal_weight": round(dirty_weight, 6),
        "source_tier_weighted_entropy": normalized,
        "classification": classify_entropy(normalized),
    }
    if governance:
        record.update(governance)
    return record


def build_signal_entropy(dataset: Dict[str, Any], governance: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    sentiment_map = dataset.get("ticker_sentiment") if isinstance(dataset.get("ticker_sentiment"), dict) else {}
    flow_map = dataset.get("capital_flow") if isinstance(dataset.get("capital_flow"), dict) else {}
    positions = (dataset.get("portfolio") or {}).get("positions") if isinstance(dataset.get("portfolio"), dict) else {}
    tickers = sorted(set(sentiment_map.keys()) | set(flow_map.keys()) | set((positions or {}).keys()))
    records: List[Dict[str, Any]] = []
    for ticker in tickers:
        sentiment = sentiment_map.get(ticker) if isinstance(sentiment_map.get(ticker), dict) else {}
        flow = flow_map.get(ticker) if isinstance(flow_map.get(ticker), dict) else {}
        old_label = str(sentiment.get("sentiment_label") or sentiment.get("label") or flow.get("institutional_bias") or "UNKNOWN")
        records.append(build_signal_entropy_record(ticker, old_label, sentiment, flow, {}, 2, governance))
    return records
