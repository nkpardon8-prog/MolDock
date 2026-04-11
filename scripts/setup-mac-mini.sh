#!/bin/bash
set -e

# =============================================================================
# MoleCopilot Mac Mini Setup Script
#
# Automated setup for the MoleCopilot API backend on macOS.
# This script is idempotent -- safe to run multiple times.
#
# What it does:
#   - Checks prerequisites (brew, git, conda, claude)
#   - Installs miniforge if not present
#   - Runs setup.sh for the conda environment
#   - Installs API dependencies (FastAPI, Celery, etc.)
#   - Installs and starts Redis
#   - Creates launchd plist files for all 4 services
#   - Loads the services
#   - Runs a health check
#
# What it does NOT do (requires interactive auth):
#   - Clone the repo (step 1 in MAC-MINI-SETUP.md)
#   - Configure Cloudflare Tunnel (step 6)
#   - Set up Tailscale (step 7)
#   - Fill in .env values (step 5 -- it copies the template but you must edit it)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/MoleCopilot"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
USERNAME="$(whoami)"

echo "============================================="
echo "  MoleCopilot Mac Mini Setup"
echo "============================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "User: $USERNAME"
echo ""

# -----------------------------------------------------------------------------
# Prerequisites
# -----------------------------------------------------------------------------

echo "[1/9] Checking prerequisites..."

if ! command -v brew &> /dev/null; then
    echo "ERROR: Homebrew not found. Install it first:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi
echo "  Homebrew: OK"

if ! command -v git &> /dev/null; then
    echo "ERROR: git not found. Install with: brew install git"
    exit 1
fi
echo "  git: OK"

if ! command -v claude &> /dev/null; then
    echo "WARNING: Claude Code CLI not found. Chat functionality will not work."
    echo "  Install with: npm install -g @anthropic-ai/claude-code"
    echo "  Continuing anyway..."
else
    echo "  Claude Code CLI: OK"
fi

echo ""

# -----------------------------------------------------------------------------
# Install miniforge (conda) if not present
# -----------------------------------------------------------------------------

echo "[2/9] Checking conda..."

if ! command -v conda &> /dev/null; then
    echo "  conda not found. Installing miniforge via Homebrew..."
    brew install miniforge
    # Initialize conda for the current shell
    conda init "$(basename "$SHELL")"
    echo ""
    echo "  miniforge installed. You may need to restart your shell."
    echo "  After restarting, re-run this script."
    exit 0
else
    echo "  conda: OK ($(conda --version))"
fi

echo ""

# -----------------------------------------------------------------------------
# Create conda environment
# -----------------------------------------------------------------------------

echo "[3/9] Setting up conda environment..."

if conda env list | grep -q "molecopilot"; then
    echo "  Conda env 'molecopilot' already exists. Skipping creation."
    echo "  To recreate: conda env remove -n molecopilot && re-run this script"
else
    echo "  Running setup.sh to create the molecopilot environment..."
    bash "$PROJECT_ROOT/setup.sh"
fi

echo ""

# -----------------------------------------------------------------------------
# Install API dependencies
# -----------------------------------------------------------------------------

echo "[4/9] Installing API dependencies..."

conda run -n molecopilot pip install -r "$PROJECT_ROOT/requirements-api.txt"

# Verify
conda run -n molecopilot python -c "import fastapi, celery, redis, supabase; print('  API dependencies: OK')"

echo ""

# -----------------------------------------------------------------------------
# Install and start Redis
# -----------------------------------------------------------------------------

echo "[5/9] Setting up Redis..."

if ! command -v redis-server &> /dev/null; then
    echo "  Installing Redis via Homebrew..."
    brew install redis
else
    echo "  Redis already installed: OK"
fi

# Check if Redis is running
if redis-cli ping &> /dev/null; then
    echo "  Redis is already running: OK"
else
    echo "  Starting Redis..."
    redis-server --daemonize yes --port 6379
    sleep 1
    if redis-cli ping &> /dev/null; then
        echo "  Redis started: OK"
    else
        echo "  WARNING: Redis failed to start. Check manually."
    fi
