from __future__ import annotations

import json
from typing import Any, Dict, List

from db.v3_db_connection import get_v3_connection
from pei.common import sgt_now, stable_id
from pei.event_resolution_rules import default_resolution_date, resolution_rules_for_event
from pei.event_schema import PEIEvent


def _law_binding(dataset: Dict[str, Any]) -> Dict[str, Any]:
    value = dataset.get("law_governance_binding")
    return value if isinstance(value, dict) else {}


def _event_from_warsh(dataset: Dict[str, Any]) -> PEIEvent:
    law = _law_binding(dataset)
    return PEIEvent(
        event_id=stable_id("PEI_EVENT", "FED_POLICY", "Warsh hawkish Fed repricing"),
        event_type="FED_POLICY",
        event_title="Warsh hawkish Fed repricing",
        event_timestamp_sgt=sgt_now(),
        source_layer="thesis_widgets.hawkish_warsh",
        source_confidence=0.78,
        affected_assets=["QQQ", "IWM", "TLT", "SHY", "UUP", "VXX", "VIXY", "ASTS", "PL", "QBTS", "QUBT"],
        affected_sleeves=["high_beta_relief_basket", "volatility_hedge", "banks_bac_wfc", "cash_fortress", "gold_miners"],
        governing_thesis="Hawkish Fed repricing can dominate relief rallies and pressure high beta.",
        initial_hypothesis="Rates and dollar strength may cap risk appetite while vol hedges retain value.",
        confirmation_signals=["10Y/30Y yields rising", "UUP/USD firm", "QQQ/IWM fade", "VXX/VIXY green", "credit weakens"],
        contradiction_signals=["yields fall", "USD weakens", "credit calm", "high beta holds bid"],
        kill_conditions=["QQQ fades while VXX rises", "credit stress appears", "yen carry unwind accelerates"],
        resolution_date=default_resolution_date(5),
        resolution_criteria=resolution_rules_for_event("FED_POLICY"),
        governance_pack_id=law.get("governance_pack_id", ""),
        report_memory_binding_id=law.get("report_memory_binding_id", ""),
    )


def _event_from_boj(dataset: Dict[str, Any]) -> PEIEvent:
    law = _law_binding(dataset)
    return PEIEvent(
        event_id=stable_id("PEI_EVENT", "YEN_CARRY_RISK", "BOJ yen carry unwind watch"),
        event_type="YEN_CARRY_RISK",
        event_title="BOJ yen carry unwind watch",
        event_timestamp_sgt=sgt_now(),
        source_layer="thesis_widgets.boj_yen_carry_event_watcher",
        source_confidence=0.76,
        affected_assets=["USDJPY", "EWJ", "DXJ", "VXX", "UVXY", "QQQ", "IWM", "ASTS", "PL"],
        affected_sleeves=["volatility_hedge", "high_beta_relief_basket", "cash_fortress", "credit_liquidity"],
        governing_thesis="Yen strength and BOJ hawkishness can force carry unwind and liquidation selling.",
        initial_hypothesis="Carry stress is active but requires cross-market confirmation before severe classification.",
        confirmation_signals=["USD/JPY breaks lower", "VXX/UVXY spike", "EWJ/DXJ weaken", "U.S. high beta sells off", "credit weakens"],
        contradiction_signals=["USD/JPY stabilizes", "Japan equities recover", "volatility fades", "credit calm"],
        kill_conditions=["USDJPY breakdown plus VXX spike plus QQQ/IWM selloff"],
        resolution_date=default_resolution_date(5),
        resolution_criteria=resolution_rules_for_event("BOJ_POLICY"),
        governance_pack_id=law.get("governance_pack_id", ""),
        report_memory_binding_id=law.get("report_memory_binding_id", ""),
    )


def _event_from_space_liquidity(dataset: Dict[str, Any]) -> PEIEvent:
    law = _law_binding(dataset)
    return PEIEvent(
        event_id=stable_id("PEI_EVENT", "PRIVATE_MARKET_CAPITAL_ABSORPTION", "SpaceX capital absorption / ASTS proxy suppression"),
        event_type="PRIVATE_MARKET_CAPITAL_ABSORPTION",
        event_title="SpaceX capital absorption / ASTS proxy suppression",
        event_timestamp_sgt=sgt_now(),
        source_layer="live_news + PEI thesis",
        source_confidence=0.66,
        affected_assets=["ASTS", "RKLB", "LUNR", "PL", "RDW", "SPCE", "BKSY", "SATS", "GSAT", "IRDM", "VSAT"],
        affected_sleeves=["space_defense", "pl_asts_tactical_cash_generation_engine", "high_beta_relief_basket"],
        governing_thesis="Public space proxies can be mechanically suppressed by private-market capital absorption without thesis failure.",
        initial_hypothesis="ASTS weakness may be reflexive suppression rather than breakdown if space thesis evidence remains intact.",
        confirmation_signals=["ASTS down while theme basket less weak", "SpaceX financing headline", "own catalysts intact", "no systemic credit breakdown"],
        contradiction_signals=["space basket broadly breaks", "own catalysts deteriorate", "outflows accelerate with credit stress"],
        kill_conditions=["theme basket fails", "ASTS catalyst breaks", "credit/liquidity systemic stress confirms"],
        resolution_date=default_resolution_date(10),
        resolution_criteria=resolution_rules_for_event("PRIVATE_MARKET_CAPITAL_ABSORPTION"),
        governance_pack_id=law.get("governance_pack_id", ""),
        report_memory_binding_id=law.get("report_memory_binding_id", ""),
    )


def build_candidate_events(dataset: Dict[str, Any]) -> List[PEIEvent]:
    events = [_event_from_warsh(dataset), _event_from_boj(dataset), _event_from_space_liquidity(dataset)]
    return events


def persist_events(events: List[PEIEvent]) -> None:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        now = sgt_now()
        for event in events:
            cur.execute(
                """
                INSERT INTO pei_event_registry (
                    event_id, event_type, event_title, event_timestamp_sgt,
                    source_layer, source_confidence, event_status, affected_sleeves,
                    governing_thesis, resolution_date, resolution_status,
                    governance_pack_id, report_memory_binding_id, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    source_confidence=VALUES(source_confidence),
                    event_status=VALUES(event_status),
                    affected_sleeves=VALUES(affected_sleeves),
                    governing_thesis=VALUES(governing_thesis),
                    updated_at=VALUES(updated_at)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.event_title,
                    event.event_timestamp_sgt,
                    event.source_layer,
                    event.source_confidence,
                    event.event_status,
                    json.dumps(event.affected_sleeves),
                    event.governing_thesis,
                    event.resolution_date,
                    "PENDING",
                    event.governance_pack_id,
                    event.report_memory_binding_id,
                    now,
                    now,
                ),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()
