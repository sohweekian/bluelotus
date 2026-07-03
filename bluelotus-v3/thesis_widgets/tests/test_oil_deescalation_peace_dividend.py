from __future__ import annotations

import ast
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest
import yaml

_TESTS_DIR = Path(__file__).resolve().parent
_WIDGET_DIR = _TESTS_DIR.parent
_ROOT = _WIDGET_DIR.parent
WIDGET_PATH = _WIDGET_DIR / "oil_deescalation_peace_dividend.py"
CONFIG_PATH = _ROOT / "config" / "thesis_widgets" / "oil_deescalation_peace_dividend.yaml"

sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import thesis_widgets.oil_deescalation_peace_dividend as widget  # noqa: E402
import dashboard_widget_manager as dashboard_widgets  # noqa: E402


@pytest.fixture(scope="module")
def cfg() -> Dict[str, Any]:
    return widget.load_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def source_code() -> str:
    return WIDGET_PATH.read_text(encoding="utf-8")


def _strings(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _mock_prices(cfg: Dict[str, Any], default: str = "watch", overrides: Dict[str, str] | None = None) -> Dict[str, Dict[str, Any]]:
    overrides = overrides or {}
    prices: Dict[str, Dict[str, Any]] = {}
    for benchmark in cfg["benchmarks"]:
        prices[benchmark] = {"available": True, "price": 100.0, "day_change_pct": 0.0}
    for basket_id, basket in cfg["baskets"].items():
        scenario = overrides.get(basket_id, default)
        for ticker in basket["tickers"]:
            symbol = ticker["yf_symbol"]
            benefit_on_rise = bool(ticker["benefit_on_rise"])
            if scenario == "pass":
                pct = 1.0 if benefit_on_rise else -1.0
            elif scenario == "fail":
                pct = -1.0 if benefit_on_rise else 1.0
            elif scenario == "unknown":
                prices[symbol] = {"available": False, "price": None, "day_change_pct": None}
                continue
            else:
                pct = 0.0
            prices[symbol] = {"available": True, "price": 100.0, "day_change_pct": pct}
    return prices


def _run_with_prices(cfg: Dict[str, Any], prices: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    with patch.object(widget, "fetch_prices", return_value=prices), \
         patch.object(widget, "score_headlines", return_value=(0.0, [])), \
         patch.object(widget, "score_escalation", return_value=(0.0, [])), \
         patch.object(widget, "read_external_evidence", return_value=[]):
        return widget.run_once(cfg)


class TestConfig:
    def test_config_file_exists(self):
        assert CONFIG_PATH.exists()

    def test_config_loads(self, cfg):
        assert cfg["thesis_id"] == "OIL_DEESCALATION_PEACE_DIVIDEND_THESIS"
        assert cfg["dashboard_section"] == "S9"

    def test_required_keys_present(self, cfg):
        required = [
            "thesis_id", "schema_version", "title", "display_title",
            "output", "refresh_interval_seconds", "market_hours",
            "benchmarks", "baskets", "signal_thresholds", "status_thresholds",
            "confidence_thresholds", "confidence_rules", "cio_action_map",
            "add_allowed_rules", "headline_keywords", "escalation_keywords",
            "false_positive_rules", "external_evidence", "blind_spots", "safety",
        ]
        for key in required:
            assert key in cfg

    def test_required_baskets_present(self, cfg):
        assert set(cfg["baskets"]) == {
            "OIL_RISK_PREMIUM",
            "TRANSPORT_AIRLINES",
            "CONSUMER_RELIEF",
            "SAFE_HAVEN_UNWIND",
            "BROAD_RISK_ON",
            "DEFENSE_CROSSCHECK",
        }

    def test_all_tickers_defined_as_yaml_dicts(self, cfg):
        for basket in cfg["baskets"].values():
            for ticker in basket["tickers"]:
                assert {"display", "yf_symbol", "benefit_on_rise"} <= set(ticker)


class TestNoHardcodingDoctrine:
    def test_tickers_not_hardcoded_in_python(self, cfg, source_code):
        literals = set(_strings(source_code))
        symbols = set(cfg["benchmarks"])
        for basket in cfg["baskets"].values():
            for ticker in basket["tickers"]:
                symbols.add(ticker["display"])
                symbols.add(ticker["yf_symbol"])
        offenders = sorted(symbol for symbol in symbols if symbol in literals)
        assert offenders == []

    def test_no_hardcoded_marker_or_endpoint(self, source_code):
        assert "oil-peace-dividend-live" not in source_code
        assert "oil_deescalation_peace_dividend_latest.json" not in source_code

    def test_no_hardcoded_thesis_id(self, source_code):
        assert "OIL_DEESCALATION_PEACE_DIVIDEND_THESIS" not in source_code

    def test_no_hardcoded_market_hours(self, source_code):
        for literal in ["09:30", "16:00", "America/New_York", "EQUITY / ETF DATA LAST SESSION CLOSE"]:
            assert literal not in source_code

    def test_no_broker_llm_qwen_ollama_imports(self, source_code):
        tree = ast.parse(source_code)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ["openai", "anthropic", "ollama", "qwen", "langchain", "alpaca", "ibapi", "ib_insync"]
        for token in forbidden:
            assert all(token not in item for item in imports)

    def test_no_v2_write_path(self, source_code):
        assert "bluelotus2" not in source_code.lower()


class TestSafety:
    def test_safety_constants(self, cfg):
        safety = cfg["safety"]
        assert safety["execution_authority"] == "CIO_ONLY_MANUAL"
        assert safety["order_routing_enabled"] is False
        assert safety["llm_order_generation"] is False

    def test_output_safety_fields(self, cfg):
        output = _run_with_prices(cfg, _mock_prices(cfg, default="pass"))
        assert output["execution_authority"] == "CIO_ONLY_MANUAL"
        assert output["order_routing_enabled"] is False
        assert output["llm_order_generation"] is False
        assert output["orders_generated"] == 0


class TestSignalLogic:
    def test_falling_oil_with_risk_on_confirms(self, cfg):
        prices = _mock_prices(cfg, default="pass")
        output = _run_with_prices(cfg, prices)
        assert output["status"] == "CONFIRMING"
        assert output["confidence"] == "HIGH"

    def test_rising_oil_with_vix_rising_fails(self, cfg):
        prices = _mock_prices(cfg, default="watch", overrides={
            "OIL_RISK_PREMIUM": "fail",
            "SAFE_HAVEN_UNWIND": "fail",
        })
        oil = cfg["baskets"]["OIL_RISK_PREMIUM"]
        safe = cfg["baskets"]["SAFE_HAVEN_UNWIND"]
        oil_signal, _, _ = widget.score_basket("OIL_RISK_PREMIUM", oil, prices, 0.0, 0.0, cfg)
        safe_signal, _, _ = widget.score_basket("SAFE_HAVEN_UNWIND", safe, prices, 0.0, 0.0, cfg)
        assert oil_signal == "FAIL"
        assert safe_signal == "FAIL"

    def test_transports_rising_while_oil_falls_passes(self, cfg):
        prices = _mock_prices(cfg, default="watch", overrides={
            "OIL_RISK_PREMIUM": "pass",
            "TRANSPORT_AIRLINES": "pass",
        })
        signal, _, _ = widget.score_basket("TRANSPORT_AIRLINES", cfg["baskets"]["TRANSPORT_AIRLINES"], prices, 0.0, 0.0, cfg)
        assert signal == "PASS"

    def test_consumer_rising_with_oil_falling_passes(self, cfg):
        prices = _mock_prices(cfg, default="watch", overrides={
            "OIL_RISK_PREMIUM": "pass",
            "CONSUMER_RELIEF": "pass",
        })
        signal, _, _ = widget.score_basket("CONSUMER_RELIEF", cfg["baskets"]["CONSUMER_RELIEF"], prices, 0.0, 0.0, cfg)
        assert signal == "PASS"

    def test_safe_haven_unwind_passes(self, cfg):
        prices = _mock_prices(cfg, default="watch", overrides={"SAFE_HAVEN_UNWIND": "pass"})
        signal, _, _ = widget.score_basket("SAFE_HAVEN_UNWIND", cfg["baskets"]["SAFE_HAVEN_UNWIND"], prices, 0.0, 0.0, cfg)
        assert signal == "PASS"

    def test_broad_risk_off_blocks_confirmation(self, cfg):
        prices = _mock_prices(cfg, default="pass", overrides={"BROAD_RISK_ON": "fail"})
        output = _run_with_prices(cfg, prices)
        assert output["confidence"] != "HIGH"
        assert output["add_allowed"] is False


class TestFalsePositiveLogic:
    def test_demand_destruction_flag(self, cfg):
        signals = {
            "OIL_RISK_PREMIUM": "PASS",
            "BROAD_RISK_ON": "FAIL",
            "TRANSPORT_AIRLINES": "FAIL",
            "CONSUMER_RELIEF": "FAIL",
        }
        penalty, flags = widget.evaluate_false_positive_rules(signals, cfg)
        assert penalty > 0
        assert any("demand" in item["message"].lower() for item in flags)

    def test_safe_haven_conflict_flag(self, cfg):
        signals = {"OIL_RISK_PREMIUM": "PASS", "SAFE_HAVEN_UNWIND": "FAIL"}
        penalty, flags = widget.evaluate_false_positive_rules(signals, cfg)
        assert penalty > 0
        assert any("safe" in item["message"].lower() for item in flags)

    def test_escalation_headlines_reduce_score(self, cfg):
        with patch.object(widget, "_headline_items", return_value=[{"headline": "Hormuz closed after tanker attack"}]):
            penalty, evidence = widget.score_escalation(cfg)
        assert penalty > 0
        assert evidence


class TestExternalEvidence:
    def test_missing_external_evidence_does_not_crash(self, cfg, tmp_path):
        test_cfg = deepcopy(cfg)
        test_cfg["external_evidence"]["sources"]["credit_liquidity"]["path"] = "missing_credit.json"
        test_cfg["external_evidence"]["sources"]["leverage_unwind"]["path"] = "missing_unwind.json"
        with patch.object(widget, "_ROOT", tmp_path):
            evidence = widget.read_external_evidence(test_cfg)
        assert len(evidence) == 2
        assert all(item["available"] is False for item in evidence)

    def test_s7_active_stress_blocks_add_allowed(self, cfg):
        evidence = [{"available": True, "status": "ACTIVE_STRESS", "blocks_add": True}]
        signals = {group: "PASS" for group in cfg["baskets"]}
        assert widget.compute_add_allowed("CONFIRMING", "HIGH", signals, 0, 0, evidence, cfg) is False

    def test_s8_watch_blocks_add_allowed(self, cfg):
        evidence = [{"available": True, "status": "WATCH", "blocks_add": True}]
        signals = {group: "PASS" for group in cfg["baskets"]}
        assert widget.compute_add_allowed("CONFIRMING", "HIGH", signals, 0, 0, evidence, cfg) is False


class TestMarketHours:
    def test_market_open_status(self, cfg):
        dt = datetime(2026, 6, 17, 10, 0)
        status = widget.get_market_status(cfg, dt)
        assert status["market_status"] == "OPEN"
        assert status["market_open"] is True

    def test_pre_market_status(self, cfg):
        dt = datetime(2026, 6, 17, 8, 0)
        assert widget.get_market_status(cfg, dt)["market_status"] == "CLOSED_PRE"

    def test_post_market_status(self, cfg):
        dt = datetime(2026, 6, 17, 17, 0)
        assert widget.get_market_status(cfg, dt)["market_status"] == "CLOSED_POST"

    def test_weekend_status(self, cfg):
        dt = datetime(2026, 6, 20, 12, 0)
        status = widget.get_market_status(cfg, dt)
        assert status["market_status"] == "CLOSED_WEEKEND"
        assert status["last_market_session"] == "2026-06-19"


class TestOutputSchema:
    def test_required_output_fields(self, cfg):
        output = _run_with_prices(cfg, _mock_prices(cfg, default="pass"))
        required = [
            "schema_version", "thesis_id", "title", "status", "score", "score_max",
            "confidence", "cio_action", "add_allowed", "risk_level",
            "last_updated_sgt", "market_open", "market_status", "market_time_et",
            "last_market_session", "data_freshness_label", "summary",
            "primary_signals", "ticker_evidence", "headline_evidence",
            "escalation_evidence", "external_evidence", "false_positive_flags",
            "pass_count", "watch_count", "fail_count", "blind_spots",
            "execution_authority", "order_routing_enabled", "llm_order_generation",
            "orders_generated",
        ]
        for key in required:
            assert key in output

    def test_score_status_and_action_valid(self, cfg):
        output = _run_with_prices(cfg, _mock_prices(cfg, default="pass"))
        assert 0 <= output["score"] <= 100
        assert output["status"] in {"CONFIRMING", "WATCH", "MIXED", "WEAKENING", "CONTRADICTED", "UNKNOWN"}
        assert output["cio_action"] in {"WAIT", "HOLD", "HOLD_REVIEW", "NO_ADD", "RISK_REVIEW", "CIO_REVIEW_REQUIRED"}

    def test_ticker_evidence_shape(self, cfg):
        output = _run_with_prices(cfg, _mock_prices(cfg, default="pass"))
        row = output["ticker_evidence"][0]
        assert {
            "display_symbol", "yf_symbol", "group", "price", "day_change_pct",
            "relative_to_spy", "relative_to_qqq", "signal", "interpretation",
        } <= set(row)


class TestDashboardRegistry:
    def test_s9_added_to_registry(self):
        registry = dashboard_widgets.load_registry()
        s9 = [item for item in registry["widgets"] if item["widget_id"] == "oil_deescalation_peace_dividend"]
        assert len(s9) == 1
        assert s9[0]["section_id"] == "S9"
        assert s9[0]["marker_id"] == "oil-peace-dividend-live"

    def test_registry_order_s6_s7_s8_s9(self):
        registry = dashboard_widgets.load_registry()
        assert [item["section_id"] for item in dashboard_widgets.enabled_widgets(registry)] == ["S6", "S7", "S8", "S9"]

    def test_widget_zone_renders_s9_before_system_health(self):
        registry = dashboard_widgets.load_registry()
        html = "<main>" + dashboard_widgets.render_widget_zone(registry) + "<div>System Health</div></main>"
        assert dashboard_widgets.verify_html(html, registry) == []
        assert html.index("oil-peace-dividend-live") < html.index("System Health")
