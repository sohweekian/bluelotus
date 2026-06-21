from __future__ import annotations

CANONICAL_VERSION = "v3.1-canonical-contract"

ALLOWED_CANONICAL_SESSIONS = {
    "REGULAR_OPEN",
    "PRE_MARKET",
    "AFTER_HOURS",
    "MARKET_CLOSED_LAST_REGULAR_CLOSE",
    "WEEKEND_SNAPSHOT",
    "HOLIDAY_CLOSED",
    "UNKNOWN_REQUIRES_REVIEW",
}

ARTIFACT_STATUS_VALUES = {
    "ARTIFACTS_CONSISTENT",
    "ARTIFACT_TIMESTAMP_MISMATCH",
    "ARTIFACT_SECTION_MISSING",
    "ARTIFACT_HASH_MISMATCH",
    "ARTIFACT_STALE",
    "PUBLICATION_BLOCKED",
}

TARGET_ACTION_CLASSIFICATIONS = {
    "LOAD_ALLOWED",
    "HALF_LOAD_ONLY",
    "KELLY_SUPPORTED_BUT_PEI_MACRO_GATED",
    "PULLBACK_ONLY_ADD",
    "HOLD_OBSERVE",
    "TRIM_REVIEW",
    "HEDGE_RETAIN",
    "ADD_BLOCKED",
    "DE_RISK_REVIEW",
    "HEDGE_INSTRUMENT_EXCLUDED_FROM_EQUITY_KELLY",
    "CIO_REVIEW_REQUIRED",
}

REQUIRED_CANONICAL_ROOT_KEYS = {
    "version",
    "generated_at",
    "governance",
    "market_state",
    "session_state",
    "portfolio_state",
    "order_state",
    "risk_state",
    "pei_state",
    "str_state",
    "target_usd_vector",
    "artifact_manifest",
    "truth_source_audit",
}

SECTION_COVERAGE_KEYS = [
    "00_MASTER_PROMPT",
    "00A_LAW_ORDER_GOVERNANCE",
    "00B_PEI",
    "00C_STR",
    "00D_BUG_CLEARANCE",
    "00E_ARTIFACT_MANIFEST",
    "00F_BENCHMARK_DASHBOARD",
    "PORTFOLIO",
    "RISK_MODEL",
    "EXECUTION_INTELLIGENCE",
    "DETERMINISTIC_OPERATOR",
    "TARGET_USD_VECTOR",
    "BENCHMARK_DASHBOARD",
]

