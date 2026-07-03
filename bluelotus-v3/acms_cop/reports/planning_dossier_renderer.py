from __future__ import annotations

from typing import Any, Dict, Iterable, List


def render_planning_dossier(ticker_rows: Iterable[Dict[str, Any]], cycle_row: Dict[str, Any], limit: int = 12) -> str:
    rows = list(ticker_rows)[:limit]
    if not rows:
        return "NO ACTION / HOLD / REVIEW\n- No candidate actions available."
    lines: List[str] = []
    permission = cycle_row.get("scale_in_status") or "BLOCKED"
    for row in rows:
        blocked = row.get("blocked_actions_json") or "[]"
        lines.extend([
            f"- Ticker: {row.get('ticker')}",
            f"  Theme: {row.get('theme') or 'UNMAPPED'}",
            f"  Intended action: HOLD / REVIEW",
            f"  ACMS state: {row.get('acms_state')}",
            f"  Thesis reference: {row.get('cio_meaning')}",
            "  Trigger condition: causal confirmation + flow confirmation + regime confirmation",
            "  Kill condition: execution safety fail or P/L truth conflict worsens",
            "  Max position size: CIO manual sizing only",
            f"  Cash impact: constrained by cash fortress mode = {cycle_row.get('cash_fortress_mode')}",
            "  Hedge impact: preserve hedge book until confirmation gates clear",
            f"  Current permission: {permission}",
            f"  Blocked reason: {blocked}",
            "  Review window: next V3 cycle",
            "  Mistake risk: chasing price without causal sponsorship",
        ])
    return "\n".join(lines)

