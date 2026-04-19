from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from api.config import settings
from api.db import get_all_proteins, get_protein_by_pdb_id, save_protein
from api.schemas import FetchProteinRequest, SearchRequest

router = APIRouter(prefix="/proteins", tags=["proteins"])


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
def list_proteins(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user_id = str(request.state.user_id)
    rows = get_all_proteins(user_id=user_id, limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}


@router.get("/{pdb_id}")
def get_protein(request: Request, pdb_id: str):
    row = get_protein_by_pdb_id(pdb_id.upper())
    if not row:
        raise HTTPException(status_code=404, detail=f"Protein {pdb_id} not found")
    return row


@router.get("/{pdb_id}/file")
def get_protein_file(request: Request, pdb_id: str):
    row = get_protein_by_pdb_id(pdb_id.upper())
    if not row:
        raise HTTPException(status_code=404, detail=f"Protein {pdb_id} not found")

    pdb_path = row.get("pdb_path") or row.get("pdbqt_path")
    if not pdb_path:
        raise HTTPException(status_code=404, detail="No file path stored for this protein")

    full_path = _validate_path(pdb_path)
    content = full_path.read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/plain")


@router.post("/fetch")
def fetch_protein_route(request: Request, body: FetchProteinRequest):
    pdb_id = body.pdb_id.strip().upper()

    user_id: str = request.state.user_id

    from core.fetch_pdb import fetch_protein, get_protein_info

    try:
        fetch_result = fetch_protein(pdb_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        info = get_protein_info(pdb_id)
    except Exception:
        info = {}

    row = save_protein(
        created_by=user_id,
        pdb_id=pdb_id,
        title=info.get("title"),
        organism=info.get("organism"),
        resolution=info.get("resolution"),
        method=info.get("method"),
        pdb_path=fetch_result.get("file_path"),
    )

    return row


@router.post("/search")
def search_proteins(request: Request, body: SearchRequest):
    from core.fetch_pdb import search_pdb

    try:
        results = search_pdb(body.query, max_results=body.max_results)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"results": results}
