# Sanitization Manifest

Source tree: `C:\bluelotus3`

Public package path: `bluelotus-v3/`

## Included

- Source modules for agents, governance, orchestration, research, MID, LLM clients, thesis evaluation, dashboard support, and tests.
- Configuration templates and schema contracts that refer to environment variables rather than real secrets.
- Technical documentation, architecture writeups, thesis documents, and selected research reports.
- Root launchers and health-check scripts that do not embed secrets or live order books.

## Excluded

- `C:\bluelotus3\.env`
- `C:\bluelotus3\.vs`
- `C:\bluelotus3\.pytest_cache`
- `C:\bluelotus3\data`
- `C:\bluelotus3\db`
- `C:\bluelotus3\logs`
- `C:\bluelotus3\temp`
- `C:\bluelotus3\archive`
- `C:\bluelotus3\replay`
- `__pycache__` folders and compiled Python files
- local database files, SQLite indexes, logs, temporary files, and generated JSONL/CSV/XLSX outputs
- `moomoo_trader.py`, because it contains live trading defaults and working order levels

## Review Performed

- Removed known secret-bearing and generated-output directories.
- Kept `.env.template` only.
- Scanned sanitized files for common credential terms.
- Excluded live broker/trading execution artifacts by default.

