from acms_cop.reports.remediation_reconciliation import build_report_status_taxonomy


def test_governance_consistency_and_data_integrity_are_separate():
    row = build_report_status_taxonomy(
        {"governance_gate_failed_gates": ["pnl_integrity"]},
        {"failed_checks": []},
        {"cost_basis_reconciliation": [{"ticker": "QUBT", "resolution_status": "UNRESOLVED_AWAITING_THIRD_SOURCE", "cio_review_required": True}]},
    )
    assert row["governance_failed_gates"] == ["pnl_integrity"]
    assert row["consistency_audit_failed_checks"] == []
    assert row["data_integrity_unresolved_items"] == ["QUBT"]
    assert row["required_wording"]["governance"] == "Governance failed gates: pnl_integrity"
    assert row["required_wording"]["consistency"] == "Consistency audit failed checks: none"
    assert row["required_wording"]["data_integrity"] == "Data integrity unresolved items: cost-basis conflicts"
