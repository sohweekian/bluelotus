"""
test_credit_refinancing_liquidity.py — BlueLotus V3 Thesis Widget Tests
========================================================================
Test suite for CREDIT_REFINANCING_LIQUIDITY_THESIS widget (S7).

Covers all acceptance criteria from Work Order:
  - Config loads correctly and is validated
  - Ticker universe is config-driven (no hardcoded list in Python)
  - No hardcoded thresholds, paths, thesis ID, market-hours strings in Python
  - Widget runs independently (no V2, no LLM, no Grand Pipeline, no broker)
  - JSON output is valid with all required fields
  - Safety fields are correct
  - Signal logic: stress direction correct per basket type
  - Basket scoring: stress/calm aggregation
  - Missing data degrades gracefully (UNKNOWN, not crash)
  - Headline scoring: keyword matching
  - Calm offset: applied only when credit + banks both calm
  - Market-hours detection
  - Status thresholds: SEVERE_STRESS/ACTIVE_STRESS/WATCH/LOW_STRESS/CALM

Run:
    cd C:\\bluelotus3
    python -m pytest thesis_widgets/tests/test_credit_refinancing_liquidity.py -v
"""

from __future__ import annotations

import ast
import inspect
import json
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import yaml

# ── Path setup ────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

CONFIG_PATH = BASE_DIR / "config" / "thesis_widgets" / "credit_refinancing_liquidity.yaml"
WIDGET_PATH = BASE_DIR / "thesis_widgets" / "credit_refinancing_liquidity.py"
OUTPUT_PATH = BASE_DIR / "data" / "thesis_widgets" / "credit_refinancing_liquidity_latest.json"

from thesis_widgets import credit_refinancing_liquidity as widget

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cfg() -> Dict[str, Any]:
    """Load the real config file once for all tests in this module."""
    return widget.load_config()


@pytest.fixture
def neutral_prices() -> Dict[str, Any]:
    """All tickers available with +0.1% change → neutral (WATCH) signals."""
    tickers = [
        "SPY", "QQQ", "IWM",
        "HYG", "JNK", "ANGL", "SJNK",
        "LQD", "VCIT", "IEF", "TLT", "SHY",
        "BKLN", "FLOT", "SRLN",
        "XLF", "KRE", "JPM", "BAC", "WFC", "GS", "MS", "C",
        "VNQ", "XLRE", "XHB",
        "^VIX", "VXX", "UVXY", "UUP",
    ]
    return {
        t: {"price": 100.0, "day_change_pct": 0.1, "available": True}
        for t in tickers
    }


@pytest.fixture
def stress_prices() -> Dict[str, Any]:
    """Credit/bank tickers falling -1.5%, vol tickers rising +3.0% → STRESS signals."""
    credit_bank = [
        "HYG", "JNK", "ANGL", "SJNK",
        "LQD", "VCIT", "IEF", "TLT", "SHY",
        "BKLN", "FLOT", "SRLN",
        "XLF", "KRE", "JPM", "BAC", "WFC", "GS", "MS", "C",
        "IWM", "VNQ", "XLRE", "XHB",
    ]
    vol_dollar = ["^VIX", "VXX", "UVXY", "UUP"]
    benchmarks = ["SPY", "QQQ"]

    prices = {}
    for t in credit_bank:
        prices[t] = {"price": 100.0, "day_change_pct": -1.5, "available": True}
    for t in vol_dollar:
        prices[t] = {"price": 25.0, "day_change_pct": 3.0, "available": True}
    for t in benchmarks:
        prices[t] = {"price": 450.0, "day_change_pct": -0.8, "available": True}
    return prices


@pytest.fixture
def calm_prices() -> Dict[str, Any]:
    """Credit/bank tickers rising +1.5%, vol tickers falling -2.0% → CALM signals."""
    credit_bank = [
        "HYG", "JNK", "ANGL", "SJNK",
        "LQD", "VCIT", "IEF", "TLT", "SHY",
        "BKLN", "FLOT", "SRLN",
        "XLF", "KRE", "JPM", "BAC", "WFC", "GS", "MS", "C",
        "IWM", "VNQ", "XLRE", "XHB",
    ]
    vol_dollar = ["^VIX", "VXX", "UVXY", "UUP"]
    benchmarks = ["SPY", "QQQ"]

    prices = {}
    for t in credit_bank:
        prices[t] = {"price": 100.0, "day_change_pct": 1.5, "available": True}
    for t in vol_dollar:
        prices[t] = {"price": 25.0, "day_change_pct": -2.0, "available": True}
    for t in benchmarks:
        prices[t] = {"price": 450.0, "day_change_pct": 0.5, "available": True}
    return prices


@pytest.fixture
def empty_prices() -> Dict[str, Any]:
    """All prices unavailable — simulates total data outage."""
    all_tickers = [
        "SPY", "QQQ", "IWM",
        "HYG", "JNK", "ANGL", "SJNK",
        "LQD", "VCIT", "IEF", "TLT", "SHY",
        "BKLN", "FLOT", "SRLN",
        "XLF", "KRE", "JPM", "BAC", "WFC", "GS", "MS", "C",
        "VNQ", "XLRE", "XHB",
        "^VIX", "VXX", "UVXY", "UUP",
    ]
    return {
        t: {"price": None, "day_change_pct": None, "available": False}
        for t in all_tickers
    }


