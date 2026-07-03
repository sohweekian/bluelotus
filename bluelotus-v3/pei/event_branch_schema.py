from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class PEIBranch:
    branch_id: str
    event_id: str
    branch_name: str
    branch_description: str
    branch_probability: float
    branch_time_horizon: str
    evidence_for: List[str]
    evidence_against: List[str]
    confirmation_signals: List[str]
    contradiction_signals: List[str]
    kill_conditions: List[str]
    affected_sleeves: List[str]
    allowed_action: str
    blocked_action: str
    resolution_criteria: List[str]
    resolution_status: str = "PENDING"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
