# MoleCopilot Architecture

System architecture for the MoleCopilot molecular docking research platform.

---

## High-Level Overview

```
                          INTERNET
                             |
     +-----------------------+------------------------+
     |                                                |
     v                                                v
 +--------+                                    +------------+
 | Netlify |  (React frontend)                 | Cloudflare |
 | SPA     |                                   | Tunnel     |
 +----+----+                                   +-----+------+
      |                                              |
      |  HTTPS (Supabase Auth JWT)                   |  HTTPS -> HTTP
      |                                              |
      +----------------+  +--------------------------+
                       |  |
                       v  v
              +------------------+
              |   Mac Mini       |
              |                  |
              |  +-----------+   |
              |  | FastAPI   |   |  :8000
              |  | (uvicorn) |   |
              |  +-----+-----+   |
              |        |         |
              |  +-----+-----+  |
              |  |  Celery   |  |  (background jobs)
              |  |  Worker   |  |
              |  +-----+-----+  |
              |        |        |
              |  +-----+-----+ |
              |  |   Redis   | |  :6379 (broker + pub/sub)
              |  +-----------+ |
              +--------+-------+
                       |
                       v
              +------------------+
              | Supabase         |
              | (PostgreSQL +    |
              |  Auth + RLS)     |
              +------------------+
```

---

## Components

### Frontend (Netlify)

- **Stack:** React 19, TypeScript, Vite, Tailwind, shadcn/ui
- **Hosting:** Netlify (static SPA deployment)
- **Auth:** Supabase Auth (email/password). JWT stored in browser, sent as
  `Authorization: Bearer <token>` to the API.
- **Communication:** HTTPS to the Mac Mini API via Cloudflare Tunnel. SSE
  (Server-Sent Events) for streaming job progress.

### API Server (FastAPI)

- **File:** `api/main.py`
- **Runtime:** uvicorn, single process, bound to `0.0.0.0:8000`
- **Auth middleware:** `api/auth.py` validates the Supabase JWT on every request
  (except `/api/health`, `/docs`, `/openapi.json`). Extracts `user_id` and attaches
  it to `request.state.user_id`.
- **Routes:** 10 route modules under `api/routes/`:
  - `chat.py` -- Create sessions, send messages, trigger Claude Code jobs
  - `dock.py` -- Submit docking jobs
  - `proteins.py` -- CRUD for proteins, fetch from RCSB PDB
  - `compounds.py` -- CRUD for compounds, search PubChem
  - `admet.py` -- Run ADMET/drug-likeness analysis
  - `results.py` -- Query docking runs, compute interactions
  - `literature.py` -- PubMed and ChEMBL literature search
  - `optimize.py` -- Submit BioNeMo optimization jobs
  - `export.py` -- Export reports as DOCX, PDF, or XLSX
  - `jobs.py` -- Job status polling and SSE streaming
- **Database access:** `api/db.py` (Supabase client using the service key)
- **Configuration:** `api/config.py` (Pydantic Settings, reads `.env`)

### Background Workers (Celery)

- **File:** `api/jobs.py`
- **Broker:** Redis (same instance as pub/sub)
- **Concurrency:** 2 worker processes (configurable)
- **Job types:**
  - `run_dock_job` -- 7-step docking pipeline (fetch protein, detect binding site,
    prepare protein, resolve compound, prepare ligand, dock with Vina, run ADMET)
  - `run_chat_job` -- Spawns `claude` CLI as a subprocess with `--output-format
    stream-json`. Streams intermediate results to the frontend via Redis pub/sub.
  - `run_optimize_job` -- Calls NVIDIA MolMIM API for molecular optimization

Each job publishes progress events to Redis pub/sub AND buffers them in a Redis list
(`job:{id}:events`). This dual-write pattern fixes a race condition: if the SSE client
connects after events have already been published, it replays from the buffer first,
then subscribes to the live channel.

### Redis

