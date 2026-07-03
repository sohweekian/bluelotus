from pei.oscillation_engine_calibrator import calibrate_oscillation_engine
from pei.tactical_cash_engine_rules import reload_allowed


def test_pei_reload_is_blocked_when_regime_is_broken():
    assert reload_allowed(regime_broken=True, over_cap=False, thesis_intact=True) is False
    assert reload_allowed(regime_broken=False, over_cap=True, thesis_intact=True) is False
    assert reload_allowed(regime_broken=False, over_cap=False, thesis_intact=False) is False


def test_pei_oscillation_calibration_fails_closed_when_history_missing(monkeypatch):
    monkeypatch.setattr("pei.oscillation_engine_calibrator._historical_closes", lambda ticker: [])

    result = calibrate_oscillation_engine("ASTS")

    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["reload_allowed"] is False
    assert result["execution_authority"] == "CIO_ONLY_MANUAL"
