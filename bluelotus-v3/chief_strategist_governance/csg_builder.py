from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
CSG_DIR = PROJECT_ROOT / "data" / "chief_strategist"
CSG_VERSION = "v3.5-csg-001"
CSG_SCHEMA_VERSION = "chief_strategist_governance.v3_5"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


def build_thesis_registry(generated_at: str) -> Dict[str, Any]:
    theses = [
        {
            "thesis_id": "THESIS_GOLD_STRUCTURAL_INFLATION",
            "name": "Gold / Gold Miners Structural Inflation Hedge",
            "classification": "STRUCTURAL",
            "doctrine": "Tactical gold score modifies timing only. It does not invalidate the structural inflation/fiscal dominance thesis unless kill conditions trigger.",
            "position_role": "core_structural_hedge",
            "tickers": ["GLD", "GDX", "GDXJ", "AU", "NEM"],
            "required_context": ["inflation", "fiscal dominance", "real yields", "USD", "miner beta"],
            "kill_conditions": [
                "Real yields trend materially higher while gold breaks support for multiple sessions.",
                "USD strength and falling inflation expectations persist together.",
                "Gold miners underperform gold during confirmed risk-off liquidation after CIO review.",
            ],
        },
        {
            "thesis_id": "THESIS_BANKS_NIM_ENGINE",
            "name": "Banks / Net Interest Margin Engine",
            "classification": "STRUCTURAL_WITH_CYCLICAL_RISK",
            "doctrine": "Banks require NIM, yield curve, credit quality, deposit beta, and XLF/BAC/WFC confirmation before tactical conclusions.",
            "position_role": "cyclical_value_income_engine",
            "tickers": ["BAC", "WFC", "XLF", "JPM", "GS", "MS"],
            "required_context": ["NIM", "credit", "yield curve", "BAC", "WFC", "XLF"],
            "kill_conditions": [
                "Credit stress widens while curve benefit fails to offset funding pressure.",
                "BAC/WFC/XLF underperform despite a favorable curve for multiple sessions.",
            ],
        },
        {
            "thesis_id": "THESIS_CASH_FORTRESS",
            "name": "Cash Fortress / Deployment Optionality",
            "classification": "PORTFOLIO_POSTURE",
            "doctrine": "High cash is intentional defensive optionality when CIO posture is WAIT/HOLD/REVIEW and second tranche is blocked.",
            "position_role": "liquidity_reserve_and_optionality",
            "tickers": ["CASH", "SGOV", "BIL", "SHY"],
            "required_context": ["cash weight", "deployment floor", "second tranche gate", "CIO posture"],
            "kill_conditions": [
                "CIO explicitly authorizes deployment.",
                "Risk-on regime is confirmed across macro, credit, and breadth gates.",
            ],
        },
        {
            "thesis_id": "THESIS_SATELLITE_CONVEXITY",
            "name": "Satellite Convexity / Scout Book",
            "classification": "SATELLITE",
            "doctrine": "ASTS/RKLB/QBTS/QUBT/LUNR-style names are scout or satellite convexity exposures, not core portfolio anchors.",
            "position_role": "small_scout_convexity",
            "tickers": ["ASTS", "RKLB", "QBTS", "QUBT", "LUNR", "IONQ", "RGTI"],
            "required_context": ["position size", "liquidity", "second tranche gate", "theme confirmation"],
            "kill_conditions": [
                "Thesis catalyst fails or funding/liquidity conditions worsen.",
                "Second tranche remains blocked while position grows beyond scout limits.",
            ],
        },
        {
            "thesis_id": "THESIS_VOLATILITY_HEDGE",
            "name": "Volatility Hedge / Risk-Off Convexity",
            "classification": "TACTICAL_HEDGE",
            "doctrine": "VXX/VIXY gains may be hedge profit, not necessarily a reason to add more volatility risk.",
            "position_role": "risk_off_hedge",
            "tickers": ["VXX", "VIXY", "UVXY"],
            "required_context": ["VIX", "beta selloff", "hedge P/L", "carry decay"],
            "kill_conditions": [
                "Volatility spike fades while beta stabilizes.",
                "CIO takes hedge profit or reduces exposure.",
            ],
        },
        {
            "thesis_id": "THESIS_RISK_OFF_DISLOCATION_SCOUTING",
            "name": "Risk-Off Dislocation Scout Orders",
            "classification": "TACTICAL_ENTRY_FRAMEWORK",
            "doctrine": "Scout orders detect dislocation and price discovery; they are not approval for second tranche deployment.",
            "position_role": "front_line_detection",
            "tickers": ["QBTS", "QUBT", "LUNR", "ASTS", "RKLB"],
            "required_context": ["order size", "scout cap", "second tranche gate", "macro confirmation"],
            "kill_conditions": [
                "Liquidity event forces removal of scout orders.",
                "Second tranche gate remains blocked and thesis evidence deteriorates.",
            ],
        },
    ]
    return {
        "schema_version": CSG_SCHEMA_VERSION,
        "governance_version": CSG_VERSION,
        "generated_at": generated_at,
        "theses": theses,
    }


