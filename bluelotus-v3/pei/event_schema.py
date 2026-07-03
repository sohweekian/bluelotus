from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


MINIMUM_EVENT_TYPES = {
    "FED_POLICY",
    "BOJ_POLICY",
    "YIELD_SHOCK",
    "YEN_CARRY_RISK",
    "GEOPOLITICAL_ESCALATION",
    "GEOPOLITICAL_DEESCALATION",
    "OIL_SHOCK",
    "CREDIT_STRESS",
    "LIQUIDITY_DRAIN",
    "IPO_LIQUIDITY_EVENT",
    "PRIVATE_MARKET_CAPITAL_ABSORPTION",
    "SPACE_SECTOR_EVENT",
    "QUANTUM_SECTOR_EVENT",
    "AI_CAPEX_EVENT",
    "EARNINGS_EVENT",
    "PORTFOLIO_CONCENTRATION_EVENT",
    "BROKER_PNL_INTEGRITY_EVENT",
}


@dataclass
class PEIEvent:
    event_id: str
    event_type: str
    event_title: str
    event_timestamp_sgt: str
    source_layer: str
    source_confidence: float
    affected_assets: List[str]
    affected_sleeves: List[str]
    governing_thesis: str
    initial_hypothesis: str
    scenario_branches: List[Dict[str, Any]] = field(default_factory=list)
    branch_probabilities: Dict[str, float] = field(default_factory=dict)
    confirmation_signals: List[str] = field(default_factory=list)
    contradiction_signals: List[str] = field(default_factory=list)
    kill_conditions: List[str] = field(default_factory=list)
    resolution_date: str = ""
    resolution_criteria: List[str] = field(default_factory=list)
    forecast_owner: str = "BlueLotus PEI"
    governance_pack_id: str = ""
    report_memory_binding_id: str = ""
    cio_only_manual_flag: bool = True
    event_status: str = "ACTIVE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
