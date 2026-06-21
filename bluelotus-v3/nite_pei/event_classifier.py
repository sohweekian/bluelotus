"""
BlueLotus V3 — NITE-PEI Sub-Engine E1: Event Classifier
=========================================================
Classifies incoming news events against the NITE-PEI event taxonomy.
No LLM — purely deterministic keyword matching.

Returns event_class and noise_discount_factor based on source tier.
Unknown events return event_class="UNKNOWN" and LR=1.0 (no thesis update).

GOVERNANCE: Advisory only. No order generation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Source-tier noise discount factors
# ---------------------------------------------------------------------------

_TIER_DISCOUNT: Dict[int, float] = {
    1: 0.00,   # T1 — CME FedWatch, FOMC minutes, primary feeds (no discount)
    2: 0.10,   # T2 — major financial news (10% discount)
    3: 0.25,   # T3 — secondary sources (25% discount)
    4: 0.50,   # T4 — noise tier, e.g. Zerohedge (50% discount)
}

# ---------------------------------------------------------------------------
# Event taxonomy keyword mapping
# Each event class maps to a list of keyword sets.
# A headline matches if ANY keyword in ANY set appears (case-insensitive).
# ---------------------------------------------------------------------------

_TAXONOMY: Dict[str, List[str]] = {
    # Monetary Policy
    "CENTRAL_BANK_HAWKISH": [
        "rate hike", "hikes rate", "raised rate", "hawkish", "quantitative tightening",
        "qt acceleration", "tighter policy", "restrictive policy", "hold rates higher",
        "higher for longer", "warsh", "bowman", "waller", "inflation fight", "50bp", "75bp",
        "fomc hawkish", "fed hawkish", "boj hike", "bank of japan hike",
        "rate increase", "rates higher", "fed speaker", "fomc speaker",
    ],
    "CENTRAL_BANK_DOVISH": [
        "rate cut", "cuts rate", "lowered rate", "dovish", "pivot", "quantitative easing",
        "qe", "easing policy", "rate reduction", "accommodative", "25bp cut",
        "boj cut", "bank of japan cut",
    ],
    "CENTRAL_BANK_NEUTRAL": [
        "holds rates", "no change", "rate unchanged", "steady rate", "pause",
        "on hold", "rates unchanged", "fomc hold", "boj hold", "bank of japan hold",
    ],
    "YEN_CARRY_RISK": [
        "yen carry", "carry unwind", "carry trade unwind", "usd/jpy", "usdjpy",
        "yen strengthens", "yen surges", "sharp yen", "boj surprise",
        "carry trade", "yen spike", "yen rally", "yen crisis",
    ],

    # Geopolitical
    "GEOPOLITICAL_ESCALATION": [
        "military action", "airstrike", "missile", "war", "invasion", "attack",
        "sanctions imposed", "blockade", "troops deployed", "conflict escalat",
        "hormuz", "strait close", "supply route threat", "embargo",
        "iran closes", "nuclear talks snag", "talks collapse", "nuclear deal fails",
        "strait of hormuz", "oil supply disruption", "middle east escalat",
    ],
    "GEOPOLITICAL_DEESCALATION": [
        "ceasefire", "peace deal", "mou signed", "diplomatic resolution",
        "de-escalation", "deescalation", "withdrawal", "truce", "peace talks",
        "hormuz mou", "iran deal", "sanctions lifted", "nuclear agreement",
        "talks progress", "deal framework", "iran nuclear deal",
    ],
    "SANCTIONS_NEW": [
        "new sanctions", "sanctions announced", "sanctioned", "export ban",
        "trade restriction", "blacklist",
    ],

    # Corporate / Sector
    "EARNINGS_BEAT_MATERIAL": [
        "earnings beat", "eps beat", "profit beat", "beat estimate", "beats estimate",
        "guidance raised", "raised guidance", "raised outlook", "above consensus",
        "blowout quarter",
    ],
    "EARNINGS_MISS_MATERIAL": [
        "earnings miss", "eps miss", "profit miss", "missed estimate", "misses estimate",
        "guidance cut", "guidance lowered", "lowered outlook", "below consensus",
        "disappointing quarter",
    ],
    "SECTOR_CONTRACT_WIN": [
        "contract awarded", "contract won", "wins contract", "awarded contract",
        "government contract", "nasa contract", "dod contract", "pentagon contract",
        "deal signed", "agreement signed",
    ],
    "SECTOR_CONTRACT_LOSS": [
        "contract lost", "contract cancelled", "loses contract", "contract terminated",
        "bid rejected", "lost award",
    ],
    "REFLEXIVE_SUPPRESSION": [
        "private placement", "secondary offering", "capital raise", "equity raise",
        "dilution", "spacex raise", "private round", "series funding",
        "spac deal", "ipo priced",
    ],

    # Macro / Inflation
    "INFLATION_ABOVE_EXPECTATION": [
        "cpi above", "inflation above", "hotter than expected", "core inflation rises",
        "pce above", "inflation surges", "price pressure", "above forecast",
        "beats inflation", "inflation beat",
    ],
    "INFLATION_BELOW_EXPECTATION": [
        "cpi below", "inflation below", "cooler than expected", "inflation falls",
        "pce below", "disinflation", "deflation", "below forecast",
        "inflation miss", "prices cool",
    ],
    "RECESSION_SIGNAL": [
        "inverted yield curve", "gdp contraction", "gdp shrinks", "pmi collapse",
        "recession", "economic contraction", "negative growth", "job losses surge",
        "layoffs surge", "credit stress",
    ],
    "LIQUIDITY_EXPANSION": [
        "fed repo", "tga drawdown", "liquidity injection", "balance sheet expansion",
        "global easing", "central bank stimulus", "qe program", "asset purchase",
    ],
    "YEN_CARRY_RISK": [
        "yen carry", "carry-trade unwind", "carry trade unwind", "usd/jpy pressure",
        "yen strengthens", "yen strengthening", "boj hike", "boj hawkish",
        "japanese yen rally", "yen funding", "carry unwind",
    ],

    # Space / Technology
    "LAUNCH_SUCCESS": [
        "launch success", "successful launch", "orbit achieved", "mission success",
        "rocket launch", "starship success", "falcon success", "orbital milestone",
        "payload deployed",
    ],
    "LAUNCH_FAILURE": [
        "launch failure", "launch anomaly", "rocket failure", "vehicle loss",
        "mission failure", "launch aborted", "explosion", "rud",
    ],
    "REGULATORY_APPROVAL": [
        "faa approval", "fcc approval", "dod approval", "sec approved",
        "permit granted", "license granted", "regulatory cleared", "approval granted",
        "greenlit",
    ],
    "REGULATORY_REJECTION": [
        "faa denied", "permit denied", "grounded", "license revoked",
        "regulatory rejection", "blocked by", "approval denied", "rejected application",
    ],

    # Quantum / Emerging Tech
    "QUANTUM_MILESTONE": [
        "quantum milestone", "qubit record", "error rate reduction", "quantum supremacy",
        "quantum advantage", "fault tolerant", "logical qubit", "quantum breakthrough",
    ],
    "QUANTUM_COMPETITOR_ADVANCE": [
        "ibm quantum", "google quantum", "microsoft quantum", "rival quantum",
        "competitor quantum", "quantum competitor",
    ],
}

# Reverse index: keyword → event_class (built once at import time)
_KEYWORD_INDEX: Dict[str, str] = {}
for _ec, _keywords in _TAXONOMY.items():
    for _kw in _keywords:
        _KEYWORD_INDEX[_kw.lower()] = _ec


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def classify_event(
    headline: str,
    ticker_tags: List[str],
    source_tier: int = 2,
) -> Dict[str, Any]:
    """
    Classify a news headline into a NITE-PEI event class.

    Args:
        headline:    Raw headline text.
        ticker_tags: Tickers mentioned / tagged with this event.
        source_tier: Source quality tier (1–4). Affects noise_discount_factor.

    Returns dict with:
        event_class           — matched class or "UNKNOWN"
        affected_tickers      — ticker_tags passed through
        source_tier           — as provided
        noise_discount_factor — 0.0 (T1) to 0.50 (T4)
        matched_keyword       — keyword that triggered the match (or None)
    """
    headline_lower = headline.lower()
    matched_class = "UNKNOWN"
    matched_keyword = None

    for keyword, event_class in _KEYWORD_INDEX.items():
        if keyword_matches(headline_lower, keyword):
            matched_class = event_class
            matched_keyword = keyword
            break

    tier = parse_source_tier(source_tier)
    noise_discount_factor = _TIER_DISCOUNT.get(tier, 0.10)

    return {
        "event_class": matched_class,
        "affected_tickers": [str(t).upper() for t in ticker_tags],
        "source_tier": tier,
        "noise_discount_factor": noise_discount_factor,
        "matched_keyword": matched_keyword,
        "manual_execution_required": True,
        "llm_order_generation": False,
    }


def known_event_classes() -> List[str]:
    """Return all defined event class names."""
    return list(_TAXONOMY.keys())


def parse_source_tier(source_tier: Any) -> int:
    """
    Parse source tier from int or string forms.

    Accepts 1..4, "1".."4", and "T1".."T4".
    Unknown values default to T3 so unrecognized provenance is treated
    conservatively instead of promoted to a major-source default.
    """
    if isinstance(source_tier, int) and source_tier in _TIER_DISCOUNT:
        return source_tier
    text = str(source_tier).strip().upper()
    if text.startswith("T"):
        text = text[1:]
    try:
        tier = int(text)
    except ValueError:
        return 3
    return tier if tier in _TIER_DISCOUNT else 3


def keyword_matches(text: str, keyword: str) -> bool:
    """Return True when keyword appears as a phrase, not as an accidental substring."""
    key = keyword.lower().strip()
    if not key:
        return False
    # Some taxonomy entries are deliberate stems.
    if key.endswith(("escalat", "accelerat")):
        return key in text
    pattern = r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None
