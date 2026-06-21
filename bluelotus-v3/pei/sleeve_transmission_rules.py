from __future__ import annotations


SLEEVE_TRANSMISSION_RULES = {
    "high_beta_relief_basket": ["RATES", "VOLATILITY", "INSTITUTIONAL_FLOW", "SECTOR_ROTATION"],
    "pl_asts_tactical_cash_generation_engine": ["REFLEXIVE_SUPPRESSION", "PRIVATE_MARKET_LIQUIDITY", "SECTOR_ROTATION"],
    "gold_miners": ["REAL_YIELDS", "USD", "OIL_RISK_PREMIUM", "NARRATIVE_SURVIVAL"],
    "banks_bac_wfc": ["RATES", "CREDIT", "USD", "EARNINGS_REVISION"],
    "volatility_hedge": ["VOLATILITY", "YEN_CARRY", "CREDIT", "OIL_RISK_PREMIUM"],
    "cash_fortress": ["CREDIT", "VOLATILITY", "GOVERNANCE", "NARRATIVE_SURVIVAL"],
    "ai_semis": ["AI_CAPEX", "VALUATION_COMPRESSION", "SECTOR_ROTATION"],
    "space_defense": ["PRIVATE_MARKET_LIQUIDITY", "REFLEXIVE_SUPPRESSION", "SECTOR_ROTATION"],
    "quantum": ["SECTOR_ROTATION", "VALUATION_COMPRESSION", "INSTITUTIONAL_FLOW"],
    "energy_oil": ["OIL_RISK_PREMIUM", "GEOPOLITICAL_RISK"],
    "credit_liquidity": ["CREDIT", "VOLATILITY", "USD", "YEN_CARRY"],
}
