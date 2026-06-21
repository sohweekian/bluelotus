from acms_cop.reports.remediation_reconciliation import link_sentiment_hygiene_entropy


def test_sentiment_hygiene_links_dirty_headlines_to_entropy_warning_layer():
    row = link_sentiment_hygiene_entropy(
        {
            "sentiment_hygiene_gate": {
                "dirty_count": 3,
                "clean_count": 7,
                "affected_tickers": ["AMD"],
            }
        },
        {"signal_entropy": [{"ticker": "AMD", "signal_entropy_normalized": 0.7}]},
    )
    assert row["dirty_headline_count"] == 3
    assert row["clean_headline_count"] == 7
    assert row["dirty_ratio"] == 0.3
    assert row["affected_tickers"] == ["AMD"]
    assert row["entropy_score"] == 0.7
    assert row["entropy_classification"] == "HIGH_ENTROPY / NOISY_SIGNAL"
    assert row["excluded_from_cio_tape"] is True
    assert row["included_in_warning_layer"] is True
