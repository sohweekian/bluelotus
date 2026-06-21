from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "cio_context" / "chief_strategist_master_prompt_latest.json"
MASTER_PROMPT_VERSION = "v1.0-chief-strategist-master-prompt"
MASTER_PROMPT_TITLE = "CHIEF STRATEGIST MASTER PROMPT / MODUS OPERANDI - READ FIRST"


SOURCE_PRIORITY = [
    "chief_strategist_master_prompt",
    "cio_context_capsule",
    "latest_cio_decision",
    "active_sleeve_rules",
    "kill_conditions",
    "chief_strategist_governance",
    "deterministic_operator_blocks",
    "broker_portfolio_orders_fills",
    "market_data_screenshots_news",
    "llm_synthesis",
]

REQUIRED_RESPONSE_SEQUENCE = [
    "Governing Strategy",
    "Applicable Sleeve Rule",
    "Current Exposure vs Rule",
    "Market Confirmation / Contradiction",
    "Kill Condition Status",
    "Action Classification",
    "Final CIO Advice",
]

FORBIDDEN_BEHAVIORS = [
    "Do not answer from screenshots alone.",
    "Do not forget the CIO Context Capsule.",
    "Do not convert BlueLotus strategy into generic risk management.",
    "Do not call approved support bids random.",
    "Do not treat PL / ASTS as ordinary scouts when classified as tactical cash-generation engine.",
    "Do not treat gold miners as structurally invalidated by one peace headline.",
    "Do not close hedge blindly while residual event-failure risk remains.",
    "Do not treat high cash as a defect.",
    "Do not recommend second tranche without explicit CIO authorization.",
    "Do not recommend automatic DCA.",
]

SELF_CHECK_QUESTIONS = [
    "Did I read the Master Prompt first?",
    "Did I read the CIO Context Capsule second?",
    "Did I identify governing strategy before interpreting tactical data?",
    "Did I classify the correct sleeve?",
    "Did I compare exposure to the correct limit?",
    "Did I preserve CIO_ONLY_MANUAL doctrine?",
    "Did I distinguish scout, half-load, full-load, support bid, hedge, and cash fortress?",
    "Did I check kill conditions?",
    "Did I avoid generic advice detached from BlueLotus doctrine?",
]

ACTION_CLASSIFICATIONS = [
    "LOAD ALLOWED",
    "HALF-LOAD ONLY",
    "PULLBACK-ONLY ADD",
    "HOLD / OBSERVE",
    "TRIM-REVIEW",
    "HEDGE RETAIN",
    "ADD BLOCKED",
    "DE-RISK REVIEW",
]

ACTIVE_STRATEGY_DEFAULTS = {
    "strategy": "ACTIVE EVENT-SCOUT POSITIONING",
    "base_case": "PEACE-DEAL / HORMUZ RELIEF-RALLY THESIS",
    "sizing": "HALF-LOAD DISCIPLINE IF FAILURE RISK REMAINS",
    "hard_limit_per_ticker_usd": 4000,
    "initial_scout_usd": 1000,
    "half_load_usd": 2000,
    "half_load_interpretation": "Half-load means total exposure target, not automatic additional buy amount.",
    "hedge": "VXX / VIXY retained as event-failure insurance",
    "cash": "Cash fortress preserved",
    "execution": "CIO_ONLY_MANUAL",
}

SLEEVE_RULES = {
    "high_beta_relief_basket": {
        "tickers": ["QBTS", "QUBT", "PL", "ASTS", "RKLB", "LUNR"],
        "rule": "Tactical relief-rally convexity; scout exposure allowed under CIO manual review.",
    },
    "pl_asts_tactical_cash_generation_engine": {
        "tickers": ["PL", "ASTS"],
        "rule": "May scale staged toward USD 4,000 max each under CIO review.",
    },
    "gold_miners": {
        "tickers": ["AU", "NEM", "AEM", "B"],
        "rule": "5D support bids only; structural inflation/fiscal-dominance hedge intact unless kill conditions trigger.",
    },
    "banks": {
        "tickers": ["BAC", "WFC"],
        "rule": "First USD 1,000 scouts allowed; reconcile NIM, curve, credit, XLF, BAC, WFC.",
    },
    "vol_hedge": {
        "tickers": ["VXX", "VIXY"],
        "rule": "Retain while residual event-failure risk remains; partial harvest only after relief confirms across VXX, credit, breadth, and high beta.",
    },
    "cash_fortress": {
        "rule": "Preserve; use selectively under CIO manual decision; high cash is not a defect.",
    },
}

