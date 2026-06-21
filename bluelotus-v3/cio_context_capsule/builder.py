from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .master_prompt import build_chief_strategist_master_prompt


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "cio_context"
CAPSULE_VERSION = "v3.5-cio-context-001"
SCHEMA_VERSION = "cio_context_capsule.v3_5"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as fh:
        fh.write(raw)
        fh.write("\n")
        tmp = Path(fh.name)
    tmp.replace(path)


def compute_capsule_hash(capsule: Dict[str, Any]) -> str:
    stable = dict(capsule)
    stable.pop("capsule_hash", None)
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _core_doctrine() -> Dict[str, Any]:
    return {
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_generated_orders": 0,
        "tactical_score_rule": "Tactical score modifies timing; it does not invalidate structural thesis unless kill condition triggers.",
        "scout_rule": "Scout order is not second tranche authorization.",
        "cash_fortress_rule": "Cash is intentional optionality, not paralysis.",
        "dca_rule": "DCA is conditional, not automatic.",
        "partial_file_rule": "If only partial data is uploaded, operate from the capsule and explicitly mark missing layers.",
    }


def _latest_cio_layer_decision(generated_at: str) -> Dict[str, Any]:
    return {
        "decision_type": "MANUAL_CIO_EVENT_SCOUT_OVERRIDE",
        "primary_catalyst": "Peace deal / Strait of Hormuz de-escalation",
        "decision_timestamp_sgt": generated_at,
        "classification": "EVENT_SCOUT_POSITIONING",
        "not_full_risk_on": True,
        "not_second_tranche": True,
        "not_system_generated": True,
    }


def _three_step_record() -> Dict[str, Any]:
    return {
        "strategic_thinking": {
            "summary": "CIO identified high-probability peace-deal relief catalyst and judged that event probability justifies scout deployment even without perfect 5D support pricing.",
            "key_probabilities": {
                "peace_deal_success": 0.75,
                "monday_relief_rally_if_deal_confirms": 0.70,
                "sustained_rally_probability": 0.60,
            },
            "core_interpretation": "This is event-probability scout positioning, not full risk-on deployment.",
            "market_read": "VXX/VIXY compression and broad index strength suggest pre-confirmation relief anticipation.",
        },
        "strategic_planning": {
            "max_capital_per_ticker_usd": 4000,
            "initial_scout_per_ticker_usd": 1000,
            "gold_miners": "Keep AU/NEM/AEM/B at 5D support bids only. Structural thesis intact but no chase.",
            "banks": "BAC/WFC first USD 1,000 scouts allowed. BAC preferred; WFC secondary pending flow stabilization.",
            "high_beta": "QBTS, QUBT, PL, ASTS, RKLB, LUNR may be built toward approximately USD 1,000 scout exposure.",
            "foundational_tactical_cash_engine": "PL and ASTS may scale up to USD 4,000 maximum each, staged and under CIO review.",
            "dca_rule": "DCA conditional only if peace thesis remains intact, VXX controlled, credit calm, and high beta stabilizes.",
            "new_ticker_rule": "No unnecessary new tickers after the scout basket; manage existing planned scouts.",
        },
        "strategic_execution": {
            "execution_mode": "CIO_ONLY_MANUAL",
            "system_orders_generated": 0,
            "routing_enabled": False,
            "positioning_status": "Portfolio positioned for Monday relief-rally thesis while preserving cash fortress.",
            "not_second_tranche": True,
            "manual_broker_execution": True,
            "system_role": "Record, analyze, validate, and archive only.",
        },
    }


