#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="$HOME/bluelotus2"
ENV_FILE=""
INIT_DB=0
CHECK_MOOMOO=0
INSTALL_LAUNCHAGENT=0
INSTALL_PYTHON_WITH_BREW=0
MYSQL_HOST="127.0.0.1"
MYSQL_PORT="3306"
MYSQL_DB="bluelotus2"
MYSQL_ADMIN_USER="root"
MYSQL_ADMIN_PASSWORD=""
APP_DB_USER="bluelotus_app"
APP_DB_PASSWORD=""

usage() {
  cat <<'EOF'
BlueLotus V2 macOS installer

Usage:
  bash install_bluelotus_v2_macos.sh [options]

Options:
  --install-root PATH              Default: ~/bluelotus2
  --env-file PATH                  Private .env to copy into install root
  --init-db                        Initialize MySQL schema
  --mysql-host HOST                Default: 127.0.0.1
  --mysql-port PORT                Default: 3306
  --mysql-db NAME                  Default: bluelotus2
  --mysql-admin-user USER          Default: root
  --mysql-admin-password PASSWORD
  --app-db-user USER               Default: bluelotus_app
  --app-db-password PASSWORD
  --check-moomoo                   Validate Moomoo OpenD quote connectivity
  --install-launchagent            Register hourly collector LaunchAgent
  --install-python-with-brew       Install python@3.12 if no suitable Python exists
  -h, --help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --init-db) INIT_DB=1; shift ;;
    --mysql-host) MYSQL_HOST="$2"; shift 2 ;;
    --mysql-port) MYSQL_PORT="$2"; shift 2 ;;
    --mysql-db) MYSQL_DB="$2"; shift 2 ;;
    --mysql-admin-user) MYSQL_ADMIN_USER="$2"; shift 2 ;;
    --mysql-admin-password) MYSQL_ADMIN_PASSWORD="$2"; shift 2 ;;
    --app-db-user) APP_DB_USER="$2"; shift 2 ;;
    --app-db-password) APP_DB_PASSWORD="$2"; shift 2 ;;
    --check-moomoo) CHECK_MOOMOO=1; shift ;;
    --install-launchagent) INSTALL_LAUNCHAGENT=1; shift ;;
    --install-python-with-brew) INSTALL_PYTHON_WITH_BREW=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] Unknown option: $1"; usage; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD_ROOT="$SCRIPT_DIR/payload/bluelotus2"
REQ_FILE="$SCRIPT_DIR/requirements-bluelotus-v2.txt"
ENV_TEMPLATE="$SCRIPT_DIR/.env.template"
SCHEMA_FILE="$SCRIPT_DIR/schema/bluelotus2_schema_mysql_8_4_9.sql"

log_step() { printf '\n==> %s\n' "$1"; }
log_ok() { printf '[OK] %s\n' "$1"; }
log_warn() { printf '[WARN] %s\n' "$1"; }

find_python() {
  if command -v python3.12 >/dev/null 2>&1; then echo "python3.12"; return; fi
  if command -v python3.13 >/dev/null 2>&1; then echo "python3.13"; return; fi
  if command -v python3 >/dev/null 2>&1; then echo "python3"; return; fi
}

set_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "$file"; then
    perl -0pi -e "s|^${key}=.*$|${key}=${value}|m" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

install_launchagent() {
  local plist_dir="$HOME/Library/LaunchAgents"
  local plist="$plist_dir/com.bluelotus.v2.collector.plist"
  mkdir -p "$plist_dir" "$INSTALL_ROOT/logs"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.bluelotus.v2.collector</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$INSTALL_ROOT/run_bluelotus_v2_hourly_macos.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$INSTALL_ROOT</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$INSTALL_ROOT/logs/launchagent.out.log</string>
  <key>StandardErrorPath</key>
  <string>$INSTALL_ROOT/logs/launchagent.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>BLUELOTUS_ROOT</key>
    <string>$INSTALL_ROOT</string>
    <key>PYTHONUTF8</key>
    <string>1</string>
    <key>PYTHONIOENCODING</key>
    <string>utf-8</string>
  </dict>
</dict>
</plist>
EOF
  launchctl unload "$plist" >/dev/null 2>&1 || true
  launchctl load "$plist"
  log_ok "LaunchAgent loaded: $plist"
}

log_step "Checking package"
[ -d "$PAYLOAD_ROOT" ] || { echo "[FAIL] Payload missing: $PAYLOAD_ROOT"; exit 2; }
[ -f "$REQ_FILE" ] || { echo "[FAIL] Requirements missing: $REQ_FILE"; exit 2; }
[ -f "$SCHEMA_FILE" ] || { echo "[FAIL] Schema missing: $SCHEMA_FILE"; exit 2; }
log_ok "Package files found"

log_step "Checking Python"
PYTHON_CMD="$(find_python || true)"
if [ -z "${PYTHON_CMD:-}" ] && [ "$INSTALL_PYTHON_WITH_BREW" -eq 1 ]; then
  command -v brew >/dev/null 2>&1 || { echo "[FAIL] Homebrew not found. Install Homebrew first."; exit 2; }
  brew install python@3.12
  PYTHON_CMD="$(find_python || true)"
fi
[ -n "${PYTHON_CMD:-}" ] || { echo "[FAIL] python3.12/python3.13/python3 not found."; exit 2; }
log_ok "Python command: $PYTHON_CMD"

