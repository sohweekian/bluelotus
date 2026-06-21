# BlueLotus V2 Runtime Guard

Purpose:

- Confirm the active Python runtime is suitable for Windows production.
- Confirm the production virtual environment at `C:\bluelotus3\.venv` exists and is used when required.
- Confirm all required Python packages import correctly.
- Write a machine-readable runtime audit artifact.

Run:

```powershell
C:\bluelotus3\run_bluelotus_v2_runtime_guard.bat --archive --label manual
```

Require the production venv:

```powershell
C:\bluelotus3\run_bluelotus_v2_runtime_guard.bat --require-venv --archive --label manual
```

Repair or rebuild the production venv:

```powershell
C:\bluelotus3\repair_bluelotus_v2_runtime.bat
```

Repair behavior:

- Builds dependencies inside `C:\bluelotus3\.venv_build_tmp`.
- Validates required imports inside the temporary venv.
- Promotes the temporary venv to `C:\bluelotus3\.venv` only after validation passes.
- Backs up an existing venv as `C:\bluelotus3\.venv_backup_<timestamp>` before promotion.
- Runs the runtime guard with `--require-venv` after promotion.

Output:

```text
C:\bluelotus3\data\audit\runtime_guard_latest.json
C:\bluelotus3\data\audit\runtime_guard_archive\
```

Doctrine:

- No database writes.
- No Moomoo or broker calls.
- No pipeline execution.
- No order generation.

