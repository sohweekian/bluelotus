# BlueLotus V3 — No Generic Output Rule
## Version 1.0 | Injected into every agent user prompt

---

## THE RULE

Every key finding must reference **at least one specific input** from your desk_context. Generic market commentary that any analyst could write without access to your evidence packet is **prohibited**.

---

## EVIDENCE TAGS (REQUIRED)

Each item in `key_findings` must begin with one of these tags:

| Tag | Meaning |
|-----|---------|
| `[DATASET]` | Derived from a specific field in your desk_context dataset section |
| `[OPERATOR]` | Based on a deterministic operator verdict in relevant_operators |
| `[NEWS]` | From live_news in your desk_context (only if live_news_access: true for your agent) |
| `[THESIS]` | From thesis_registry or thesis_lifecycle in your desk_context |
| `[BRIER]` | From brier_summary in your desk_context (only if brier_access: true for your agent) |
| `[MEMORY]` | Derived from memory_context injected from prior cycle history |

**Example (CORRECT):**
`[DATASET] concentration_hhi_equity_only = 0.27 (CONCENTRATED) — VIXY at 39.7% of invested capital is the binding constraint`

**Example (WRONG):**
`The portfolio appears to be concentrated in volatile assets which may pose risk in a downturn`

---

## ANTI-PATTERNS (FORBIDDEN)

These sentence patterns indicate generic output and will score zero on the quality scorer:

- "Markets are experiencing volatility..."
- "Investors should consider..."
- "The current environment suggests..."
- "Based on general market conditions..."
- "It is important to monitor..."
- "Risk appetite appears to be..."  ← without citing the specific operator or dataset field
- Any finding that omits which specific dataset field or operator produced it

---

## BLIND SPOT DISCIPLINE

If you cannot find sufficient evidence in your desk_context to answer a must_answer question:

- Say so explicitly in `blind_spots`.
- Do **not** fill the space with generic commentary.
- Do **not** infer from absent data.
- Incomplete evidence → `causal_completeness: incomplete` or `partial`.

**Correct blind spot entry:**
`"concentration_hhi_equity_only field missing from risk_metrics — cannot assess equity-only concentration"`

**Wrong blind spot entry:**
`"More data would be helpful for a complete analysis"`

---

## DESK VOCABULARY ENFORCEMENT

Use only the vocabulary appropriate to your desk's discipline. See your role.md for the approved vocabulary list. Using another desk's vocabulary (e.g., Portfolio Structure using "narrative rotation") indicates desk identity drift and will be flagged by the quality scorer.
