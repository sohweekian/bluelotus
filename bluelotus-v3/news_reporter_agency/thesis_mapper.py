from __future__ import annotations

import re
from typing import Dict, List


THESIS_KEYWORDS = {
    "TRUMP_UNCERTAINTY_THESIS": ["trump", "tariff", "white house", "election", "deal"],
    "PETRO_RECYCLED_DOLLAR_THESIS": ["oil", "crude", "opec", "hormuz", "energy", "petro"],
    "STICKY_INFLATION_THESIS": ["inflation", "cpi", "ppi", "prices", "wages"],
    "HAWKISH_WARSH_THESIS": ["warsh", "fed", "fomc", "powell", "rate", "yield"],
    "HAWKISH_BOJ_THESIS": ["boj", "bank of japan", "yen", "jgb"],
    "GOLD_SAFE_HAVEN_THESIS": ["gold", "gld", "gdx", "gdxj", "newmont", "anglogold", "safe haven"],
    "MIDDLE_EAST_WAR_THESIS": ["iran", "israel", "hizbollah", "hezbollah", "gaza", "hormuz", "middle east"],
    "AI_SEMIS_THESIS": ["nvidia", "nvda", "semiconductor", "chips", "ai", "tsmc", "amd"],
    "QUANTUM_THESIS": ["quantum", "ionq", "rigetti", "d-wave", "qbts", "qubt"],
    "SPACE_THESIS": ["spacex", "rocket", "satellite", "space", "asts", "rklb", "lunr"],
    "BANKS_DEFENSIVE_THESIS": ["bank", "banks", "wells fargo", "bank of america", "jpmorgan", "credit"],
}


ASSET_KEYWORDS = {
    "SPY": ["s&p", "stocks", "equities", "risk-on", "risk off"],
    "QQQ": ["nasdaq", "tech", "growth"],
    "VIX": ["volatility", "vix", "fear"],
    "UUP": ["dollar", "usd", "dxy"],
    "GLD": ["gold", "safe haven"],
    "GDX": ["gold miners", "miners", "newmont", "anglogold"],
    "USO": ["oil", "crude", "hormuz", "opec"],
    "TLT": ["treasury", "bonds", "yield", "rates"],
    "NVDA": ["nvidia", "nvda"],
    "AU": ["anglogold", "au"],
    "NEM": ["newmont", "nem"],
}


def map_theses(headline: str, summary: str = "") -> List[str]:
    text = f"{headline} {summary}".lower()
    linked = []
    for thesis, words in THESIS_KEYWORDS.items():
        if any(term_matches(text, w) for w in words):
            linked.append(thesis)
    return linked


def map_assets(headline: str, summary: str = "") -> List[str]:
    text = f"{headline} {summary}".lower()
    linked = []
    for asset, words in ASSET_KEYWORDS.items():
        if any(term_matches(text, w) for w in words):
            linked.append(asset)
    return linked


def term_matches(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if len(term) <= 3 or term.isupper():
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text
