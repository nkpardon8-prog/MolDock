-- =============================================================================
-- MoleCopilot Supabase Schema
--
-- Full PostgreSQL schema for the MoleCopilot project.
-- This file is documentation/reference -- the migration was already applied
-- via the Supabase API. To recreate from scratch, run this SQL in the
-- Supabase SQL Editor.
--
-- Tables:
--   1. proteins         -- Protein structures fetched from RCSB PDB
--   2. compounds        -- Chemical compounds with SMILES, ADMET data
--   3. docking_runs     -- Docking results (energies, grid box, interactions)
--   4. chat_sessions    -- Chat session metadata (title, owner)
--   5. chat_messages    -- Individual chat messages per session
--   6. jobs             -- Background job tracking (Celery tasks)
--   7. literature_searches -- Saved PubMed/ChEMBL/Perplexity search results
--
-- All tables use UUIDs as primary keys and include RLS policies that
-- restrict access to the owning user (identified by auth.uid()).
-- =============================================================================

-- Enable the uuid extension (usually already enabled in Supabase)
create extension if not exists "uuid-ossp";


-- ---------------------------------------------------------------------------
-- 1. proteins
--
-- Stores protein structures fetched from RCSB PDB. Deduplication is by
-- pdb_id (the 4-character PDB identifier like '3S7S'). The binding_site
-- column stores the detected binding pocket as JSONB (center_x/y/z,
-- size_x/y/z). File paths (pdb_path, pdbqt_path) are relative to the
-- project data directory.
-- ---------------------------------------------------------------------------

create table if not exists proteins (
    id          uuid primary key default uuid_generate_v4(),
    created_by  uuid references auth.users(id) on delete cascade not null,
    pdb_id      text unique not null,
    title       text,
    organism    text,
    resolution  double precision,
    method      text,
    pdb_path    text,
    pdbqt_path  text,
    binding_site jsonb,
    created_at  timestamptz default now() not null
);

alter table proteins enable row level security;

create policy "Users can view their own proteins"
    on proteins for select
    using (auth.uid() = created_by);

create policy "Users can insert their own proteins"
    on proteins for insert
    with check (auth.uid() = created_by);

create policy "Users can update their own proteins"
    on proteins for update
    using (auth.uid() = created_by);

create policy "Users can delete their own proteins"
    on proteins for delete
    using (auth.uid() = created_by);


-- ---------------------------------------------------------------------------
-- 2. compounds
--
-- Stores chemical compounds. Identified by SMILES string (canonical) or
-- PubChem CID. The admet column stores the full ADMET analysis result as
-- JSONB (Lipinski properties, Veber rules, SA score, etc.).
-- drug_likeness_score is extracted from admet for fast sorting/filtering
-- (0.0 = fails all Lipinski rules, 1.0 = passes all).
-- ---------------------------------------------------------------------------

create table if not exists compounds (
    id                  uuid primary key default uuid_generate_v4(),
    created_by          uuid references auth.users(id) on delete cascade not null,
    name                text,
    smiles              text,
    cid                 text,
    sdf_path            text,
    pdbqt_path          text,
    admet               jsonb,
    drug_likeness_score double precision,
    created_at          timestamptz default now() not null
);

alter table compounds enable row level security;

create policy "Users can view their own compounds"
    on compounds for select
    using (auth.uid() = created_by);

create policy "Users can insert their own compounds"
    on compounds for insert
    with check (auth.uid() = created_by);

create policy "Users can update their own compounds"
    on compounds for update
    using (auth.uid() = created_by);

create policy "Users can delete their own compounds"
    on compounds for delete
    using (auth.uid() = created_by);


-- ---------------------------------------------------------------------------
-- 3. docking_runs
--
-- Stores the results of each AutoDock Vina docking run. References both a
-- protein and a compound. Grid box is defined by center (x/y/z) and size
-- (x/y/z) in Angstroms. best_energy is the top-scoring pose energy in
-- kcal/mol (more negative = stronger binding). all_energies stores every
-- pose energy as a JSONB array. interactions stores PLIP analysis results.
-- ---------------------------------------------------------------------------

