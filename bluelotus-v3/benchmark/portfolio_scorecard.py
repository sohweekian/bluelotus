from __future__ import annotations

from typing import Any, Dict


def build_portfolio_scorecard(dataset: Dict[str, Any]) -> Dict[str, object]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    risk = dataset.get("risk_overlay") if isinstance(dataset.get("risk_overlay"), dict) else {}
    risk_portfolio = risk.get("portfolio") if isinstance(risk.get("portfolio"), dict) else {}
    return {
        "portfolio_value": portfolio.get("total_assets") or portfolio.get("total_value"),
        "cash_weight": risk_portfolio.get("cash_weight"),
        "cash_overlay_status": risk_portfolio.get("cash_overlay_status"),
        "risk_overlay_status": risk.get("risk_overlay_status"),
        "portfolio_scorecard_status": "OBSERVE",
    }

