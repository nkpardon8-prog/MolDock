from fastapi import APIRouter, HTTPException, Query, Request

from api.db import get_all_compounds
from api.schemas import NpAtlasSearchRequest, SearchRequest

router = APIRouter(prefix="/compounds", tags=["compounds"])


@router.get("")
def list_compounds(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user_id = str(request.state.user_id)
    rows = get_all_compounds(user_id=user_id, limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}


@router.post("/search")
def search_compounds(request: Request, body: SearchRequest):
    from core.fetch_compounds import search_pubchem

    try:
        results = search_pubchem(body.query, max_results=body.max_results)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"results": results}


@router.post("/search-npatlas")
def search_npatlas_route(request: Request, body: NpAtlasSearchRequest):
    from core.fetch_compounds import search_npatlas, search_npatlas_similar

    try:
        if body.search_type == "similarity":
            results = search_npatlas_similar(body.query, max_results=body.max_results)
        else:
            results = search_npatlas(body.query, max_results=body.max_results)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"results": results}