create table if not exists docking_runs (
    id              uuid primary key default uuid_generate_v4(),
    user_id         uuid references auth.users(id) on delete cascade not null,
    protein_id      uuid references proteins(id) on delete cascade not null,
    compound_id     uuid references compounds(id) on delete cascade not null,
    best_energy     double precision,
    all_energies    jsonb,
    exhaustiveness  integer default 32,
    center_x        double precision,
    center_y        double precision,
    center_z        double precision,
    size_x          double precision,
    size_y          double precision,
    size_z          double precision,
    output_path     text,
    interactions    jsonb,
    created_at      timestamptz default now() not null
);

alter table docking_runs enable row level security;

create policy "Users can view their own docking runs"
    on docking_runs for select
    using (auth.uid() = user_id);

create policy "Users can insert their own docking runs"
    on docking_runs for insert
    with check (auth.uid() = user_id);

create policy "Users can update their own docking runs"
    on docking_runs for update
    using (auth.uid() = user_id);

create policy "Users can delete their own docking runs"
    on docking_runs for delete
    using (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 4. chat_sessions
--
-- Groups chat messages into sessions. Each session has a title (usually
-- the first user message, truncated to 50 chars). Users can have multiple
-- concurrent sessions.
-- ---------------------------------------------------------------------------

create table if not exists chat_sessions (
    id          uuid primary key default uuid_generate_v4(),
    user_id     uuid references auth.users(id) on delete cascade not null,
    title       text not null,
    created_at  timestamptz default now() not null
);

alter table chat_sessions enable row level security;

create policy "Users can view their own chat sessions"
    on chat_sessions for select
    using (auth.uid() = user_id);

create policy "Users can insert their own chat sessions"
    on chat_sessions for insert
    with check (auth.uid() = user_id);

create policy "Users can delete their own chat sessions"
    on chat_sessions for delete
    using (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 5. chat_messages
--
-- Individual messages within a chat session. Role is 'user' or 'assistant'.
-- Artifacts stores optional structured data returned by tools (e.g., docking
-- results, ADMET data) as JSONB.
-- ---------------------------------------------------------------------------

create table if not exists chat_messages (
    id          uuid primary key default uuid_generate_v4(),
    session_id  uuid references chat_sessions(id) on delete cascade not null,
    role        text not null check (role in ('user', 'assistant')),
    content     text not null,
    artifacts   jsonb,
    created_at  timestamptz default now() not null
);

alter table chat_messages enable row level security;

-- Messages are accessed via their session; the policy joins to chat_sessions
-- to verify ownership.
create policy "Users can view messages in their own sessions"
    on chat_messages for select
    using (
        exists (
            select 1 from chat_sessions
            where chat_sessions.id = chat_messages.session_id
              and chat_sessions.user_id = auth.uid()
        )
    );

create policy "Users can insert messages in their own sessions"
    on chat_messages for insert
    with check (
        exists (
            select 1 from chat_sessions
            where chat_sessions.id = chat_messages.session_id
              and chat_sessions.user_id = auth.uid()
        )
    );

create policy "Users can delete messages in their own sessions"
    on chat_messages for delete
    using (
        exists (
            select 1 from chat_sessions
            where chat_sessions.id = chat_messages.session_id
              and chat_sessions.user_id = auth.uid()
        )
    );


-- ---------------------------------------------------------------------------
-- 6. jobs
--
-- Tracks background jobs processed by Celery workers. job_type is one of
-- 'dock', 'chat', or 'optimize'. Status transitions: pending -> running ->
-- complete|failed. input_data stores the original request parameters.
-- result stores the final output (docking energies, chat response, etc.).
-- error stores the error message if the job failed.
-- ---------------------------------------------------------------------------

create table if not exists jobs (
    id            uuid primary key default uuid_generate_v4(),
    user_id       uuid references auth.users(id) on delete cascade not null,
    job_type      text not null,
    status        text not null default 'pending'
                      check (status in ('pending', 'running', 'complete', 'failed')),
    input         jsonb,
    result        jsonb,
    error         text,
    created_at    timestamptz default now() not null,
    started_at    timestamptz,
    completed_at  timestamptz
);

alter table jobs enable row level security;

create policy "Users can view their own jobs"
    on jobs for select
    using (auth.uid() = user_id);

create policy "Users can insert their own jobs"
    on jobs for insert
    with check (auth.uid() = user_id);

create policy "Users can update their own jobs"
    on jobs for update
    using (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 8. run_reports
--
-- Per-run narrative reports generated by LLM from run data. run_id is nullable:
-- for project-rollup reports it is NULL and source_run_ids holds the aggregated
-- docking_runs.id list. The partial unique index enforces one report per
-- (run_id, run_type) for non-project types; projects can freely coexist since
-- NULLs are distinct in PG unique indexes.
-- ---------------------------------------------------------------------------

create table if not exists run_reports (
    id                  uuid primary key default uuid_generate_v4(),
    user_id             uuid references auth.users(id) on delete cascade not null,
    run_id              uuid,
    run_type            text not null check (run_type in ('dock', 'optimize', 'chat_session', 'project')),
    research_question   text,
    display_title       text,
    sections            jsonb not null,
    model               text not null,
    source_run_ids      jsonb,
    status              text not null default 'complete'
                            check (status in ('complete', 'failed')),
    error               text,
    created_at          timestamptz default now() not null,
    regenerated_at      timestamptz
);

create unique index if not exists uq_run_reports_run
    on run_reports(run_id, run_type)
    where run_id is not null;

alter table run_reports enable row level security;

create policy "Users can view their own run reports"
    on run_reports for select using (auth.uid() = user_id);
create policy "Users can insert their own run reports"
    on run_reports for insert with check (auth.uid() = user_id);
create policy "Users can update their own run reports"
    on run_reports for update using (auth.uid() = user_id);
create policy "Users can delete their own run reports"
    on run_reports for delete using (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 7. literature_searches
--
-- Stores saved literature search results from PubMed, ChEMBL, Perplexity,
-- or UniProt. Results are stored as JSONB (the raw API response). Tags are
-- user-assigned labels stored as a JSONB array of strings. Timeframe is an
-- optional filter like '5years' used in the original search.
-- ---------------------------------------------------------------------------

create table if not exists literature_searches (
    id          uuid primary key default uuid_generate_v4(),
    user_id     uuid references auth.users(id) on delete cascade not null,
    query       text not null,
    source_type text not null,
    results     jsonb not null,
    tags        jsonb default '[]'::jsonb,
    timeframe   text,
    created_at  timestamptz default now() not null
);

alter table literature_searches enable row level security;

create policy "Users can view their own literature searches"
    on literature_searches for select
    using (auth.uid() = user_id);

create policy "Users can insert their own literature searches"
    on literature_searches for insert
    with check (auth.uid() = user_id);

create policy "Users can update their own literature searches"
    on literature_searches for update
    using (auth.uid() = user_id);

create policy "Users can delete their own literature searches"
    on literature_searches for delete
    using (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Fast lookup by PDB ID (already unique but explicit index for clarity)
create index if not exists idx_proteins_pdb_id on proteins(pdb_id);

-- Fast lookup by SMILES
create index if not exists idx_compounds_smiles on compounds(smiles);

-- Sort docking runs by energy (best first)
create index if not exists idx_docking_runs_energy on docking_runs(best_energy asc);

-- List docking runs by user, newest first
create index if not exists idx_docking_runs_user_date on docking_runs(user_id, created_at desc);

-- List chat sessions by user, newest first
create index if not exists idx_chat_sessions_user_date on chat_sessions(user_id, created_at desc);

-- List chat messages by session, chronological
create index if not exists idx_chat_messages_session_date on chat_messages(session_id, created_at asc);

-- List jobs by user, newest first
create index if not exists idx_jobs_user_date on jobs(user_id, created_at desc);

-- List run reports by user, newest first; lookup by (run_id, run_type)
create index if not exists idx_run_reports_user_date on run_reports(user_id, created_at desc);
create index if not exists idx_run_reports_run on run_reports(run_id, run_type);

-- Filter literature searches by source type and date
create index if not exists idx_literature_source_date on literature_searches(source_type, created_at desc);
