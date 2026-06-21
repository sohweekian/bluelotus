# BlueLotus V2 Dataset Contract

Purpose:

- Validate `dataset_raw.json` before it reaches CIO reporting.
- Enforce required top-level blocks, JSON types, ticker coverage, forecasting blocks, risk model blocks, cross-market confirmation, and CIO-only execution doctrine.
- Produce a machine-readable audit artifact for every manual or smoke-gate run.

Run:

```powershell
C:\bluelotus3\run_bluelotus_v2_dataset_contract.bat
```

Archive a timestamped copy:

```powershell
C:\bluelotus3\run_bluelotus_v2_dataset_contract.bat --archive --label manual
```

Output:

```text
C:\bluelotus3\data\audit\dataset_contract_latest.json
C:\bluelotus3\data\audit\dataset_contract_archive\
```

Core contract checks:

- Required production blocks exist and have the expected JSON type.
- `meta` has export version, ingest version, generated timestamp, source counts, and signal counts.
- Coverage thresholds are met for live prices, analyst targets, fundamentals, capital flow, source health, latest signals, security master, and historical prices.
- Security master ticker classifications are populated.
- Portfolio, risk, and target-weight blocks preserve the CIO-only read/extract doctrine.
- Read-only Moomoo order/deal history blocks preserve the CIO-only no-routing doctrine.
- Cross-market confirmation has coverage, derived scores, and interpretation flags.
- Risk model has operational status, return observations, VaR, factor exposure, and portfolio beta.
- Forecasting contains both `BLUELOTUS_CONSERVATIVE` and `ANALYST_CONSENSUS`.
- Institutional quant readiness score is at least 90 and no institutional process has `FAIL`.
- Data-quality SLA source coverage is present; SLA breaches are warnings unless another contract rule fails.

Exit behavior:

- Returns `0` when there are no `FAIL` findings.
- Returns `1` when any `FAIL` finding exists.
- Returns `2` with `--strict` when warnings exist but no failures exist.

Doctrine:

- No database writes.
- No Moomoo or broker calls.
- No pipeline execution.
- No order generation.