log_step "Copying BlueLotus V2 payload to $INSTALL_ROOT"
mkdir -p "$INSTALL_ROOT"
rsync -a --delete "$PAYLOAD_ROOT/" "$INSTALL_ROOT/"
cp "$SCRIPT_DIR/bin/run_bluelotus_v2_once_macos.sh" "$INSTALL_ROOT/run_bluelotus_v2_once_macos.sh"
cp "$SCRIPT_DIR/bin/run_bluelotus_v2_hourly_macos.sh" "$INSTALL_ROOT/run_bluelotus_v2_hourly_macos.sh"
chmod +x "$INSTALL_ROOT/run_bluelotus_v2_once_macos.sh" "$INSTALL_ROOT/run_bluelotus_v2_hourly_macos.sh"
mkdir -p "$INSTALL_ROOT/data/frontend" "$INSTALL_ROOT/data/archive" "$INSTALL_ROOT/data/audit" \
  "$INSTALL_ROOT/data/brier" "$INSTALL_ROOT/data/forecasts" "$INSTALL_ROOT/data/history" \
  "$INSTALL_ROOT/data/portfolio" "$INSTALL_ROOT/data/reference" "$INSTALL_ROOT/data/regime" \
  "$INSTALL_ROOT/data/risk" "$INSTALL_ROOT/data/thesis" "$INSTALL_ROOT/logs" "$INSTALL_ROOT/reports"
log_ok "Application copied"

log_step "Preparing .env"
if [ -n "$ENV_FILE" ]; then
  [ -f "$ENV_FILE" ] || { echo "[FAIL] Env file not found: $ENV_FILE"; exit 2; }
  cp "$ENV_FILE" "$INSTALL_ROOT/.env"
  log_ok "Private .env copied"
elif [ ! -f "$INSTALL_ROOT/.env" ]; then
  cp "$ENV_TEMPLATE" "$INSTALL_ROOT/.env"
  log_warn "Created .env from template. Fill API keys and passwords before production runs."
fi
set_env_key "$INSTALL_ROOT/.env" "BLUELOTUS_ROOT" "$INSTALL_ROOT"
set_env_key "$INSTALL_ROOT/.env" "MYSQL_HOST" "$MYSQL_HOST"
set_env_key "$INSTALL_ROOT/.env" "MYSQL_PORT" "$MYSQL_PORT"
set_env_key "$INSTALL_ROOT/.env" "MYSQL_DATABASE" "$MYSQL_DB"
set_env_key "$INSTALL_ROOT/.env" "MYSQL_USER" "$APP_DB_USER"
if [ -n "$APP_DB_PASSWORD" ]; then set_env_key "$INSTALL_ROOT/.env" "MYSQL_PASSWORD" "$APP_DB_PASSWORD"; fi
set_env_key "$INSTALL_ROOT/.env" "DB_HOST" "$MYSQL_HOST"
set_env_key "$INSTALL_ROOT/.env" "DB_PORT" "$MYSQL_PORT"
set_env_key "$INSTALL_ROOT/.env" "DB_NAME" "$MYSQL_DB"
set_env_key "$INSTALL_ROOT/.env" "DB_USER" "$APP_DB_USER"
if [ -n "$APP_DB_PASSWORD" ]; then set_env_key "$INSTALL_ROOT/.env" "DB_PASSWORD" "$APP_DB_PASSWORD"; fi

log_step "Creating Python virtual environment"
if [ ! -x "$INSTALL_ROOT/.venv/bin/python" ]; then
  "$PYTHON_CMD" -m venv "$INSTALL_ROOT/.venv"
fi
VENV_PY="$INSTALL_ROOT/.venv/bin/python"
log_ok "Virtual environment ready: $INSTALL_ROOT/.venv"

log_step "Installing Python dependencies"
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r "$REQ_FILE"
log_ok "Dependencies installed"

if [ "$INIT_DB" -eq 1 ]; then
  log_step "Initializing MySQL database"
  DB_ARGS=(
    "$SCRIPT_DIR/scripts/initialize_database.py"
    --root "$INSTALL_ROOT"
    --schema "$SCHEMA_FILE"
    --host "$MYSQL_HOST"
    --port "$MYSQL_PORT"
    --database "$MYSQL_DB"
    --admin-user "$MYSQL_ADMIN_USER"
    --app-user "$APP_DB_USER"
  )
  if [ -n "$MYSQL_ADMIN_PASSWORD" ]; then DB_ARGS+=(--admin-password "$MYSQL_ADMIN_PASSWORD"); fi
  if [ -n "$APP_DB_PASSWORD" ]; then DB_ARGS+=(--app-password "$APP_DB_PASSWORD"); fi
  "$VENV_PY" "${DB_ARGS[@]}"
  log_ok "Database initialized"
else
  log_warn "Database initialization skipped. See MACOS_MYSQL_8_4_9_INSTALL_GUIDE.md."
fi

if [ "$INSTALL_LAUNCHAGENT" -eq 1 ]; then
  log_step "Installing LaunchAgent"
  install_launchagent
else
  log_warn "LaunchAgent not installed. Use --install-launchagent for 24/7 collection."
fi

log_step "Running validator"
VALIDATE_ARGS=("$SCRIPT_DIR/scripts/validate_environment_macos.py" --root "$INSTALL_ROOT")
if [ "$CHECK_MOOMOO" -eq 1 ]; then VALIDATE_ARGS+=(--check-moomoo); fi
"$VENV_PY" "${VALIDATE_ARGS[@]}" || log_warn "Validation reported issues. Fix before production hourly collection."

cat <<EOF

BlueLotus V2 macOS collector install finished.

Run once:
  $INSTALL_ROOT/run_bluelotus_v2_once_macos.sh

Run hourly:
  $INSTALL_ROOT/run_bluelotus_v2_hourly_macos.sh

Reports:
  $INSTALL_ROOT/research

Logs:
  $INSTALL_ROOT/logs
EOF
