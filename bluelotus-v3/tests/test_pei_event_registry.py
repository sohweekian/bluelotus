from pei.event_registry import build_candidate_events


def _dataset():
    return {
        "law_governance_binding": {
            "status": "BOUND",
            "governance_pack_id": "GOVPACK_TEST",
            "governance_pack_hash": "hash",
            "report_memory_binding_id": "BIND_TEST",
        }
    }


def test_pei_event_registry_builds_core_event_types():
    events = build_candidate_events(_dataset())
    event_types = {event.event_type for event in events}

    assert {"FED_POLICY", "YEN_CARRY_RISK", "PRIVATE_MARKET_CAPITAL_ABSORPTION"} <= event_types
    assert all(event.resolution_criteria for event in events)
    assert all(event.governance_pack_id == "GOVPACK_TEST" for event in events)
