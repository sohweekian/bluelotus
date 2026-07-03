from pei.reflexive_suppression_detector import detect_reflexive_suppression


def test_pei_reflexive_suppression_distinguishes_proxy_pressure_from_breakdown():
    dataset = {
        "live_prices": {
            "ASTS": {"change_pct": -5.2},
            "RKLB": {"change_pct": 1.2},
            "LUNR": {"change_pct": 0.6},
            "PL": {"change_pct": -0.4},
        }
    }

    result = detect_reflexive_suppression(dataset, "ASTS")

    assert result["classification"] in {"REFLEXIVE_SUPPRESSION_LIKELY", "REFLEXIVE_SUPPRESSION_POSSIBLE"}
    assert result["classification"] != "THESIS_BREAKDOWN_LIKELY"
    assert result["execution_authority"] == "CIO_ONLY_MANUAL"
