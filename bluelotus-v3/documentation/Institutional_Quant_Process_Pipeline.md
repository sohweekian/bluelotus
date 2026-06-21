# BlueLotus Institutional Quant Process Pipeline

## Purpose

This layer converts the institutional quant requirements into an auditable
database-backed process step.

It does not replace the existing MID ingest pipeline or `export_dataset_raw.py`.
It adds a new process-result layer that:

1. Reads the latest `data/frontend/dataset_raw.json`.
2. Runs institutional-readiness checks.
3. Stores the dataset snapshot, run summary, process results, and audit event in
   MySQL.
4. Lets `mid/export_dataset_raw.py` publish the latest completed run under the
   top-level `institutional_quant` key.

## New Files

- `mid/institutional_quant_tables.py`
  Creates the required MySQL tables.

- `mid/institutional_quant_pipeline.py`
  Runs the process checks and writes results to the database.

- `mid/export_dataset_raw.py`
  Updated to extract the latest completed institutional quant run into
  `dataset_raw.json`.

## New Database Tables

- `institutional_dataset_snapshots`
  Stores immutable dataset snapshots by SHA-256 hash.

- `institutional_quant_runs`
  Stores one row per process run, including readiness score and summary.

- `institutional_quant_process_results`
  Stores one row per process inside the run.

- `institutional_quant_audit_events`
  Stores lightweight audit events for process runs.

## Process Checks

The current v0.1 runner produces these process results:

- `data_quality`
- `point_in_time_readiness`
- `bias_controls`
- `signal_validation`
- `risk_model`
- `portfolio_construction`
- `execution_readiness`
- `monitoring_governance`

Each process writes:

- status: `PASS`, `WARNING`, or `FAIL`
- readiness score
- readiness label
- result JSON
- metrics JSON
- warnings JSON

## Run Commands

Create or verify tables:

```powershell
cd C:\bluelotus3\mid
python institutional_quant_pipeline.py --init-db-only
```

Dry run without database writes:

```powershell
cd C:\bluelotus3\mid
python institutional_quant_pipeline.py --dry-run
```

Run and write process results to MySQL:

```powershell
cd C:\bluelotus3\mid
python institutional_quant_pipeline.py
```

Rebuild `dataset_raw.json` from the extractor:

```powershell
cd C:\bluelotus3\mid
python -X utf8 export_dataset_raw.py
```

The project batch file now runs:

```text
python institutional_quant_pipeline.py
python export_dataset_raw.py
```

before the research report is generated.

## Current Result

The first stored run produced:

```text
run_id          : iq_20260606_102744_693805c4
status          : COMPLETED_WITH_GAPS
readiness score : 62.659
readiness label : DEVELOPING
processes       : 8
```

The rebuilt `dataset_raw.json` now includes:

```json
"institutional_quant": {
  "status": "COMPLETED_WITH_GAPS",
  "run_id": "iq_20260606_102744_693805c4",
  "readiness_score": 62.659,
  "readiness_label": "DEVELOPING",
  "processes": {
    "data_quality": "...",
    "point_in_time_readiness": "...",
    "bias_controls": "...",
    "signal_validation": "...",
    "risk_model": "...",
    "portfolio_construction": "...",
    "execution_readiness": "...",
    "monitoring_governance": "..."
  }
}
```

## Design Note

The process runner strips any prior `institutional_quant` block before hashing
or analyzing the dataset. This prevents the process layer from self-referencing
on future runs.

