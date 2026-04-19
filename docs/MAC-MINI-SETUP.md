# Mac Mini Deployment Guide

Step-by-step guide for deploying MoleCopilot on a Mac Mini as a self-hosted API backend.
The frontend (React) is deployed separately on Netlify. This guide covers only the
backend services: FastAPI, Celery, Redis, and Cloudflare Tunnel.

---

## Prerequisites

- macOS (Apple Silicon or Intel)
- Homebrew installed (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`)
- Claude Code CLI installed and authenticated with a Max subscription
- A domain name pointed to Cloudflare (for the tunnel)
- A Cloudflare account (free tier is sufficient)
- Git access to the MoleCopilot repository
- A Supabase project with the schema applied (see `supabase/schema.sql`)

---

## Step 1: Clone the Repository

```bash
git clone <repo-url> ~/MolDock
cd ~/MolDock
```

---

## Step 2: Install System Dependencies

```bash
brew install miniforge redis
```

If `miniforge` was already installed via another method (e.g., the installer pkg), skip
that part. Verify with:

```bash
conda --version
redis-server --version
```

---

## Step 3: Create the Conda Environment

```bash
cd ~/MolDock
bash setup.sh
```

This creates the `molecopilot` conda environment with Python 3.12 and all 21 science
dependencies (AutoDock Vina, RDKit, PDBFixer, OpenMM, Open Babel, ProLIF, Meeko, PLIP,
BioPython, etc.). The script also runs `tests/verify_imports.py` to confirm everything
installed correctly.

If the script fails partway through, it is safe to re-run. Conda will skip packages
that are already installed.

---

## Step 4: Install API Dependencies

The API backend has its own requirements (FastAPI, Celery, Supabase client, SSE) that
are separate from the science stack:

```bash
conda run -n molecopilot pip install -r ~/MolDock/requirements-api.txt
```

Verify:

```bash
conda run -n molecopilot python -c "import fastapi, celery, redis, supabase; print('API deps OK')"
```

---

## Step 5: Configure Environment Variables

```bash
cp ~/MolDock/.env.example ~/MolDock/.env
```

Edit `~/MolDock/.env` and fill in the required values:

```
# Required -- Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_KEY=your_service_key_here

# Required -- Redis (default works if Redis is running locally)
REDIS_URL=redis://localhost:6379

# Optional -- NVIDIA BioNeMo (for molecular generation)
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx

# Optional -- Perplexity (for AI-powered literature search)
PERPLEXITY_API_KEY=your_key_here

# Optional -- NCBI (increases PubMed rate limit from 3 to 10 req/sec)
NCBI_API_KEY=your_key_here
```

Get Supabase keys from: Project Settings > API in the Supabase dashboard.

---

## Step 6: Install and Configure Cloudflare Tunnel

Cloudflare Tunnel exposes the local FastAPI server to the internet without opening
any ports on the Mac Mini's firewall.

```bash
brew install cloudflared
cloudflared tunnel login
```

This opens a browser window. Log in and authorize the tunnel for your Cloudflare zone.

```bash
cloudflared tunnel create molecopilot
```

Note the tunnel ID printed (e.g., `a1b2c3d4-e5f6-...`). Then create a DNS route:

```bash
cloudflared tunnel route dns molecopilot api.yourdomain.com
```

Create the tunnel configuration file:

```bash
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <TUNNEL-ID>
credentials-file: /Users/<your-username>/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: api.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF
```

Replace `<TUNNEL-ID>` with the actual tunnel ID and `<your-username>` with your macOS
username. Test it:

```bash
cloudflared tunnel run molecopilot
```

If it connects without errors, stop it (Ctrl+C) and proceed to set it up as a service.

---

## Step 7: Install Tailscale (Remote SSH Access)

Tailscale provides a private VPN so you can SSH into the Mac Mini from anywhere for
maintenance, without exposing SSH to the public internet.

```bash
brew install tailscale
sudo tailscale up
```

Follow the URL printed to authenticate. Once connected:

```bash
# From any other device on your Tailscale network:
ssh <your-username>@<mac-mini-tailscale-hostname>
```

---

## Step 8: Create launchd Services

macOS uses `launchd` (not systemd) for managing services. Each service gets a `.plist`
file in `~/Library/LaunchAgents/`. These start automatically on login and restart on
failure.

First, create the log directory:

```bash
mkdir -p ~/Library/Logs/MoleCopilot
```

Find the conda Python binary path (needed for the plist files):

```bash
CONDA_PYTHON=$(conda run -n molecopilot which python)
echo "Conda Python: $CONDA_PYTHON"
```

It will be something like `/opt/homebrew/Caskroom/miniforge/base/envs/molecopilot/bin/python`.
Use this exact path in the plist files below.

### 8a. Redis Server

```bash
cat > ~/Library/LaunchAgents/com.molecopilot.redis.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.redis</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/redis-server</string>
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
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/redis.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/redis.err</string>
</dict>
</plist>
EOF
```

### 8b. FastAPI Server (uvicorn)

```bash
cat > ~/Library/LaunchAgents/com.molecopilot.api.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>CONDA_PYTHON_PATH</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>api.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOURUSERNAME/MolDock</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/YOURUSERNAME/MolDock</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/api.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/api.err</string>
</dict>
</plist>
EOF
```

Replace `CONDA_PYTHON_PATH` with the path from the `conda run -n molecopilot which python`
command above.

### 8c. Celery Worker

```bash
cat > ~/Library/LaunchAgents/com.molecopilot.celery.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.celery</string>
    <key>ProgramArguments</key>
    <array>
        <string>CONDA_PYTHON_PATH</string>
        <string>-m</string>
        <string>celery</string>
        <string>-A</string>
        <string>api.jobs</string>
        <string>worker</string>
        <string>--loglevel=info</string>
        <string>--concurrency=2</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOURUSERNAME/MolDock</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/YOURUSERNAME/MolDock</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/celery.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/celery.err</string>
</dict>
</plist>
EOF
```

Replace `CONDA_PYTHON_PATH` with the conda env Python path.

### 8d. Cloudflare Tunnel

```bash
cat > ~/Library/LaunchAgents/com.molecopilot.tunnel.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.molecopilot.tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/cloudflared</string>
        <string>tunnel</string>
        <string>run</string>
        <string>molecopilot</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/tunnel.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOURUSERNAME/Library/Logs/MoleCopilot/tunnel.err</string>
</dict>
</plist>
EOF
```

**Important:** In all four plist files above, replace `YOURUSERNAME` with your actual
macOS username. You can find it with `whoami`.

---

## Step 9: Start Services

Load all four services:

```bash
launchctl load ~/Library/LaunchAgents/com.molecopilot.redis.plist
launchctl load ~/Library/LaunchAgents/com.molecopilot.api.plist
launchctl load ~/Library/LaunchAgents/com.molecopilot.celery.plist
launchctl load ~/Library/LaunchAgents/com.molecopilot.tunnel.plist
```

Check they are running:

```bash
launchctl list | grep molecopilot
```

You should see all four services with a PID (first column). A `-` means the service
is not running -- check the error logs.

---

## Step 10: Verify

### Local health check

```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

### Remote health check (via Cloudflare Tunnel)

```bash
curl https://api.yourdomain.com/api/health
```

Expected: `{"status":"ok"}`

### Redis

```bash
redis-cli ping
```

Expected: `PONG`

### Celery

```bash
conda run -n molecopilot python -c "
from api.jobs import celery_app
i = celery_app.control.inspect()
print('Active workers:', list(i.active_queues() or {}).keys() if i.active_queues() else 'NONE')
"
```

---

## Troubleshooting

### Service fails to start

Check logs:

```bash
tail -50 ~/Library/Logs/MoleCopilot/api.err
tail -50 ~/Library/Logs/MoleCopilot/celery.err
tail -50 ~/Library/Logs/MoleCopilot/redis.err
tail -50 ~/Library/Logs/MoleCopilot/tunnel.err
```

### "Module not found" errors in API or Celery logs

The `PYTHONPATH` in the plist must point to the MolDock root directory. Verify:

```bash
conda run -n molecopilot python -c "import api.main; print('OK')"
```

### Wrong Python binary

The `ProgramArguments` in the plist must use the conda env Python, not the system Python.
Find it:

```bash
conda run -n molecopilot which python
```

### Redis connection refused

Ensure Redis is running on port 6379:

```bash
redis-cli ping
```

If it says "Connection refused", start Redis manually first to see the error:

```bash
redis-server --port 6379
```

### Celery "connection refused" to Redis

Same as above -- Celery uses Redis as its broker. If Redis is not running, Celery
will fail with a connection error.

### Cloudflare Tunnel "connection failed"

Ensure the tunnel credentials file exists:

```bash
ls ~/.cloudflared/*.json
```

If missing, re-run `cloudflared tunnel login` and `cloudflared tunnel create molecopilot`.

### API returns 401 on all requests

The API requires a Supabase JWT in the `Authorization: Bearer <token>` header for all
endpoints except `/api/health`. This is expected behavior -- the health check endpoint
is the one to use for deployment verification.

### Restarting a single service

```bash
launchctl stop com.molecopilot.api
launchctl start com.molecopilot.api
```

### Stopping all services

```bash
launchctl unload ~/Library/LaunchAgents/com.molecopilot.api.plist
launchctl unload ~/Library/LaunchAgents/com.molecopilot.celery.plist
launchctl unload ~/Library/LaunchAgents/com.molecopilot.redis.plist
launchctl unload ~/Library/LaunchAgents/com.molecopilot.tunnel.plist
```

### Updating the code

```bash
cd ~/MolDock
git pull
launchctl stop com.molecopilot.api
launchctl stop com.molecopilot.celery
launchctl start com.molecopilot.api
launchctl start com.molecopilot.celery
```

### Checking the Claude Code chat integration

The chat endpoint spawns `claude` as a subprocess. Verify Claude Code is installed and
accessible:

```bash
which claude
claude --version
```

The Celery worker runs `claude` with `--dangerously-skip-permissions` to allow autonomous
tool usage. This is required for the chat to invoke MCP tools. See the security notes
in `docs/ARCHITECTURE.md`.

---

## Automated Setup

For a faster setup, use the automated script:

```bash
bash ~/MolDock/scripts/setup-mac-mini.sh
```

This script performs steps 2-5 and 8-10 automatically. You still need to complete
steps 1 (clone), 6 (Cloudflare Tunnel), and 7 (Tailscale) manually, as they require
interactive authentication.
