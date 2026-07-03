# BlueLotus V2 Windows Installation Guide

This package installs BlueLotus V2 as a Windows research and intelligence system.

Target install path: `C:\bluelotus3`

Important: use this exact path for now. Several V2 production modules use `C:\bluelotus3` as the fixed production root.

## What This Installer Does

- Copies the BlueLotus V2 application to `C:\bluelotus3`.
- Creates a local Python virtual environment at `C:\bluelotus3\.venv`.
- Installs the pinned Python dependencies used by the working production system.
- Copies a `.env.template` and optionally installs your private `.env`.
- Can initialize a fresh MySQL `bluelotus2` database from the schema-only dump.
- Creates desktop shortcuts for one-shot and hourly pipeline runs.
- Validates Python runtime, package imports, MySQL connectivity, schema coverage, dataset contract, and runner safety.

## What This Installer Does Not Do

- It does not ship your `.env` secrets.
- It does not ship your private database rows, portfolio history, reports, or API keys.
- It does not execute broker orders.
- It does not request or store a Moomoo trade password.
- It does not include the legacy `moomoo_trader.py` order helper.

## Required Software

1. Windows 10 or Windows 11, 64-bit.
2. Python `3.13.x`.
3. MySQL Community Server `8.4.9 LTS`, Win64.
4. Moomoo Desktop plus Moomoo OpenD running on `127.0.0.1:11111`.
5. A private `.env` file containing that machine owner's API keys and MySQL credentials.

## Fresh Install Steps

1. Install MySQL first.

   Follow `MYSQL_8_4_9_INSTALL_GUIDE.md`.

2. Extract this package anywhere, for example:

   ```powershell
   C:\Users\<user>\Downloads\BlueLotusV2_Windows_Install
   ```

3. Open PowerShell as Administrator.

4. Run the installer:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   cd C:\Users\<user>\Downloads\BlueLotusV2_Windows_Install
   .\Install-BlueLotusV2.ps1
   ```

5. If you already prepared a private `.env` file:

   ```powershell
   .\Install-BlueLotusV2.ps1 -EnvFile C:\Users\<user>\Desktop\bluelotus.env
   ```

6. To initialize the database during install:

   ```powershell
   .\Install-BlueLotusV2.ps1 `
     -EnvFile C:\Users\<user>\Desktop\bluelotus.env `
     -InitializeDatabase `
     -MySQLAdminUser root `
     -MySQLAdminPassword "ROOT_PASSWORD" `
     -AppMySQLUser bluelotus_app `
     -AppMySQLPassword "APP_PASSWORD"
   ```

7. After Moomoo OpenD is running, validate broker quote connectivity:

   ```powershell
   C:\bluelotus3\.venv\Scripts\python.exe .\scripts\validate_environment.py --root C:\bluelotus3 --check-moomoo
   ```

## Running BlueLotus

Run smoke/hygiene diagnostics:

```powershell
C:\bluelotus3\run_bluelotus_v2_smoke_hygiene.bat --check-moomoo
```

Run only the runtime guard:

```powershell
C:\bluelotus3\run_bluelotus_v2_runtime_guard.bat --archive --label manual
```

Repair or rebuild the local virtual environment:

```powershell
C:\bluelotus3\repair_bluelotus_v2_runtime.bat
```

Run only the `dataset_raw.json` contract validator:

```powershell
C:\bluelotus3\run_bluelotus_v2_dataset_contract.bat --archive --label manual
```

The production hourly runner also performs pre-flight and post-flight diagnostics. If pre-flight reports any `FAIL`, that hourly cycle is skipped and retried after the normal wait interval.

Run one full pipeline cycle:

```powershell
C:\bluelotus3\run_bluelotus_v2_once_installed.bat
```

Run the hourly loop:

```powershell
C:\bluelotus3\run_bluelotus_v2_hourly_installed.bat
```

Main outputs:

- `C:\bluelotus3\data\frontend\dataset_raw.json`
- `C:\bluelotus3\data\execution\execution_readonly_latest.json`
- `C:\bluelotus3\research\research_report.txt`
- `C:\bluelotus3\research\BlueLotus_V2_R6_CIO_Operating_Report.xlsx`
- `C:\bluelotus3\research\BlueLotus_V2_R6_CIO_Word_Report.docx`
- `C:\bluelotus3\research\research_report_delivery_latest.json`
- `C:\bluelotus3\data\audit\smoke_hygiene_latest.json`
- `C:\bluelotus3\data\audit\runtime_guard_latest.json`
- `C:\bluelotus3\data\audit\dataset_contract_latest.json`

## Required Private `.env` Keys

Minimum required:

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=bluelotus3
MYSQL_USER=bluelotus_app
MYSQL_PASSWORD=...

MOOMOO_OPEND_HOST=127.0.0.1
MOOMOO_OPEND_PORT=11111
```

Useful optional APIs:

```dotenv
FINNHUB_API_KEY=
FRED_API_KEY=
EIA_API_KEY=
BEA_API_KEY=
BLS_API_KEY=
USDA_FAS_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
XAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## Moomoo Setup Notes

- Start Moomoo Desktop and log in.
- Start Moomoo OpenD.
- Confirm OpenD host/port is `127.0.0.1:11111`.
- The production package uses quote snapshots, read-only account/position extraction, and read-only open order/order history/deal history extraction.
- Do not place any trade password in `.env`.
- CIO execution remains manual and outside this installer.

## Troubleshooting

Run validation:

```powershell
C:\bluelotus3\.venv\Scripts\python.exe C:\Users\<user>\Downloads\BlueLotusV2_Windows_Install\scripts\validate_environment.py --root C:\bluelotus3
```

If Python packages fail, rerun:

```powershell
C:\bluelotus3\.venv\Scripts\python.exe -m pip install -r .\requirements-bluelotus-v2.txt
```

If MySQL fails, confirm:

- MySQL service is running.
- MySQL version is `8.4.9`.
- Database is named `bluelotus2`.
- `.env` has the correct app user and password.
- The app user has privileges on `bluelotus2.*`.

## Building A New Installer ZIP

From the production machine:

```powershell
cd C:\bluelotus3\installer
.\Build-BlueLotusV2Package.ps1
```

The distributable ZIP appears in:

```text
C:\bluelotus3\installer\dist
```


