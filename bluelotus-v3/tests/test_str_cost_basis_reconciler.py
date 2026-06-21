from acms_cop.learning.cost_basis_reconciler import reconcile_cost_basis


def test_cost_basis_conflict_unresolved_without_third_witness():
    row = reconcile_cost_basis("QBTS", 104.82, 10.57)
    assert row["resolution_status"] == "UNRESOLVED_AWAITING_THIRD_SOURCE"
    assert row["selected_source"] == "BROKER_REPORTED"
    assert row["cio_review_required"] is True


def test_cost_basis_conflict_resolves_with_third_witness():
    row = reconcile_cost_basis("QBTS", 104.82, 10.57, third_witness_unrealized=103.95)
    assert row["resolution_status"] == "RESOLVED_WITH_THIRD_WITNESS"
    assert row["selected_source"] == "BROKER_REPORTED"
    assert row["cio_review_required"] is False


def test_cost_basis_agreement_is_high_confidence():
    row = reconcile_cost_basis("VXX", 7.50, 7.51)
    assert row["resolution_status"] == "RESOLVED_HIGH_CONFIDENCE"
    assert row["cio_review_required"] is False
