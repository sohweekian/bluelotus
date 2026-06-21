from pei.brier_crs_engine import brier_score, crs_decomposition


def test_pei_brier_score_math():
    assert round(brier_score(0.7, 1), 2) == 0.09
    assert round(brier_score(0.2, 1), 2) == 0.64


def test_pei_crs_collecting_until_resolved_history_exists():
    crs = crs_decomposition([])

    assert crs["status"] == "COLLECTING"
    assert crs["resolved_forecasts"] == 0
