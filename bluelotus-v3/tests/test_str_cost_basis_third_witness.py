from copy import deepcopy

from acms_cop.learning.cost_basis_reconciler import build_cost_basis_reconciliation, reconcile_cost_basis


def test_missing_third_witness_remains_unresolved():
    row = reconcile_cost_basis("QUBT", -21.26, 21.40, None)
    assert row["resolution_status"] == "UNRESOLVED_AWAITING_THIRD_SOURCE"
    assert row["selected_source"] == "BROKER_REPORTED"
    assert row["cio_review_required"] is True


def test_third_witness_equal_to_broker_selects_broker():
    row = reconcile_cost_basis("ASTS", 131.23, 121.52, 131.00)
    assert row["resolution_status"] == "RESOLVED_WITH_THIRD_WITNESS"
    assert row["selected_source"] == "BROKER_REPORTED"
    assert row["cio_review_required"] is False


def test_third_witness_equal_to_computed_selects_computed():
    row = reconcile_cost_basis("LUNR", 42.40, 27.92, 28.00)
    assert row["resolution_status"] == "RESOLVED_WITH_THIRD_WITNESS"
    assert row["selected_source"] == "PIPELINE_COMPUTED"
    assert row["cio_review_required"] is False


def test_third_witness_different_from_both_requires_manual_review():
    row = reconcile_cost_basis("QBTS", 104.82, 10.57, 55.00)
    assert row["resolution_status"] == "MANUAL_REVIEW_REQUIRED"
    assert row["selected_source"] == "NO_SOURCE_SELECTED"
    assert row["cio_review_required"] is True


def test_cost_basis_reconciliation_does_not_mutate_broker_records():
    dataset = {
        "portfolio": {"positions": {"QBTS": {"unrealized": 104.82, "computed_unrealized": 10.57}}},
        "cost_basis_third_witness": {"QBTS": {"unrealized": 10.57}},
    }
    before = deepcopy(dataset)
    build_cost_basis_reconciliation(dataset, tickers=("QBTS",))
    assert dataset == before
