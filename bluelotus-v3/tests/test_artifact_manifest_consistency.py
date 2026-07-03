from research.research_report_generator import build_section_coverage_map


def test_section_coverage_map_requires_str_remediation_and_manifest_surfaces():
    coverage = build_section_coverage_map(
        [
            "STR_Signal_Entropy", "STR_Source_Capacity", "STR_Cost_Basis",
            "STR_Kelly_Sizing", "STR_Hedge_Review", "STR_Cycle_Summary",
            "V3_STR_Remediation", "Open_Order_State",
            "Artifact_Manifest", "Canonical_Reconciliation",
        ],
        "STR - SIGNAL, ENTROPY, AND EDGE\nV3 / STR BUG-CLEARANCE RECONCILIATION\nARTIFACT MANIFEST AND CANONICAL TRUTH-SOURCE AUDIT",
    )
    assert all(all(v for v in row.values()) for row in coverage.values())