- **Port:** 6379 (localhost only)
- **Roles:**
  1. Celery message broker (job queue)
  2. Celery result backend (job status/results)
  3. Pub/sub channel for SSE streaming (`job:{job_id}`)
  4. Event buffer for SSE replay (`job:{job_id}:events`, TTL 1 hour)

### Database (Supabase / PostgreSQL)

- **Schema:** 7 tables (see `supabase/schema.sql`)
  - `proteins` -- Protein structures fetched from RCSB PDB
  - `compounds` -- Chemical compounds with SMILES, ADMET data
  - `docking_runs` -- Docking results (energies, grid box, interactions)
  - `chat_sessions` -- Chat session metadata
  - `chat_messages` -- Individual chat messages per session
  - `jobs` -- Background job tracking (status, input, result, error)
  - `literature_searches` -- Saved literature search results
- **Auth:** Supabase Auth (email/password, JWT)
- **RLS:** Row-Level Security on all tables. Users can only access their own data.
- **Access patterns:**
  - Frontend reads directly from Supabase (anon key + RLS)
  - API uses the service key (bypasses RLS) for writes from background jobs

### Cloudflare Tunnel

- **Purpose:** Exposes the local FastAPI server to the internet without opening ports
  or configuring NAT/firewall rules on the Mac Mini.
- **Configuration:** `~/.cloudflared/config.yml` maps the hostname to `localhost:8000`.
- **DNS:** A CNAME record pointing `api.yourdomain.com` to the tunnel.
- **TLS:** Terminated at Cloudflare. Traffic from Cloudflare to the Mac Mini is plain
  HTTP over the encrypted tunnel.

### Local SQLite (Streamlit Dashboard)

- **File:** `molecopilot.db` (auto-created by `components/database.py`)
- **Purpose:** Local persistence for the Streamlit dashboard and MCP server. Contains
  the same entity types as the Supabase schema but in SQLite format. This is the
  original data store used before the API backend was added.
- **Not used by the API.** The API talks exclusively to Supabase.

---

## Data Flows

### Chat Request (SSE Streaming)

```
Browser                  API (FastAPI)           Celery Worker         Redis        Claude CLI
  |                         |                        |                  |              |
  |-- POST /api/chat ------>|                        |                  |              |
  |                         |-- create_job() ------->|                  |              |
  |                         |-- run_chat_job.delay()->|                  |              |
  |<-- {job_id, session_id}-|                        |                  |              |
  |                         |                        |                  |              |
  |-- GET /api/jobs/{id}/stream (SSE) -------------->|                  |              |
  |                         |                        |-- subprocess --->|              |
  |                         |                        |   claude -p ...  |              |
  |                         |                        |                  |              |
  |                         |                        |<-- stream-json --|              |
  |                         |                        |                  |              |
  |                         |                        |-- RPUSH + PUBLISH|              |
  |<--------- SSE event: progress (partial text) ----|                  |              |
  |<--------- SSE event: progress (more text) -------|                  |              |
  |<--------- SSE event: complete (final text) ------|                  |              |
  |                         |                        |                  |              |
```

1. Frontend sends `POST /api/chat` with the user message.
2. API creates a job row in Supabase, enqueues a Celery task, returns `job_id`.
3. Frontend opens an SSE connection to `GET /api/jobs/{job_id}/stream`.
4. SSE handler first replays any buffered events from `job:{id}:events` (Redis list),
   then subscribes to `job:{id}` (Redis pub/sub) for live events.
5. Celery worker spawns `claude -p <message> --output-format stream-json` as a
   subprocess. As Claude streams output, the worker parses each JSON line and publishes
   progress events.
6. On completion, the worker saves the assistant response to `chat_messages` in Supabase
   and publishes a `complete` event.
7. Frontend receives the `complete` event and closes the SSE connection.

### Docking Job

