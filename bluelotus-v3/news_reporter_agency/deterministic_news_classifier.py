from __future__ import annotations

import re
from typing import Dict, List

from thesis_mapper import map_assets, map_theses


LABEL_RULES = {
    "RISK_ON_DEESCALATION": ["ceasefire", "stand down", "deal", "truce", "de-escalation", "reopen"],
    "RISK_OFF_ESCALATION": ["attack", "missile", "strike", "war", "invasion", "retaliation"],
    "OIL_SHOCK_RELIEF": ["hormuz reopen", "strait reopen", "oil falls", "crude falls", "supply restored"],
    "OIL_SHOCK_ESCALATION": ["hormuz", "oil spike", "crude spike", "tanker", "opec shock"],
    "SAFE_HAVEN_UNWIND": ["ceasefire", "deal", "risk-on", "gold falls", "safe haven unwind"],
    "SAFE_HAVEN_SURGE": ["gold jumps", "safe haven", "flight to safety", "war risk"],
    "FED_HAWKISH_SHOCK": ["fed hawkish", "rate hike", "higher for longer", "hot cpi"],
    "FED_DOVISH_RELIEF": ["fed dovish", "rate cut", "cool cpi", "inflation cools"],
    "BOJ_HAWKISH_SHOCK": ["boj", "yen", "jgb", "bank of japan", "rate hike"],
    "USD_STRENGTH_EVENT": ["dollar jumps", "usd rises", "dxy rises", "dollar strength"],
    "CHINA_POLICY_SHOCK": ["china stimulus", "pboc", "beijing policy", "china crackdown"],
    "PORTFOLIO_COMPANY_EVENT": ["nvidia", "newmont", "anglogold", "rocket lab", "asts", "d-wave", "ionq"],
    "PORTFOLIO_PROFIT_TAKING_WINDOW": ["ceasefire", "deal", "de-escalation", "relief rally"],
    "GEOPOLITICAL_DEESCALATION": ["ceasefire", "stand down", "peace", "deal", "truce", "de-escalation"],
    "GEOPOLITICAL_ESCALATION": ["attack", "strike", "war", "missile", "retaliation"],
    "MIDDLE_EAST_WAR_RISK": ["iran", "israel", "hizbollah", "hezbollah", "gaza"],
    "STRAIT_OF_HORMUZ_RISK": ["hormuz", "strait"],
}


P1_TERMS = ["war", "ceasefire", "fed surprise", "boj", "cpi shock", "banking stress", "crash", "hormuz", "missile", "attack"]
P2_TERMS = ["policy", "earnings", "analyst", "ceo", "keynote", "oil", "gold", "rates", "inflation", "nvidia", "china"]


def classify_event(event: Dict, threshold: float = 0.55) -> Dict:
    headline = str(event.get("headline") or "")
    summary = str(event.get("summary") or "")
    text = f"{headline} {summary}".lower()

    labels: List[str] = []
    for label, words in LABEL_RULES.items():
        if any(term_matches(text, w) for w in words):
            labels.append(label)

    theses = map_theses(headline, summary)
    assets = map_assets(headline, summary)

    market_score = min(1.0, 0.12 * len(labels) + 0.08 * len(theses) + 0.06 * len(assets))
    portfolio_score = min(1.0, 0.14 * len([a for a in assets if a not in {"SPY", "QQQ", "VIX", "UUP", "USO", "TLT"}]))

    if any(term_matches(text, term) for term in P1_TERMS) and market_score >= 0.45:
        priority = "P1"
    elif any(term_matches(text, term) for term in P2_TERMS) or market_score >= threshold:
        priority = "P2"
    else:
        priority = "P3"

    if event.get("freshness_status") != "FRESH":
        alert = False
        alert_reason = "outside_freshness_window_or_unverified"
    elif priority in {"P1", "P2"}:
        alert = True
        alert_reason = f"{priority}_within_freshness_window"
    else:
        alert = False
        alert_reason = "P3_context_only"

    event.update({
        "priority": priority,
        "event_labels": labels,
        "linked_theses": theses,
        "linked_assets": assets,
        "market_relevance_score": round(market_score, 4),
        "portfolio_relevance_score": round(portfolio_score, 4),
        "telegram_alert_required": alert,
        "telegram_alert_reason": alert_reason,
        "market_meaning": market_meaning(labels),
    })
    return event


def market_meaning(labels: List[str]) -> str:
    if "GEOPOLITICAL_DEESCALATION" in labels:
        return "Tactical risk-on bias possible; gold/oil safe-haven premium may fade. Verify with market prices."
    if "GEOPOLITICAL_ESCALATION" in labels or "MIDDLE_EAST_WAR_RISK" in labels:
        return "Risk-off impulse possible; watch oil, gold, VIX, USD, and high-beta drawdown."
    if "FED_HAWKISH_SHOCK" in labels or "BOJ_HAWKISH_SHOCK" in labels:
        return "Rates/liquidity shock risk. Verify Treasury, yen, dollar, and growth factors."
    if "FED_DOVISH_RELIEF" in labels:
        return "Rates relief possible. Verify equity breadth and long-duration assets."
    return "Market relevance detected. Manual CIO verification required before interpretation."


def term_matches(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if len(term) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text
