from fastapi import APIRouter, HTTPException, Query, Request

from api.db import get_all_compounds
from api.schemas import SearchRequest

router = APIRouter(prefix="/compounds", tags=["compounds"])


@router.get("")
def list_compounds(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = get_all_compounds(limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}


@router.post("/search")
def search_compounds(request: Request, body: SearchRequest):
    from core.fetch_compounds import search_pubchem

    try:
        results = search_pubchem(body.query, max_results=body.max_results)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"results": results}