```
Browser                  API (FastAPI)           Celery Worker         Supabase
  |                         |                        |                  |
  |-- POST /api/dock ------>|                        |                  |
  |                         |-- create_job() ------->|                  |
  |                         |-- run_dock_job.delay()->|                  |
  |<-- {job_id} ------------|                        |                  |
  |                         |                        |                  |
  |-- GET /api/jobs/{id}/stream (SSE) -->            |                  |
  |                         |                        |                  |
  |<-- progress: Fetching protein... ----------------|                  |
  |<-- progress: Detecting binding site... ----------|                  |
  |<-- progress: Preparing protein... ---------------|                  |
  |<-- progress: Resolving compound... --------------|                  |
  |<-- progress: Preparing ligand... ----------------|                  |
  |<-- progress: Running AutoDock Vina... -----------|                  |
  |<-- progress: Running ADMET analysis... ----------|                  |
  |                         |                        |-- save_protein ->|
  |                         |                        |-- save_compound->|
  |                         |                        |-- save_docking ->|
  |<-- complete: {run_id, best_energy, admet} -------|                  |
```

The 7-step pipeline runs entirely in the Celery worker:
1. Fetch protein from RCSB PDB
2. Detect binding site from co-crystallized ligand
3. Prepare protein (clean, add H, convert to PDBQT)
4. Resolve compound (SMILES validation or PubChem search)
5. Prepare ligand (SDF to PDBQT via Meeko)
6. Dock with AutoDock Vina
7. Run ADMET/drug-likeness analysis

Results are persisted to Supabase (proteins, compounds, docking_runs tables).

---

## Technology Choices

| Component | Technology | Why |
|---|---|---|
| API framework | FastAPI | Async, auto-generated OpenAPI docs, Pydantic validation |
| Task queue | Celery + Redis | Docking jobs take 1-30 minutes; must run in background |
| Streaming | SSE (sse-starlette) | Simpler than WebSockets for one-directional progress updates |
| Database | Supabase (Postgres) | Auth + RLS + real-time subscriptions out of the box |
| Tunnel | Cloudflare Tunnel | Zero-config ingress, free, no port forwarding needed |
| Remote access | Tailscale | Private VPN for SSH maintenance without public exposure |
| Docking engine | AutoDock Vina | Gold standard academic docking, free, produces kcal/mol scores |
| Cheminformatics | RDKit | De facto standard Python cheminformatics toolkit |
| AI chat | Claude Code CLI | Subprocess invocation with MCP tool access to the science pipeline |
| Molecular gen. | NVIDIA MolMIM | Property-directed analog generation via CMA-ES in latent space |

---

## Security Considerations

### Claude Code and --dangerously-skip-permissions

The Celery worker spawns `claude` with the `--dangerously-skip-permissions` flag
(`api/jobs.py`, `run_chat_job`). This allows Claude to execute tools (docking,
literature search, ADMET checks, etc.) without requiring interactive approval for
each tool call.

**Risks:**
- Claude can execute arbitrary shell commands, read/write files, and make network
  requests on the Mac Mini.
- The 30-minute watchdog timer (`threading.Timer(1800, ...)`) limits runaway processes
  but does not prevent all abuse.

**Mitigations:**
- The API requires Supabase JWT authentication. Only authenticated users can trigger
  chat jobs.
- The Mac Mini should not store sensitive credentials beyond what is in `.env`.
- The Cloudflare Tunnel only exposes port 8000 (the API). No SSH or other services
  are exposed to the public internet.
- Tailscale provides a private network for administrative SSH access.
- The Celery worker runs as the logged-in user, not root.

### Network Security

- **No open ports.** The Mac Mini does not need any inbound firewall rules. Cloudflare
  Tunnel initiates an outbound connection to Cloudflare's edge.
- **TLS everywhere.** Browser-to-Cloudflare is HTTPS. Cloudflare-to-Mac-Mini is an
  encrypted tunnel. Browser-to-Supabase is HTTPS.
- **Local-only Redis.** Redis binds to `localhost:6379` and is not accessible from
  the network.

### Supabase RLS

All 7 tables have Row-Level Security policies that restrict access to the owning user.
The API uses the service key (which bypasses RLS) only for writes from Celery workers
that run on behalf of authenticated users. The frontend uses the anon key with RLS
enforced.

