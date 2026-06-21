import importlib.util
from pathlib import Path


def _load_engine():
    path = Path(r"C:\bluelotus3\mid\warsh_thesis_engine.py")
    spec = importlib.util.spec_from_file_location("warsh_thesis_engine_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_warsh_rates_enriches_missing_yfinance_yields_from_official_history(monkeypatch):
    engine = _load_engine()
    monkeypatch.setattr(engine, "_load_dataset_treasury", lambda: {
        "snapshot_date": "2026-06-18",
        "yield_10y": 4.43,
        "yield_30y": 4.93,
    })
    monkeypatch.setattr(engine, "_load_previous_macro_yields", lambda current_date: {
        "snapshot_date": "2026-06-17",
        "yield_10y": 4.47,
        "yield_30y": 4.97,
    })

    md = engine.enrich_market_data_with_treasury({
        "tlt": 0.16,
        "ief": -0.53,
        "shy": -0.30,
        "tnx": None,
        "tyx": None,
    })
    assert md["tnx"] == -0.04
    assert md["tyx"] == -0.04
    assert md["yield_delta_source"] == "FRED_DB_HISTORY"

    _, _, rates = engine._gate_rates(md)
    assert rates["us_10y_proxy"] == -0.04
    assert rates["us_30y_proxy"] == -0.04
    assert rates["us_10y_level"] == 4.43
    assert rates["yield_previous_snapshot_date"] == "2026-06-17"


def test_warsh_rates_keeps_missing_yield_delta_as_none(monkeypatch):
    engine = _load_engine()
    monkeypatch.setattr(engine, "_load_dataset_treasury", lambda: {})
    monkeypatch.setattr(engine, "_load_previous_macro_yields", lambda current_date: {})

    md = engine.enrich_market_data_with_treasury({"tlt": 0.0, "ief": 0.0, "shy": 0.0, "tnx": None, "tyx": None})
    assert md["tnx"] is None
    assert md["tyx"] is None

    _, _, rates = engine._gate_rates(md)
    assert rates["us_10y_proxy"] is None
    assert rates["us_30y_proxy"] is None
    assert "unavailable" in " ".join(rates["evidence"]).lower()

