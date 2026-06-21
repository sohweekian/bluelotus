from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def default_resolution_date(days: int = 5) -> str:
    return (datetime.now(ZoneInfo("Asia/Singapore")) + timedelta(days=days)).date().isoformat()


def resolution_rules_for_event(event_type: str) -> list[str]:
    rules = {
        "FED_POLICY": [
            "Yields, USD, QQQ, high beta, and volatility confirm or reject the Fed repricing branch.",
            "Resolution after five U.S. trading sessions or next major Fed communication.",
        ],
        "BOJ_POLICY": [
            "USD/JPY, EWJ/DXJ, VXX/UVXY, credit, and U.S. high beta confirm or reject yen-carry unwind.",
            "Resolution after five U.S. trading sessions or BOJ communication clarification.",
        ],
        "GEOPOLITICAL_DEESCALATION": [
            "Oil risk premium, VXX/VIXY, SPY/QQQ breadth, and credit confirm or reject relief rally survival.",
            "Resolution after five U.S. trading sessions or confirmed walk-back/escalation.",
        ],
        "PRIVATE_MARKET_CAPITAL_ABSORPTION": [
            "Public proxy recovers after absorption window while own catalysts remain intact.",
            "Resolution after five to ten trading sessions.",
        ],
    }
    return rules.get(event_type, [
        "Branch resolves when confirmation signals or kill conditions are observed.",
        "Resolution after five U.S. trading sessions unless the catalyst is invalidated earlier.",
    ])
