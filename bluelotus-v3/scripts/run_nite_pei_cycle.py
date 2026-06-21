"""
BlueLotus V3 - NITE-PEI Cycle Runner
====================================
Runs NITE-PEI against live dataset_raw.json events, updates thesis
probabilities, writes Brier preregistration records, and writes
nite_pei_block.json into the latest V3 cycle folder for publisher pickup.

Run:
  python -m scripts.run_nite_pei_cycle

Governance:
  Advisory only. No broker routing. No generated orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nite_pei.bayesian_updater import compute_posterior, get_lr, reload_lr_table
from nite_pei.brier_calibration_loop import write_forecast_record
from nite_pei.cio_advisory_renderer import build_nite_pei_block, determine_posture, render_advisory_text
from nite_pei.ckri_calculator import compute_ckri_from_registry, write_risk_state
from nite_pei.event_classifier import classify_event
from nite_pei.kelly_nite_coupler import build_kelly_advisory
from nite_pei.kill_condition_state_machine import build_kill_state_snapshot, update_kill_conditions, worst_kill_state
from nite_pei.thesis_registry_writer import load_thesis_registry, save_thesis_registry

_ROOT = Path(__file__).resolve().parents[1]
_DATASET_PATH = _ROOT / "data" / "frontend" / "dataset_raw.json"
_REGISTRY_PATH = _ROOT / "config" / "thesis_registry.yaml"
_CYCLES_ROOT = _ROOT / "data" / "v3_cycles"

THESIS_EVENT_MAP: dict[str, list[str]] = {
    "TRUMP_UNCERTAINTY_THESIS": ["GEOPOLITICAL_ESCALATION", "GEOPOLITICAL_DEESCALATION", "YEN_CARRY_RISK", "CENTRAL_BANK_HAWKISH"],
    "PETRO_RECYCLED_DOLLAR_THESIS": ["GEOPOLITICAL_ESCALATION", "SANCTIONS_NEW", "YEN_CARRY_RISK", "RECESSION_SIGNAL"],
    "STICKY_INFLATION_THESIS": ["CENTRAL_BANK_HAWKISH", "CENTRAL_BANK_DOVISH", "INFLATION_ABOVE_EXPECTATION", "INFLATION_BELOW_EXPECTATION", "YEN_CARRY_RISK"],
    "HAWKISH_WARSH_THESIS": ["CENTRAL_BANK_HAWKISH", "CENTRAL_BANK_DOVISH", "INFLATION_ABOVE_EXPECTATION", "INFLATION_BELOW_EXPECTATION", "YEN_CARRY_RISK"],
    "HAWKISH_BOJ_THESIS": ["YEN_CARRY_RISK", "CENTRAL_BANK_HAWKISH", "CENTRAL_BANK_DOVISH"],
}


def sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


def stable_event_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def latest_cycle_dir() -> Optional[Path]:
    if not _CYCLES_ROOT.exists():
        return None
    folders = sorted([d for d in _CYCLES_ROOT.iterdir() if d.is_dir() and d.name.startswith("v3_cycle_")])
    return folders[-1] if folders else None


def load_dataset(path: Path = _DATASET_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: dataset_raw not loaded: {exc}")
        return {}


def source_tier_from_signal(signal: Dict[str, Any]) -> int:
    score = signal.get("quality_score")
    try:
        q = float(score)
    except (TypeError, ValueError):
        q = 0.65
    if q >= 0.90:
        return 1
    if q >= 0.75:
        return 2
    if q >= 0.50:
        return 3
    return 4


def infer_macro_tickers(event: str, impact_class: str) -> List[str]:
    text = f"{event} {impact_class}".lower()
    tickers: List[str] = []
    if "boj" in text or "yen" in text or "fx" in text:
        tickers.extend(["VXX", "VIXY"])
    if "fomc" in text or "fed" in text or "rate" in text:
        tickers.extend(["TLT", "SHY", "GLD"])
    if "oil" in text or "hormuz" in text:
        tickers.extend(["USO", "XLE"])
    return list(dict.fromkeys(tickers))


def event_from_signal(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = str(signal.get("raw_text") or signal.get("headline") or signal.get("title") or "").strip()
    if not text:
        return None
    sid = signal.get("id")
    event_id = f"signal:{sid}" if sid is not None else stable_event_id("signal", signal.get("source"), signal.get("received_at"), text)
    return {
        "event_id": event_id,
        "raw_headline": text,
        "source": str(signal.get("source") or signal.get("source_feed") or "signals_latest"),
        "source_tier": source_tier_from_signal(signal),
        "affected_tickers": [str(t).upper() for t in signal.get("ticker_tags", []) if t] if isinstance(signal.get("ticker_tags"), list) else [],
        "published_at": signal.get("published_at") or signal.get("received_at") or "",
        "source_url": signal.get("source_url") or "",
    }


def event_from_macro(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event = str(item.get("event") or "").strip()
    if not event:
        return None
    impact = str(item.get("impact_class") or "")
    return {
        "event_id": stable_event_id("macro", item.get("event_date"), event, impact),
        "raw_headline": f"{event} {impact}".strip(),
        "source": f"macro_event_risks:{item.get('category', '')}",
        "source_tier": 1,
        "affected_tickers": infer_macro_tickers(event, impact),
        "published_at": item.get("event_date") or "",
        "source_url": "",
    }


def events_from_ticker_sentiment(dataset: Dict[str, Any], max_headlines_per_ticker: int = 3) -> Iterable[Dict[str, Any]]:
    sentiment = dataset.get("ticker_sentiment")
    if not isinstance(sentiment, dict):
        return []
    events: List[Dict[str, Any]] = []
    for ticker, payload in sentiment.items():
        if not isinstance(payload, dict):
            continue
        headlines = payload.get("headlines") or []
        if not isinstance(headlines, list):
            continue
        for idx, headline in enumerate(headlines[:max_headlines_per_ticker]):
            text = str(headline).strip()
            if not text:
                continue
            events.append({
                "event_id": stable_event_id("ticker_sentiment", ticker, payload.get("cycle_ts"), idx, text),
                "raw_headline": text,
                "source": f"ticker_sentiment:{ticker}",
                "source_tier": 3,
                "affected_tickers": [str(ticker).upper()],
                "published_at": payload.get("cycle_ts") or "",
                "source_url": "",
            })
    return events


def extract_live_events(dataset: Dict[str, Any], max_signals: int = 150) -> List[Dict[str, Any]]:
    """Extract candidate events from dataset_raw.json without hardcoded headlines."""
    events: List[Dict[str, Any]] = []

    for signal in dataset.get("signals_latest", [])[:max_signals] if isinstance(dataset.get("signals_latest"), list) else []:
        if isinstance(signal, dict):
            event = event_from_signal(signal)
            if event:
                events.append(event)

    for macro in dataset.get("macro_event_risks", []) if isinstance(dataset.get("macro_event_risks"), list) else []:
        if isinstance(macro, dict):
            event = event_from_macro(macro)
            if event:
                events.append(event)

    events.extend(events_from_ticker_sentiment(dataset))

    deduped: Dict[str, Dict[str, Any]] = {}
    for event in events:
        deduped.setdefault(event["event_id"], event)
    return list(deduped.values())


def classify_live_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    classified: List[Dict[str, Any]] = []
    for event in events:
        result = classify_event(event["raw_headline"], event.get("affected_tickers", []), event.get("source_tier", 3))
        if result["event_class"] == "UNKNOWN":
            continue
        classified.append({**event, **result})
    return classified


def prior_event_ids(thesis_data: Dict[str, Any]) -> set[str]:
    seen: set[str] = set()
    history = thesis_data.get("probability_history", [])
    if not isinstance(history, list):
        return seen
    for record in history:
        if not isinstance(record, dict):
            continue
        for key in ("event_ids", "applied_event_ids"):
            value = record.get(key)
            if isinstance(value, list):
                seen.update(str(item) for item in value if item)
        if record.get("event_id"):
            seen.add(str(record["event_id"]))
    return seen


def affected_tickers_for_thesis(thesis_data: Dict[str, Any]) -> List[str]:
    mapped = thesis_data.get("mapped_assets", [])
    if isinstance(mapped, list):
        return [str(t).upper() for t in mapped]
    if isinstance(mapped, dict):
        tickers: List[str] = []
        for value in mapped.values():
            if isinstance(value, list):
                tickers.extend(str(t).upper() for t in value)
        return list(dict.fromkeys(tickers))
    return []


def load_agent_reports(cycle_dir: Optional[Path]) -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    if not cycle_dir:
        return reports
    report_dir = cycle_dir / "agent_reports"
    if not report_dir.exists():
        return reports
    for path in sorted(report_dir.glob("*.json")):
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return reports


def run(dataset_path: Path = _DATASET_PATH, registry_path: Path = _REGISTRY_PATH, cycle_dir: Optional[Path] = None) -> Dict[str, Any]:
    reload_lr_table()
    dataset = load_dataset(dataset_path)
    raw_events = extract_live_events(dataset)
    classified = classify_live_events(raw_events)

    print(f"  Candidate events extracted: {len(raw_events)}")
    print(f"  Classified events retained: {len(classified)}")
    for event in classified[:20]:
        print(f"  CLASSIFY [{event['event_class']}] id={event['event_id']} tier=T{event['source_tier']} | {event['raw_headline'][:90]}")
    if len(classified) > 20:
        print(f"  ... {len(classified) - 20} more classified events omitted from console")

    registry = load_thesis_registry(registry_path)
    target_cycle_dir = cycle_dir or latest_cycle_dir()
    target_cycle_id = target_cycle_dir.name if target_cycle_dir else "NO_CYCLE"
    thesis_snapshots: List[Dict[str, Any]] = []
    kelly_advisories: List[Dict[str, Any]] = []

    for thesis_id, thesis_data in registry.get("theses", {}).items():
        if str(thesis_data.get("status", "")).lower() not in ("active", "watch"):
            continue

        thesis_type = str(thesis_data.get("thesis_type", thesis_id))
        p_prior = float(thesis_data.get("current_probability", 0.50))
        p_current = p_prior
        relevant_classes = set(THESIS_EVENT_MAP.get(thesis_id, []))
        already_seen = prior_event_ids(thesis_data)
        events_applied: List[Dict[str, Any]] = []
        lr_lookups: List[Dict[str, Any]] = []
        kill_conds = list(thesis_data.get("kill_conditions", []))

        for event in classified:
            event_id = str(event["event_id"])
            event_class = str(event["event_class"])
            if event_class not in relevant_classes or event_id in already_seen:
                continue

            lr_result = get_lr(event_class, thesis_type, event["noise_discount_factor"], None)
            post_result = compute_posterior(p_current, lr_result["lr_adjusted"])
            prior_odds = round(p_current / (1.0 - p_current), 6)
            posterior_odds = round(prior_odds * lr_result["lr_adjusted"], 6)

            events_applied.append({
                "event_id": event_id,
                "event_class": event_class,
                "raw_headline": event["raw_headline"],
                "source": event["source"],
                "source_tier": event["source_tier"],
                "published_at": event.get("published_at", ""),
                "source_url": event.get("source_url", ""),
                "matched_keyword": event.get("matched_keyword"),
                "noise_discount_factor": event["noise_discount_factor"],
                "lr_raw": lr_result["lr_raw"],
                "lr_adjusted": lr_result["lr_adjusted"],
                "lr_source": lr_result["lr_source"],
                "confidence": lr_result["confidence"],
                "bayesian_equation": {
                    "step_1_prior_odds": f"prior_odds = P/(1-P) = {p_current:.4f} / {1-p_current:.4f} = {prior_odds:.4f}",
                    "step_2_lr_adjustment": (
                        f"LR_adjusted = 1 + (LR_raw({lr_result['lr_raw']:.4f}) - 1) "
                        f"x (1 - noise_discount({event['noise_discount_factor']:.2f})) = {lr_result['lr_adjusted']:.4f}"
                    ),
                    "step_3_posterior_odds": f"posterior_odds = prior_odds({prior_odds:.4f}) x LR_adjusted({lr_result['lr_adjusted']:.4f}) = {posterior_odds:.4f}",
                    "step_4_posterior_prob": f"P_posterior = posterior_odds / (1 + posterior_odds) = {posterior_odds:.4f} / {1+posterior_odds:.4f} = {post_result['p_posterior']:.4f}",
                    "step_5_clamp": f"clamp([0.05, 0.95]) => {post_result['p_posterior']:.4f}",
                    "delta_p": f"{post_result['delta_p']:+.4f}",
                },
                "p_prior_step": round(p_current, 6),
                "p_posterior_step": post_result["p_posterior"],
                "delta_p_step": post_result["delta_p"],
            })
            lr_lookups.append({
                "event_id": event_id,
                "event_class": event_class,
                "lr_adjusted": lr_result["lr_adjusted"],
                "lr_source": lr_result["lr_source"],
                "confidence": lr_result["confidence"],
            })
            kill_conds = update_kill_conditions(kill_conds, event_class, post_result["p_posterior"])
            p_current = post_result["p_posterior"]

        event_ids = [event["event_id"] for event in events_applied]
        delta_total = round(p_current - p_prior, 6)
        brier_record_id = ""
        if events_applied:
            combined_event_id = stable_event_id("nite_pei_cycle", target_cycle_id, thesis_id, ",".join(event_ids))
            combined_lr = round((p_current / (1 - p_current)) / (p_prior / (1 - p_prior)), 6) if 0 < p_prior < 1 and 0 < p_current < 1 else 1.0
            brier_record_id = write_forecast_record(
                thesis_id=thesis_id,
                event_id=combined_event_id,
                p_prior=p_prior,
                lr_used=combined_lr,
                lr_source=f"NITE_PEI_COMBINED/{thesis_type}",
                p_posterior=p_current,
                delta_p=delta_total,
            )

            prob_hist = list(thesis_data.get("probability_history", []))
            prob_hist.append({
                "p_prior": round(p_prior, 6),
                "p_posterior": round(p_current, 6),
                "delta_p": delta_total,
                "events": len(events_applied),
                "event_ids": event_ids,
                "brier_record_id": brier_record_id,
                "cycle": target_cycle_id,
                "created_at_sgt": sgt_now(),
            })
            thesis_data["probability_history"] = prob_hist
            thesis_data["current_probability"] = round(p_current, 6)
            thesis_data["kill_conditions"] = kill_conds

        kill_snapshot = build_kill_state_snapshot(kill_conds)
        posture = determine_posture(delta_total, kill_snapshot)
        update_record = {
            "p_prior_initial": p_prior,
            "p_posterior_final": p_current,
            "delta_p_total": delta_total,
            "events_applied": events_applied,
            "lr_lookups": lr_lookups,
        }
        snapshot = {
            "thesis_id": thesis_id,
            "thesis_type": thesis_type,
            "P_prior": round(p_prior, 6),
            "P_posterior": round(p_current, 6),
            "delta_p": delta_total,
            "events_applied": events_applied,
            "event_ids": event_ids,
            "brier_record_id": brier_record_id,
            "lr_lookups": lr_lookups,
            "kill_state_snapshot": kill_snapshot,
            "worst_kill_state": worst_kill_state(kill_conds),
            "posture": posture,
            "advisory_text": render_advisory_text(thesis_id, update_record, None, posture),
        }
        thesis_snapshots.append(snapshot)

        tickers = affected_tickers_for_thesis(thesis_data)
        kelly_advisories.append(build_kelly_advisory(thesis_id, thesis_type, p_current, 0.15, tickers, dataset))

        print(f"  {thesis_id}: {p_prior:.4f} -> {p_current:.4f} ({delta_total:+.4f}) | events={len(events_applied)} | {posture.split(' — ')[0]}")

    save_thesis_registry(registry, registry_path)
    registry2 = load_thesis_registry(registry_path)
    ckri_result = compute_ckri_from_registry(registry2)
    write_risk_state(ckri_result)

    agent_reports = load_agent_reports(target_cycle_dir)
    block = build_nite_pei_block(thesis_snapshots, ckri_result, kelly_advisories, agent_reports)
    block["source_cycle_id"] = target_cycle_id
    block["source_cycle_path"] = str(target_cycle_dir) if target_cycle_dir else ""
    block["nite_pei_generated_at_sgt"] = sgt_now()
    block["generation_mode"] = "live_cycle" if target_cycle_dir else "no_cycle_available"
    block["event_extraction"] = {
        "dataset_path": str(dataset_path),
        "candidate_events": len(raw_events),
        "classified_events": len(classified),
        "applied_events": sum(len(item.get("events_applied", [])) for item in thesis_snapshots),
    }

    if target_cycle_dir:
        out = target_cycle_dir / "nite_pei_block.json"
        out.write_text(json.dumps(block, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  NITE-PEI block -> {out}")
    else:
        print("  WARNING: no V3 cycle folder available; block not written")

    print(f"  CKRI: {block['ckri']:.4f}  Zone: {block['ckri_zone']}")
    print(f"  Contradictions: {block['nite_pei_contradiction_count']} (P1: {block['nite_pei_p1_count']})")
    return block


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(_DATASET_PATH))
    parser.add_argument("--registry", default=str(_REGISTRY_PATH))
    parser.add_argument("--cycle-dir", default="")
    args = parser.parse_args()
    cycle_dir = Path(args.cycle_dir) if args.cycle_dir else None

    print("=" * 70)
    print("NITE-PEI CYCLE RUNNER - BlueLotus V3")
    print("=" * 70)
    run(Path(args.dataset), Path(args.registry), cycle_dir)
    print("Done. Run publisher to regenerate reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