def build_active_thesis_reconciliation(dataset: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") or {}
    cash = float(portfolio.get("cash_pct") or portfolio.get("cash_weight") or 0)
    if cash > 1.5:
        cash = cash / 100.0
    return {
        "schema_version": CSG_SCHEMA_VERSION,
        "generated_at": generated_at,
        "gold_miners": {
            "strategic_thesis": "Structural inflation / fiscal dominance hedge",
            "tactical_state": "Score can be WATCH/FAIL during liquidation or relief-rally windows",
            "allowed_interpretation": "Reduce/add timing may change; structural thesis remains active unless kill conditions trigger.",
            "forbidden_interpretation": "Iran peace or one weak miner session automatically invalidates gold thesis.",
            "required_kill_conditions": [
                "real_yields_rising_confirmed",
                "gold_support_break_confirmed",
                "miners_underperform_gold_persistently",
            ],
        },
        "banks_bac_wfc": {
            "strategic_thesis": "NIM and curve-sensitive value engine",
            "tactical_state": "Requires curve, credit, deposit beta, XLF, BAC, and WFC confirmation",
            "allowed_interpretation": "Bank weakness is a tactical warning until NIM/credit/curve reconciliation is complete.",
            "forbidden_interpretation": "Banks are bullish or bearish without NIM, credit, curve, BAC/WFC/XLF context.",
            "required_kill_conditions": ["credit_spread_breakout", "curve_benefit_absent", "bank_relative_breakdown"],
        },
        "satellites": {
            "strategic_thesis": "Convex optionality and scout-book discovery",
            "tactical_state": "High beta can liquidate under risk-off; second tranche remains governed separately",
            "allowed_interpretation": "Scout exposure can remain as detection while additional deployment is blocked.",
            "forbidden_interpretation": "Satellite names are core holdings or automatic add candidates.",
            "required_kill_conditions": ["catalyst_failure", "liquidity_breakdown", "position_exceeds_scout_limits"],
        },
        "cash": {
            "strategic_thesis": "Cash fortress and deployment optionality",
            "cash_weight": cash,
            "allowed_interpretation": "High cash is intentional when CIO posture is WAIT/HOLD/REVIEW.",
            "forbidden_interpretation": "High cash is automatically a defect or missed opportunity.",
            "required_kill_conditions": ["cio_deployment_authorized", "risk_on_regime_confirmed"],
        },
        "volatility_hedge": {
            "strategic_thesis": "Risk-off convexity hedge",
            "tactical_state": "VXX/VIXY gains confirm stress or hedge value but do not authorize automatic adds.",
            "allowed_interpretation": "Hedge profits may be reviewed or partially harvested under CIO authority.",
            "forbidden_interpretation": "Volatility strength means add more risk without CIO approval.",
            "required_kill_conditions": ["vol_spike_fades", "beta_stabilizes", "cio_profit_take"],
        },
        "risk_off_dislocation_scouting": {
            "strategic_thesis": "Scout orders as front-line market detector",
            "tactical_state": "Scout orders may sit during dislocation; second tranche remains blocked until macro confirmation",
            "allowed_interpretation": "Scout orders observe price discovery and can be reviewed manually.",
            "forbidden_interpretation": "Scout fill means full deployment permission.",
            "required_kill_conditions": ["macro_confirmation_fails", "liquidity_stress_expands", "cio_cancels_scouts"],
        },
    }


def build_event_thesis_map(generated_at: str) -> Dict[str, Any]:
    rows = [
        ("iran_deescalation", "THESIS_GOLD_STRUCTURAL_INFLATION", "tactical_relief_window", "May lower immediate safe-haven bid; does not kill inflation/fiscal thesis."),
        ("warsh_hawkish_fed", "THESIS_GOLD_STRUCTURAL_INFLATION", "real_yield_pressure", "Pressures gold timing if real yields rise; requires yield confirmation."),
        ("warsh_hawkish_fed", "THESIS_BANKS_NIM_ENGINE", "curve_nim_review", "Bank thesis must reconcile curve steepening/flattening, credit, BAC/WFC/XLF."),
        ("big_beautiful_bill", "THESIS_GOLD_STRUCTURAL_INFLATION", "fiscal_dominance_support", "Large deficit/fiscal impulse can reinforce structural gold thesis."),
        ("stargate_ai_spending", "THESIS_SATELLITE_CONVEXITY", "ai_capex_tailwind", "Supports selected satellites only with liquidity and theme confirmation."),
        ("golden_dome_defense_spending", "THESIS_SATELLITE_CONVEXITY", "space_defense_tailwind", "Supports space/defense-linked names; still scout governed."),
        ("petrodollar_recycling", "THESIS_GOLD_STRUCTURAL_INFLATION", "dollar_liquidity_channel", "Requires USD, oil, and reserve-flow reconciliation."),
        ("tariff_uncertainty", "THESIS_CASH_FORTRESS", "optionality_support", "Supports cash fortress until uncertainty clears."),
        ("boj_yen_carry_risk", "THESIS_VOLATILITY_HEDGE", "carry_unwind_stress", "Yen strength and vol spike can validate hedge review."),
        ("boj_yen_carry_risk", "THESIS_RISK_OFF_DISLOCATION_SCOUTING", "scout_detection", "Scout orders detect forced liquidation zones; second tranche remains blocked."),
        ("credit_stress", "THESIS_BANKS_NIM_ENGINE", "credit_quality_risk", "Credit deterioration can override NIM benefit."),
        ("vix_volatility_regime", "THESIS_VOLATILITY_HEDGE", "hedge_signal", "Volatility strength confirms hedge utility but requires profit/risk review."),
    ]
    return {
        "schema_version": CSG_SCHEMA_VERSION,
        "governance_version": CSG_VERSION,
        "generated_at": generated_at,
        "events": [
            {
                "event_key": event,
                "thesis_id": thesis,
                "relationship": relationship,
                "reconciliation_note": note,
            }
            for event, thesis, relationship, note in rows
        ],
    }


def build_reconciliation_matrix(generated_at: str) -> Dict[str, Any]:
    rows = [
        {
            "claim_tag": "GOLD_TACTICAL_WEAKNESS",
            "strategic_context_required": "Structural inflation / fiscal dominance thesis and kill conditions",
            "allowed_output": "Gold timing is tactically weak; structural thesis remains active pending kill-condition review.",
            "blocked_output": "Gold thesis is invalidated by one tactical score.",
        },
        {
            "claim_tag": "IRAN_PEACE_GOLD_RELIEF",
            "strategic_context_required": "Separate geopolitical premium from inflation/fiscal dominance premium",
            "allowed_output": "Peace headline reduces immediate war premium but does not by itself negate structural gold.",
            "blocked_output": "Iran peace means sell all gold miners.",
        },
        {
            "claim_tag": "BANKS_DIRECTIONAL_CALL",
            "strategic_context_required": "NIM, curve, credit, BAC/WFC/XLF, deposit beta",
            "allowed_output": "Bank view is provisional until curve and credit evidence are reconciled.",
            "blocked_output": "Banks are simple risk-on beta without NIM/credit context.",
        },
        {
            "claim_tag": "SCOUT_ORDER_FILLED",
            "strategic_context_required": "Scout size, second tranche gate, CIO_ONLY_MANUAL",
            "allowed_output": "Scout order is a detection position; second tranche remains separately blocked.",
            "blocked_output": "Scout fill authorizes full deployment.",
        },
        {
            "claim_tag": "SATELLITE_POSITION",
            "strategic_context_required": "Satellite/core distinction and liquidity limits",
            "allowed_output": "Satellite exposure is convex optionality, not core allocation.",
            "blocked_output": "Satellite names are core holdings.",
        },
        {
            "claim_tag": "CASH_WEIGHT_HIGH",
            "strategic_context_required": "Cash fortress mode and CIO posture",
            "allowed_output": "High cash is intentional optionality under WAIT/HOLD/REVIEW.",
            "blocked_output": "High cash is automatically a portfolio defect.",
        },
    ]
    return {
        "schema_version": CSG_SCHEMA_VERSION,
        "governance_version": CSG_VERSION,
        "generated_at": generated_at,
        "rows": rows,
    }


def build_required_briefing_points(generated_at: str) -> Dict[str, Any]:
    points = [
        "State whether tactical score changes timing or structural thesis validity.",
        "For gold/gold miners, mention structural inflation/fiscal dominance context and kill conditions.",
        "For banks, include NIM, curve, credit, BAC/WFC/XLF context before directional claims.",
        "For scout orders, distinguish scout detection from second tranche deployment.",
        "For satellites, state satellite/core classification.",
        "Preserve CIO_ONLY_MANUAL and order routing disabled.",
        "Include probability/confidence language when making forecasts.",
        "Link current events to thesis registry where relevant.",
    ]
    return {"generated_at": generated_at, "required_briefing_points": points}


def build_forbidden_interpretations(generated_at: str) -> Dict[str, Any]:
    forbidden = [
        "Do not state that Iran peace invalidates gold without structural reconciliation.",
        "Do not call banks bullish/bearish without NIM, curve, credit, BAC/WFC/XLF.",
        "Do not confuse scout orders with second tranche authorization.",
        "Do not classify satellite convexity names as core holdings.",
        "Do not imply automatic execution; CIO_ONLY_MANUAL remains mandatory.",
        "Do not override deterministic blocked actions with narrative enthusiasm.",
        "Do not omit kill conditions when challenging an active structural thesis.",
    ]
    return {"generated_at": generated_at, "forbidden_interpretations": forbidden}


def build_governance(dataset: Dict[str, Any], generated_at: str, output_files: Dict[str, str]) -> Dict[str, Any]:
    return {
        "schema_version": CSG_SCHEMA_VERSION,
        "governance_version": CSG_VERSION,
        "status": "ACTIVE",
        "mandatory_for_chief_strategist": True,
        "generated_at": generated_at,
        "source_priority": [
            "broker_portfolio_and_orders",
            "governance_gate_approved_truth",
            "deterministic_operators",
            "thesis_registry",
            "market_data",
            "news_and_external_evidence",
            "llm_agent_commentary",
        ],
        "hard_rules": [
            "TACTICAL_SCORE_MODIFIES_TIMING_NOT_THESIS_VALIDITY",
            "STRUCTURAL_THESIS_REQUIRES_KILL_CONDITION_FOR_INVALIDATION",
            "CIO_ONLY_MANUAL",
            "ORDER_ROUTING_DISABLED",
            "SCOUT_ORDER_NOT_SECOND_TRANCHE_AUTHORIZATION",
            "SATELLITE_NOT_CORE_WITHOUT_REGISTRY_APPROVAL",
        ],
        "required_dataset_keys": [
            "chief_strategist_governance",
            "active_thesis_reconciliation",
            "strategic_tactical_reconciliation_matrix",
        ],
        "output_files": output_files,
        "dataset_hash_before_embedding": _json_hash(dataset),
    }


def build_chief_strategist_context(
    governance: Dict[str, Any],
    registry: Dict[str, Any],
    active_reconciliation: Dict[str, Any],
    event_map: Dict[str, Any],
    reconciliation_matrix: Dict[str, Any],
    required_points: Dict[str, Any],
    forbidden: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": CSG_SCHEMA_VERSION,
        "governance_version": CSG_VERSION,
        "generated_at": governance.get("generated_at"),
        "governance": governance,
        "thesis_registry": registry,
        "active_thesis_reconciliation": active_reconciliation,
        "event_thesis_map": event_map,
        "strategic_tactical_reconciliation_matrix": reconciliation_matrix,
        "required_briefing_points": required_points.get("required_briefing_points", []),
        "forbidden_interpretations": forbidden.get("forbidden_interpretations", []),
    }


def build_chief_strategist_governance_pack(
    dataset_path: Path = DEFAULT_DATASET,
    output_dir: Path = CSG_DIR,
    embed: bool = True,
) -> Dict[str, Any]:
    dataset_path = Path(dataset_path)
    output_dir = Path(output_dir)
    dataset = _read_json(dataset_path)
    generated_at = _utc_now()

    output_files = {
        "thesis_registry": str(output_dir / "thesis_registry.json"),
        "event_thesis_map": str(output_dir / "event_thesis_map_latest.json"),
        "reconciliation_matrix": str(output_dir / "reconciliation_matrix_latest.json"),
        "chief_strategist_context": str(output_dir / "chief_strategist_context_latest.json"),
        "reply_audit": str(output_dir / "chief_strategist_reply_audit_latest.json"),
        "required_briefing_points": str(output_dir / "required_briefing_points_latest.json"),
        "forbidden_interpretations": str(output_dir / "forbidden_interpretations_latest.json"),
    }
    registry = build_thesis_registry(generated_at)
    active_reconciliation = build_active_thesis_reconciliation(dataset, generated_at)
    event_map = build_event_thesis_map(generated_at)
    reconciliation_matrix = build_reconciliation_matrix(generated_at)
    required_points = build_required_briefing_points(generated_at)
    forbidden = build_forbidden_interpretations(generated_at)
    governance = build_governance(dataset, generated_at, output_files)
    context = build_chief_strategist_context(
        governance,
        registry,
        active_reconciliation,
        event_map,
        reconciliation_matrix,
        required_points,
        forbidden,
    )

    _atomic_write_json(output_dir / "thesis_registry.json", registry)
    _atomic_write_json(output_dir / "event_thesis_map_latest.json", event_map)
    _atomic_write_json(output_dir / "reconciliation_matrix_latest.json", reconciliation_matrix)
    _atomic_write_json(output_dir / "required_briefing_points_latest.json", required_points)
    _atomic_write_json(output_dir / "forbidden_interpretations_latest.json", forbidden)
    _atomic_write_json(output_dir / "chief_strategist_context_latest.json", context)

    if embed and dataset:
        dataset["chief_strategist_governance"] = governance
        dataset["active_thesis_reconciliation"] = active_reconciliation
        dataset["strategic_tactical_reconciliation_matrix"] = reconciliation_matrix
        dataset["event_thesis_map"] = event_map
        dataset["required_briefing_points"] = required_points.get("required_briefing_points", [])
        dataset["forbidden_interpretations"] = forbidden.get("forbidden_interpretations", [])
        dataset.setdefault("meta", {})["chief_strategist_governance_version"] = CSG_VERSION
        dataset.setdefault("meta", {})["chief_strategist_governance_generated_at"] = generated_at
        _atomic_write_json(dataset_path, dataset)

    manifest = {
        "status": "PASS",
        "generated_at": generated_at,
        "governance_version": CSG_VERSION,
        "dataset_path": str(dataset_path),
        "embedded": bool(embed and dataset),
        "output_files": output_files,
        "context_hash": _json_hash(context),
    }
    _atomic_write_json(output_dir / "chief_strategist_governance_manifest_latest.json", manifest)
    return manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build BlueLotus V3 Chief Strategist Governance pack.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(CSG_DIR))
    parser.add_argument("--no-embed", action="store_true")
    args = parser.parse_args(argv)
    manifest = build_chief_strategist_governance_pack(
        dataset_path=Path(args.dataset),
        output_dir=Path(args.output_dir),
        embed=not args.no_embed,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
