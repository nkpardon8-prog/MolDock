import json
from typing import Any, Optional

from supabase import create_client

from api.config import settings

_supabase = create_client(settings.supabase_url, settings.supabase_service_key)


# ---------------------------------------------------------------------------
# Proteins
# ---------------------------------------------------------------------------

def save_protein(
    created_by: str,
    pdb_id: str,
    title: Optional[str] = None,
    organism: Optional[str] = None,
    resolution: Optional[float] = None,
    method: Optional[str] = None,
    pdb_path: Optional[str] = None,
    pdbqt_path: Optional[str] = None,
    binding_site: Optional[dict] = None,
) -> dict:
    existing = (
        _supabase.table("proteins")
        .select("*")
        .eq("pdb_id", pdb_id)
        .maybe_single()
        .execute()
    )
    row: dict[str, Any] = {"pdb_id": pdb_id, "created_by": created_by}
    if title is not None:
        row["title"] = title
    if organism is not None:
        row["organism"] = organism
    if resolution is not None:
        row["resolution"] = resolution
    if method is not None:
        row["method"] = method
    if pdb_path is not None:
        row["pdb_path"] = pdb_path
    if pdbqt_path is not None:
        row["pdbqt_path"] = pdbqt_path
    if binding_site is not None:
        row["binding_site"] = binding_site

    if existing.data:
        update_row = {k: v for k, v in row.items() if k != "created_by"}
        result = (
            _supabase.table("proteins")
            .update(update_row)
            .eq("pdb_id", pdb_id)
            .execute()
        )
        return result.data[0]
    else:
        result = _supabase.table("proteins").insert(row).execute()
        return result.data[0]


def get_protein_by_pdb_id(pdb_id: str) -> Optional[dict]:
    result = (
        _supabase.table("proteins")
        .select("*")
        .eq("pdb_id", pdb_id)
        .maybe_single()
        .execute()
    )
    return result.data


def get_protein_by_id(protein_id: str) -> Optional[dict]:
    result = (
        _supabase.table("proteins")
        .select("*")
        .eq("id", protein_id)
        .maybe_single()
        .execute()
    )
    return result.data


