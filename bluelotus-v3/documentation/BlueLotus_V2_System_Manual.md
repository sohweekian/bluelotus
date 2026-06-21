# BlueLotus V2 — System Manual
**Private Family Fund Intelligence System**
**Written for: Soh Wee Loon & Soh Wee Lian**
**Maintained by: Windows Platform Team (Claude Code & Codex)**
**Last updated: 2026-06-15**

---

## Table of Contents

1. [What Is BlueLotus V2?](#1-what-is-bluelotus-v2)
2. [System Architecture — Five Layers](#2-system-architecture--five-layers)
3. [Software Components — What Each Script Does](#3-software-components--what-each-script-does)
4. [Database — MySQL Schema Reference](#4-database--mysql-schema-reference)
5. [The Dashboard — Website Purpose & Functions](#5-the-dashboard--website-purpose--functions)
6. [Independent Daemons — The Watch Tower](#6-independent-daemons--the-watch-tower)
7. [Windows Installation Guide](#7-windows-installation-guide)
8. [Starting, Stopping & Daily Operations](#8-starting-stopping--daily-operations)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. What Is BlueLotus V2?

BlueLotus V2 is the **private intelligence and CIO operating system** for the Soh family fund. It is a piece of software that runs on a Windows computer, connects to financial data sources around the world, stores everything in a private database, and produces professional research reports every 39 minutes.

Think of it as a **24/7 financial analyst** running quietly in the background. It:

- Watches 50+ live data sources (central banks, commodity markets, news feeds, broker positions, earnings calendars)
- Stores all observations in a private MySQL database (nothing is ever deleted — this is institutional memory)
- Runs a governance check every cycle to determine if the data is trustworthy enough to publish
- Generates a full CIO research report in three formats: plain text, Microsoft Word, and Microsoft Excel
- Publishes a live dashboard to the web every cycle
- Alerts you on Telegram every 10 minutes with the latest news headlines

**What it does NOT do:**
- It does not place any trade orders. All execution is manual by the CIO (Kian Soh).
- It does not make investment decisions. It produces research and analysis only.
- It does not share your portfolio data publicly. The database is private on your local machine.

**Where the system lives:**
- All software: `C:\bluelotus3\`
- Private database: MySQL on your local machine (database name: `bluelotus2`)
- Public dashboard: https://sohweekian.github.io/bluelotus/

---

## 2. System Architecture — Five Layers

The system is organised into five clean layers. Data flows top to bottom.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1 — DATA SOURCES                                     │
│  50+ external feeds: brokers, central banks, RSS, APIs      │
└──────────────────────────┬──────────────────────────────────┘
                           │ fetch & ingest
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 2 — MYSQL DATABASE (bluelotus2)                      │
│  Private, local. All observations stored permanently.       │
└──────────────────────────┬──────────────────────────────────┘
                           │ export
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 3 — CANONICAL JSON (dataset_raw.json)                │
│  Single file. All analysis engines read from this.          │
└──────────────────────────┬──────────────────────────────────┘
                           │ governance check
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 4 — GOVERNANCE GATE                                  │
│  Approves or blocks the data before any report is issued.   │
│  Output: APPROVED / APPROVED_WITH_WARNINGS / BLOCKED        │
└──────────────────────────┬──────────────────────────────────┘
                           │ publish
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 5 — REPORTS & DASHBOARD                              │
│  TXT report · Word report · Excel report                    │
│  GitHub Pages dashboard · Telegram news bulletin            │
└─────────────────────────────────────────────────────────────┘
```

**The Pipeline Loop:**
The main pipeline (`run_v2_pipeline.bat`) runs this full cycle automatically every **39 minutes**, 24 hours a day. Each cycle executes over 65 scripts in sequence, ending with a fresh research report and an updated dashboard.

---

## 3. Software Components — What Each Script Does

All scripts live inside `C:\bluelotus3\`. Here is every major component in plain language.

---

### 3.1 The Main Pipeline Runner

| File | `run_v2_pipeline.bat` |
|---|---|
| Location | `C:\bluelotus3\` |
| What it does | Runs the entire system in a loop every 39 minutes. Calls all 65+ scripts in order. Counts errors. Never stops automatically. |
| How to start | Double-click `run_v2_pipeline.bat`, or run it in a Command Prompt window. |
| How to stop | Close the Command Prompt window, or press Ctrl+C. |

---

### 3.2 Data Fetchers (Layer 1 → Layer 2)

These scripts collect data from the outside world and store it in MySQL. They run at the start of every pipeline cycle.

| Script | Data Source | What It Collects |
|---|---|---|
| `fetch_analyst_targets.py` | Finnhub API | Analyst buy/hold/sell ratings and price targets for portfolio stocks |
| `fetch_capital_flow.py` | Various APIs | Institutional capital flows, ETF fund flows, short interest |
| `fetch_fundamentals.py` | Finnhub / Yahoo | P/E ratios, earnings, revenue, balance sheet data |
| `fetch_treasury_yields.py` | World Bank / FRED | US Treasury yield curve (2Y, 5Y, 10Y, 30Y) |
| `fetch_cross_market_confirmation.py` | Yahoo Finance / RSS | VIX, gold, oil, USD/JPY, DXY — cross-asset regime signals |
| `fetch_portfolio_readonly.py` | Moomoo OpenD (local) | Live portfolio positions, prices, unrealised P/L (read-only) |
| `fetch_execution_records_readonly.py` | Moomoo OpenD (local) | Order history and deal history (read-only, never places orders) |
| `fetch_corporate_actions.py` | Finnhub / Moomoo | Dividends, splits, special distributions |
| `fetch_tech_publications.py` | RSS feeds | Technology and AI news from CNBC Tech, NASA, Space news |
| `fetch_conference_calendar.py` | RSS / scrape | Upcoming tech and AI conferences relevant to portfolio themes |
| `fetch_ceo_appearances.py` | RSS / scrape | CEO speeches, earnings calls, investor days |
| `fetch_ticker_earnings.py` | Finnhub | Upcoming earnings dates and EPS estimates for portfolio tickers |
| `fetch_catalyst_calendar.py` | Finnhub / computed | Full catalyst calendar: earnings, conferences, dividends — with IMMINENT / ACTIVE / UPCOMING flags |
| `fetch_historical_prices.py` | Yahoo Finance | 180 days of daily price history for all portfolio and factor tickers |

---

### 3.3 Ingest Engine

| File | `mid/ingest.py` |
|---|---|
| What it does | The master signal ingestion engine. Reads from 50+ sources (central banks, news RSS, commodity feeds, economic data), processes them through circuit-breakers (so a single failing source doesn't crash the whole system), and stores all raw signals into the `raw_signal_archive` MySQL table. Also computes the **regime detection** (RISK ON / MILD RISK OFF / RISK OFF) from multiple market factors. |
| Key doctrine | 100% deterministic. No AI. No guessing. Observes reality exactly as it is. |

**Sources ingested by `ingest.py`:**
- Federal Reserve (Fed_Press, FOMC minutes)
- Bank of Japan (BOJ_Press)
- Monetary Authority of Singapore (MAS_Press)
- People's Bank of China (PBOC_Policy, PBOC_LPR, PBOC_CNY)
- European Central Bank (ECB_Press)
- Financial Times, Reuters, CNBC, Bloomberg, WSJ
- CNN Fear & Greed Index
- Commodity feeds: OPEC, EIA oil inventory, gold, silver
- Space sector: NASA news, Space Google News
- Macroeconomic: World Bank GDP, CPI, unemployment
- Live prices from Moomoo OpenD

---

### 3.4 Dataset Export Engine

| File | `mid/export_dataset_raw.py` |
|---|---|
| Output | `data/frontend/dataset_raw.json` |
| What it does | Reads all the latest data from MySQL and packages it into one single JSON file. This file is the **canonical intelligence feed** — every analysis engine, governance check, and report reads from this one file, not from the database directly. Think of it as a daily newspaper printed from the database. |
| Key rule | READ-ONLY. Never writes to MySQL. Never modifies anything. |

---

### 3.5 Processing Engines (Layer 3 → enriched data)

These scripts read `dataset_raw.json` and run calculations, then write results back to MySQL and re-export.

| Script | What It Does |
|---|---|
| `historical_risk_model.py` | Computes Value-at-Risk (VaR 95%), Expected Shortfall (ES), beta, and portfolio-level risk constraints from 180 days of price history. |
| `institutional_quant_pipeline.py` | Scores the fund's institutional readiness (0–100). Checks causal explanation completeness, blind spot audit, concentration risk, data quality, and more. Target: ≥90 = INSTITUTIONAL_READY. |
| `run_monitoring_alerts.py` | Generates structured alerts for the CIO: concentration warnings, regime shifts, data freshness failures, thesis lifecycle gaps. |
| `run_freshness_recovery.py` | Detects stale signals and attempts to recover them from alternative sources. |
| `seed_thesis_lifecycle.py` | Writes the current thesis lifecycle state (S1 Stated → S2 Monitored → S3 Evidence → S4 Closed) for each portfolio theme. |
| `seed_cio_decision_journal.py` | Seeds the CIO decision journal — pending decisions, orders count (always 0), reasoning records. |
| `record_cio_cognition.py` | Records CIO cognition: Strategic Thinking, Planning intent, Execution gate, Thesis Review, and Mistake/Risk notes. This is the governance memory of why decisions were made. |
| `run_deterministic_operators.py` | Runs deterministic operating truth calculations — regime, concentration, governance gate scores — deterministically (no AI, same input always gives same output). |
| `archive_dataset_snapshot.py` | Takes a point-in-time snapshot of `dataset_raw.json` and stores it in MySQL for historical audit. |
| `bluelotus_superforecast_engine.py` | Generates BlueLotus Conservative price forecasts for portfolio tickers. Competes against analyst consensus. |
| `forecast_resolution_tracker.py` | Tracks whether past forecasts were correct. Brier score accuracy. |
| `forecast_method_comparison.py` | Compares BlueLotus forecast methods against analyst estimates. |

---

### 3.6 Governance Gate (Layer 3 → Layer 4)

| File | `governance/governance_gate.py` |
|---|---|
| Input | `data/frontend/dataset_raw.json` + `governance/governance_config.json` |
| Outputs | `data/governance/approved_operating_truth.json` — the final approved state<br>`data/governance/governance_audit.json` — full audit trail<br>`data/governance/release_status.txt` — APPROVED / APPROVED_WITH_WARNINGS / BLOCKED |
| What it does | Before any report is issued, this gate runs a multi-check approval process. It checks data freshness, regime consistency, concentration risk, causal explanation completeness, and sentiment hygiene. If all checks pass: APPROVED. Minor warnings: APPROVED_WITH_WARNINGS. Critical failures: BLOCKED (no report issued). |

| File | `governance/scenario_overlay_engine.py` |
|---|---|
| What it does | Scans live headlines for breaking catalysts (e.g. Iran deal, Hormuz re-opening, central bank surprise). If detected, overlays a scenario onto the CIO briefing — e.g. "RELIEF RALLY WATCH" — without overwriting the base regime. Produces `data/governance/approved_cio_briefing.json`. |

| File | `governance/regression_tests.py` |
|---|---|
| What it does | Runs 61 automated tests after every pipeline cycle. Verifies that governance fields are never UNKNOWN, orders_generated is always 0, execution_authority is always CIO_ONLY_MANUAL, gold miner actions are never BUY when concentration is CRITICAL, and more. Pipeline will log warnings if tests fail. |

---

### 3.7 Report Generators (Layer 4 → Layer 5)

| File | What It Produces |
|---|---|
| `research/research_report_generator_r6.py` | **Plain text report** (`research/research_report.txt`) — the canonical text archive. Full CIO briefing, portfolio, watchlist, gold thesis, governance, causal engine, blind spot checklist. |
| `research/research_report_generator.py` | **Word report** (`BlueLotus_V2_R6_CIO_Word_Report.docx`) and **Excel report** (`BlueLotus_V2_R6_CIO_Operating_Report.xlsx`). Institutional quality. Suitable for printing and sharing. |

---

### 3.8 Publisher (Layer 5 → Web + Telegram)

| File | `mid/bluelotus_publisher.py` |
|---|---|
| What it does | Takes the latest `dataset_raw.json` and research outputs, builds the dashboard HTML, and pushes it to GitHub Pages. Also pushes `portfolio_live.json` so the dashboard's Fund Status section updates live. Sends a formatted Telegram bulletin if configured. |
| Runs every | 39 minutes (at the end of every pipeline cycle) |

---

## 4. Database — MySQL Schema Reference

The database is named `bluelotus2` and runs on MySQL 8.4.9 on your local machine (`127.0.0.1:3306`).

**Connection credentials** are stored in your `.env` file and never hard-coded anywhere.

### Key Tables

#### Raw Signal Storage
| Table | Purpose |
|---|---|
| `raw_signal_archive` | The master signal table. Every piece of intelligence ingested — news articles, price signals, economic data, central bank statements — lands here. ~24,000+ rows. Never deleted. |

#### Portfolio & Prices
| Table | Purpose |
|---|---|
| `portfolio_snapshots` | Read-only snapshots of portfolio positions pulled from Moomoo. Ticker, quantity, average cost, current price, unrealised P/L. |
| `live_prices` | Intraday prices from Moomoo OpenD. Pre-market, regular, after-hours sessions. |
| `historical_prices` | 180-day daily OHLCV price history for all portfolio and factor tickers (SPY, QQQ, VXX, GLD, GDX, etc.) |
| `analyst_targets` | Analyst ratings and price targets from Finnhub. Buy/Hold/Sell counts, consensus target prices, upside/downside. |

#### Earnings & Catalysts
| Table | Purpose |
|---|---|
| `ticker_earnings` | Earnings dates and EPS estimates for each portfolio ticker. Fetched daily from Finnhub. |
| `portfolio_catalyst_calendar` | Full catalyst calendar: earnings (IMMINENT/ACTIVE/UPCOMING/FUTURE), conferences, dividends, corporate actions. Deduped by latest snapshot. |
| `corporate_actions` | Dividends, stock splits, special distributions. |

#### Risk & Governance
| Table | Purpose |
|---|---|
| `risk_models` | VaR, Expected Shortfall, beta, correlation matrix — one record per pipeline cycle. |
| `institutional_dataset_snapshots` | Point-in-time archive of every `dataset_raw.json` export. Enables historical comparison. |
| `cio_decision_journal` | All CIO-pending decisions, their reasoning, and resolution status. orders_generated is always 0. |
| `cio_cognition_journal` | Strategic Thinking, Planning, Execution intent, Thesis Review, Mistake/Risk notes recorded before any capital action. |
| `thesis_lifecycle` | State of each investment thesis (S1 Stated → S2 Monitored → S3 Evidence Gathered → S4 Closed). |
| `monitoring_alerts` | WARNING / INFO alerts generated each cycle: concentration risk, regime shift, data freshness gaps. |

#### Forecasts & Research
| Table | Purpose |
|---|---|
| `research_forecasts` | BlueLotus Conservative price forecasts with confidence intervals. |
| `forecast_resolutions` | Whether past forecasts resolved correctly. Brier score tracking. |

### Key Governance Files (not in MySQL — stored as JSON)

| File | Purpose |
|---|---|
| `data/governance/approved_operating_truth.json` | The single source of truth for all report renderers. Contains regime, governance score, release status, concentration risk, and all contract fields. |
| `data/governance/approved_cio_briefing.json` | CIO briefing with scenario overlay (breaking catalysts, Monday open scenarios). |
| `data/governance/governance_audit.json` | Full audit trail of every governance gate decision. |
| `data/frontend/dataset_raw.json` | Canonical intelligence export (~3 MB). All scripts read from this. |

---

## 5. The Dashboard — Website Purpose & Functions

**URL:** https://sohweekian.github.io/bluelotus/

**What it is:** A live intelligence dashboard hosted on GitHub Pages (free, public URL, no server required). The content is updated every time the main pipeline completes a cycle (~every 39 minutes).

**Who can access it:** Anyone with the URL. The data shown is fund intelligence and market analysis — no private account numbers, no passwords, no personally identifiable information.

**How it gets updated:**
1. The main pipeline runs `bluelotus_publisher.py` at the end of each cycle
2. The publisher pushes a new `index.html` and `portfolio_live.json` to the GitHub repository
3. GitHub Pages serves the new files within ~60 seconds
4. The dashboard's Fund Status section polls `portfolio_live.json` every 60 seconds via JavaScript, so it auto-refreshes without a page reload

### Dashboard Sections (top to bottom)

#### ▲ HEADLINES
Live news from three sources, updated every 10 minutes by the news probe daemon (independent of the main pipeline). Shows the most recent articles within the last 60 minutes. Each headline is **clickable** — tapping or clicking takes you to the source article so you can verify it.

- **📰 FT World** — Financial Times global news (direct RSS, very fresh)
- **🛢 Reuters Commodities** — Oil, gold, metals, energy headlines from Reuters
- **💻 Tech Intelligence** — AI, semiconductor, and technology market news

#### COMMAND HEADER (Fund Status)
Shows the current operating state of the fund. Updates live (every 60 seconds) from `portfolio_live.json`.

- **Regime badge** — RISK ON / MILD RISK OFF / RISK OFF
- **Governance score** — 0–100 institutional quality score
- **CIO Action** — WAIT / HOLD / BUY DIP / etc.
- **Cycle timestamp** — when the last pipeline cycle completed
- **Integrity status** — data quality flag

#### PULSE STRIP
A single-line strip showing five live metrics:
- VIX (fear gauge)
- Fear & Greed Index
- Regime Score
- Portfolio market value
- Cash position

#### SITUATION BOARD
Key cross-asset signals at a glance: Gold status, Oil risk premium, Equity relief probability, Bond yield direction.

#### S3 · THESIS EVIDENCE
A table showing the current status of each investment thesis — the same Causal Explanation Engine (ECE) output that appears in the Word report. Shows:
- Theme name (e.g. "Gold Safe Haven", "AI Infrastructure")
- Direction (RISK ON / RISK OFF / WATCH / NEUTRAL)
- Basket move (e.g. "+2.3%")
- Evidence summary
- Confidence level

This section updates every 10 minutes from `thesis_evidence_live.json` pushed by the thesis probe daemon.

#### FORWARD CATALYST CALENDAR
Upcoming earnings and events for portfolio tickers: ORCL, AU, NEM, QBTS, ASTS, etc. Colour-coded by urgency (ACTIVE = today, IMMINENT = within 3 days, UPCOMING = within 14 days).

#### SYSTEM HEALTH
Pipeline cycle stats — last run time, number of errors, governance release status.

---

## 6. Independent Daemons — The Watch Tower

The "watch tower" consists of two Python scripts that run **independently of the main pipeline**. They never stop. They watch, probe, and alert continuously.

```
┌──────────────────────────────────────────────────────────┐
│  WATCH TOWER (always running, independent)               │
│                                                          │
│  news_probe_daemon.py   →  Headlines every 10 min       │
│                          →  GitHub Pages JSON updated    │
│                          →  Telegram bulletin sent       │
│                                                          │
│  thesis_probe_daemon.py →  Gold thesis every 10 min     │
│                          →  yfinance live prices         │
│                          →  GitHub Pages JSON updated    │
└──────────────────────────────────────────────────────────┘
```

---

### 6.1 News Probe Daemon (`mid/news_probe_daemon.py`)

**Purpose:** Watches three news sources continuously. Every 10 minutes it fetches the latest RSS feeds, filters for articles published within the last 60 minutes, and pushes the results to GitHub Pages. It also sends a Telegram bulletin every 10 minutes so the CIO receives breaking news on their phone.

**What it watches:**

| Source | Feed | Freshness Filter |
|---|---|---|
| FT World | FT.com direct RSS | Articles within last 60 min |
| Reuters Commodities | Google News keyword search | Articles within last 60 min |
| Tech Intelligence | Google News keyword search (AI, chips, semiconductor) | Articles within last 60 min |

**Junk filtering:** Automatically discards "Print Edition", "Subscribe to read", "Members Only" and similar non-news articles.

**Telegram format:** Each bulletin uses HTML formatting so headlines are **clickable links** — tap the headline in Telegram to open the source article directly.

**Log file:** `C:\bluelotus3\logs\news_probe.log`

**How to start:**
```
python C:\bluelotus3\mid\news_probe_daemon.py
```

**How to check it's running:** Look at the log file — you should see a new cycle logged every 10 minutes.

---

### 6.2 Thesis Probe Daemon (`mid/thesis_probe_daemon.py`)

**Purpose:** Watches the Gold Safe-Haven Thesis in real time. Every 10 minutes it fetches live intraday prices for 14 gold-related tickers via `yfinance`, runs the 8-check Gold Thesis Tracker, and pushes results to `data/thesis_evidence_live.json` on GitHub Pages. The dashboard S3 Thesis Evidence section reads from this JSON.

**The 8 checks it runs:**

1. GLD stabilises and rises (gold price trend)
2. Silver/Gold ratio (GSR) — risk-on vs safe-haven signal
3. GDX/GDXJ vs GLD (miners tracking bullion)
4. AU/NEM vs GDX (high-quality miners leading)
5. Real yields direction (TLT/IEF — key gold driver)
6. DXY/UUP (US dollar — inverse to gold)
7. Oil risk premium (XLE vs SPY — inflation premium)
8. Equity beta / liquidity (SPY vs VXX — risk appetite)

**Status output:**
- `CONFIRMING` (score ≥ 0.75) — thesis is confirmed by evidence
- `WATCH` (0.50–0.74) — monitoring, no action
- `WARNING` (0.30–0.49) — caution, adding blocked
- `FAILING` (<0.30) — thesis failing, deconcentration review

**Tickers monitored:** GLD, SLV, GDX, GDXJ, AU, NEM, UUP, TLT, IEF, SPY, QQQ, VXX, UVXY, XLE

**Log file:** `C:\bluelotus3\logs\thesis_probe.log`

**How to start:**
```
python C:\bluelotus3\mid\thesis_probe_daemon.py
```

---

### 6.3 Starting Both Daemons at Once (`start_daemons.bat`)

Run this file to start both daemons in separate windows:
```
C:\bluelotus3\start_daemons.bat
```

To have them start automatically when Windows boots, add `start_daemons.bat` to your Windows Startup folder (`shell:startup`).

---

## 7. Windows Installation Guide

This guide walks Soh Wee Loon or Soh Wee Lian through installing BlueLotus V2 on a fresh Windows machine from scratch.

**Time required:** Approximately 45–60 minutes for a first-time install.

**Prerequisites:** A Windows 10 or Windows 11 computer with administrator access and an internet connection.

---

### Step 1 — Install Python 3.13

1. Go to: https://www.python.org/downloads/
2. Download **Python 3.13.x** (64-bit Windows installer)
3. Run the installer
4. **IMPORTANT:** On the first screen, tick **"Add Python to PATH"** before clicking Install
5. When done, open Command Prompt and verify:
   ```
   python --version
   ```
   You should see: `Python 3.13.x`

---

### Step 2 — Install MySQL 8.4.9

1. Go to: https://dev.mysql.com/downloads/mysql/
2. Download **MySQL Community Server 8.4.9 LTS** (Windows x86_64 MSI Installer)
3. Run the installer
4. Choose **"Developer Default"** setup type
5. During configuration:
   - Set the root password (write it down — you will need it once)
   - Create a new user: username `bluelotus_app`, give it a strong password (write it down)
   - Set the new user to have full access to a database called `bluelotus2`
6. Let MySQL start as a Windows Service (ticked by default — leave it)
7. After install, open Command Prompt and verify:
   ```
   mysql --version
   ```
   You should see: `mysql  Ver 8.4.9 ...`

---

### Step 3 — Install Git

1. Go to: https://git-scm.com/download/win
2. Download and install Git for Windows (accept all defaults)
3. Verify:
   ```
   git --version
   ```

---

### Step 4 — Install Moomoo OpenD

1. Download Moomoo Desktop from: https://www.moomoo.com/
2. Install and log in to your Moomoo account
3. Start **Moomoo OpenD** (separate program, usually found in the Moomoo installation folder)
4. Confirm it is running on `127.0.0.1:11111` (the default port)
5. BlueLotus uses Moomoo OpenD only to read your portfolio and prices. It never places trades.

---

### Step 5 — Copy the BlueLotus V2 Files

Obtain the BlueLotus V2 package (a ZIP file or copied folder) from Kian Soh's production machine.

Extract or copy the entire contents to:
```
C:\bluelotus3\
```

**This path is mandatory.** The system is hardcoded to `C:\bluelotus3`. Do not install it anywhere else.

After copying, your folder should contain: `run_v2_pipeline.bat`, `mid\`, `research\`, `governance\`, `core\`, `data\`, etc.

---

### Step 6 — Create the Python Virtual Environment

Open Command Prompt as Administrator, then run:

```
cd C:\bluelotus3
python -m venv .venv
.venv\Scripts\activate
pip install -r installer\requirements-bluelotus-v2.txt
```

This installs all required Python packages. It takes about 3–5 minutes.

Verify the installation:
```
python -c "import mysql.connector, feedparser, yfinance, requests; print('All packages OK')"
```

---

### Step 7 — Set Up the Database Schema

This creates all the empty tables that BlueLotus needs.

1. Open Command Prompt
2. Log in to MySQL:
   ```
   mysql -u root -p
   ```
   (Enter the root password you set in Step 2)

3. Create the database and user:
   ```sql
   CREATE DATABASE IF NOT EXISTS bluelotus2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER IF NOT EXISTS 'bluelotus_app'@'127.0.0.1' IDENTIFIED BY 'YOUR_APP_PASSWORD';
   GRANT ALL PRIVILEGES ON bluelotus2.* TO 'bluelotus_app'@'127.0.0.1';
   FLUSH PRIVILEGES;
   EXIT;
   ```

4. Import the schema:
   ```
   mysql -u root -p bluelotus2 < C:\bluelotus3\installer\schema\bluelotus2_schema_mysql_8_4_9.sql
   ```

---

### Step 8 — Create the `.env` File

The `.env` file holds all private configuration. It is **never shared** and **never committed to GitHub**.

1. Copy the template:
   ```
   copy C:\bluelotus3\installer\.env.template C:\bluelotus3\.env
   ```

2. Open `C:\bluelotus3\.env` in Notepad and fill in your values:

```dotenv
# ── Database ───────────────────────────────────────────────
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=bluelotus3
MYSQL_USER=bluelotus_app
MYSQL_PASSWORD=YOUR_APP_PASSWORD_HERE

# ── Moomoo Broker ──────────────────────────────────────────
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111

# ── GitHub Pages (for dashboard publishing) ────────────────
GITHUB_TOKEN=YOUR_GITHUB_PERSONAL_ACCESS_TOKEN
GITHUB_USERNAME=sohweekian
GITHUB_PAGES_REPO=bluelotus3
GITHUB_BRANCH=main

# ── Telegram (for news alerts) ─────────────────────────────
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID

# ── Optional Data APIs ─────────────────────────────────────
FINNHUB_API_KEY=YOUR_FINNHUB_KEY
EIA_API_KEY=YOUR_EIA_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
```

**Note on GitHub Token:**
- Go to https://github.com/settings/tokens
- Generate a new Personal Access Token (Classic) with `repo` scope
- Paste it as `GITHUB_TOKEN`
- This allows BlueLotus to push the dashboard to GitHub Pages

**Note on Telegram:**
- Create a bot via @BotFather on Telegram
- Get the `TELEGRAM_BOT_TOKEN` from BotFather
- Get your `TELEGRAM_CHAT_ID` by messaging @userinfobot on Telegram

---

### Step 9 — Validate the Installation

Run the validation script:
```
cd C:\bluelotus3
.venv\Scripts\python.exe installer\scripts\validate_environment.py --root C:\bluelotus3
```

Then (with Moomoo OpenD running):
```
.venv\Scripts\python.exe installer\scripts\validate_environment.py --root C:\bluelotus3 --check-moomoo
```

All checks should return PASS. Fix any failures before running the pipeline.

---

### Step 10 — First Run

Run one complete pipeline cycle to confirm everything works end-to-end:

```
cd C:\bluelotus3
run_v2_pipeline.bat
```

Watch the output. The first run takes about 10–15 minutes because it fetches 180 days of historical price data. Subsequent cycles take approximately 8–12 minutes each.

After the first run, check that these files were created:
- `C:\bluelotus3\data\frontend\dataset_raw.json` (the canonical data export)
- `C:\bluelotus3\research\research_report.txt` (CIO text report)
- `C:\bluelotus3\research\BlueLotus_V2_R6_CIO_Operating_Report.xlsx` (Excel report)
- `C:\bluelotus3\research\BlueLotus_V2_R6_CIO_Word_Report.docx` (Word report)
- `C:\bluelotus3\data\governance\approved_operating_truth.json` (governance approval)

If all five files exist and the governance status is APPROVED or APPROVED_WITH_WARNINGS, the installation is successful.

---

## 8. Starting, Stopping & Daily Operations

### Normal Daily Operation

On a typical day, the production machine (Kian Soh's desktop) runs:

1. **Main pipeline** — runs itself in a loop every 39 minutes. Start it once; it runs forever.
   ```
   C:\bluelotus3\run_v2_pipeline.bat
   ```

2. **Watch Tower daemons** — run independently. Start them once; they run forever.
   ```
   C:\bluelotus3\start_daemons.bat
   ```

3. **Moomoo OpenD** — must be running for the pipeline to pull live portfolio data.

### How to Start Everything (Morning Routine)

1. Start Moomoo Desktop and log in
2. Start Moomoo OpenD
3. Double-click `start_daemons.bat` — starts both news and thesis probes
4. Double-click `run_v2_pipeline.bat` — starts the main 39-minute loop

### How to Stop Everything

- For the pipeline: Close the Command Prompt window running `run_v2_pipeline.bat`
- For the daemons: Close their Command Prompt windows, or use Task Manager → find python.exe processes

### Checking the System is Healthy

**Check the log files:**
- `C:\bluelotus3\logs\news_probe.log` — should show a new cycle every 10 minutes
- `C:\bluelotus3\logs\thesis_probe.log` — should show a new cycle every 10 minutes
- `C:\bluelotus3\logs\bluelotus_v2_pipeline_*.log` — should show cycles completing

**Check the dashboard:**
- Open https://sohweekian.github.io/bluelotus/
- The Fund Status timestamp should be within the last 40 minutes
- Headlines should show articles from within the last 60 minutes

**Check the regression tests:**
- After any pipeline cycle, open `C:\bluelotus3\data\governance\regression_test_results.json`
- All 61 tests should show PASS

### What If the Pipeline Crashes?

The pipeline is designed to recover. Individual script failures are logged but the pipeline continues to the next step. Only a complete system crash (power outage, Python error in the bat file itself) would stop it.

To restart: simply run `run_v2_pipeline.bat` again. It picks up from the current time.

---

## 9. Troubleshooting

### "No fresh news in last 60 min" on the dashboard
- This is normal outside US and European market hours (12:00 AM – 8:00 AM SGT)
- The 60-minute freshness filter is intentional — it shows nothing rather than stale data
- Check `logs/news_probe.log` to confirm the daemon is running

### Reports show "GOVERNANCE: BLOCKED"
- One or more governance gate checks failed
- Open `data/governance/governance_audit.json` to see which check failed
- Common cause: database freshness failure (a data source stopped updating)
- Resolution: wait for the next pipeline cycle to attempt recovery, or run `run_freshness_recovery.py` manually

### MySQL connection error
- Confirm MySQL service is running: Windows Services → MySQL84
- Confirm `.env` has the correct `MYSQL_USER` and `MYSQL_PASSWORD`
- Confirm the `bluelotus_app` user has privileges on `bluelotus2`

### Moomoo: no portfolio data
- Confirm Moomoo OpenD is running on `127.0.0.1:11111`
- Log in to Moomoo Desktop first, then start OpenD
- The pipeline will continue without Moomoo data but portfolio sections will be empty

### Telegram: not receiving messages
- Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct in `.env`
- Send `/start` to your bot in Telegram to activate the chat
- Check `logs/news_probe.log` for "Telegram: PASS" or error messages

### Dashboard not updating
- Confirm `GITHUB_TOKEN` in `.env` is valid and has `repo` scope
- GitHub tokens expire — generate a new one if it has been 90+ days
- Check `logs/` for "GitHub push: FAIL" messages

### Python package errors after Windows update
- Re-run the pip install:
  ```
  cd C:\bluelotus3
  .venv\Scripts\activate
  pip install -r installer\requirements-bluelotus-v2.txt
  ```

---

## Appendix A — Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `MYSQL_HOST` | Yes | MySQL server address. Usually `127.0.0.1` |
| `MYSQL_PORT` | Yes | MySQL port. Usually `3306` |
| `MYSQL_DATABASE` | Yes | Database name: `bluelotus2` |
| `MYSQL_USER` | Yes | App database user: `bluelotus_app` |
| `MYSQL_PASSWORD` | Yes | App database password |
| `MOOMOO_HOST` | Yes | Moomoo OpenD host: `127.0.0.1` |
| `MOOMOO_PORT` | Yes | Moomoo OpenD port: `11111` |
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token (repo scope) |
| `GITHUB_USERNAME` | Yes | GitHub account: `sohweekian` |
| `GITHUB_PAGES_REPO` | Yes | Repo name: `bluelotus` |
| `GITHUB_BRANCH` | Yes | Branch: `main` |
| `TELEGRAM_BOT_TOKEN` | Recommended | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Recommended | Your Telegram chat ID from @userinfobot |
| `FINNHUB_API_KEY` | Recommended | Free API key from finnhub.io |
| `EIA_API_KEY` | Optional | Free from EIA.gov — US energy data |
| `ANTHROPIC_API_KEY` | Optional | Used by AI-assisted research modules |

---

## Appendix B — Directory Structure

```
C:\bluelotus3\
├── .env                        ← Private config (never share this)
├── .venv\                      ← Python virtual environment
├── run_v2_pipeline.bat         ← MAIN: start the pipeline loop
├── start_daemons.bat           ← Start both watch tower daemons
│
├── core\                       ← Database connection layer
│   ├── db.py                   ← MySQL connection pool + cycle connections
│   └── db_writers.py           ← Raw signal archive writer
│
├── mid\                        ← Market Intelligence Data layer
│   ├── fetch_*.py              ← 15 data fetchers
│   ├── ingest.py               ← Signal ingestion engine (50+ sources)
│   ├── export_dataset_raw.py   ← Canonical JSON export
│   ├── historical_risk_model.py
│   ├── institutional_quant_pipeline.py
│   ├── run_monitoring_alerts.py
│   ├── bluelotus_publisher.py  ← Pushes dashboard to GitHub Pages
│   ├── news_probe_daemon.py    ← Watch tower: news every 10 min
│   └── thesis_probe_daemon.py  ← Watch tower: gold thesis every 10 min
│
├── research\                   ← Report generation
│   ├── research_report_generator.py    ← Word + Excel reports
│   ├── research_report_generator_r6.py ← TXT report
│   └── validate_bluelotus_outputs.py
│
├── governance\                 ← Governance and approval layer
│   ├── governance_gate.py
│   ├── scenario_overlay_engine.py
│   ├── regression_tests.py
│   ├── governance_config.json
│   ├── report_contract.json
│   └── breaking_catalyst_rules.json
│
├── data\                       ← All data artifacts
│   ├── frontend\dataset_raw.json    ← CANONICAL: all scripts read this
│   ├── governance\                  ← Approved truth, audit, briefing
│   ├── audit\                       ← All audit trail JSONs
│   ├── risk\                        ← Risk model outputs
│   └── ...
│
├── reports\                    ← Generated reports (TXT, DOCX, XLSX)
├── logs\                       ← All pipeline and daemon logs
├── installer\                  ← Windows installation package
│   ├── requirements-bluelotus-v2.txt
│   ├── schema\bluelotus2_schema_mysql_8_4_9.sql
│   └── scripts\validate_environment.py
└── documentation\              ← This manual and schema references
```

---

## Appendix C — Python Packages Required

| Package | Version | Purpose |
|---|---|---|
| `mysql-connector-python` | 9.7.0 | MySQL database connectivity |
| `requests` | 2.32.5 | HTTP requests to all APIs and RSS feeds |
| `feedparser` | 6.0.12 | RSS feed parsing (news probe daemon) |
| `yfinance` | 1.3.0 | Live and historical market prices (thesis probe) |
| `python-docx` | 1.2.0 | Word report generation |
| `openpyxl` | (via pandas) | Excel report generation |
| `pandas` | 2.2.3 | Data manipulation and analysis |
| `numpy` | 1.26.4 | Numerical computation (VaR, ES) |
| `python-dotenv` | 1.2.2 | `.env` file loading |
| `moomoo-api` | 10.6.6608 | Moomoo OpenD broker connectivity |
| `vaderSentiment` | 3.3.2 | Sentiment analysis on news signals |
| `anthropic` | 0.102.0 | AI-assisted research (optional) |
| `rich` | 14.3.3 | Formatted console output |

---

*Document maintained by the Windows Platform Team.*
*For questions about this system, contact Kian Soh.*
*Repository: C:\bluelotus3\ (private, local)*
*Dashboard: https://sohweekian.github.io/bluelotus/*


