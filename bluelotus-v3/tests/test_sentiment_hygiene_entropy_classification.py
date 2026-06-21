from acms_cop.reports.remediation_reconciliation import link_sentiment_hygiene_entropy


def test_dirty_only_sentiment_is_not_called_clean():
    dataset = {
        "sentiment_hygiene_gate": {
            "dirty_count": 9,
            "clean_count": 0,
            "affected_tickers": ["GOOGL"],
        }
    }
    result = link_sentiment_hygiene_entropy(dataset, {"signal_entropy": []})
    assert result["dirty_ratio"] == 1.0
    assert result["hygiene_classification"] == "HIGH_DIRTY_RATIO"
    assert result["cio_tape_eligible"] is False
    assert "CLEAN" not in result["entropy_classification"]
