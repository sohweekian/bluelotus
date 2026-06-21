"""
BlueLotus V3 — Agent Quality Scorer
=====================================
Scores each agent report on a 10-dimension rubric (0–10 each, max 100).

SCORING DIMENSIONS:
  D1  Evidence Tagging          — key_findings start with valid evidence tags
  D2  No Generic Output         — findings reference specific dataset fields
  D3  Desk Identity             — vocabulary appropriate to desk mandate
  D4  Must-Answer Coverage      — all must_answer questions addressed
  D5  Causal Completeness       — causal chain logic is present and labelled
  D6  Blind Spot Honesty        — blind spots cite specific missing fields
  D7  Risk Flag Priority        — risk_flags start with P1/P2/P3
  D8  Schema Compliance         — all required fields present, correct types
  D9  Confidence Calibration    — confidence level appropriate to evidence
  D10 Governance Compliance     — manual_execution=true, llm_order=false, no order language

USAGE:
    from quality.agent_quality_scorer import score_agent_report, QualityReport

    report = json.loads(agent_output)
    quality = score_agent_report(agent_id, report, agent_config)
    print(quality.total_score)          # 0–100
    print(quality.grade)                # A/B/C/D/F
    print(quality.dimension_scores)     # dict of D1–D10 scores

ANTI-HARDCODE RULE:
  - Desk vocabulary lists come from agent_registry.yaml via caller.
    No hardcoded desk vocabulary in this module — caller provides
    approved_vocabulary list from agent_config.
  - All threshold values are module constants at the top of each
    dimension function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Result Data Classes
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    dimension: str
    label: str
    score: float          # 0.0 – 10.0
    max_score: float = 10.0
    notes: List[str] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score else 0.0


@dataclass
class QualityReport:
    agent_id: str
    cycle_id: str
    dimension_scores: Dict[str, DimensionScore] = field(default_factory=dict)

    @property
    def total_score(self) -> float:
        return sum(d.score for d in self.dimension_scores.values())

    @property
    def max_total_score(self) -> float:
        return sum(d.max_score for d in self.dimension_scores.values())

    @property
    def pct_score(self) -> float:
        return (self.total_score / self.max_total_score * 100) if self.max_total_score else 0.0

    @property
    def grade(self) -> str:
        pct = self.pct_score
        if pct >= 90:
            return "A"
        if pct >= 80:
            return "B"
        if pct >= 70:
            return "C"
        if pct >= 60:
            return "D"
        return "F"

    @property
    def pass_fail(self) -> str:
        return "PASS" if self.pct_score >= 70 else "FAIL"

    def summary(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "cycle_id": self.cycle_id,
            "total_score": round(self.total_score, 2),
            "max_total_score": self.max_total_score,
            "pct_score": round(self.pct_score, 1),
            "grade": self.grade,
            "pass_fail": self.pass_fail,
            "dimension_scores": {
                k: {
                    "score": round(v.score, 2),
                    "max": v.max_score,
                    "pct": round(v.pct, 1),
                    "notes": v.notes,
                }
                for k, v in self.dimension_scores.items()
            },
        }


# ---------------------------------------------------------------------------
# Evidence Tag Constants
# ---------------------------------------------------------------------------

VALID_EVIDENCE_TAGS = {"[DATASET]", "[OPERATOR]", "[NEWS]", "[THESIS]", "[BRIER]", "[MEMORY]"}

VALID_RISK_PRIORITY_PREFIXES = {"P1", "P2", "P3"}

VALID_RECOMMENDATION_ENUM = {
    "WAIT", "HOLD", "REVIEW", "MANUAL_REVIEW_REQUIRED",
    "CIO_VERIFICATION_REQUIRED", "RISK_REVIEW_REQUIRED",
    "THESIS_REVIEW_REQUIRED", "REDUCE_RISK_REVIEW",
    "RAISE_CASH_REVIEW", "HEDGE_REVIEW",
}

VALID_CAUSAL_COMPLETENESS = {"complete", "partial", "incomplete"}

# Forbidden order language — these patterns require execution context, not bare financial words.
# "sell put trade" / "buy-side" / "options sell" are analysis vocabulary and must not trigger.
# Only catch: explicit share counts, explicit position disposal commands, order routing.
FORBIDDEN_ORDER_LANGUAGE = [
    # buy/sell + quantity (e.g. "buy 100 shares", "sell 500 contracts")
    r"\b(?:buy|sell)\s+\d+\s*(?:shares?|contracts?|units?|lots?)",
    # buy/sell + all/entire position (e.g. "sell all positions", "sell the entire position")
    r"\b(?:buy|sell)\s+(?:all|the\s+(?:entire|full|remaining))\s+(?:my\s+)?(?:position|holdings?|shares?|stake)",
    # "sell the position" / "buy the position" with no qualifier
    r"\b(?:buy|sell)\s+(?:the\s+)?position\b",
    # execute + order/trade/transaction
    r"\bexecute\s+(?:the\s+)?(?:order|trade|transaction)\b",
    # enter/exit + position (not "enter data" or "exit strategy")
    r"\benter\s+(?:a\s+)?(?:long|short|the)\s+position\b",
    r"\bexit\s+(?:the\s+)?(?:position|trade)\b",
    # explicit order routing terms (already specific enough)
    r"\bopen order\b", r"\bclose order\b",
    r"\bbroker\b.*\border\b", r"\bplace an order\b", r"\broute to\b",
    r"\bsubmit order\b", r"\bfill at\b",
]

# Generic output anti-patterns — any of these = likely generic finding
GENERIC_PATTERNS = [
    r"markets are (experiencing|facing|showing)",
    r"investors should consider",
    r"the current environment suggests",
    r"based on general market conditions",
    r"it is important to monitor",
    r"overall market conditions",
    r"market participants",
]

# Required schema fields
REQUIRED_SCHEMA_FIELDS = {
    "schema_version", "cycle_id", "agent_id", "agent_name", "agent_role",
    "summary", "key_findings", "risk_flags", "blocked_actions_observed",
    "allowed_actions_observed", "affected_theses", "affected_assets",
    "causal_completeness", "blind_spots", "confidence",
    "recommendation_to_chief_strategist", "requires_cio_attention",
    "manual_execution_required", "llm_order_generation",
}


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def score_agent_report(
    agent_id: str,
    report: Dict[str, Any],
    agent_config: Optional[Dict[str, Any]] = None,
) -> QualityReport:
    """
    Score a single agent report on all 10 dimensions.

    Args:
        agent_id: Agent identifier
        report: Parsed agent report dict
        agent_config: Agent config from agent_registry.yaml (optional but improves scoring)

    Returns:
        QualityReport with scores and notes per dimension
    """
    cycle_id = str(report.get("cycle_id", "unknown"))
    quality = QualityReport(agent_id=agent_id, cycle_id=cycle_id)

    quality.dimension_scores["D1"] = _score_d1_evidence_tagging(report)
    quality.dimension_scores["D2"] = _score_d2_no_generic_output(report)
    quality.dimension_scores["D3"] = _score_d3_desk_identity(report, agent_config)
    quality.dimension_scores["D4"] = _score_d4_must_answer(report, agent_config)
    quality.dimension_scores["D5"] = _score_d5_causal_completeness(report)
    quality.dimension_scores["D6"] = _score_d6_blind_spot_honesty(report)
    quality.dimension_scores["D7"] = _score_d7_risk_flag_priority(report)
    quality.dimension_scores["D8"] = _score_d8_schema_compliance(report)
    quality.dimension_scores["D9"] = _score_d9_confidence_calibration(report)
    quality.dimension_scores["D10"] = _score_d10_governance_compliance(report)

    return quality


def score_multiple_reports(
    reports: List[Dict[str, Any]],
    agent_configs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, QualityReport]:
    """
    Score a list of agent reports from one cycle.
    Returns dict of {agent_id: QualityReport}.
    """
    results: Dict[str, QualityReport] = {}
    for report in reports:
        agent_id = str(report.get("agent_id", "unknown"))
        config = (agent_configs or {}).get(agent_id)
        results[agent_id] = score_agent_report(agent_id, report, config)
    return results


# ---------------------------------------------------------------------------
# D1 — Evidence Tagging
# ---------------------------------------------------------------------------

def _score_d1_evidence_tagging(report: Dict[str, Any]) -> DimensionScore:
    """Each key_finding must start with a valid [TAG]. Max 10."""
    key_findings: List[str] = report.get("key_findings", [])
    if not key_findings:
        return DimensionScore("D1", "Evidence Tagging", 0.0, notes=["key_findings is empty"])

    tagged = 0
    untagged_items = []
    for finding in key_findings:
        text = str(finding).strip()
        has_tag = any(text.startswith(tag) for tag in VALID_EVIDENCE_TAGS)
        if has_tag:
            tagged += 1
        else:
            untagged_items.append(text[:60])

    score = (tagged / len(key_findings)) * 10.0
    notes = [f"Tagged {tagged}/{len(key_findings)} findings"]
    if untagged_items:
        notes.append(f"Untagged: {untagged_items}")
    return DimensionScore("D1", "Evidence Tagging", score, notes=notes)


# ---------------------------------------------------------------------------
# D2 — No Generic Output
# ---------------------------------------------------------------------------

def _score_d2_no_generic_output(report: Dict[str, Any]) -> DimensionScore:
    """No generic market commentary patterns. Max 10."""
    all_text = _collect_text_fields(report)
    generic_hits = []
    for pattern in GENERIC_PATTERNS:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        if matches:
            generic_hits.extend(matches)

    if not generic_hits:
        return DimensionScore("D2", "No Generic Output", 10.0, notes=["No generic patterns detected"])

    # Each generic pattern hit deducts 2 points, min 0
    deduction = min(len(generic_hits) * 2.5, 10.0)
    score = max(10.0 - deduction, 0.0)
    notes = [f"{len(generic_hits)} generic pattern(s) detected: {generic_hits[:3]}"]
    return DimensionScore("D2", "No Generic Output", score, notes=notes)


# ---------------------------------------------------------------------------
# D3 — Desk Identity
# ---------------------------------------------------------------------------

def _score_d3_desk_identity(
    report: Dict[str, Any],
    agent_config: Optional[Dict[str, Any]],
) -> DimensionScore:
    """
    Report uses vocabulary appropriate to desk mandate.
    Currently assessed via absence of other desks' exclusive vocabulary.
    Full scoring requires agent_config with distinctive_behavior field.
    """
    if not agent_config:
        return DimensionScore("D3", "Desk Identity", 7.0, notes=["No agent_config — partial scoring only"])

    agent_id = str(report.get("agent_id", ""))
    summary = str(report.get("summary", ""))

    # Check that summary mentions the desk's lens
    distinctive = str(agent_config.get("distinctive_behavior", "")).lower()
    desk_vocabulary_words = _extract_vocabulary_words(distinctive)

    all_text = _collect_text_fields(report).lower()
    matched = [w for w in desk_vocabulary_words if w in all_text]
    coverage = len(matched) / max(len(desk_vocabulary_words), 1)

    score = 5.0 + (coverage * 5.0)  # 5–10 based on vocabulary coverage
    notes = [f"Desk vocabulary coverage: {len(matched)}/{len(desk_vocabulary_words)} words found"]

    # Penalise if summary doesn't reference the desk's specific lens
    agent_role = str(agent_config.get("agent_role", "")).lower()
    role_words = [w for w in agent_role.split() if len(w) > 4]
    role_in_summary = any(w in summary.lower() for w in role_words)
    if not role_in_summary:
        score = max(score - 2.0, 0.0)
        notes.append("summary does not reference this desk's specific lens")

    return DimensionScore("D3", "Desk Identity", min(score, 10.0), notes=notes)


def _extract_vocabulary_words(distinctive_text: str) -> List[str]:
    """Extract key vocabulary words from distinctive_behavior field."""
    words = re.findall(r'\b[a-z]{4,}\b', distinctive_text.lower())
    # Remove common stop words
    stop = {"your", "this", "that", "with", "from", "have", "been", "they", "will", "also"}
    return [w for w in set(words) if w not in stop]


# ---------------------------------------------------------------------------
# D4 — Must-Answer Coverage
# ---------------------------------------------------------------------------

def _score_d4_must_answer(
    report: Dict[str, Any],
    agent_config: Optional[Dict[str, Any]],
) -> DimensionScore:
    """All must_answer questions should be addressed in key_findings or blind_spots."""
    if not agent_config:
        return DimensionScore("D4", "Must-Answer Coverage", 7.0, notes=["No agent_config — cannot verify must_answer"])

    must_answer: List[str] = agent_config.get("must_answer", [])
    if not must_answer:
        return DimensionScore("D4", "Must-Answer Coverage", 10.0, notes=["No must_answer questions defined"])

    all_text = _collect_text_fields(report).lower()

    answered = 0
    unanswered_questions: List[str] = []
    for question in must_answer:
        # Extract key terms from the question (5+ chars, meaningful words)
        key_terms = [w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', question)]
        # A question is "answered" if 2+ of its key terms appear in the report
        matches = sum(1 for t in key_terms if t in all_text)
        if matches >= max(len(key_terms) // 2, 2):
            answered += 1
        else:
            unanswered_questions.append(question)

    score = (answered / len(must_answer)) * 10.0
    notes = [f"Must-answer coverage: {answered}/{len(must_answer)} questions addressed"]
    if unanswered_questions:
        notes.append(f"Potentially unaddressed: {unanswered_questions[:2]}")
    return DimensionScore("D4", "Must-Answer Coverage", score, notes=notes)


# ---------------------------------------------------------------------------
# D5 — Causal Completeness
# ---------------------------------------------------------------------------

def _score_d5_causal_completeness(report: Dict[str, Any]) -> DimensionScore:
    """causal_completeness field correct, and causal chains present in key_findings."""
    causal = str(report.get("causal_completeness", "")).lower()
    notes = []

    if causal not in VALID_CAUSAL_COMPLETENESS:
        return DimensionScore("D5", "Causal Completeness", 0.0,
                              notes=[f"Invalid causal_completeness value: '{causal}'"])

    # Base score from field value
    base_scores = {"complete": 7.0, "partial": 5.0, "incomplete": 3.0}
    score = base_scores[causal]
    notes.append(f"causal_completeness declared: {causal}")

    # Bonus points for causal language in key_findings
    causal_language = ["because", "due to", "which", "causes", "leads to", "results in",
                       "signals", "indicates", "confirms", "contradicts"]
    findings_text = " ".join(str(f) for f in report.get("key_findings", []))
    causal_words_found = sum(1 for w in causal_language if w in findings_text.lower())

    if causal == "complete" and causal_words_found >= 2:
        score = min(score + 3.0, 10.0)
        notes.append(f"Causal language present ({causal_words_found} indicators)")
    elif causal == "complete" and causal_words_found < 1:
        score = max(score - 2.0, 0.0)
        notes.append("causal_completeness=complete but no causal language found in findings")

    return DimensionScore("D5", "Causal Completeness", score, notes=notes)


# ---------------------------------------------------------------------------
# D6 — Blind Spot Honesty
# ---------------------------------------------------------------------------

def _score_d6_blind_spot_honesty(report: Dict[str, Any]) -> DimensionScore:
    """Blind spots cite specific missing fields, not vague gaps."""
    blind_spots: List[str] = report.get("blind_spots", [])
    notes = []

    if not blind_spots:
        # No blind spots declared — acceptable if causal_completeness is complete
        causal = str(report.get("causal_completeness", "")).lower()
        if causal == "complete":
            return DimensionScore("D6", "Blind Spot Honesty", 9.0,
                                  notes=["No blind spots declared with causal_completeness=complete"])
        else:
            return DimensionScore("D6", "Blind Spot Honesty", 5.0,
                                  notes=["No blind spots declared but causal_completeness is not complete"])

    vague_patterns = [
        r"more data", r"additional information", r"further analysis",
        r"would be helpful", r"could be improved", r"is needed",
    ]
    specific_patterns = [
        r"field.*missing", r"not in.*context", r"not available", r"null",
        r"cannot.*assess", r"missing from", r"\w+_\w+.*missing",
    ]

    vague_count = 0
    specific_count = 0
    for spot in blind_spots:
        text = str(spot).lower()
        if any(re.search(p, text) for p in vague_patterns):
            vague_count += 1
        if any(re.search(p, text) for p in specific_patterns):
            specific_count += 1

    total = len(blind_spots)
    specificity_ratio = specific_count / total if total else 0.0
    score = 5.0 + (specificity_ratio * 5.0) - (vague_count * 1.0)
    score = max(min(score, 10.0), 0.0)
    notes.append(f"{specific_count}/{total} blind spots are specific; {vague_count} are vague")
    return DimensionScore("D6", "Blind Spot Honesty", score, notes=notes)


# ---------------------------------------------------------------------------
# D7 — Risk Flag Priority
# ---------------------------------------------------------------------------

def _score_d7_risk_flag_priority(report: Dict[str, Any]) -> DimensionScore:
    """Each risk_flag must start with P1, P2, or P3."""
    risk_flags: List[str] = report.get("risk_flags", [])
    if not risk_flags:
        return DimensionScore("D7", "Risk Flag Priority", 5.0,
                              notes=["No risk_flags — acceptable if no risks identified"])

    prioritised = 0
    unprioritised = []
    for flag in risk_flags:
        text = str(flag).strip()
        has_priority = any(text.startswith(p) for p in VALID_RISK_PRIORITY_PREFIXES)
        if has_priority:
            prioritised += 1
        else:
            unprioritised.append(text[:60])

    score = (prioritised / len(risk_flags)) * 10.0
    notes = [f"Prioritised {prioritised}/{len(risk_flags)} risk flags"]
    if unprioritised:
        notes.append(f"Unprioritised: {unprioritised}")
    return DimensionScore("D7", "Risk Flag Priority", score, notes=notes)


# ---------------------------------------------------------------------------
# D8 — Schema Compliance
# ---------------------------------------------------------------------------

def _score_d8_schema_compliance(report: Dict[str, Any]) -> DimensionScore:
    """All required fields present with correct types."""
    missing = REQUIRED_SCHEMA_FIELDS - set(report.keys())
    notes = []

    if missing:
        # Each missing required field costs points
        deduction = min(len(missing) * 2.0, 10.0)
        score = max(10.0 - deduction, 0.0)
        notes.append(f"Missing required fields: {sorted(missing)}")
    else:
        score = 10.0
        notes.append("All required fields present")

    # Type checks
    type_errors = []
    if not isinstance(report.get("confidence"), (int, float)):
        type_errors.append("confidence must be number")
    if report.get("manual_execution_required") is not True:
        type_errors.append("manual_execution_required must be true")
    if report.get("llm_order_generation") is not False:
        type_errors.append("llm_order_generation must be false")
    if not isinstance(report.get("key_findings"), list):
        type_errors.append("key_findings must be array")
    if not isinstance(report.get("risk_flags"), list):
        type_errors.append("risk_flags must be array")

    if type_errors:
        score = max(score - (len(type_errors) * 1.5), 0.0)
        notes.extend(type_errors)

    # Array length checks
    if len(report.get("key_findings", [])) > 3:
        score = max(score - 2.0, 0.0)
        notes.append(f"key_findings has {len(report['key_findings'])} items — max is 3")
    if len(report.get("risk_flags", [])) > 3:
        score = max(score - 2.0, 0.0)
        notes.append(f"risk_flags has {len(report['risk_flags'])} items — max is 3")
    if len(report.get("affected_assets", [])) > 3:
        score = max(score - 1.0, 0.0)
        notes.append(f"affected_assets has {len(report['affected_assets'])} items — max is 3")

    # Recommendation enum check
    rec = str(report.get("recommendation_to_chief_strategist", ""))
    if rec not in VALID_RECOMMENDATION_ENUM:
        score = max(score - 2.0, 0.0)
        notes.append(f"Invalid recommendation: '{rec}'")

    return DimensionScore("D8", "Schema Compliance", max(min(score, 10.0), 0.0), notes=notes)


# ---------------------------------------------------------------------------
# D9 — Confidence Calibration
# ---------------------------------------------------------------------------

def _score_d9_confidence_calibration(report: Dict[str, Any]) -> DimensionScore:
    """Confidence level appropriate to evidence quality and completeness."""
    confidence = report.get("confidence")
    causal = str(report.get("causal_completeness", "")).lower()
    blind_spots: List[str] = report.get("blind_spots", [])
    notes = []

    if not isinstance(confidence, (int, float)):
        return DimensionScore("D9", "Confidence Calibration", 0.0,
                              notes=["confidence is not a number"])

    c = float(confidence)
    if not (0.0 <= c <= 1.0):
        return DimensionScore("D9", "Confidence Calibration", 0.0,
                              notes=[f"confidence {c} is out of [0, 1] range"])

    score = 7.0  # Baseline
    notes.append(f"confidence={c}")

    # Penalise overconfidence when evidence is incomplete
    if causal == "incomplete" and c > 0.8:
        score -= 3.0
        notes.append(f"OVERCONFIDENCE: causal=incomplete but confidence={c} — should be <= 0.7")
    elif causal == "partial" and c > 0.85:
        score -= 2.0
        notes.append(f"OVERCONFIDENCE: causal=partial but confidence={c} — should be <= 0.8")

    # Penalise if many blind spots but high confidence
    if len(blind_spots) >= 2 and c > 0.85:
        score -= 1.5
        notes.append(f"OVERCONFIDENCE: {len(blind_spots)} blind spots with confidence={c}")

    # Reward appropriately humble confidence
    if causal == "complete" and 0.70 <= c <= 0.90:
        score = min(score + 2.0, 10.0)
        notes.append("Well-calibrated confidence for complete causal chain")
    elif causal == "incomplete" and c <= 0.5:
        score = min(score + 1.5, 10.0)
        notes.append("Appropriately humble confidence for incomplete evidence")

    return DimensionScore("D9", "Confidence Calibration", max(min(score, 10.0), 0.0), notes=notes)


# ---------------------------------------------------------------------------
# D10 — Governance Compliance
# ---------------------------------------------------------------------------

def _score_d10_governance_compliance(report: Dict[str, Any]) -> DimensionScore:
    """No order language, manual_execution=true, llm_order=false."""
    notes = []
    score = 10.0

    # Hard governance fields
    if report.get("manual_execution_required") is not True:
        score -= 5.0
        notes.append("GOVERNANCE FAIL: manual_execution_required is not true")

    if report.get("llm_order_generation") is not False:
        score -= 5.0
        notes.append("GOVERNANCE FAIL: llm_order_generation is not false")

    # Scan all text for forbidden order language
    all_text = _collect_text_fields(report)
    order_hits = []
    for pattern in FORBIDDEN_ORDER_LANGUAGE:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        if matches:
            order_hits.extend(matches[:2])

    if order_hits:
        score -= min(len(order_hits) * 2.0, 5.0)
        notes.append(f"GOVERNANCE FAIL: order language detected: {order_hits[:3]}")

    if not notes:
        notes.append("Governance compliance: PASS")

    return DimensionScore("D10", "Governance Compliance", max(score, 0.0), notes=notes)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _collect_text_fields(report: Dict[str, Any]) -> str:
    """Collect all string content from the report for pattern scanning."""
    parts = []
    for key, value in report.items():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, str))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Cycle-Level Quality Summary
# ---------------------------------------------------------------------------

def summarise_cycle_quality(
    quality_reports: Dict[str, QualityReport],
) -> Dict[str, Any]:
    """
    Summarise quality across all agents in one cycle.

    Returns:
        {
            "cycle_pass_rate": 0.8,
            "average_score": 82.5,
            "worst_agent": "...",
            "best_agent": "...",
            "failed_agents": [...],
            "critical_governance_failures": [...],
            "agent_grades": {...},
        }
    """
    if not quality_reports:
        return {"error": "No quality reports provided"}

    agent_scores = {aid: qr.pct_score for aid, qr in quality_reports.items()}
    agent_grades = {aid: qr.grade for aid, qr in quality_reports.items()}
    failed = [aid for aid, qr in quality_reports.items() if qr.pass_fail == "FAIL"]

    # Governance failures — D10 < 5 is critical
    gov_failures = [
        aid for aid, qr in quality_reports.items()
        if qr.dimension_scores.get("D10", DimensionScore("D10", "", 10.0)).score < 5.0
    ]

    sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1])
    worst = sorted_agents[0][0] if sorted_agents else None
    best = sorted_agents[-1][0] if sorted_agents else None

    return {
        "cycle_pass_rate": round((len(quality_reports) - len(failed)) / len(quality_reports), 2),
        "average_score": round(sum(agent_scores.values()) / len(agent_scores), 1),
        "worst_agent": worst,
        "best_agent": best,
        "failed_agents": failed,
        "critical_governance_failures": gov_failures,
        "agent_grades": agent_grades,
        "agent_scores": {aid: round(s, 1) for aid, s in agent_scores.items()},
    }