fi

echo ""

# -----------------------------------------------------------------------------
# Copy .env template if not present
# -----------------------------------------------------------------------------

echo "[6/9] Checking .env configuration..."

if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "  .env file exists. Skipping copy."
    echo "  Make sure your Supabase keys are filled in."
else
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo "  Copied .env.example to .env"
        echo "  IMPORTANT: Edit $PROJECT_ROOT/.env and fill in your Supabase keys."
        echo "  The API will not start correctly without valid Supabase credentials."
    else
        echo "  WARNING: No .env.example found. Create .env manually."
    fi
fi

echo ""

# -----------------------------------------------------------------------------
# Find conda Python path
# -----------------------------------------------------------------------------

CONDA_PYTHON="$(conda run -n molecopilot which python)"
echo "  Conda Python: $CONDA_PYTHON"

# Verify the path exists
if [ ! -f "$CONDA_PYTHON" ]; then
    echo "ERROR: Conda Python binary not found at $CONDA_PYTHON"
    exit 1
fi

echo ""

# -----------------------------------------------------------------------------
# Create log directory
# -----------------------------------------------------------------------------

echo "[7/9] Creating directories..."

mkdir -p "$LOG_DIR"
echo "  Log directory: $LOG_DIR"

mkdir -p "$LAUNCH_DIR"
echo "  LaunchAgents directory: $LAUNCH_DIR"

# Create data directories
mkdir -p "$PROJECT_ROOT/data/proteins"
mkdir -p "$PROJECT_ROOT/data/ligands"
mkdir -p "$PROJECT_ROOT/data/results"
mkdir -p "$PROJECT_ROOT/data/libraries"
mkdir -p "$PROJECT_ROOT/reports"
echo "  Data directories: OK"

echo ""

# -----------------------------------------------------------------------------
# Create launchd plist files
# -----------------------------------------------------------------------------

echo "[8/9] Creating launchd service definitions..."

# Unload existing services (ignore errors if they don't exist)
launchctl unload "$LAUNCH_DIR/com.molecopilot.redis.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_DIR/com.molecopilot.api.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_DIR/com.molecopilot.celery.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_DIR/com.molecopilot.tunnel.plist" 2>/dev/null || true

# Determine redis-server path
REDIS_PATH="$(which redis-server)"

# Determine cloudflared path
CLOUDFLARED_PATH="$(which cloudflared 2>/dev/null || echo "/opt/homebrew/bin/cloudflared")"

# --- Redis ---
cat > "$LAUNCH_DIR/com.molecopilot.redis.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.redis</string>
    <key>ProgramArguments</key>
    <array>
        <string>${REDIS_PATH}</string>
        <string>--port</string>
        <string>6379</string>
        <string>--daemonize</string>
        <string>no</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/redis.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/redis.err</string>
</dict>
</plist>
PLIST
echo "  Created com.molecopilot.redis.plist"

# --- FastAPI ---
cat > "$LAUNCH_DIR/com.molecopilot.api.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CONDA_PYTHON}</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>api.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${PROJECT_ROOT}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/api.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/api.err</string>
</dict>
</plist>
PLIST
echo "  Created com.molecopilot.api.plist"

# --- Celery ---
cat > "$LAUNCH_DIR/com.molecopilot.celery.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.celery</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CONDA_PYTHON}</string>
        <string>-m</string>
        <string>celery</string>
        <string>-A</string>
        <string>api.jobs</string>
        <string>worker</string>
        <string>--loglevel=info</string>
        <string>--concurrency=2</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${PROJECT_ROOT}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/celery.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/celery.err</string>
</dict>
</plist>
PLIST
echo "  Created com.molecopilot.celery.plist"

# --- Cloudflare Tunnel ---
if [ -f "$HOME/.cloudflared/config.yml" ]; then
    cat > "$LAUNCH_DIR/com.molecopilot.tunnel.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CLOUDFLARED_PATH}</string>
        <string>tunnel</string>
        <string>run</string>
        <string>molecopilot</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/tunnel.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/tunnel.err</string>
