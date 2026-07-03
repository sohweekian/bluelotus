from acms_cop.learning.kelly_edge_calculator import compute_kelly_advisory


def test_kelly_output_never_generates_orders():
    row = compute_kelly_advisory("QUBT", 60, 0.70, 50000, 1000)
    assert row["advisory_only"] is True
    assert row["orders_generated"] == 0
    assert row["order_routing_enabled"] is False
    assert row["cio_override_required"] is True


def test_negative_kelly_returns_no_size_status():
    row = compute_kelly_advisory("AU", 10, 0.50, 50000, 0)
    assert row["full_kelly_fraction"] <= 0
    assert row["kelly_status"] == "KELLY_NO_SIZE / SCOUT_ONLY_IF_CIO_APPROVES"


def test_quarter_kelly_and_cap_are_computed():
    row = compute_kelly_advisory("QUBT", 100, 0.75, 100000, 0, max_capital_per_ticker_usd=4000)
    assert row["full_kelly_fraction"] == 0.5
    assert row["quarter_kelly_fraction"] == 0.125
    assert row["quarter_kelly_usd"] == 12500.0
    assert row["capped_advisory_size_usd"] == 4000.0


def test_negative_available_upside_is_not_silent_zero_default():
    row = compute_kelly_advisory("AMD", -5.08, 0.6182, 57867.88, 0)
    assert row["kelly_input_status"] == "NEGATIVE_EXPECTED_RETURN"
    assert row["kelly_b"] == -0.0508
    assert row["kelly_p"] == 0.6182
    assert row["kelly_q"] == 0.3818
    assert row["full_kelly_fraction"] < 0
    assert row["kelly_status"] == "KELLY_NO_SIZE / SCOUT_ONLY_IF_CIO_APPROVES"


def test_missing_kelly_inputs_get_explicit_insufficient_data_status():
    row = compute_kelly_advisory("MISSING", None, None, 50000, 0)
    assert row["full_kelly_fraction"] is None
    assert row["kelly_input_status"] == "INSUFFICIENT_DATA"
    assert "analyst_consensus_upside" in row["kelly_missing_inputs"]
    assert "probability" in row["kelly_missing_inputs"]
    assert row["kelly_status"] == "KELLY_INSUFFICIENT_DATA / CIO_REVIEW_REQUIRED"
