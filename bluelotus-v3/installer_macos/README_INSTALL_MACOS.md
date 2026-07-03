# BlueLotus V2 macOS 24/7 Collector Installation Guide

This package installs BlueLotus V2 as a macOS data collector and reporting node.

Default install path:

```text
~/bluelotus2
```

This macOS package is separate from the Windows installer. The payload is patched during package build so active V2 modules resolve their project root from their own installed location instead of `C:\bluelotus3`.

## What This Installer Does

- Copies the BlueLotus V2 application to `~/bluelotus2`.
- Creates a local Python virtual environment at `~/bluelotus2/.venv`.
- Installs the pinned Python dependencies.
- Copies a `.env.template` and optionally installs your private `.env`.
- Can initialize a fresh MySQL `bluelotus2` schema.
- Can register a macOS LaunchAgent for 24/7 hourly collection.
- Validates Python imports, MySQL schema, shell runner safety, path patching, and optional Moomoo OpenD connectivity.

## What This Installer Does Not Do

- It does not ship your `.env` secrets.
- It does not ship private database rows, portfolio history, reports, Excel/Word outputs, or runtime JSON.
- It does not execute broker orders.
- It does not request or store a Moomoo trade password.
- It does not include the legacy `moomoo_trader.py` order helper.

## Required Software

1. macOS on Apple Silicon or Intel.
2. Python `3.12.x` recommended. Python `3.13.x` may also work, but `3.12.x` is the safer macOS package baseline.
3. MySQL Community Server `8.4.9 LTS`.
4. Moomoo Desktop/OpenD running on `127.0.0.1:11111`.
5. A private `.env` file for that machine.

Official Moomoo references say OpenD supports Windows, macOS, Ubuntu, and CentOS, and the Python SDK can be installed by pip.

## Fresh Install Steps

1. Install MySQL `8.4.9`.

   Follow:

   ```text
   MACOS_MYSQL_8_4_9_INSTALL_GUIDE.md
   ```

2. Install Python `3.12`.

   With Homebrew:

   ```bash
   brew install python@3.12
   ```

3. Extract this package on the Mac.

4. Open Terminal in the extracted package folder.

5. Run install:

   ```bash
   bash install_bluelotus_v2_macos.sh
   ```

6. If you prepared a private `.env`:

   ```bash
   bash install_bluelotus_v2_macos.sh --env-file "$HOME/Desktop/bluelotus.env"
   ```

7. To initialize MySQL and register the 24/7 collector:

   ```bash
   bash install_bluelotus_v2_macos.sh \
     --env-file "$HOME/Desktop/bluelotus.env" \
     --init-db \
     --mysql-admin-user root \
     --mysql-admin-password "ROOT_PASSWORD" \
     --app-db-user bluelotus_app \
     --app-db-password "APP_PASSWORD" \
     --install-launchagent
   ```

8. After Moomoo OpenD is running:

   ```bash
   ~/bluelotus2/.venv/bin/python scripts/validate_environment_macos.py \
     --root "$HOME/bluelotus2" \
     --check-moomoo
   ```

## Running Manually

Run one full cycle:

```bash
~/bluelotus2/run_bluelotus_v2_once_macos.sh
```

Run the hourly loop manually:

```bash
~/bluelotus2/run_bluelotus_v2_hourly_macos.sh
```

## LaunchAgent Commands

The installer can create:

```text
~/Library/LaunchAgents/com.bluelotus.v2.collector.plist
```

Check status:

```bash
launchctl list | grep bluelotus
```

Stop collector:

```bash
launchctl unload "$HOME/Library/LaunchAgents/com.bluelotus.v2.collector.plist"
```

Start collector:

```bash
launchctl load "$HOME/Library/LaunchAgents/com.bluelotus.v2.collector.plist"
```

Logs:

```text
~/bluelotus2/logs
```

## Prevent macOS Sleep

For a real 24/7 collector, configure the Mac so it does not sleep.

System Settings path:

```text
System Settings -> Displays / Battery / Energy
```

Terminal option:

```bash
sudo pmset -a sleep 0 disksleep 0
```

Use display sleep if desired:

```bash
sudo pmset -a displaysleep 10
```

## Main Outputs

- `~/bluelotus2/data/frontend/dataset_raw.json`
- `~/bluelotus2/research/research_report.txt`
- `~/bluelotus2/research/BlueLotus_V2_R6_CIO_Operating_Report.xlsx`
- `~/bluelotus2/research/BlueLotus_V2_R6_CIO_Word_Report.docx`
- `~/bluelotus2/research/research_report_delivery_latest.json`

## Required Private `.env` Keys

Minimum:

```dotenv
BLUELOTUS_ROOT=/Users/<user>/bluelotus2
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=bluelotus3
MYSQL_USER=bluelotus_app
MYSQL_PASSWORD=...
MOOMOO_OPEND_HOST=127.0.0.1
MOOMOO_OPEND_PORT=11111
```

Optional:

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

## Building A New macOS ZIP From Windows Production

From the Windows production machine:

```powershell
cd C:\bluelotus3\installer_macos
.\Build-BlueLotusV2MacOSPackage.ps1
```

The ZIP appears in:

```text
C:\bluelotus3\installer_macos\dist
```


