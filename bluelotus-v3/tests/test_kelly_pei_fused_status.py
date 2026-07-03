from acms_cop.reports.signal_edge_dashboard_renderer import _apply_kelly_pei_fusion


def test_kelly_supported_names_are_macro_gated_by_pei():
    rows = _apply_kelly_pei_fusion(
        {"prospective_event_intelligence": {"events": [{"name": "Warsh/BOJ macro add risk blocked"}]}},
        [{"ticker": "PL", "kelly_status": "KELLY_SUPPORTS_SIZE_REVIEW_BUT_CIO_ONLY"}],
    )
    assert rows[0]["kelly_pei_fused_status"] == "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED"