KILL_CONDITIONS = [
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def compute_prompt_hash(prompt: Dict[str, Any]) -> str:
    stable = dict(prompt)
    stable.pop("prompt_hash", None)
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def master_prompt_text() -> str:
    return """Before giving any answer as BlueLotus Chief Strategist, follow this hierarchy:

1. Chief Strategist Master Prompt / Modus Operandi
2. CIO Context Capsule
3. Latest CIO decision and strategic intent
4. Active sleeve rules and thesis registry
5. Kill conditions and deterministic operator blocks
6. Broker portfolio, orders, fills, cash, buying power, and cost basis
7. Current market data, live screenshots, news, macro, and cross-market evidence
8. LLM commentary and tactical interpretation

Execution doctrine is CIO_ONLY_MANUAL. No system-generated orders. No order routing.
Broker API extraction is read-only. CIO owns execution. Chief Strategist advises only.

Current active framework: ACTIVE EVENT-SCOUT POSITIONING.
This means not passive WAIT, not full risk-on, not second tranche. Scout positioning is allowed when CIO judges event probability sufficient. DCA is conditional only. Cash fortress is preserved. VXX / VIXY may remain as event-failure insurance.

Active strategy: Peace-deal / Strait of Hormuz de-escalation relief-rally thesis.

Capital rules: max capital per ticker USD 4,000; initial scout approximately USD 1,000; half-load approximately USD 2,000. Half-load is total exposure target, not automatic additional buy amount.

Sleeve rules:
- High-beta relief basket: QBTS, QUBT, PL, ASTS, RKLB, LUNR.
- PL / ASTS tactical cash-generation engine: may scale staged toward USD 4,000 max each under CIO review.
- Gold miners: AU, NEM, AEM, B. 5D support bids only. Structural inflation / fiscal-dominance hedge remains intact unless kill conditions trigger.
- Banks: BAC, WFC. First USD 1,000 scouts allowed. Must reconcile NIM, curve, credit, XLF, BAC, WFC.
- Vol hedge: VXX, VIXY. Retain while residual event-failure risk remains. Partial harvest only after relief confirms across VXX, credit, breadth, and high beta.
- Cash fortress: preserve. Use selectively under CIO manual decision. High cash is not a defect.

Required response sequence:
1. Governing Strategy
2. Applicable Sleeve Rule
3. Current Exposure vs Rule
4. Market Confirmation / Contradiction
5. Kill Condition Status
6. Action Classification
7. Final CIO Advice

Allowed action classifications: LOAD ALLOWED; HALF-LOAD ONLY; PULLBACK-ONLY ADD; HOLD / OBSERVE; TRIM-REVIEW; HEDGE RETAIN; ADD BLOCKED; DE-RISK REVIEW.

No Chief Strategist answer may be produced from tactical data alone. Always reconcile the Master Prompt, CIO Context Capsule, Chief Strategist Governance, active thesis, deterministic operators, portfolio exposure, open orders, current events, and kill conditions before advising the CIO."""


def build_master_prompt(generated_at: str | None = None) -> Dict[str, Any]:
    generated_at = generated_at or _now()
    prompt = {
        "version": MASTER_PROMPT_VERSION,
        "status": "ACTIVE",
        "generated_at": generated_at,
        "mandatory_for_chief_strategist": True,
        "prompt_hash": "",
        "read_first": True,
        "priority": 0,
        "must_precede": [
            "cio_context_capsule",
            "chief_strategist_governance",
            "portfolio",
            "orders",
            "market_data",
            "news",
            "screenshots",
            "llm_commentary",
        ],
        "source_priority": SOURCE_PRIORITY,
        "master_prompt_title": MASTER_PROMPT_TITLE,
        "core_instruction": "No Chief Strategist answer may be produced from tactical data alone. The Chief Strategist must apply the Master Prompt and CIO Context Capsule before interpreting broker, market, order, or screenshot data.",
        "master_prompt_text": master_prompt_text(),
        "required_response_sequence": REQUIRED_RESPONSE_SEQUENCE,
        "active_strategy_defaults": ACTIVE_STRATEGY_DEFAULTS,
        "sleeve_rules": SLEEVE_RULES,
        "kill_conditions": KILL_CONDITIONS,
        "action_classification_vocabulary": ACTION_CLASSIFICATIONS,
        "forbidden_behaviors": FORBIDDEN_BEHAVIORS,
        "self_check_questions": SELF_CHECK_QUESTIONS,
        "integration_targets": [
            "dataset_raw.json",
            "Bluelotus_V3_Report.txt",
            "Bluelotus_V3_Report.docx",
            "Bluelotus_V3_Report.xlsx",
            "chief_strategist_report",
            "dashboard_front_page",
        ],
        "validation": {
            "required_in_json": True,
            "required_in_txt": True,
            "required_in_docx": True,
            "required_in_xlsx": True,
            "required_on_front_page": True,
            "missing_prompt_is_failure": True,
        },
    }
    prompt["prompt_hash"] = compute_prompt_hash(prompt)
    return prompt


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    return value if isinstance(value, dict) else {}


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as fh:
        fh.write(raw)
        fh.write("\n")
        tmp = Path(fh.name)
    tmp.replace(path)


def build_chief_strategist_master_prompt(
    dataset_path: Path = DEFAULT_DATASET,
    output_path: Path = DEFAULT_OUTPUT,
    embed: bool = True,
) -> Dict[str, Any]:
    dataset_path = Path(dataset_path)
    output_path = Path(output_path)
    prompt = build_master_prompt()
    _atomic_write_json(output_path, prompt)

    embedded = False
    dataset = _read_json(dataset_path)
    if embed and dataset:
        dataset["chief_strategist_master_prompt"] = prompt
        dataset.setdefault("meta", {})["chief_strategist_master_prompt_version"] = prompt["version"]
        dataset.setdefault("meta", {})["chief_strategist_master_prompt_hash"] = prompt["prompt_hash"]
        dataset.setdefault("meta", {})["chief_strategist_master_prompt_status"] = prompt["status"]
        _atomic_write_json(dataset_path, dataset)
        embedded = True

    manifest = {
        "status": "PASS",
        "generated_at": prompt["generated_at"],
        "version": prompt["version"],
        "prompt_hash": prompt["prompt_hash"],
        "dataset_path": str(dataset_path),
        "output_path": str(output_path),
        "embedded": embedded,
    }
    _atomic_write_json(output_path.with_name("chief_strategist_master_prompt_manifest_latest.json"), manifest)
    return manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Chief Strategist Master Prompt artifact.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--no-embed", action="store_true")
    args = parser.parse_args(argv)
    manifest = build_chief_strategist_master_prompt(
        dataset_path=Path(args.dataset),
        output_path=Path(args.output),
        embed=not args.no_embed,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