</dict>
</plist>
PLIST
    echo "  Created com.molecopilot.tunnel.plist"
else
    echo "  SKIPPED com.molecopilot.tunnel.plist (no ~/.cloudflared/config.yml found)"
    echo "  Set up Cloudflare Tunnel first (see docs/MAC-MINI-SETUP.md step 6)"
fi

echo ""

# -----------------------------------------------------------------------------
# Load services
# -----------------------------------------------------------------------------

echo "[9/9] Loading services..."

# Stop any manually-started Redis first
redis-cli shutdown 2>/dev/null || true
sleep 1

launchctl load "$LAUNCH_DIR/com.molecopilot.redis.plist"
echo "  Loaded com.molecopilot.redis"

# Wait for Redis to be ready
for i in 1 2 3 4 5; do
    if redis-cli ping &> /dev/null; then
        break
    fi
    sleep 1
done

launchctl load "$LAUNCH_DIR/com.molecopilot.api.plist"
echo "  Loaded com.molecopilot.api"

launchctl load "$LAUNCH_DIR/com.molecopilot.celery.plist"
echo "  Loaded com.molecopilot.celery"

if [ -f "$LAUNCH_DIR/com.molecopilot.tunnel.plist" ]; then
    launchctl load "$LAUNCH_DIR/com.molecopilot.tunnel.plist"
    echo "  Loaded com.molecopilot.tunnel"
fi

echo ""

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------

echo "Running health checks..."
echo ""

# Wait for API to start
sleep 3

# Redis
if redis-cli ping &> /dev/null; then
    echo "  Redis: OK"
else
    echo "  Redis: FAILED (check $LOG_DIR/redis.err)"
fi

# API
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "  FastAPI: OK (http://localhost:8000/api/health)"
else
    echo "  FastAPI: FAILED (HTTP $HTTP_CODE -- check $LOG_DIR/api.err)"
    echo "  If you see .env errors, make sure Supabase keys are configured."
fi

# Celery (check if process is running)
if launchctl list | grep -q "com.molecopilot.celery"; then
    CELERY_PID=$(launchctl list | grep com.molecopilot.celery | awk '{print $1}')
    if [ "$CELERY_PID" != "-" ] && [ -n "$CELERY_PID" ]; then
        echo "  Celery: OK (PID $CELERY_PID)"
    else
        echo "  Celery: FAILED (not running -- check $LOG_DIR/celery.err)"
    fi
else
    echo "  Celery: NOT LOADED"
fi

# Tunnel
if [ -f "$LAUNCH_DIR/com.molecopilot.tunnel.plist" ]; then
    if launchctl list | grep -q "com.molecopilot.tunnel"; then
        TUNNEL_PID=$(launchctl list | grep com.molecopilot.tunnel | awk '{print $1}')
        if [ "$TUNNEL_PID" != "-" ] && [ -n "$TUNNEL_PID" ]; then
            echo "  Cloudflare Tunnel: OK (PID $TUNNEL_PID)"
        else
            echo "  Cloudflare Tunnel: FAILED (check $LOG_DIR/tunnel.err)"
        fi
    else
        echo "  Cloudflare Tunnel: NOT LOADED"
    fi
else
    echo "  Cloudflare Tunnel: SKIPPED (not configured)"
fi

echo ""
echo "============================================="
echo "  Setup complete!"
echo "============================================="
echo ""
echo "Services are running. Check status with:"
echo "  launchctl list | grep molecopilot"
echo ""
echo "View logs:"
echo "  tail -f $LOG_DIR/api.log"
echo "  tail -f $LOG_DIR/celery.log"
echo ""
echo "Next steps:"
echo "  1. Edit $PROJECT_ROOT/.env with your Supabase keys (if not done)"
echo "  2. Set up Cloudflare Tunnel (see docs/MAC-MINI-SETUP.md step 6)"
echo "  3. Set up Tailscale for remote SSH (see docs/MAC-MINI-SETUP.md step 7)"
echo ""
