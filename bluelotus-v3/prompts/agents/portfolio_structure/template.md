# Portfolio Structure Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "portfolio_structure",
  "agent_name": "Portfolio Structure Agent",
  "agent_role": "Interpret concentration, cash, cluster exposure, HHI, largest position, and top exposures.",
  "model_used": "",
  "input_refs": {},
  "summary": "Portfolio structure: equity-only HHI <N> (<DIVERSIFIED|MODERATE|CONCENTRATED>), largest position <TICKER> at <N>% of invested capital, cash at <N>% — add-risk is <ALLOWED|BLOCKED|CONDITIONAL>.",
  "key_findings": [
    "[DATASET] concentration_hhi_equity_only = <value> (<DIVERSIFIED|MODERATE|CONCENTRATED>) — largest position <TICKER> is <pct>% of invested capital ($<value> equity deployed)",
    "[OPERATOR] concentration_risk verdict: <specific verdict> — <specific blocked or allowed action>",
    "[DATASET] PNL integrity: <N> conflict(s) detected — <ticker>: broker $<X> vs computed $<Y>, delta $<Z>"
  ],
  "risk_flags": [
    "P1 <if HHI_equity > 0.25 or cluster breach>: <TICKER> at <pct>% of equity capital exceeds concentration limit",
    "P2 <if PNL conflict exists>: <TICKER> BROKER_PNL_SOURCE_CONFLICT — delta $<N> — verify cost basis in moomoo",
    "P3 <if cash near floor>: Cash at <pct>% — within <N>% of cash floor mandate"
  ],
  "blocked_actions_observed": [
    "<specific blocked action from concentration_risk or portfolio_mandate operator>",
    "add-risk to <TICKER cluster> blocked — cluster at <pct>% vs <limit>% maximum"
  ],
  "allowed_actions_observed": [
    "<specific allowed action from operator — always append: CIO manual execution required>",
    "Deconcentration of <TICKER> — CIO manual review required"
  ],
  "affected_theses": ["WATCH theses affected by concentration constraints — see thesis lifecycle desk"],
  "affected_assets": [
    "<TICKER of largest position>",
    "<TICKER of second largest>",
    "<TICKER with PNL conflict if any>"
  ],
  "causal_completeness": "complete",
  "blind_spots": [
    "<specific field missing — e.g., 'avg_cost missing for LUNR — cannot compute PNL integrity'>",
    "<cluster definition missing from portfolio_constraints — cannot assess cluster limit>"
  ],
  "confidence": 0.9,
  "recommendation_to_chief_strategist": "MANUAL_REVIEW_REQUIRED",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- **ALWAYS use `concentration_hhi_equity_only`**, not `concentration_hhi_vs_total_aum`.
- **ALWAYS use `weight_vs_equity_capital`** for the largest position calculation.
- If `pnl_integrity_conflicts` list is non-empty, it must appear in both `key_findings` and `risk_flags`.
- `recommendation`: `MANUAL_REVIEW_REQUIRED` is the baseline. Use `REDUCE_RISK_REVIEW` if HHI_equity > 0.35. Use `RAISE_CASH_REVIEW` if cash is below floor.
- **CASH_FORTRESS_ACTIVE**: When cash >= 70% and CIO action is WAIT/HOLD/REVIEW, do NOT label cash level as a risk flag. Use `ℹ CASH_FORTRESS_ACTIVE — high cash is intentional under current CIO defensive posture` in `key_findings`. Do not put it in `risk_flags`.
- **EQUITY_SLEEVE_CONCENTRATION_ONLY**: When a position has high `weight_vs_equity_capital` but low `weight_vs_total_aum` (< 5%), use this label in `key_findings` with a note. Only add to `risk_flags` (P1/P2) if `weight_vs_total_aum` also exceeds the fund-level threshold.
- **cash_fortress_mode operator**: Check `relevant_operators.cash_fortress_mode.metrics` for `cash_fortress_mode`, `scout_mode`, `second_tranche_blocked` flags. Use these to suppress inappropriate risk escalation.
- **Wording priority**: `CASH_FORTRESS_ACTIVE` > `CASH_WEIGHT_HIGH`. If cash fortress is active, the word "WARNING" must not appear in relation to cash level.
