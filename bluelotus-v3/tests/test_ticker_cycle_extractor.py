from openpyxl import Workbook

from acms_cop.extractors.ticker_cycle_extractor import extract_ticker_cycles


def test_ticker_extractor_preserves_201_flow_labels(tmp_path):
    path = tmp_path / "report.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Capital Flow"
    ws.append(["Ticker", "Bias", "Main Net", "Super Large Net", "Large Net", "Medium Net", "Small Net", "In Flow", "Snapshot", "Cycle TS"])
    labels = ["ACCUMULATE", "DISTRIBUTE", "INFLOW", "OUTFLOW"]
    for idx in range(201):
        ws.append([f"T{idx}", labels[idx % 4], idx, idx, idx, idx, idx, idx, "2026-06-18", "2026-06-18T05:00:00"])
    wb.save(path)
    rows = extract_ticker_cycles({"regime": {"regime": "NEUTRAL"}, "live_prices": {}}, path)
    assert len(rows) == 201
    assert {r["flow_bias"] for r in rows} == set(labels)

