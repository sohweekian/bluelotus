from acms_cop.classifiers.behavioral_state_classifier import classify_behavioral_state
from acms_cop.classifiers.flow_collision_classifier import classify_flow_collision


def test_flow_collision_acceptance_cases():
    assert classify_flow_collision("UP", "OUTFLOW")["flow_collision_state"] == "DISTRIBUTION_INTO_STRENGTH_CANDIDATE"
    assert classify_flow_collision("UP", "ACCUMULATE")["flow_collision_state"] == "CLEAN_ACCUMULATION_CANDIDATE"
    assert classify_flow_collision("DOWN", "DISTRIBUTE")["flow_collision_state"] == "FORCED_LIQUIDATION_CANDIDATE"
    assert classify_flow_collision("FLAT", "INFLOW")["flow_collision_state"] == "ACCUMULATION_INTO_WEAKNESS_CANDIDATE"


def test_behavioral_classifier_returns_state_payload():
    row = classify_behavioral_state("UP", "OUTFLOW", causal_status="PARTIAL", institutional_selling_present=True)
    assert row["acms_state"] == "DISTRIBUTION_INTO_STRENGTH"
    assert row["confidence"] > 0
    assert row["recommended_posture"] == "REVIEW"