def _active_sleeve_rules() -> Dict[str, Any]:
    return {
        "gold_miners": {
            "role": "STRUCTURAL_INFLATION_FISCAL_DOMINANCE_HEDGE",
            "tickers": ["AU", "NEM", "AEM", "B"],
            "current_policy": "5D_SUPPORT_BIDS_ONLY",
            "allowed": "Maintain support bids; no chase.",
            "forbidden": "Do not interpret one weak tactical tracker as structural thesis invalidation.",
            "add_rule": "Add only if GLD stabilizes and GDX/GDXJ stop persistent underperformance, or if CIO manually confirms support-bid execution.",
            "kill_conditions": ["real_yields_rising_confirmed", "gold_support_break_confirmed", "miners_underperform_gold_persistently"],
        },
        "banks_bac_wfc": {
            "role": "CONTROLLED_INFLATION_NIM_ENGINE",
            "tickers": ["BAC", "WFC"],
            "current_policy": "FIRST_USD_1000_SCOUT_ALLOWED",
            "allowed": "BAC/WFC may receive initial USD 1,000 scout exposure under CIO manual execution.",
            "forbidden": "Do not judge banks without NIM, curve, credit stress, XLF, BAC, and WFC context.",
            "add_rule": "Add/reload only if credit remains calm and curve/NIM support remains intact.",
            "kill_conditions": ["credit_spread_breakout", "curve_benefit_absent", "bank_relative_breakdown"],
        },
        "high_beta_satellites": {
            "role": "TACTICAL_RELIEF_RALLY_CONVEXITY",
            "tickers": ["QBTS", "QUBT", "PL", "ASTS", "RKLB", "LUNR"],
            "current_policy": "USD_1000_SCOUT_TARGET",
            "allowed": "Build toward USD 1,000 scout exposure if relief conditions remain valid.",
            "forbidden": "Do not treat satellites as core holdings unless CIO explicitly upgrades them.",
            "dca_rule": "DCA only if peace thesis intact, VXX controlled, credit calm, and price stabilizes/reclaims.",
            "kill_conditions": ["catalyst_failure", "liquidity_breakdown", "position_exceeds_scout_limits", "vxx_reversal_green", "high_beta_gap_up_fade"],
        },
        "foundational_tactical_cash_engine": {
            "role": "TACTICAL_CASH_GENERATION_ENGINE",
            "tickers": ["PL", "ASTS"],
            "max_capital_per_ticker_usd": 4000,
            "current_policy": "MAY_SCALE_STAGED_TO_4000_MAX",
            "allowed": "PL/ASTS may scale toward USD 4,000 maximum each under staged CIO manual review.",
            "forbidden": "Do not convert to unlimited conviction holdings.",
            "trim_rule": "Review trims into strength after relief rally or 5-8% sleeve gain.",
            "kill_conditions": ["large_outflow_persists_after_relief", "support_break_without_reclaim", "catalyst_failure", "risk_regime_reverts_to_systemic_risk_off"],
        },
        "volatility_hedge": {
            "role": "EVENT_HEDGE",
            "tickers": ["VXX", "VIXY"],
            "current_policy": "KEEP_UNTIL_RELIEF_CONFIRMED",
            "allowed": "Review partial harvest only if relief is confirmed across VXX, credit, breadth, and high beta.",
            "forbidden": "Do not close hedge blindly before peace implementation quality is verified.",
            "kill_conditions": ["vol_spike_fades", "beta_stabilizes", "cio_profit_take"],
        },
        "cash_fortress": {
            "role": "OPTIONALITY_AND_DCA_RESERVE",
            "current_policy": "PRESERVE",
            "allowed": "Use cash selectively only under CIO manual decision.",
            "forbidden": "Do not treat high cash as a defect.",
            "dca_rule": "DCA is conditional, not automatic.",
        },
    }


def _kill_conditions() -> List[str]:
    return [
        "peace_deal_fails_or_is_delayed",
        "us_or_iran_walks_back_deal",
        "weekend_military_incident_occurs",
        "oil_risk_premium_returns_sharply",
        "vxx_or_uvxy_reverses_green",
        "spy_qqq_fade_with_vxx_rising",
        "hyg_jnk_credit_stress_appears",
        "usd_jpy_breaks_down_sharply_or_yen_carry_unwinds",
        "high_beta_gap_up_fades_intraday",
        "institutional_outflows_worsen_after_price_bounce",
        "gold_breaks_while_real_yields_and_usd_rise",
        "xlf_underperforms_spy_while_bac_wfc_weaken",
        "blind_spot_warning_escalates_to_fail",
        "pnl_integrity_conflict_blocks_decision",
    ]