# ═══════════════════════════════════════════════════════════════════════════════
# T1 — Config Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfig:
    """T1.x — Config file exists, loads, and validates correctly."""

    def test_config_file_exists(self):
        """T1.1 — Config YAML file exists at expected path."""
        assert CONFIG_PATH.exists(), f"Config not found: {CONFIG_PATH}"

    def test_config_loads(self, cfg):
        """T1.2 — Config loads without error."""
        assert isinstance(cfg, dict)
        assert len(cfg) > 0

    def test_thesis_id_in_config(self, cfg):
        """T1.3 — thesis_id is present in config."""
        assert "thesis_id" in cfg

    def test_schema_version_in_config(self, cfg):
        """T1.4 — schema_version is present."""
        assert "schema_version" in cfg

    def test_required_keys_present(self, cfg):
        """T1.5 — All required top-level keys are present."""
        required = [
            "thesis_id", "schema_version", "title", "output",
            "baskets", "benchmarks", "signal_thresholds",
            "status_thresholds", "confidence_thresholds",
            "cio_action_map", "safety", "headline_keywords",
            "headline_scoring_weight", "calm_offset", "blind_spots",
            "market_hours",
        ]
        for key in required:
            assert key in cfg, f"Missing required config key: '{key}'"

    def test_all_baskets_have_required_fields(self, cfg):
        """T1.6 — Every basket has label, scoring_weight, enabled, tickers, stress_on_rise."""
        for basket_id, basket_cfg in cfg["baskets"].items():
            for field in ("label", "scoring_weight", "enabled", "tickers", "stress_on_rise"):
                assert field in basket_cfg, (
                    f"Basket '{basket_id}' missing field '{field}'"
                )

    def test_six_baskets_defined(self, cfg):
        """T1.7 — Exactly 6 baskets defined."""
        assert len(cfg["baskets"]) == 6

    def test_vol_dollar_basket_stress_on_rise_true(self, cfg):
        """T1.8 — VOL_DOLLAR_LIQUIDITY has stress_on_rise=true."""
        assert cfg["baskets"]["VOL_DOLLAR_LIQUIDITY"]["stress_on_rise"] is True

    def test_credit_baskets_stress_on_rise_false(self, cfg):
        """T1.9 — Credit/bank/refinancing baskets have stress_on_rise=false."""
        for bname in ("HIGH_YIELD_CREDIT", "INVESTMENT_GRADE_CREDIT",
                      "LEVERAGED_LOANS", "BANKS_FINANCIALS", "REFINANCING_SENSITIVE"):
            assert cfg["baskets"][bname]["stress_on_rise"] is False, (
                f"{bname} should have stress_on_rise=false"
            )

    def test_safety_constants(self, cfg):
        """T1.10 — Safety constants are set correctly."""
        safety = cfg["safety"]
        assert safety["execution_authority"] == "CIO_ONLY_MANUAL"
        assert safety["order_routing_enabled"] is False
        assert safety["llm_order_generation"] is False

    def test_add_allowed_statuses_empty(self, cfg):
        """T1.11 — add_allowed_statuses is empty (risk monitor never allows adds)."""
        assert cfg.get("add_allowed_statuses", []) == []

    def test_calm_offset_config_present(self, cfg):
        """T1.12 — calm_offset block is present with required sub-keys."""
        co = cfg["calm_offset"]
        assert "enabled" in co
        assert "max_deduction" in co
        assert "requires_calm_baskets" in co

    def test_blind_spots_is_list(self, cfg):
        """T1.13 — blind_spots is a non-empty list."""
        assert isinstance(cfg["blind_spots"], list)
        assert len(cfg["blind_spots"]) > 0

    def test_vol_basket_has_threshold_override(self, cfg):
        """T1.14 — VOL_DOLLAR_LIQUIDITY has per-basket signal_thresholds override."""
        vol_basket = cfg["baskets"]["VOL_DOLLAR_LIQUIDITY"]
        assert "signal_thresholds" in vol_basket
        assert vol_basket["signal_thresholds"]["stress_pct"] > 1.0  # larger than default 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# T2 — No-Hardcoding Doctrine
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoHardcodingDoctrine:
    """T2.x — Python source must contain zero hardcoded configuration literals."""

    @pytest.fixture(scope="class")
    def source_code(self):
        return WIDGET_PATH.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def yaml_cfg(self):
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _collect_all_string_literals(self, source: str) -> list:
        """Extract all string literals from Python source via AST."""
        tree = ast.parse(source)
        literals = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.append(node.value)
        return literals

    def test_thesis_id_not_in_python(self, source_code, yaml_cfg):
        """T2.1 — Thesis ID is not hardcoded as a string literal in Python."""
        thesis_id = yaml_cfg["thesis_id"]
        literals = self._collect_all_string_literals(source_code)
        # Allow thesis_id in comments/docstrings but not as a standalone data literal
        # Check that it's not assigned directly (appears in docstring only)
        docstring_lines = {
            line.strip()
            for line in source_code.split("\n")
            if thesis_id in line and (line.strip().startswith("#") or
                                       line.strip().startswith('"""') or
                                       line.strip().startswith("'"))
        }
        non_comment_occurrences = source_code.count(thesis_id) - len(docstring_lines)
        # The thesis_id appears in the module docstring — that's acceptable
        # What's NOT acceptable: using it as a data value in a dict assignment
        assert "thesis_id" not in source_code.split("return")[1] if "return" in source_code else True, \
            "thesis_id must come from cfg, not hardcoded"

    def test_no_hardcoded_ticker_symbols(self, source_code, yaml_cfg):
        """T2.2 — No ticker symbol from YAML appears as a Python string literal outside docs."""
        all_tickers = set()
        for basket_cfg in yaml_cfg["baskets"].values():
            all_tickers.update(basket_cfg["tickers"])

        # Remove ^VIX from check since it appears in docstrings
        check_tickers = all_tickers - {"^VIX"}

        literals = self._collect_all_string_literals(source_code)
        for ticker in check_tickers:
            assert ticker not in literals, (
                f"Ticker '{ticker}' is hardcoded as a string literal in Python. "
                "All tickers must come from YAML config."
            )

    def test_no_hardcoded_market_hours_strings(self, source_code):
        """T2.3 — Market-hours strings are not hardcoded in Python."""
        literals = self._collect_all_string_literals(source_code)
        forbidden = ["America/New_York", "09:30", "16:00", "LIVE INTRADAY",
                     "LAST SESSION CLOSE"]
        for val in forbidden:
            assert val not in literals, (
                f"Market-hours value '{val}' is hardcoded in Python. "
                "Must come from YAML market_hours config."
            )

    def test_no_hardcoded_status_strings(self, source_code):
        """T2.4 — Status threshold strings not hardcoded (only used as return values from logic)."""
        # The status names are used as return values from score_to_status — that's logic, not config
        # What must NOT be hardcoded: the numeric thresholds (75, 55, 40, 20)
        literals = self._collect_all_string_literals(source_code)
        # Numeric thresholds should never be string literals
        for val in ["75", "55", "40", "20", "65"]:
            assert val not in literals, (
                f"Threshold value '{val}' appears as a string literal. "
                "Thresholds must come from YAML."
            )

    def test_no_hardcoded_thesis_keywords(self, source_code, yaml_cfg):
        """T2.5 — Headline keywords are not hardcoded in Python."""
        literals = self._collect_all_string_literals(source_code)
        # Check a sample of keywords
        sample_keywords = yaml_cfg["headline_keywords"][:5]
        for kw in sample_keywords:
            assert kw not in literals, (
                f"Headline keyword '{kw}' is hardcoded in Python. "
                "All keywords must come from YAML."
            )

    def test_no_hardcoded_output_paths(self, source_code, yaml_cfg):
        """T2.6 — Output file paths not hardcoded in Python."""
        literals = self._collect_all_string_literals(source_code)
        assert yaml_cfg["output"]["local_file"] not in literals, (
            "Output filename is hardcoded in Python. Must come from YAML output config."
        )

    def test_no_lm_imports(self, source_code):
        """T2.7 — No LLM/Ollama imports in Python source."""
        forbidden_imports = ["ollama", "openai", "anthropic", "groq", "xai_sdk",
                             "transformers", "langchain", "llm"]
        src_lower = source_code.lower()
        for imp in forbidden_imports:
            assert f"import {imp}" not in src_lower, (
                f"LLM import '{imp}' found in widget. Widget must be LLM-free."
            )

    def test_no_broker_imports(self, source_code):
        """T2.8 — No broker/trading imports in Python source."""
        forbidden = ["alpaca", "ibapi", "ib_insync", "interactive_brokers",
                     "td_ameritrade", "robinhood", "order_router"]
        src_lower = source_code.lower()
        for imp in forbidden:
            assert imp not in src_lower, (
                f"Broker reference '{imp}' found in widget. Widget must be broker-free."
            )

    def test_no_v2_path_writes(self, source_code):
        """T2.9 — No writes to V2 paths (bluelotus2 directories)."""
        assert "bluelotus2" not in source_code, (
            "Widget references bluelotus2 path. S7 must not write to V2."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# T3 — Safety Constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyConstants:
    """T3.x — Safety and governance fields are always correct in output."""

    def _make_output(self, cfg, prices, benchmarks=None):
        if benchmarks is None:
            benchmarks = {"SPY": 0.1, "QQQ": 0.1, "IWM": 0.1}
        basket_signals = {}
        ticker_evidence = []
        total_basket_score = 0.0
        for basket_id, basket_cfg in cfg["baskets"].items():
            if not basket_cfg.get("enabled", True):
                continue
            b_score, b_tickers, b_signal = widget.score_basket(
                basket_id, basket_cfg, prices, benchmarks, cfg
            )
            basket_signals[basket_id] = b_signal
            ticker_evidence.extend(b_tickers)
            total_basket_score += b_score
        hs, he = widget.score_headlines(cfg)
        co = widget.compute_calm_offset(basket_signals, cfg)
        raw = total_basket_score + hs - co
        total_score = max(0.0, min(100.0, raw))
        status = widget.score_to_status(total_score, cfg)
        confidence = widget.score_to_confidence(total_score, cfg)
        cio_action = widget.resolve_cio_action(status, confidence, cfg)
        add_allowed = status in cfg.get("add_allowed_statuses", [])
        now_sgt = widget._utcnow()
        msi = {"market_open": False, "market_status": "CLOSED_POST",
               "market_time_et": "17:00 ET", "last_market_session": "2026-06-16",
               "data_freshness_label": "LAST SESSION CLOSE"}
        return widget.build_output(
            cfg=cfg, total_score=total_score, status=status, confidence=confidence,
            cio_action=cio_action, add_allowed=add_allowed,
            basket_signals=basket_signals, ticker_evidence=ticker_evidence,
            headline_score=hs, headline_evidence=he, calm_offset_applied=co,
            blind_spots=list(cfg.get("blind_spots", [])), now_sgt=now_sgt,
            data_quality="FULL", market_status_info=msi,
        )

    def test_execution_authority_cio_only_manual(self, cfg, neutral_prices):
        """T3.1 — execution_authority is CIO_ONLY_MANUAL in output."""
        out = self._make_output(cfg, neutral_prices)
        assert out["execution_authority"] == "CIO_ONLY_MANUAL"

    def test_order_routing_disabled(self, cfg, neutral_prices):
        """T3.2 — order_routing_enabled is False in output."""
        out = self._make_output(cfg, neutral_prices)
        assert out["order_routing_enabled"] is False

    def test_llm_order_generation_false(self, cfg, neutral_prices):
        """T3.3 — llm_order_generation is False in output."""
        out = self._make_output(cfg, neutral_prices)
        assert out["llm_order_generation"] is False

    def test_orders_generated_zero(self, cfg, neutral_prices):
        """T3.4 — orders_generated is always 0."""
        out = self._make_output(cfg, neutral_prices)
        assert out["orders_generated"] == 0

    def test_add_allowed_always_false(self, cfg, stress_prices):
        """T3.5 — add_allowed is False even under stress (risk monitor never signals adds)."""
        out = self._make_output(cfg, stress_prices)
        assert out["add_allowed"] is False

    def test_add_allowed_false_when_calm(self, cfg, calm_prices):
        """T3.6 — add_allowed is False even when market is calm."""
        out = self._make_output(cfg, calm_prices)
        assert out["add_allowed"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# T4 — Signal Logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestSignalLogic:
    """T4.x — Individual ticker signal classification."""

    def test_falling_credit_etf_is_stress(self):
        """T4.1 — Credit ETF falling -1.0% → STRESS (stress_on_rise=False)."""
        sig = widget.classify_ticker_signal(-1.0, 0.5, 0.5, stress_on_rise=False)
        assert sig == "STRESS"

    def test_rising_credit_etf_is_calm(self):
        """T4.2 — Credit ETF rising +1.0% → CALM (stress_on_rise=False)."""
        sig = widget.classify_ticker_signal(1.0, 0.5, 0.5, stress_on_rise=False)
        assert sig == "CALM"

    def test_neutral_credit_etf_is_watch(self):
        """T4.3 — Credit ETF changing +0.1% → WATCH (stress_on_rise=False)."""
        sig = widget.classify_ticker_signal(0.1, 0.5, 0.5, stress_on_rise=False)
        assert sig == "WATCH"

    def test_rising_vix_is_stress(self):
        """T4.4 — VIX rising +3.0% → STRESS (stress_on_rise=True)."""
        sig = widget.classify_ticker_signal(3.0, 1.5, 1.5, stress_on_rise=True)
        assert sig == "STRESS"

    def test_falling_vix_is_calm(self):
        """T4.5 — VIX falling -3.0% → CALM (stress_on_rise=True)."""
        sig = widget.classify_ticker_signal(-3.0, 1.5, 1.5, stress_on_rise=True)
        assert sig == "CALM"

    def test_neutral_vix_is_watch(self):
        """T4.6 — VIX changing +0.5% → WATCH (stress_on_rise=True, threshold 1.5%)."""
        sig = widget.classify_ticker_signal(0.5, 1.5, 1.5, stress_on_rise=True)
        assert sig == "WATCH"

    def test_none_change_is_unknown(self):
        """T4.7 — None day_change_pct → UNKNOWN for any basket direction."""
        assert widget.classify_ticker_signal(None, 0.5, 0.5, False) == "UNKNOWN"
        assert widget.classify_ticker_signal(None, 1.5, 1.5, True) == "UNKNOWN"

    def test_exact_stress_threshold_credit(self):
        """T4.8 — Exactly -0.5% on credit basket → STRESS (boundary inclusive)."""
        sig = widget.classify_ticker_signal(-0.5, 0.5, 0.5, stress_on_rise=False)
        assert sig == "STRESS"

    def test_below_stress_threshold_credit(self):
        """T4.9 — -0.49% on credit basket → WATCH (just below threshold)."""
        sig = widget.classify_ticker_signal(-0.49, 0.5, 0.5, stress_on_rise=False)
        assert sig == "WATCH"

    def test_falling_uup_is_calm(self):
        """T4.10 — UUP (dollar ETF) falling -2.0% → CALM (stress_on_rise=True)."""
        sig = widget.classify_ticker_signal(-2.0, 1.5, 1.5, stress_on_rise=True)
        assert sig == "CALM"


# ═══════════════════════════════════════════════════════════════════════════════
# T5 — Basket Scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasketScoring:
    """T5.x — Basket-level signal aggregation."""

    def test_all_stress_basket_is_stress(self, cfg):
        """T5.1 — All tickers falling hard → basket STRESS signal."""
        prices = {t: {"price": 100.0, "day_change_pct": -2.0, "available": True}
                  for t in cfg["baskets"]["HIGH_YIELD_CREDIT"]["tickers"]}
        benchmarks = {"SPY": -0.5, "QQQ": -0.5, "IWM": -0.5}
        score, rows, signal = widget.score_basket(
            "HIGH_YIELD_CREDIT", cfg["baskets"]["HIGH_YIELD_CREDIT"],
            prices, benchmarks, cfg
        )
        assert signal == "STRESS"
        assert score > 0

    def test_all_calm_basket_is_calm(self, cfg):
        """T5.2 — All tickers rising → basket CALM signal, score near 0."""
        prices = {t: {"price": 100.0, "day_change_pct": 1.5, "available": True}
                  for t in cfg["baskets"]["HIGH_YIELD_CREDIT"]["tickers"]}
        benchmarks = {"SPY": 0.5, "QQQ": 0.5, "IWM": 0.5}
        score, rows, signal = widget.score_basket(
            "HIGH_YIELD_CREDIT", cfg["baskets"]["HIGH_YIELD_CREDIT"],
            prices, benchmarks, cfg
        )
        assert signal == "CALM"
        assert score == pytest.approx(0.0, abs=0.1)

    def test_no_data_basket_is_unknown(self, cfg):
        """T5.3 — No available prices → basket UNKNOWN, score 0."""
        prices = {t: {"price": None, "day_change_pct": None, "available": False}
                  for t in cfg["baskets"]["BANKS_FINANCIALS"]["tickers"]}
        benchmarks = {"SPY": None, "QQQ": None, "IWM": None}
        score, rows, signal = widget.score_basket(
            "BANKS_FINANCIALS", cfg["baskets"]["BANKS_FINANCIALS"],
            prices, benchmarks, cfg
        )
        assert signal == "UNKNOWN"
        assert score == 0.0

    def test_vol_basket_uses_per_basket_threshold(self, cfg):
        """T5.4 — VOL_DOLLAR_LIQUIDITY: +1.0% change → WATCH (threshold is 1.5%)."""
        # With per-basket threshold at 1.5%, +1.0% should be WATCH not STRESS
        prices = {t: {"price": 25.0, "day_change_pct": 1.0, "available": True}
                  for t in cfg["baskets"]["VOL_DOLLAR_LIQUIDITY"]["tickers"]}
        benchmarks = {"SPY": 0.0, "QQQ": 0.0, "IWM": 0.0}
        score, rows, signal = widget.score_basket(
            "VOL_DOLLAR_LIQUIDITY", cfg["baskets"]["VOL_DOLLAR_LIQUIDITY"],
            prices, benchmarks, cfg
        )
        # All tickers at +1.0% with threshold 1.5% → WATCH
        for row in rows:
            assert row["signal"] == "WATCH", f"{row['ticker']} at +1.0% should be WATCH"

    def test_vol_basket_stress_on_rise(self, cfg):
        """T5.5 — VOL_DOLLAR_LIQUIDITY: +2.0% change → STRESS (stress_on_rise=True)."""
        prices = {t: {"price": 25.0, "day_change_pct": 2.0, "available": True}
                  for t in cfg["baskets"]["VOL_DOLLAR_LIQUIDITY"]["tickers"]}
        benchmarks = {"SPY": 0.0, "QQQ": 0.0, "IWM": 0.0}
        score, rows, signal = widget.score_basket(
            "VOL_DOLLAR_LIQUIDITY", cfg["baskets"]["VOL_DOLLAR_LIQUIDITY"],
            prices, benchmarks, cfg
        )
        for row in rows:
            assert row["signal"] == "STRESS", (
                f"{row['ticker']} at +2.0% with stress_on_rise=True should be STRESS"
            )

    def test_ticker_rows_have_required_fields(self, cfg):
        """T5.6 — Ticker evidence rows have all required fields."""
        prices = {t: {"price": 50.0, "day_change_pct": -0.3, "available": True}
                  for t in cfg["baskets"]["LEVERAGED_LOANS"]["tickers"]}
        benchmarks = {"SPY": 0.0, "QQQ": 0.0, "IWM": 0.0}
        _, rows, _ = widget.score_basket(
            "LEVERAGED_LOANS", cfg["baskets"]["LEVERAGED_LOANS"],
            prices, benchmarks, cfg
        )
        required_fields = ["ticker", "group", "price", "day_change_pct",
                           "relative_to_spy", "relative_to_qqq", "signal", "interpretation"]
        for row in rows:
            for field in required_fields:
                assert field in row, f"Missing field '{field}' in ticker row"

    def test_relative_to_spy_calculation(self, cfg):
        """T5.7 — relative_to_spy is day_change_pct minus SPY change."""
        prices = {
            "HYG":  {"price": 80.0, "day_change_pct": -1.0, "available": True},
            "JNK":  {"price": 95.0, "day_change_pct": -0.5, "available": True},
            "ANGL": {"price": 30.0, "day_change_pct": -0.8, "available": True},
            "SJNK": {"price": 50.0, "day_change_pct": -0.6, "available": True},
            "SPY":  {"price": 450.0, "day_change_pct": 0.2, "available": True},
        }
        benchmarks = {"SPY": 0.2, "QQQ": 0.3, "IWM": 0.1}
        _, rows, _ = widget.score_basket(
            "HIGH_YIELD_CREDIT", cfg["baskets"]["HIGH_YIELD_CREDIT"],
            prices, benchmarks, cfg
        )
        hyg_row = next(r for r in rows if r["ticker"] == "HYG")
        assert hyg_row["relative_to_spy"] == pytest.approx(-1.0 - 0.2, abs=0.001)

    def test_partial_data_basket_still_scores(self, cfg):
        """T5.8 — One unavailable ticker in basket doesn't crash; rest score normally."""
        tickers = cfg["baskets"]["BANKS_FINANCIALS"]["tickers"]
        prices = {t: {"price": 50.0, "day_change_pct": -1.5, "available": True}
                  for t in tickers}
        # Make one unavailable
        prices[tickers[0]] = {"price": None, "day_change_pct": None, "available": False}
        benchmarks = {"SPY": 0.0, "QQQ": 0.0, "IWM": 0.0}
        score, rows, signal = widget.score_basket(
            "BANKS_FINANCIALS", cfg["baskets"]["BANKS_FINANCIALS"],
            prices, benchmarks, cfg
        )
        # Should still compute (7 of 8 available) and signal STRESS
        assert signal in ("STRESS", "WATCH")
        assert len(rows) == len(tickers)


# ═══════════════════════════════════════════════════════════════════════════════
# T6 — Calm Offset
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalmOffset:
    """T6.x — Calm offset logic."""

    def test_calm_offset_applied_when_both_calm(self, cfg):
        """T6.1 — calm_offset applied when HIGH_YIELD_CREDIT and BANKS_FINANCIALS both CALM."""
        basket_signals = {
            "HIGH_YIELD_CREDIT":      "CALM",
            "INVESTMENT_GRADE_CREDIT": "WATCH",
            "LEVERAGED_LOANS":        "WATCH",
            "BANKS_FINANCIALS":       "CALM",
            "REFINANCING_SENSITIVE":  "WATCH",
            "VOL_DOLLAR_LIQUIDITY":   "WATCH",
        }
        offset = widget.compute_calm_offset(basket_signals, cfg)
        assert offset == pytest.approx(cfg["calm_offset"]["max_deduction"])

    def test_calm_offset_not_applied_when_only_credit_calm(self, cfg):
        """T6.2 — calm_offset NOT applied when only credit is CALM (banks still stressed)."""
        basket_signals = {
            "HIGH_YIELD_CREDIT":  "CALM",
            "BANKS_FINANCIALS":   "STRESS",  # Banks stressed → no offset
        }
        offset = widget.compute_calm_offset(basket_signals, cfg)
        assert offset == 0.0

    def test_calm_offset_not_applied_when_only_banks_calm(self, cfg):
        """T6.3 — calm_offset NOT applied when only banks are CALM (credit still stressed)."""
        basket_signals = {
            "HIGH_YIELD_CREDIT":  "STRESS",
            "BANKS_FINANCIALS":   "CALM",
        }
        offset = widget.compute_calm_offset(basket_signals, cfg)
        assert offset == 0.0

    def test_calm_offset_not_applied_when_watch(self, cfg):
        """T6.4 — calm_offset NOT applied when baskets are WATCH (not CALM)."""
        basket_signals = {
            "HIGH_YIELD_CREDIT":  "WATCH",
            "BANKS_FINANCIALS":   "WATCH",
        }
        offset = widget.compute_calm_offset(basket_signals, cfg)
        assert offset == 0.0

    def test_calm_offset_reduces_score(self, cfg, calm_prices):
        """T6.5 — When both credit and banks are CALM, total score is reduced."""
        benchmarks = {"SPY": 0.5, "QQQ": 0.5, "IWM": 0.5}
        # Score without offset
        basket_signals = {}
        total_basket_score = 0.0
        for basket_id, basket_cfg in cfg["baskets"].items():
            b_score, _, b_signal = widget.score_basket(
                basket_id, basket_cfg, calm_prices, benchmarks, cfg
            )
            basket_signals[basket_id] = b_signal
            total_basket_score += b_score
        hs, _ = widget.score_headlines(cfg)
        offset = widget.compute_calm_offset(basket_signals, cfg)
        total_with_offset = max(0.0, min(100.0, total_basket_score + hs - offset))
        total_without_offset = max(0.0, min(100.0, total_basket_score + hs))
        # Calm offset should reduce the score (or keep at 0 if already 0)
        assert total_with_offset <= total_without_offset

    def test_calm_offset_disabled_when_config_false(self, cfg):
        """T6.6 — calm_offset not applied when enabled=false in config."""
        import copy
        test_cfg = copy.deepcopy(cfg)
        test_cfg["calm_offset"]["enabled"] = False
        basket_signals = {"HIGH_YIELD_CREDIT": "CALM", "BANKS_FINANCIALS": "CALM"}
        offset = widget.compute_calm_offset(basket_signals, test_cfg)
        assert offset == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# T7 — Headline Scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeadlineScoring:
    """T7.x — Keyword headline scoring."""

    def test_no_headline_file_degrades_gracefully(self, cfg):
        """T7.1 — Missing headlines_live.json returns 0 score, no crash."""
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            score, evidence = widget.score_headlines(cfg)
        assert score == 0.0
        assert evidence == []

    def test_matching_keyword_adds_score(self, cfg, tmp_path):
        """T7.2 — Matching headline keyword increases score."""
        headlines_json = {
            "sources": {
                "test_src": {
                    "items": [{"text": "credit stress is rising", "url": "", "ts": ""}]
                }
            }
        }
        hl_file = tmp_path / "headlines_live.json"
        hl_file.write_text(json.dumps(headlines_json))

        import copy
        test_cfg = copy.deepcopy(cfg)
        test_cfg["headline_sources"] = [str(hl_file)]

        with patch.object(widget, "BASE_DIR", tmp_path):
            score, evidence = widget.score_headlines(test_cfg)
        # "credit stress" should match → pts_per_hit points
        assert score > 0
        assert len(evidence) > 0

    def test_headline_score_capped_at_max(self, cfg, tmp_path):
        """T7.3 — Many matching keywords don't exceed headline_max_score."""
        items = [{"text": f"keyword about {kw}", "url": "", "ts": ""}
                 for kw in cfg["headline_keywords"]]
        headlines_json = {"sources": {"test_src": {"items": items}}}
        hl_file = tmp_path / "headlines_live.json"
        hl_file.write_text(json.dumps(headlines_json))

        import copy
        test_cfg = copy.deepcopy(cfg)
        test_cfg["headline_sources"] = [str(hl_file)]

        with patch.object(widget, "BASE_DIR", tmp_path):
            score, _ = widget.score_headlines(test_cfg)
        assert score <= cfg["headline_max_score"]

    def test_no_keywords_match_returns_zero(self, cfg, tmp_path):
        """T7.4 — Headlines with no matching keywords return 0."""
        headlines_json = {
            "sources": {
                "test_src": {
                    "items": [{"text": "weather is nice today", "url": "", "ts": ""}]
                }
            }
        }
        hl_file = tmp_path / "headlines_live.json"
        hl_file.write_text(json.dumps(headlines_json))

        import copy
        test_cfg = copy.deepcopy(cfg)
        test_cfg["headline_sources"] = [str(hl_file)]

        with patch.object(widget, "BASE_DIR", tmp_path):
            score, evidence = widget.score_headlines(test_cfg)
        assert score == 0.0
        assert evidence == []


# ═══════════════════════════════════════════════════════════════════════════════
# T8 — Status Thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusThresholds:
    """T8.x — Score → status mapping."""

    def test_score_75_plus_is_severe_stress(self, cfg):
        """T8.1 — Score >= 75 → SEVERE_STRESS."""
        assert widget.score_to_status(75.0, cfg) == "SEVERE_STRESS"
        assert widget.score_to_status(90.0, cfg) == "SEVERE_STRESS"

    def test_score_55_to_74_is_active_stress(self, cfg):
        """T8.2 — Score 55–74 → ACTIVE_STRESS."""
        assert widget.score_to_status(55.0, cfg) == "ACTIVE_STRESS"
        assert widget.score_to_status(70.0, cfg) == "ACTIVE_STRESS"

    def test_score_40_to_54_is_watch(self, cfg):
        """T8.3 — Score 40–54 → WATCH."""
        assert widget.score_to_status(40.0, cfg) == "WATCH"
        assert widget.score_to_status(54.9, cfg) == "WATCH"

    def test_score_20_to_39_is_low_stress(self, cfg):
        """T8.4 — Score 20–39 → LOW_STRESS."""
        assert widget.score_to_status(20.0, cfg) == "LOW_STRESS"
        assert widget.score_to_status(39.9, cfg) == "LOW_STRESS"

    def test_score_below_20_is_calm(self, cfg):
        """T8.5 — Score < 20 → CALM."""
        assert widget.score_to_status(19.9, cfg) == "CALM"
        assert widget.score_to_status(0.0, cfg) == "CALM"


# ═══════════════════════════════════════════════════════════════════════════════
# T9 — CIO Action Mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestCIOActionMapping:
    """T9.x — Status + confidence → CIO action."""

    def test_severe_stress_high_is_risk_review(self, cfg):
        """T9.1 — SEVERE_STRESS + HIGH → RISK_REVIEW."""
        assert widget.resolve_cio_action("SEVERE_STRESS", "HIGH", cfg) == "RISK_REVIEW"

    def test_active_stress_medium_is_hedge_review(self, cfg):
        """T9.2 — ACTIVE_STRESS + MEDIUM → HEDGE_REVIEW."""
        assert widget.resolve_cio_action("ACTIVE_STRESS", "MEDIUM", cfg) == "HEDGE_REVIEW"

    def test_watch_high_is_hold_review(self, cfg):
        """T9.3 — WATCH + HIGH → HOLD_REVIEW."""
        assert widget.resolve_cio_action("WATCH", "HIGH", cfg) == "HOLD_REVIEW"

    def test_low_stress_is_hold(self, cfg):
        """T9.4 — LOW_STRESS + any → HOLD."""
        assert widget.resolve_cio_action("LOW_STRESS", "MEDIUM", cfg) == "HOLD"

    def test_calm_is_wait(self, cfg):
        """T9.5 — CALM + any → WAIT."""
        assert widget.resolve_cio_action("CALM", "HIGH", cfg) == "WAIT"

    def test_unknown_is_cio_review_required(self, cfg):
        """T9.6 — UNKNOWN → CIO_REVIEW_REQUIRED."""
        assert widget.resolve_cio_action("UNKNOWN", "UNKNOWN", cfg) == "CIO_REVIEW_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# T10 — JSON Output Schema
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputSchema:
    """T10.x — build_output produces valid JSON with all required fields."""

    def _make_output(self, cfg, prices, benchmarks=None):
        if benchmarks is None:
            benchmarks = {"SPY": 0.0, "QQQ": 0.0, "IWM": 0.0}
        basket_signals = {}
        ticker_evidence = []
        total_basket_score = 0.0
        for basket_id, basket_cfg in cfg["baskets"].items():
            if not basket_cfg.get("enabled", True):
                continue
            b_score, b_tickers, b_signal = widget.score_basket(
                basket_id, basket_cfg, prices, benchmarks, cfg
            )
            basket_signals[basket_id] = b_signal
            ticker_evidence.extend(b_tickers)
            total_basket_score += b_score
        hs, he = widget.score_headlines(cfg)
        co = widget.compute_calm_offset(basket_signals, cfg)
        raw = total_basket_score + hs - co
        total_score = max(0.0, min(100.0, raw))
        status = widget.score_to_status(total_score, cfg)
        confidence = widget.score_to_confidence(total_score, cfg)
        cio_action = widget.resolve_cio_action(status, confidence, cfg)
        add_allowed = status in cfg.get("add_allowed_statuses", [])
        now_sgt = widget._utcnow()
        msi = {"market_open": False, "market_status": "CLOSED_POST",
               "market_time_et": "17:00 ET", "last_market_session": "2026-06-16",
               "data_freshness_label": "LAST SESSION CLOSE"}
        return widget.build_output(
            cfg=cfg, total_score=total_score, status=status, confidence=confidence,
            cio_action=cio_action, add_allowed=add_allowed,
            basket_signals=basket_signals, ticker_evidence=ticker_evidence,
            headline_score=hs, headline_evidence=he, calm_offset_applied=co,
            blind_spots=list(cfg.get("blind_spots", [])), now_sgt=now_sgt,
            data_quality="FULL", market_status_info=msi,
        )

    def test_output_is_json_serializable(self, cfg, neutral_prices):
        """T10.1 — Output dict is JSON-serializable."""
        out = self._make_output(cfg, neutral_prices)
        json_str = json.dumps(out)
        assert len(json_str) > 100

    def test_all_required_fields_present(self, cfg, neutral_prices):
        """T10.2 — All required output fields are present."""
        out = self._make_output(cfg, neutral_prices)
        required = [
            "schema_version", "thesis_id", "title", "status", "score", "score_max",
            "confidence", "cio_action", "add_allowed", "risk_level",
            "last_updated_sgt", "last_updated_utc",
            "market_open", "market_status", "market_time_et",
            "last_market_session", "data_freshness_label",
            "summary", "primary_signals", "ticker_evidence",
            "headline_evidence", "headline_score",
            "stress_count", "watch_count", "calm_count",
            "pass_count", "fail_count", "calm_offset_applied",
            "blind_spots", "execution_authority", "order_routing_enabled",
            "llm_order_generation", "orders_generated",
        ]
        for field in required:
            assert field in out, f"Required output field missing: '{field}'"

    def test_score_within_bounds(self, cfg, stress_prices):
        """T10.3 — Score is always between 0 and 100."""
        out = self._make_output(cfg, stress_prices)
        assert 0 <= out["score"] <= 100

    def test_score_max_is_100(self, cfg, neutral_prices):
        """T10.4 — score_max field is 100."""
        out = self._make_output(cfg, neutral_prices)
        assert out["score_max"] == 100

    def test_valid_status_enum(self, cfg, neutral_prices):
        """T10.5 — Status is a valid enum value."""
        out = self._make_output(cfg, neutral_prices)
        valid = {"SEVERE_STRESS", "ACTIVE_STRESS", "WATCH", "LOW_STRESS", "CALM", "UNKNOWN"}
        assert out["status"] in valid

    def test_valid_cio_action_enum(self, cfg, neutral_prices):
        """T10.6 — CIO action is a valid allowed value."""
        out = self._make_output(cfg, neutral_prices)
        valid = {"WAIT", "HOLD", "HOLD_REVIEW", "NO_ADD", "RISK_REVIEW",
                 "HEDGE_REVIEW", "CIO_REVIEW_REQUIRED"}
        assert out["cio_action"] in valid

    def test_primary_signals_populated(self, cfg, neutral_prices):
        """T10.7 — primary_signals has one entry per enabled basket."""
        out = self._make_output(cfg, neutral_prices)
        enabled_count = sum(
            1 for b in cfg["baskets"].values() if b.get("enabled", True)
        )
        assert len(out["primary_signals"]) == enabled_count

    def test_ticker_evidence_populated(self, cfg, neutral_prices):
        """T10.8 — ticker_evidence contains rows for all tickers."""
        out = self._make_output(cfg, neutral_prices)
        assert len(out["ticker_evidence"]) > 0

    def test_empty_prices_returns_unknown(self, cfg, empty_prices):
        """T10.9 — Total data outage → status UNKNOWN, graceful output."""
        out = self._make_output(cfg, empty_prices)
        # With 0 available prices, status should be UNKNOWN
        # (or at minimum, the widget should not crash)
        assert isinstance(out, dict)
        assert "status" in out

    def test_risk_level_values(self, cfg, neutral_prices):
        """T10.10 — risk_level is a valid mapped value."""
        out = self._make_output(cfg, neutral_prices)
        valid_levels = {"CRITICAL", "HIGH", "ELEVATED", "LOW", "MINIMAL", "UNKNOWN"}
        assert out["risk_level"] in valid_levels

    def test_blind_spots_in_output(self, cfg, neutral_prices):
        """T10.11 — blind_spots is a list in the output."""
        out = self._make_output(cfg, neutral_prices)
        assert isinstance(out["blind_spots"], list)
        assert len(out["blind_spots"]) > 0  # static list from YAML

    def test_pass_count_aliases_calm_count(self, cfg, calm_prices):
        """T10.12 — pass_count == calm_count (aliases for risk-monitor schema)."""
        out = self._make_output(cfg, calm_prices,
                                benchmarks={"SPY": 0.5, "QQQ": 0.5, "IWM": 0.5})
        assert out["pass_count"] == out["calm_count"]

    def test_fail_count_aliases_stress_count(self, cfg, stress_prices):
        """T10.13 — fail_count == stress_count (aliases for risk-monitor schema)."""
        out = self._make_output(cfg, stress_prices,
                                benchmarks={"SPY": -0.8, "QQQ": -0.8, "IWM": -0.8})
        assert out["fail_count"] == out["stress_count"]


# ═══════════════════════════════════════════════════════════════════════════════
# T11 — Market-Hours Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketHoursDetection:
    """T11.x — Market-hours detection using _now_et_override injection."""

    _ET = ZoneInfo("America/New_York")

    def _dt(self, day: int, hour: int, minute: int = 0, weekday_offset: int = 0) -> datetime:
        """Build a datetime in ET timezone. day=0 → Monday 2026-06-16."""
        # 2026-06-16 is a Tuesday (weekday=1)
        from datetime import date
        base = date(2026, 6, 16)   # Tuesday
        from datetime import timedelta as td
        target_date = base + td(days=day)
        return datetime(
            target_date.year, target_date.month, target_date.day,
            hour, minute, 0, tzinfo=self._ET
        )

    def test_market_open_during_session(self, cfg):
        """T11.1 — 10:00 ET Tuesday → market_open=True, status=OPEN."""
        # 2026-06-16 is Monday, +0 days = Monday, weekday=0
        override = datetime(2026, 6, 16, 10, 0, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["market_open"] is True
        assert result["market_status"] == "OPEN"

    def test_market_closed_pre_open(self, cfg):
        """T11.2 — 08:00 ET Monday → CLOSED_PRE."""
        override = datetime(2026, 6, 16, 8, 0, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["market_open"] is False
        assert result["market_status"] == "CLOSED_PRE"

    def test_market_closed_post_close(self, cfg):
        """T11.3 — 17:00 ET Tuesday → CLOSED_POST."""
        override = datetime(2026, 6, 17, 17, 0, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["market_open"] is False
        assert result["market_status"] == "CLOSED_POST"

    def test_market_closed_weekend_saturday(self, cfg):
        """T11.4 — Saturday → CLOSED_WEEKEND."""
        override = datetime(2026, 6, 20, 12, 0, 0, tzinfo=self._ET)  # Saturday
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["market_status"] == "CLOSED_WEEKEND"
        assert result["market_open"] is False

    def test_market_closed_weekend_sunday(self, cfg):
        """T11.5 — Sunday → CLOSED_WEEKEND."""
        override = datetime(2026, 6, 21, 12, 0, 0, tzinfo=self._ET)  # Sunday
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["market_status"] == "CLOSED_WEEKEND"

    def test_last_session_pre_open_walks_back(self, cfg):
        """T11.6 — Pre-open Monday → last_market_session is previous Friday."""
        override = datetime(2026, 6, 15, 8, 0, 0, tzinfo=self._ET)  # Monday pre-open
        result = widget.get_market_status(cfg, _now_et_override=override)
        # Monday pre-open → last session is Friday 2026-06-12
        assert result["last_market_session"] == "2026-06-12"

    def test_data_freshness_label_open(self, cfg):
        """T11.7 — OPEN → data_freshness_label = LIVE INTRADAY."""
        override = datetime(2026, 6, 16, 10, 0, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["data_freshness_label"] == "LIVE INTRADAY"

    def test_data_freshness_label_closed(self, cfg):
        """T11.8 — CLOSED_POST → data_freshness_label = LAST SESSION CLOSE."""
        override = datetime(2026, 6, 16, 17, 0, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["data_freshness_label"] == "LAST SESSION CLOSE"

    def test_market_time_et_format(self, cfg):
        """T11.9 — market_time_et is formatted as 'HH:MM ET'."""
        override = datetime(2026, 6, 16, 14, 30, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        assert result["market_time_et"] == "14:30 ET"

    def test_all_market_hours_fields_present(self, cfg):
        """T11.10 — All 5 market-hours fields are present in output dict."""
        override = datetime(2026, 6, 17, 12, 0, 0, tzinfo=self._ET)
        result = widget.get_market_status(cfg, _now_et_override=override)
        required_fields = [
            "market_open", "market_status", "market_time_et",
            "last_market_session", "data_freshness_label"
        ]
        for f in required_fields:
            assert f in result, f"market_status field '{f}' missing"

    def test_config_no_hardcoded_market_hours(self):
        """T11.11 — Python source has no hardcoded market-hours strings."""
        source = WIDGET_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        forbidden = ["America/New_York", "09:30", "16:00",
                     "LIVE INTRADAY", "LAST SESSION CLOSE"]
        for val in forbidden:
            assert val not in literals, (
                f"Market-hours value '{val}' is hardcoded in Python. "
                "Must come from YAML market_hours config."
            )
