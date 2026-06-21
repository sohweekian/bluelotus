from acms_cop.classifiers.signal_entropy_classifier import (
    build_signal_entropy_record,
    classify_entropy,
    shannon_entropy,
)


def test_entropy_score_equals_one_for_even_clean_dirty_split():
    raw, norm, k = shannon_entropy([1, 1])
    assert raw == 1.0
    assert norm == 1.0
    assert k == 2
    assert classify_entropy(norm) == "HIGH_ENTROPY / NOISY_SIGNAL"


def test_entropy_decreases_when_evidence_concentrates():
    _, even_norm, _ = shannon_entropy([5, 5])
    _, concentrated_norm, _ = shannon_entropy([9, 1])
    assert concentrated_norm < even_norm


def test_signal_entropy_record_preserves_old_label_and_number():
    row = build_signal_entropy_record(
        "GOOGL",
        old_label="REVIEW",
        sentiment={"clean_headline_count": 3, "dirty_headline_count": 3, "sentiment_label": "NEUTRAL"},
    )
    assert row["ticker"] == "GOOGL"
    assert row["old_label"] == "REVIEW"
    assert row["signal_entropy_normalized"] > 0
    assert "classification" in row
