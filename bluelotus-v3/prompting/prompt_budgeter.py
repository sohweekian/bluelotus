"""
BlueLotus V3 — Prompt Budgeter
================================
Enforces the 5-layer prompt budget policy to prevent context overflow.

BUDGET ALLOCATION (% of max_response_chars from env):
  Layer 1  Doctrine (constitution + safety + no-generic + json-only)   10%
  Layer 2  Agent charter (role.md + template.md)                       15%
  Layer 3  Current context (desk_context + memory_context)             50%
  Layer 4  Memory injection                                            15%
  Layer 5  Output schema hint                                          10%

ANTI-HARDCODE RULE:
  - All percentage allocations are defined here as module constants.
  - The total budget ceiling comes from LLM_MAX_RESPONSE_CHARS env var.
  - PromptBudgeter validates and warns but does NOT truncate Layer 1 or 2
    (doctrine and role are sacred — never truncated).
  - Layer 3 (desk_context) is the main compression target.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Budget Allocation Constants (% of total prompt budget)
# ---------------------------------------------------------------------------

BUDGET_DOCTRINE_PCT = 0.10      # constitution + safety + no-generic + json-only
BUDGET_AGENT_CHARTER_PCT = 0.15  # role.md + template.md
BUDGET_DESK_CONTEXT_PCT = 0.50  # desk_context (dataset fields + operators)
BUDGET_MEMORY_PCT = 0.15        # memory_context from MemoryRetriever
BUDGET_OUTPUT_SCHEMA_PCT = 0.10  # JSON schema hint in user prompt

# Minimum floor for desk_context — never compress below this
DESK_CONTEXT_MIN_CHARS = 2000

# Default total chars if env var not set
DEFAULT_TOTAL_BUDGET_CHARS = 12000


@dataclass
class PromptBudget:
    """Represents the character budget allocations for one agent prompt."""
    total: int
    doctrine: int
    agent_charter: int
    desk_context: int
    memory: int
    output_schema: int
    warnings: list = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_budget_chars": self.total,
            "doctrine_chars": self.doctrine,
            "agent_charter_chars": self.agent_charter,
            "desk_context_chars": self.desk_context,
            "memory_chars": self.memory,
            "output_schema_chars": self.output_schema,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

class PromptBudgeter:
    """
    Validates and allocates character budgets for each prompt layer.
    Use one instance per prompt build cycle.
    """

    def __init__(self, total_budget_chars: Optional[int] = None) -> None:
        if total_budget_chars is not None:
            self.total = total_budget_chars
        else:
            env_val = os.getenv("LLM_MAX_RESPONSE_CHARS")
            self.total = int(env_val) if env_val and env_val.isdigit() else DEFAULT_TOTAL_BUDGET_CHARS

    def allocate(self) -> PromptBudget:
        """Compute budget allocations from total."""
        return PromptBudget(
            total=self.total,
            doctrine=int(self.total * BUDGET_DOCTRINE_PCT),
            agent_charter=int(self.total * BUDGET_AGENT_CHARTER_PCT),
            desk_context=max(int(self.total * BUDGET_DESK_CONTEXT_PCT), DESK_CONTEXT_MIN_CHARS),
            memory=int(self.total * BUDGET_MEMORY_PCT),
            output_schema=int(self.total * BUDGET_OUTPUT_SCHEMA_PCT),
        )

    def validate_layers(
        self,
        budget: PromptBudget,
        doctrine_chars: int,
        agent_charter_chars: int,
        desk_context_chars: int,
        memory_chars: int,
    ) -> PromptBudget:
        """
        Validates actual layer sizes against budget allocations.
        Adds warnings to budget.warnings for overruns.
        Layer 1 (doctrine) and Layer 2 (agent charter) overruns are warnings only —
        content is NEVER truncated.
        Layer 3 (desk_context) overrun triggers compression recommendation.
        Layer 4 (memory) overrun triggers memory trim recommendation.
        """
        warnings = list(budget.warnings)

        if doctrine_chars > budget.doctrine:
            overrun_pct = (doctrine_chars - budget.doctrine) / budget.doctrine * 100
            warnings.append(
                f"DOCTRINE_OVERRUN: {doctrine_chars} chars vs budget {budget.doctrine} "
                f"(+{overrun_pct:.0f}%) — doctrine is sacred, NOT truncated"
            )

        if agent_charter_chars > budget.agent_charter:
            overrun_pct = (agent_charter_chars - budget.agent_charter) / budget.agent_charter * 100
            warnings.append(
                f"CHARTER_OVERRUN: {agent_charter_chars} chars vs budget {budget.agent_charter} "
                f"(+{overrun_pct:.0f}%) — role.md is sacred, NOT truncated"
            )

        if desk_context_chars > budget.desk_context:
            overrun_pct = (desk_context_chars - budget.desk_context) / budget.desk_context * 100
            warnings.append(
                f"CONTEXT_OVERRUN: {desk_context_chars} chars vs budget {budget.desk_context} "
                f"(+{overrun_pct:.0f}%) — context_builder should compress per-field budgets"
            )

        if memory_chars > budget.memory:
            overrun_pct = (memory_chars - budget.memory) / budget.memory * 100
            warnings.append(
                f"MEMORY_OVERRUN: {memory_chars} chars vs budget {budget.memory} "
                f"(+{overrun_pct:.0f}%) — memory_retriever should trim oldest entries"
            )

        total_actual = doctrine_chars + agent_charter_chars + desk_context_chars + memory_chars
        if total_actual > budget.total:
            warnings.append(
                f"TOTAL_OVERRUN: {total_actual} chars vs total budget {budget.total} — "
                f"primary compression target is desk_context"
            )

        return PromptBudget(
            total=budget.total,
            doctrine=budget.doctrine,
            agent_charter=budget.agent_charter,
            desk_context=budget.desk_context,
            memory=budget.memory,
            output_schema=budget.output_schema,
            warnings=warnings,
        )

    def measure_text(self, text: str) -> int:
        """Return character count of a text block."""
        return len(text)

    def measure_json(self, value: Any) -> int:
        """Return character count of a JSON-serialised value."""
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