def _required_behavior() -> List[str]:
    return [
        "Read CIO Context Capsule first.",
        "State current CIO decision record before new analysis.",
        "Separate strategic thesis from tactical tape.",
        "Do not invalidate structural gold thesis from one tactical gold warning.",
        "Do not treat scout orders as second tranche.",
        "Do not treat satellites as core holdings unless CIO explicitly upgrades them.",
        "Always preserve CIO_ONLY_MANUAL execution doctrine.",
        "Always state kill conditions before DCA logic.",
        "If only partial data is uploaded, operate from capsule and mark missing layers explicitly.",
        "If current broker screenshot conflicts with report data, treat screenshot as later live state but preserve report doctrine.",
        "Use source hierarchy before inference.",
        "Do not give generic caution; give operational interpretation.",
    ]


def _bootstrap_prompt() -> Dict[str, str]:
    return {
        "purpose": "Instruction for any Chief Strategist agent opening this package.",
        "text": "Before answering the CIO, read cio_context_capsule first. Treat it as the portable institutional memory layer. Do not answer from tactical data alone. Reconcile CIO doctrine, latest CIO three-step decision record, active thesis, current events, portfolio exposure, open orders, kill conditions, and deterministic operator blocks. Preserve CIO_ONLY_MANUAL execution doctrine. Tactical score modifies timing; it does not invalidate structural thesis unless kill condition triggers. Scout orders are not second-tranche authorization. DCA is conditional, not automatic.",
    }


def make_capsule(generated_at: str) -> Dict[str, Any]:
    capsule = {
        "schema_version": SCHEMA_VERSION,
        "version": CAPSULE_VERSION,
        "status": "ACTIVE",
        "generated_at": generated_at,
        "mandatory_for_all_chief_strategist_replies": True,
        "capsule_hash": "",
        "source_hierarchy": [
            "cio_context_capsule",
            "chief_strategist_governance",
            "cio_cognition_ledger",
            "active_thesis_reconciliation",
            "deterministic_operators",
            "portfolio_and_orders",
            "market_data",
            "news_and_external_evidence",
            "llm_agent_commentary",
        ],
        "core_doctrine": _core_doctrine(),
        "latest_cio_layer_decision": _latest_cio_layer_decision(generated_at),
        "cio_three_step_record": _three_step_record(),
        "active_sleeve_rules": _active_sleeve_rules(),
        "kill_conditions": _kill_conditions(),
        "required_chief_strategist_behavior": _required_behavior(),
        "conversation_bootstrap_prompt": _bootstrap_prompt(),
    }
    capsule["capsule_hash"] = compute_capsule_hash(capsule)
    return capsule


def build_cio_context_capsule(
    dataset_path: Path = DEFAULT_DATASET,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    embed: bool = True,
) -> Dict[str, Any]:
    dataset_path = Path(dataset_path)
    output_dir = Path(output_dir)
    build_chief_strategist_master_prompt(dataset_path=dataset_path)
    dataset = _read_json(dataset_path)
    generated_at = _now_utc()
    capsule = make_capsule(generated_at)

    latest_path = output_dir / "cio_context_capsule_latest.json"
    history_path = output_dir / "cio_context_capsule_history.jsonl"
    manifest_path = output_dir / "cio_context_capsule_manifest_latest.json"
    _atomic_write_json(latest_path, capsule)
    output_dir.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(capsule, ensure_ascii=False, sort_keys=True))
        fh.write("\n")

    if embed and dataset:
        dataset["cio_context_capsule"] = capsule
        dataset.setdefault("meta", {})["cio_context_capsule_version"] = CAPSULE_VERSION
        dataset.setdefault("meta", {})["cio_context_capsule_hash"] = capsule["capsule_hash"]
        dataset.setdefault("meta", {})["cio_context_capsule_generated_at"] = generated_at
        _atomic_write_json(dataset_path, dataset)

    manifest = {
        "status": "PASS",
        "generated_at": generated_at,
        "capsule_version": CAPSULE_VERSION,
        "capsule_hash": capsule["capsule_hash"],
        "dataset_path": str(dataset_path),
        "embedded": bool(embed and dataset),
        "outputs": {
            "latest": str(latest_path),
            "history": str(history_path),
            "manifest": str(manifest_path),
        },
    }
    _atomic_write_json(manifest_path, manifest)
    return manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build BlueLotus V3 CIO Context Capsule.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--no-embed", action="store_true")
    args = parser.parse_args(argv)
    manifest = build_cio_context_capsule(
        dataset_path=Path(args.dataset),
        output_dir=Path(args.output_dir),
        embed=not args.no_embed,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
