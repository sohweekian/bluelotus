# BlueLotus V2 Smoke / Hygiene Diagnostics

Purpose:

- Validate the Windows V2 production tree without running the pipeline.
- Confirm Python runtime and package-import hygiene.
- Confirm MySQL version, schema coverage, required tables, and raw archive triggers.
- Confirm `dataset_raw.json`, reports, installer ZIP hygiene, and documentation markers.
- Confirm read-only Moomoo execution/order history blocks are exported and non-routing.
- Run the formal `dataset_raw.json` contract validator and write its audit artifact.
- AST-scan active Python code for forbidden broker execution calls.
- Optionally run a read-only Moomoo OpenD quote snapshot check.

Run:

```powershell
C:\bluelotus3\run_bluelotus_v2_smoke_hygiene.bat
```

Run with read-only Moomoo check:

```powershell
C:\bluelotus3\run_bluelotus_v2_smoke_hygiene.bat --check-moomoo
```

Archive a timestamped diagnostic copy:

```powershell
C:\bluelotus3\run_bluelotus_v2_smoke_hygiene.bat --check-moomoo --archive --label manual
```

Output:

```text
C:\bluelotus3\data\audit\smoke_hygiene_latest.json
C:\bluelotus3\data\audit\smoke_hygiene_archive\
C:\bluelotus3\data\audit\runtime_guard_latest.json
C:\bluelotus3\data\audit\dataset_contract_latest.json
```

Production hourly runner:

- Runs pre-flight diagnostics before each cycle.
- Skips the cycle if the pre-flight diagnostic returns any `FAIL`.
- Runs post-flight diagnostics after report generation.
- Archives both pre-flight and post-flight diagnostic JSON.

Doctrine:

- No database writes.
- No pipeline execution.
- No trade unlock.
- No order placement, modification, cancellation, or routing.

Related direct check:

```powershell
C:\bluelotus3\run_bluelotus_v2_dataset_contract.bat --archive --label manual
```

```powershell
C:\bluelotus3\run_bluelotus_v2_runtime_guard.bat --archive --label manual
```

