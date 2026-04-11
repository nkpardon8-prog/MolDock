from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from api.config import settings
from api.db import get_docking_run, get_docking_runs, get_protein_by_id

router = APIRouter(prefix="/results", tags=["results"])


def _validate_path(file_path: str) -> Path:
    """Validate file path stays within data_root. Prevents path traversal."""
    root = Path(settings.data_root).resolve()
    full = (root / file_path).resolve()
    if not str(full).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not full.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return full


@router.get("")
def list_results(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    protein_id: str | None = Query(None),
    energy_min: float | None = Query(None),
    energy_max: float | None = Query(None),
):
    rows = get_docking_runs(
        limit=limit, offset=offset,
        protein_id=protein_id, energy_min=energy_min, energy_max=energy_max,
    )
    return {"items": rows, "limit": limit, "offset": offset}


@router.get("/{run_id}")
def get_result(request: Request, run_id: str):
    row = get_docking_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Docking run {run_id} not found")
    return row


@router.get("/{run_id}/file")
def get_result_file(request: Request, run_id: str):
    row = get_docking_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Docking run {run_id} not found")

    output_path = row.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="No output file path stored for this run")

    full_path = _validate_path(output_path)
    content = full_path.read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/plain")


@router.post("/{run_id}/interactions")
def compute_interactions(request: Request, run_id: str):
    row = get_docking_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Docking run {run_id} not found")

    protein_id = row.get("protein_id")
    if not protein_id:
        raise HTTPException(status_code=400, detail="Docking run has no protein_id")

    protein_row = get_protein_by_id(protein_id)
    if not protein_row:
        raise HTTPException(status_code=404, detail="Associated protein not found")

    protein_pdb = protein_row.get("pdb_path")
    if not protein_pdb:
        raise HTTPException(status_code=400, detail="Protein has no PDB file path")

    ligand_path = row.get("output_path")
    if not ligand_path:
        raise HTTPException(status_code=400, detail="Docking run has no output file")

    from core.analyze_results import get_interactions

    try:
        interactions = get_interactions(protein_pdb, ligand_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return interactions
