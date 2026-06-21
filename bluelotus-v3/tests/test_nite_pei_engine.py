"""
BlueLotus V3 — NITE-PEI Engine: Acceptance Test Suite
======================================================
WO-20260621-002 acceptance criteria.
Covers all 6 phases: event classification, Bayesian updating,
kill-condition state machine, CKRI, Kelly-NITE, dual action gates.

GOVERNANCE: Pure deterministic unit tests. No LLM. No order generation.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure bluelotus3 root is importable
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ===========================================================================
# PHASE 1A — Event Classifier
# ===========================================================================

from nite_pei.event_classifier import classify_event, known_event_classes, parse_source_tier


class TestEventClassifier:
    def test_known_event_classes_non_empty(self):
        classes = known_event_classes()
        assert len(classes) >= 20

    def test_unknown_event_returns_lr_neutral(self):
        result = classify_event("xyzzy gibberish flurble", [], 2)
        assert result["event_class"] == "UNKNOWN"
        assert result["noise_discount_factor"] == pytest.approx(0.10)

    def test_geopolitical_headline_classifies(self):
        """Use a headline that matches the taxonomy (military escalation)."""
        result = classify_event("US military airstrike on Iran missiles reported", ["USO"], 1)
        assert result["event_class"] == "GEOPOLITICAL_ESCALATION"
        assert result["noise_discount_factor"] == pytest.approx(0.0)

    def test_sanctions_headline_classifies(self):
        """Trade restriction headline maps to SANCTIONS_NEW."""
        result = classify_event("US imposes trade restrictions on China exports blacklist", ["BABA"], 1)
        assert result["event_class"] == "SANCTIONS_NEW"

    def test_source_tier_discounts(self):
        r1 = classify_event("random noise", [], 1)
        r2 = classify_event("random noise", [], 2)
        r3 = classify_event("random noise", [], 3)
        r4 = classify_event("random noise", [], 4)
        assert r1["noise_discount_factor"] == pytest.approx(0.00)
        assert r2["noise_discount_factor"] == pytest.approx(0.10)
        assert r3["noise_discount_factor"] == pytest.approx(0.25)
        assert r4["noise_discount_factor"] == pytest.approx(0.50)

    def test_source_tier_string_forms(self):
        assert parse_source_tier("1") == 1
        assert parse_source_tier("T1") == 1
        assert parse_source_tier("4") == 4
        assert parse_source_tier("T4") == 4
        assert classify_event("Fed hawkish statement", [], "T1")["noise_discount_factor"] == pytest.approx(0.00)
        assert classify_event("Fed hawkish statement", [], "T4")["noise_discount_factor"] == pytest.approx(0.50)

    def test_governance_fields_present(self):
        result = classify_event("Fed raises rates", [], 1)
        assert result["manual_execution_required"] is True
        assert result["llm_order_generation"] is False

    def test_affected_tickers_passthrough(self):
        result = classify_event("Gold surges on safe-haven demand", ["GLD", "GDX"], 1)
        assert "GLD" in result["affected_tickers"]
        assert "GDX" in result["affected_tickers"]

    def test_keyword_matching_does_not_read_warnings_as_war(self):
        result = classify_event("Monitoring governance: alerts 4 | critical 0 | warnings 3", [], 1)
        assert result["event_class"] == "UNKNOWN"


# ===========================================================================
# PHASE 1B — Bayesian Updater
# ===========================================================================

from nite_pei.bayesian_updater import adjust_lr_toward_neutral, compute_posterior, get_lr, update_thesis


class TestBayesianUpdater:
    def test_compute_posterior_gold_geopolitical(self):
        """Thesis §5 example: p_prior=0.55, LR=1.40 → p_posterior ≈ 0.630"""
        result = compute_posterior(p_prior=0.55, lr_adjusted=1.40)
        assert abs(result["p_posterior"] - 0.630) < 0.005
        assert result["delta_p"] > 0

    def test_compute_posterior_bearish_lr(self):
        """LR < 1.0 should decrease posterior"""
        result = compute_posterior(p_prior=0.60, lr_adjusted=0.60)
        assert result["p_posterior"] < 0.60
        assert result["delta_p"] < 0

    def test_bayesian_clamp_upper_boundary(self):
        """Very high LR on high p_prior should clamp to 0.95"""
        result = compute_posterior(0.93, 8.0)
        assert result["p_posterior"] == pytest.approx(0.95)

    def test_bayesian_clamp_lower_boundary(self):
        """Very low LR on low p_prior should clamp to 0.05"""
        result = compute_posterior(0.07, 0.05)
        assert result["p_posterior"] == pytest.approx(0.05)

    def test_lr_neutral_no_change(self):
        """LR=1.0 means no evidence, posterior equals prior"""
        result = compute_posterior(0.60, 1.00)
        assert abs(result["p_posterior"] - 0.60) < 0.001
        assert abs(result["delta_p"]) < 0.001

    def test_noise_discount_preserves_neutral_lr(self):
        assert adjust_lr_toward_neutral(1.0, 0.50) == pytest.approx(1.0)
        assert compute_posterior(0.50, adjust_lr_toward_neutral(1.0, 0.50))["p_posterior"] == pytest.approx(0.50)

    def test_noise_discount_pulls_supportive_lr_toward_one(self):
        assert adjust_lr_toward_neutral(1.40, 0.50) == pytest.approx(1.20)

    def test_noise_discount_pulls_adverse_lr_toward_one(self):
        assert adjust_lr_toward_neutral(0.60, 0.50) == pytest.approx(0.80)

    def test_get_lr_returns_float(self):
        """get_lr should return a dict with numeric lr_adjusted"""
        result = get_lr("UNKNOWN", "ANY_THESIS", 0.0, None)
        assert "lr_adjusted" in result
        assert isinstance(result["lr_adjusted"], float)
        # UNKNOWN always returns 1.0 (no update)
        assert result["lr_adjusted"] == pytest.approx(1.0)

    def test_update_thesis_sequential(self):
        """Multiple events applied sequentially; posterior compounds correctly."""
        events = [
            {"event_class": "UNKNOWN", "noise_discount_factor": 0.0},
            {"event_class": "UNKNOWN", "noise_discount_factor": 0.0},
        ]
        result = update_thesis(
            thesis_id="TEST_THESIS",
            thesis_type="ANY",
            p_prior=0.55,
            events=events,
            lr_table=None,
        )
        assert "p_posterior_final" in result
        assert "delta_p_total" in result
        # With UNKNOWN/ANY events (LR=1.0) posterior should be unchanged
        assert abs(result["p_posterior_final"] - 0.55) < 0.001

    def test_update_thesis_governance_fields(self):
        result = update_thesis("T1", "ANY", 0.50, [], None)
        assert result["manual_execution_required"] is True
        assert result["llm_order_generation"] is False


# ===========================================================================
# PHASE 1C — Kill Condition State Machine
# ===========================================================================

from nite_pei.kill_condition_state_machine import (
    classify_kill_state,
    update_kill_conditions,
    build_kill_state_snapshot,
    worst_kill_state,
)


class TestKillConditionStateMachine:
    def test_classify_kill_state_inactive(self):
        assert classify_kill_state(0.05) == "INACTIVE"
        assert classify_kill_state(0.09) == "INACTIVE"

    def test_classify_kill_state_watch(self):
        assert classify_kill_state(0.10) == "WATCH"
        assert classify_kill_state(0.34) == "WATCH"

    def test_classify_kill_state_triggered(self):
        assert classify_kill_state(0.35) == "TRIGGERED"
        assert classify_kill_state(0.64) == "TRIGGERED"

    def test_classify_kill_state_confirmed(self):
        assert classify_kill_state(0.65) == "CONFIRMED"
        assert classify_kill_state(1.00) == "CONFIRMED"

    def test_update_kill_conditions_matching_trigger(self):
        kill_conditions = [
            {
                "kill_id": "KC-001",
                "kill_weight": 0.5,
                "P_kill": 0.05,
                "current_state": "INACTIVE",
                "event_classes_that_trigger": ["GEOPOLITICAL_ESCALATION"],
            }
        ]
        updated = update_kill_conditions(kill_conditions, "GEOPOLITICAL_ESCALATION", 0.70)
        assert updated[0]["current_state"] == "CONFIRMED"
        assert updated[0]["P_kill"] == pytest.approx(0.70)

    def test_update_kill_conditions_no_match(self):
        """Non-matching event_class should leave kill condition unchanged."""
        kill_conditions = [
            {
                "kill_id": "KC-001",
                "kill_weight": 0.5,
                "P_kill": 0.05,
                "current_state": "INACTIVE",
                "event_classes_that_trigger": ["CENTRAL_BANK_HAWKISH"],
            }
        ]
        updated = update_kill_conditions(kill_conditions, "COMMODITY_SUPPLY_SHOCK", 0.80)
        assert updated[0]["P_kill"] == pytest.approx(0.05)
        assert updated[0]["current_state"] == "INACTIVE"

    def test_build_kill_state_snapshot(self):
        kill_conditions = [
            {"kill_id": "KC-A", "P_kill": 0.05, "current_state": "INACTIVE"},
            {"kill_id": "KC-B", "P_kill": 0.70, "current_state": "CONFIRMED"},
        ]
        snap = build_kill_state_snapshot(kill_conditions)
        assert "KC-A" in snap
        assert snap["KC-B"]["state"] == "CONFIRMED"

    def test_worst_kill_state_priority(self):
        kill_conditions = [
            {"kill_id": "KC-A", "P_kill": 0.05, "current_state": "INACTIVE"},
            {"kill_id": "KC-B", "P_kill": 0.40, "current_state": "TRIGGERED"},
        ]
        assert worst_kill_state(kill_conditions) == "TRIGGERED"


# ===========================================================================
# PHASE 3 — CKRI Calculator
# ===========================================================================

from nite_pei.ckri_calculator import compute_ckri, get_ckri_zone


class TestCKRICalculator:
    def test_ckri_clear_zone(self):
        theses = [
            {
                "thesis_id": "T1",
                "kill_conditions": [
                    {"kill_weight": 0.5, "P_kill": 0.05, "event_classes_that_trigger": []},
                ],
            }
        ]
        r = compute_ckri(theses)
        assert r["ckri_zone"] == "CLEAR"
        assert r["ckri"] < 0.20

    def test_ckri_critical_zone(self):
        theses = [
            {
                "thesis_id": "T1",
                "kill_conditions": [
                    {"kill_weight": 1.0, "P_kill": 0.90, "event_classes_that_trigger": ["MACRO_SHOCK"]},
                    {"kill_weight": 1.0, "P_kill": 0.85, "event_classes_that_trigger": ["MACRO_SHOCK"]},
                ],
            }
        ]
        r = compute_ckri(theses)
        assert r["ckri_zone"] in ("HIGH", "CRITICAL")

    def test_ckri_empty_theses_returns_zero(self):
        r = compute_ckri([])
        assert r["ckri"] == 0.0
        assert r["ckri_zone"] == "CLEAR"

    def test_ckri_correlation_penalty_increases_ckri(self):
        """Shared trigger event classes should add a correlation penalty."""
        theses_no_overlap = [
            {
                "thesis_id": "T1",
                "kill_conditions": [
                    {"kill_weight": 1.0, "P_kill": 0.50, "event_classes_that_trigger": ["EVENT_A"]},
                    {"kill_weight": 1.0, "P_kill": 0.50, "event_classes_that_trigger": ["EVENT_B"]},
                ],
            }
        ]
        theses_with_overlap = [
            {
                "thesis_id": "T1",
                "kill_conditions": [
                    {"kill_weight": 1.0, "P_kill": 0.50, "event_classes_that_trigger": ["EVENT_A"]},
                    {"kill_weight": 1.0, "P_kill": 0.50, "event_classes_that_trigger": ["EVENT_A"]},
                ],
            }
        ]
        r_no = compute_ckri(theses_no_overlap)
        r_ov = compute_ckri(theses_with_overlap)
        assert r_ov["ckri"] >= r_no["ckri"]

    def test_ckri_governance_fields(self):
        r = compute_ckri([])
        assert r["manual_execution_required"] is True
        assert r["llm_order_generation"] is False
        assert r["order_routing_enabled"] is False

    def test_get_ckri_zone_boundaries(self):
        assert get_ckri_zone(0.00) == "CLEAR"
        assert get_ckri_zone(0.19) == "CLEAR"
        assert get_ckri_zone(0.20) == "WATCH"
        assert get_ckri_zone(0.40) == "ELEVATED"
        assert get_ckri_zone(0.60) == "HIGH"
        assert get_ckri_zone(0.80) == "CRITICAL"
        assert get_ckri_zone(1.00) == "CRITICAL"


# ===========================================================================
# PHASE 4 — Kelly-NITE Coupler
# ===========================================================================

from nite_pei.kelly_nite_coupler import (
    compute_coherence,
    compute_fractional_multiplier,
    compute_kelly,
)


class TestKellyNITECoupler:
    def test_coherence_at_max_noise(self):
        """H_norm=1, dispersion=1 → coherence=0.0"""
        assert compute_coherence(1.0, 1.0) == pytest.approx(0.0, abs=0.001)

    def test_coherence_at_clean_signal(self):
        """H_norm=0, dispersion=0 → coherence=1.0"""
        assert compute_coherence(0.0, 0.0) == pytest.approx(1.0, abs=0.001)

    def test_coherence_at_midpoint(self):
        """H_norm=0.5, dispersion=0.5 → coherence=0.5"""
        assert compute_coherence(0.5, 0.5) == pytest.approx(0.5, abs=0.001)

    def test_coherence_clamped_to_zero(self):
        """Invalid inputs should clamp to [0, 1]"""
        assert compute_coherence(2.0, 2.0) == pytest.approx(0.0)

    def test_fractional_multiplier_min_at_zero_coherence(self):
        assert compute_fractional_multiplier(0.0) == pytest.approx(0.05, abs=0.001)

    def test_fractional_multiplier_max_at_full_coherence(self):
        assert compute_fractional_multiplier(1.0) == pytest.approx(0.35, abs=0.001)

    def test_fractional_multiplier_midpoint(self):
        assert compute_fractional_multiplier(0.5) == pytest.approx(0.20, abs=0.001)

    def test_kelly_negative_clamps_to_zero(self):
        """Low p_posterior should produce f*_kelly = 0"""
        result = compute_kelly(
            p_posterior=0.20,
            analyst_upside_pct=0.10,
            fractional_multiplier=0.25,
        )
        assert result["f_star_kelly"] == pytest.approx(0.0)

    def test_kelly_positive_case(self):
        """Strong thesis above breakeven p > 1/(b+1) should produce positive f*_kelly.
        For b=0.30, breakeven is p > 0.769; using p=0.85."""
        result = compute_kelly(
            p_posterior=0.85,
            analyst_upside_pct=0.30,
            fractional_multiplier=0.25,
        )
        assert result["f_star_kelly"] > 0
        assert result["f_star_full"] > 0

    def test_kelly_zero_upside_returns_zero(self):
        """b=0 (no upside) should guard divide-by-zero and return 0"""
        result = compute_kelly(
            p_posterior=0.80,
            analyst_upside_pct=0.0,
            fractional_multiplier=0.25,
        )
        assert result["f_star_kelly"] == pytest.approx(0.0)
        assert result["f_star_full"] == pytest.approx(0.0)

    def test_kelly_governance_fields(self):
        result = compute_kelly(0.60, 0.20, 0.25)
        assert result["manual_execution_required"] is True
        assert result["llm_order_generation"] is False


# ===========================================================================
# PHASE 5 — CIO Advisory Renderer
# ===========================================================================

from nite_pei.cio_advisory_renderer import (
    determine_posture,
    render_advisory_text,
    evaluate_nite_pei_contradictions,
    build_nite_pei_block,
)


class TestCIOAdvisoryRenderer:
    def test_determine_posture_kill_confirmed(self):
        kill_states = {"KC-001": {"state": "CONFIRMED"}}
        assert "KILL_CONDITION_CONFIRMED" in determine_posture(0.0, kill_states)

    def test_determine_posture_thesis_retired(self):
        kill_states = {"KC-001": {"state": "RETIRED"}, "KC-002": {"state": "RETIRED"}}
        assert "THESIS_RETIRED" in determine_posture(0.0, kill_states)

    def test_determine_posture_strengthened(self):
        kill_states = {"KC-001": {"state": "INACTIVE"}}
        assert "THESIS_STRENGTHENED" in determine_posture(0.20, kill_states)

    def test_determine_posture_weakened(self):
        kill_states = {"KC-001": {"state": "TRIGGERED"}}
        assert "THESIS_WEAKENED" in determine_posture(-0.20, kill_states)

    def test_determine_posture_unchanged(self):
        kill_states = {"KC-001": {"state": "INACTIVE"}}
        assert "THESIS_UNCHANGED" in determine_posture(0.05, kill_states)

    def test_render_advisory_text_contains_thesis_id(self):
        update_record = {
            "p_prior_initial": 0.55,
            "p_posterior_final": 0.65,
            "delta_p_total": 0.10,
            "events_applied": [{"event_class": "GEOPOLITICAL_ESCALATION"}],
            "lr_lookups": [],
        }
        text = render_advisory_text("GOLD_THESIS", update_record, None, "THESIS_UNCHANGED — MONITOR")
        assert "GOLD_THESIS" in text
        assert "MANUAL_EXECUTION_REQUIRED" in text

    def test_nitepei_001_contradiction_detected(self):
        """P_posterior < 0.30 but agent recommends ADD → P3 contradiction"""
        thesis_snapshots = [{"thesis_id": "T1", "P_posterior": 0.20}]
        agent_reports = [{"agent_id": "A1", "recommendation_to_chief_strategist": "THESIS_SUPPORTS_ADD"}]
        contradictions = evaluate_nite_pei_contradictions(thesis_snapshots, agent_reports, "CLEAR")
        assert any(c["rule"] == "NITEPEI-001" for c in contradictions)
        assert all(c["severity"] == "P3" for c in contradictions if c["rule"] == "NITEPEI-001")

    def test_nitepei_001_no_false_positive_when_p_above_threshold(self):
        """P_posterior >= 0.30 should NOT trigger NITEPEI-001"""
        thesis_snapshots = [{"thesis_id": "T1", "P_posterior": 0.55}]
        agent_reports = [{"agent_id": "A1", "recommendation_to_chief_strategist": "ADD"}]
        contradictions = evaluate_nite_pei_contradictions(thesis_snapshots, agent_reports, "CLEAR")
        assert not any(c["rule"] == "NITEPEI-001" for c in contradictions)

    def test_nitepei_002_contradiction_detected(self):
        """CKRI HIGH with no agent risk_flags → P1 contradiction"""
        thesis_snapshots = []
        agent_reports = [{"agent_id": "A1", "risk_flags": []}]
        contradictions = evaluate_nite_pei_contradictions(thesis_snapshots, agent_reports, "HIGH")
        assert any(c["rule"] == "NITEPEI-002" for c in contradictions)
        assert all(c["severity"] == "P1" for c in contradictions if c["rule"] == "NITEPEI-002")
        assert all(c["cio_attention_required"] is True for c in contradictions if c["rule"] == "NITEPEI-002")

    def test_nitepei_002_no_false_positive_clear_zone(self):
        """CKRI CLEAR with no agent risk_flags should NOT trigger NITEPEI-002"""
        thesis_snapshots = []
        agent_reports = [{"agent_id": "A1", "risk_flags": []}]
        contradictions = evaluate_nite_pei_contradictions(thesis_snapshots, agent_reports, "CLEAR")
        assert not any(c["rule"] == "NITEPEI-002" for c in contradictions)

    def test_build_nite_pei_block_schema(self):
        ckri_result = {
            "ckri": 0.10,
            "ckri_zone": "CLEAR",
            "weighted_sum": 0.10,
            "correlation_penalty_applied": 0.0,
            "total_weight": 1.0,
            "kill_breakdown": [],
        }
        block = build_nite_pei_block([], ckri_result, [])
        assert block["schema_version"] == "bluelotus_v3_nite_pei_v1.0"
        assert block["manual_execution_required"] is True
        assert block["llm_order_generation"] is False
        assert block["order_routing_enabled"] is False
        assert "nite_pei_contradictions" in block
        assert "kelly_advisories" in block


# ===========================================================================
# PHASE 6 — Dual Action Gate
# ===========================================================================

from nite_pei.equity_action_gate import (
    HEDGE_TICKERS as EQUITY_GATE_HEDGE_EXCLUSIONS,
    equity_de_risk_advisory,
    per_thesis_equity_review,
)
from nite_pei.hedge_action_gate import (
    HEDGE_TICKERS as HEDGE_GATE_TICKERS,
    hedge_sizing_advisory,
    hedge_status_snapshot,
)


class TestEquityActionGate:
    def test_vxx_excluded_from_equity_gate(self):
        advisory = equity_de_risk_advisory("HIGH", [], {}, affected_tickers=["AAPL", "VXX", "VIXY", "GLD"])
        assert "VXX" not in advisory["equity_tickers_in_scope"]
        assert "VIXY" not in advisory["equity_tickers_in_scope"]
        assert "AAPL" in advisory["equity_tickers_in_scope"]

    def test_equity_gate_clear_zone_no_action(self):
        advisory = equity_de_risk_advisory("CLEAR", [], {})
        assert advisory["action"] == "NO_ACTION"
        assert advisory["de_risk_pct_advisory"] == 0.0

    def test_equity_gate_high_zone_flags_review(self):
        advisory = equity_de_risk_advisory("HIGH", [], {})
        assert advisory["de_risk_pct_advisory"] > 0

    def test_equity_gate_critical_zone_larger_review(self):
        advisory_high = equity_de_risk_advisory("HIGH", [], {})
        advisory_crit = equity_de_risk_advisory("CRITICAL", [], {})
        assert advisory_crit["de_risk_pct_advisory"] > advisory_high["de_risk_pct_advisory"]

    def test_equity_gate_governance_fields(self):
        advisory = equity_de_risk_advisory("CLEAR", [], {})
        assert advisory["manual_execution_required"] is True
        assert advisory["llm_order_generation"] is False
        assert advisory["order_routing_enabled"] is False
        assert advisory["gate"] == "equity_action_gate"
        assert advisory["doctrine_ref"] == "BLV3-DOCTRINE-007"

    def test_equity_gate_hedge_exclusions_constant(self):
        assert "VXX" in EQUITY_GATE_HEDGE_EXCLUSIONS
        assert "VIXY" in EQUITY_GATE_HEDGE_EXCLUSIONS

    def test_per_thesis_equity_review_only_when_high_ckri(self):
        theses = [{"thesis_id": "T1", "status": "active", "affected_tickers": ["AAPL"], "mapped_assets": {}, "kill_conditions": []}]
        result = per_thesis_equity_review(theses, "CLEAR", {})
        assert result == []  # Only triggers on HIGH/CRITICAL

    def test_per_thesis_equity_review_excludes_hedge_tickers(self):
        theses = [
            {
                "thesis_id": "T1",
                "status": "active",
                "affected_tickers": ["VXX", "GLD"],
                "mapped_assets": {},
                "kill_conditions": [],
            }
        ]
        result = per_thesis_equity_review(theses, "HIGH", {})
        assert len(result) == 1
        assert "VXX" not in result[0]["equity_tickers"]
        assert "GLD" in result[0]["equity_tickers"]


class TestHedgeActionGate:
    def test_hedge_gate_only_governs_hedge_tickers(self):
        assert "VXX" in HEDGE_GATE_TICKERS
        assert "VIXY" in HEDGE_GATE_TICKERS
        assert "AAPL" not in HEDGE_GATE_TICKERS
        assert "GLD" not in HEDGE_GATE_TICKERS

    def test_hedge_sizing_advisory_governance_fields(self):
        advisory = hedge_sizing_advisory(1.0, {})
        assert advisory["manual_execution_required"] is True
        assert advisory["llm_order_generation"] is False
        assert advisory["order_routing_enabled"] is False
        assert advisory["gate"] == "hedge_action_gate"
        assert advisory["doctrine_ref"] == "BLV3-DOCTRINE-007"

    def test_hedge_gate_higher_ckri_increases_target(self):
        """CRITICAL ckri_zone should produce higher hedge target than CLEAR."""
        advisory_clear = hedge_sizing_advisory(1.0, {}, ckri_zone="CLEAR")
        advisory_crit = hedge_sizing_advisory(1.0, {}, ckri_zone="CRITICAL")
        assert advisory_crit["ckri_hedge_multiplier"] > advisory_clear["ckri_hedge_multiplier"]
        # Both with zero NAV → both targets are zero, but multiplier distinguishes intent
        assert advisory_crit["hedge_target_usd_after_ckri"] >= advisory_clear["hedge_target_usd_after_ckri"]

    def test_hedge_sizing_with_nav(self):
        """With known NAV, target should be a positive fraction of NAV."""
        dataset = {"portfolio": {"total_value": 1_000_000.0, "positions": {}}}
        advisory = hedge_sizing_advisory(1.0, dataset, ckri_zone="CLEAR")
        assert advisory["nav_total"] == pytest.approx(1_000_000.0)
        assert advisory["hedge_target_usd_after_ckri"] > 0

    def test_hedge_status_snapshot_cio_attention_when_zero_hedges_and_high_ckri(self):
        """Zero hedge value + HIGH CKRI should flag CIO attention."""
        dataset = {"portfolio": {"positions": {}}}
        snap = hedge_status_snapshot(dataset, ckri_zone="HIGH")
        assert snap["cio_attention_required"] is True

    def test_hedge_status_snapshot_no_attention_when_clear(self):
        """CLEAR zone + no hedges should NOT require CIO attention."""
        dataset = {"portfolio": {"positions": {}}}
        snap = hedge_status_snapshot(dataset, ckri_zone="CLEAR")
        assert snap["cio_attention_required"] is False

    def test_hedge_gate_reads_vxx_position(self):
        """Gate should correctly read VXX market value from positions."""
        dataset = {
            "portfolio": {
                "total_value": 500_000.0,
                "positions": {
                    "VXX": {"market_value": 15_000.0},
                    "VIXY": {"market_value": 5_000.0},
                },
            }
        }
        advisory = hedge_sizing_advisory(1.2, dataset, ckri_zone="ELEVATED")
        assert advisory["current_hedge_total_usd"] == pytest.approx(20_000.0)


# ===========================================================================
# Safety invariants — cross-module
# ===========================================================================

class TestSafetyInvariants:
    def test_equity_gate_never_returns_vxx(self):
        """No matter what tickers are passed, equity gate must never include VXX/VIXY."""
        all_tickers = ["VXX", "VIXY", "SPY", "QQQ", "GLD", "TLT"]
        advisory = equity_de_risk_advisory("CRITICAL", [], {}, affected_tickers=all_tickers)
        for ticker in advisory["equity_tickers_in_scope"]:
            assert ticker.upper() not in {"VXX", "VIXY"}, f"Hedge ticker {ticker} leaked into equity gate"

    def test_hedge_gate_manual_execution_always_true(self):
        advisory = hedge_sizing_advisory(0.5, {}, ckri_zone="CRITICAL")
        assert advisory["manual_execution_required"] is True

    def test_kelly_order_generation_always_false(self):
        result = compute_kelly(0.80, 0.25, 0.35)
        assert result["llm_order_generation"] is False

    def test_ckri_order_routing_always_false(self):
        r = compute_ckri([])
        assert r["order_routing_enabled"] is False

    def test_nite_pei_block_order_routing_always_false(self):
        block = build_nite_pei_block([], {"ckri": 0.0, "ckri_zone": "CLEAR",
                                         "weighted_sum": 0.0, "correlation_penalty_applied": 0.0,
                                         "total_weight": 0.0, "kill_breakdown": []}, [])
        assert block["order_routing_enabled"] is False
        assert block["llm_order_generation"] is False
        assert block["manual_execution_required"] is True
