-- =============================================================================
-- Protein cascade fix
--
-- proteins is a shared catalog (UNIQUE on pdb_id, one row per PDB entry).
-- The previous schema had proteins.created_by cascade-delete with auth.users,
-- which meant deleting the first-fetcher's account dropped the shared row —
-- and via docking_runs.protein_id ON DELETE CASCADE, this cascade-deleted
-- every other user's docking runs against that PDB.
--
-- Treat created_by as attribution metadata only: nullable, ON DELETE SET NULL.
-- Prevent protein deletion while any docking_run references it (RESTRICT).
-- =============================================================================

alter table public.proteins
    alter column created_by drop not null;

alter table public.proteins
    drop constraint proteins_created_by_fkey;

alter table public.proteins
    add constraint proteins_created_by_fkey
    foreign key (created_by) references auth.users(id) on delete set null;

alter table public.docking_runs
    drop constraint docking_runs_protein_id_fkey;

alter table public.docking_runs
    add constraint docking_runs_protein_id_fkey
    foreign key (protein_id) references public.proteins(id) on delete restrict;