def get_all_proteins(limit: int = 20, offset: int = 0) -> list[dict]:
    result = (
        _supabase.table("proteins")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


# ---------------------------------------------------------------------------
# Compounds
# ---------------------------------------------------------------------------

def save_compound(
    created_by: str,
    name: Optional[str] = None,
    smiles: Optional[str] = None,
    cid: Optional[str] = None,
    sdf_path: Optional[str] = None,
    pdbqt_path: Optional[str] = None,
    admet: Optional[dict] = None,
    drug_likeness_score: Optional[float] = None,
) -> dict:
    existing = None
    if smiles:
        existing = (
            _supabase.table("compounds")
            .select("*")
            .eq("smiles", smiles)
            .maybe_single()
            .execute()
        ).data

    row: dict[str, Any] = {"created_by": created_by}
    if name is not None:
        row["name"] = name
    if smiles is not None:
        row["smiles"] = smiles
    if cid is not None:
        row["cid"] = cid
    if sdf_path is not None:
        row["sdf_path"] = sdf_path
    if pdbqt_path is not None:
        row["pdbqt_path"] = pdbqt_path
    if admet is not None:
        row["admet"] = admet
    if drug_likeness_score is not None:
        row["drug_likeness_score"] = drug_likeness_score

    if existing:
        update_row = {k: v for k, v in row.items() if k != "created_by"}
        result = (
            _supabase.table("compounds")
            .update(update_row)
            .eq("smiles", smiles)
            .execute()
        )
        return result.data[0]
    else:
        result = _supabase.table("compounds").insert(row).execute()
        return result.data[0]


def get_compound_by_smiles(smiles: str) -> Optional[dict]:
    result = (
        _supabase.table("compounds")
        .select("*")
        .eq("smiles", smiles)
        .maybe_single()
        .execute()
    )
    return result.data


def get_all_compounds(limit: int = 20, offset: int = 0) -> list[dict]:
    result = (
        _supabase.table("compounds")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


# ---------------------------------------------------------------------------
# Docking Runs
# ---------------------------------------------------------------------------

def save_docking_run(
    user_id: str,
    protein_id: str,
    compound_id: str,
    best_energy: float,
    all_energies: Optional[list[float]] = None,
    exhaustiveness: int = 32,
    center: Optional[tuple[float, float, float]] = None,
    size: Optional[tuple[float, float, float]] = None,
    output_path: Optional[str] = None,
    interactions: Optional[dict] = None,
) -> dict:
    row: dict[str, Any] = {
        "user_id": user_id,
        "protein_id": protein_id,
        "compound_id": compound_id,
        "best_energy": best_energy,
        "exhaustiveness": exhaustiveness,
    }
    if all_energies is not None:
        row["all_energies"] = all_energies
    if center is not None:
        row["center_x"] = center[0]
        row["center_y"] = center[1]
        row["center_z"] = center[2]
    if size is not None:
        row["size_x"] = size[0]
        row["size_y"] = size[1]
        row["size_z"] = size[2]
    if output_path is not None:
        row["output_path"] = output_path
    if interactions is not None:
        row["interactions"] = interactions

    result = _supabase.table("docking_runs").insert(row).execute()
    return result.data[0]


def get_docking_runs(
    limit: int = 20,
    offset: int = 0,
    protein_id: Optional[str] = None,
    energy_min: Optional[float] = None,
    energy_max: Optional[float] = None,
) -> list[dict]:
    query = _supabase.table("docking_runs").select("*")
    if protein_id:
        query = query.eq("protein_id", protein_id)
    if energy_min is not None:
        query = query.gte("best_energy", energy_min)
    if energy_max is not None:
        query = query.lte("best_energy", energy_max)
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return result.data


def get_docking_run(run_id: str) -> Optional[dict]:
    result = (
        _supabase.table("docking_runs")
        .select("*")
        .eq("id", run_id)
        .maybe_single()
        .execute()
    )
    return result.data


def get_recent_docking_runs(limit: int = 10) -> list[dict]:
    result = (
        _supabase.table("docking_runs")
        .select("*, proteins(pdb_id), compounds(name)")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


# ---------------------------------------------------------------------------
# Chat (NEW data model: chat_sessions + chat_messages)
# ---------------------------------------------------------------------------

def create_chat_session(user_id: str, title: str) -> dict:
    result = (
        _supabase.table("chat_sessions")
        .insert({"user_id": user_id, "title": title})
        .execute()
    )
    return result.data[0]


def get_chat_sessions(user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    result = (
        _supabase.table("chat_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    artifacts: Optional[dict] = None,
) -> dict:
    row: dict[str, Any] = {
        "session_id": session_id,
        "role": role,
        "content": content,
    }
    if artifacts is not None:
        row["artifacts"] = artifacts

    result = _supabase.table("chat_messages").insert(row).execute()
    return result.data[0]


def get_chat_messages(session_id: str) -> list[dict]:
    result = (
        _supabase.table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def delete_chat_session(session_id: str) -> None:
    _supabase.table("chat_messages").delete().eq("session_id", session_id).execute()
    _supabase.table("chat_sessions").delete().eq("id", session_id).execute()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def create_job(user_id: str, job_type: str, input_data: dict) -> dict:
    result = (
        _supabase.table("jobs")
        .insert({
            "user_id": user_id,
            "job_type": job_type,
            "input": input_data,
            "status": "pending",
        })
        .execute()
    )
    return result.data[0]


def update_job(
    job_id: str,
    status: Optional[str] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> dict:
    row: dict[str, Any] = {}
    if status is not None:
        row["status"] = status
    if result is not None:
        row["result"] = result
    if error is not None:
        row["error"] = error

    if not row:
        return get_job(job_id)

    resp = (
        _supabase.table("jobs")
        .update(row)
        .eq("id", job_id)
        .execute()
    )
    return resp.data[0]


def get_job(job_id: str) -> Optional[dict]:
    result = (
        _supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .maybe_single()
        .execute()
    )
    return result.data


def verify_session_owner(session_id: str, user_id: str) -> dict:
    """Get session and verify ownership. Raises ValueError if not owned."""
    result = (
        _supabase.table("chat_sessions")
        .select("*")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ValueError("Session not found")
    if result.data.get("user_id") != user_id:
        raise ValueError("Not authorized")
    return result.data


def verify_job_owner(job_id: str, user_id: str) -> dict:
    """Get job and verify ownership. Raises ValueError if not owned."""
    result = (
        _supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ValueError("Job not found")
    if result.data.get("user_id") != user_id:
        raise ValueError("Not authorized")
    return result.data


def verify_literature_owner(search_id: str, user_id: str) -> dict:
    """Get literature search and verify ownership. Raises ValueError if not owned."""
    result = (
        _supabase.table("literature_searches")
        .select("*")
        .eq("id", search_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise ValueError("Search not found")
    if result.data.get("user_id") != user_id:
        raise ValueError("Not authorized")
    return result.data


# ---------------------------------------------------------------------------
# Literature
# ---------------------------------------------------------------------------

def save_literature_search(
    user_id: str,
    query: str,
    source_type: str,
    results: Any,
    tags: Optional[list[str]] = None,
    timeframe: Optional[str] = None,
) -> dict:
    row: dict[str, Any] = {
        "user_id": user_id,
        "query": query,
        "source_type": source_type,
        "results": results,
    }
    if tags is not None:
        row["tags"] = tags
    if timeframe is not None:
        row["timeframe"] = timeframe

    resp = _supabase.table("literature_searches").insert(row).execute()
    return resp.data[0]


def get_literature_searches(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    result = (
        _supabase.table("literature_searches")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


def get_literature_search(search_id: str) -> Optional[dict]:
    result = (
        _supabase.table("literature_searches")
        .select("*")
        .eq("id", search_id)
        .maybe_single()
        .execute()
    )
    return result.data


def update_literature_search(
    search_id: str,
    results: Optional[Any] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    row: dict[str, Any] = {}
    if results is not None:
        row["results"] = results
    if tags is not None:
        row["tags"] = tags

    resp = (
        _supabase.table("literature_searches")
        .update(row)
        .eq("id", search_id)
        .execute()
    )
    return resp.data[0]


def delete_literature_search(search_id: str) -> None:
    _supabase.table("literature_searches").delete().eq("id", search_id).execute()


def get_all_literature_tags(user_id: str) -> list[str]:
    result = (
        _supabase.table("literature_searches")
        .select("tags")
        .eq("user_id", user_id)
        .execute()
    )
    all_tags = set()
    for row in result.data:
        tags = row.get("tags")
        if isinstance(tags, list):
            all_tags.update(tags)
    return sorted(all_tags)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    proteins = _supabase.table("proteins").select("id", count="exact").execute()
    compounds = _supabase.table("compounds").select("id", count="exact").execute()
    runs = _supabase.table("docking_runs").select("id", count="exact").execute()

    best_run = (
        _supabase.table("docking_runs")
        .select("best_energy")
        .order("best_energy", desc=False)
        .limit(1)
        .execute()
    )

    best_energy = None
    if best_run.data:
        best_energy = best_run.data[0]["best_energy"]

    return {
        "total_proteins": proteins.count or 0,
        "total_compounds": compounds.count or 0,
        "total_runs": runs.count or 0,
        "best_energy": best_energy,
    }
