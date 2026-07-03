from acms_cop.classifiers.source_capacity_tracker import build_source_capacity_record


def test_source_capacity_remains_collecting_below_30_resolved():
    row = build_source_capacity_record({
        "source": "Yahoo_Finance_RSS",
        "tier": 4,
        "signal_count": 20,
        "confirmed_count": 5,
        "contradicted_count": 4,
    })
    assert row["status"] == "CAPACITY_COLLECTING"
    assert row["validation_status"] == "NOT_YET_VALIDATED"
    assert row["capacity_confidence"] == "INSUFFICIENT_RESOLVED_FORECASTS"
    assert row["automatic_tier_change_allowed"] is False


def test_source_capacity_does_not_auto_validate_or_change_tiers():
    row = build_source_capacity_record({
        "source": "Test_Source",
        "tier": 2,
        "signal_count": 10,
        "confirmed_count": 10,
        "contradicted_count": 0,
    })
    assert row["status"] == "CAPACITY_COLLECTING"
    assert row["validation_status"] == "NOT_YET_VALIDATED"
    assert row["tier_upgrade_candidate"] is False
    assert row["tier_downgrade_candidate"] is False