---

## File System Layout on Mac Mini

```
~/MolDock/                          # Project root
  api/
    main.py                         # FastAPI app factory
    config.py                       # Settings (reads .env)
    auth.py                         # JWT validation middleware
    db.py                           # Supabase data access layer
    schemas.py                      # Pydantic request/response models
    jobs.py                         # Celery task definitions
    routes/                         # 10 API route modules
  core/                             # Science pipeline modules
    fetch_pdb.py                    # RCSB PDB protein download
    prep_protein.py                 # Protein cleaning + PDBQT conversion
    fetch_compounds.py              # PubChem compound search + SDF download
    prep_ligand.py                  # Ligand PDBQT conversion (Meeko/OpenBabel)
    dock_vina.py                    # AutoDock Vina docking
    analyze_results.py              # PLIP interactions + ranking
    admet_check.py                  # Drug-likeness (Lipinski, Veber, SA score)
    bionemo.py                      # NVIDIA MolMIM API wrapper
    literature.py                   # PubMed, ChEMBL, UniProt, Perplexity
    export_docs.py                  # DOCX/PDF/XLSX report export
    generate_figures.py             # Matplotlib/RDKit figure generation
    utils.py                        # Shared paths and helpers
  components/                       # Streamlit dashboard components
    database.py                     # SQLite data access (local dashboard)
    charts.py                       # Plotly chart builders
    mol3d.py                        # py3Dmol 3D viewer
    file_viewer.py                  # File content viewer
  pages/                            # Streamlit dashboard pages (8)
  mcp_server.py                     # MCP server (22 tools via FastMCP)
  app.py                            # Streamlit entry point
  setup.sh                          # Conda environment setup
  .env                              # Environment variables (not in git)
  .env.example                      # Template for .env
  molecopilot.db                    # SQLite database (local, not in git)
  data/                             # Runtime data (not in git)
    proteins/                       # Downloaded PDB files
    ligands/                        # Prepared ligand files
    results/                        # Docking output files
    libraries/                      # Compound libraries
  reports/                          # Generated reports (not in git)
  docs/
    TOOLS.md                        # Tool & software registry
    ARCHITECTURE.md                 # This file
    MAC-MINI-SETUP.md               # Deployment guide
  scripts/
    setup-mac-mini.sh               # Automated deployment script
  supabase/
    schema.sql                      # PostgreSQL schema reference
  tests/
    test_pipeline.py                # Pipeline integration tests
    verify_imports.py               # Dependency verification

~/Library/LaunchAgents/             # macOS service definitions
  com.molecopilot.api.plist
  com.molecopilot.celery.plist
  com.molecopilot.redis.plist
  com.molecopilot.tunnel.plist

~/Library/Logs/MoleCopilot/         # Service logs
  api.log / api.err
  celery.log / celery.err
  redis.log / redis.err
  tunnel.log / tunnel.err

~/.cloudflared/
  config.yml                        # Tunnel configuration
  <tunnel-id>.json                  # Tunnel credentials
```

---

## MCP Server

The MCP (Model Context Protocol) server (`mcp_server.py`) exposes 22 tools that wrap
the `core/` science modules. It is used by Claude Code when running as the AI chat
backend. The MCP server is not a network service -- it communicates over stdio with
the Claude CLI process that spawns it.

Tool categories:
- **Core Pipeline (6):** fetch_protein, prepare_protein, fetch_compound, prepare_ligand, dock, full_pipeline
- **Batch Operations (3):** batch_prepare_ligands, batch_dock, batch_admet
- **Analysis (5):** detect_binding_site, analyze_interactions, rank_results, admet_check, compare_compounds
- **Generative Chemistry (3):** generate_analogs, optimize_compound, synthetic_check
- **Database Queries (4):** search_proteins, search_compounds, search_literature, get_known_actives
- **Visualization & Output (4):** draw_molecule, protein_info, generate_report, export_report
