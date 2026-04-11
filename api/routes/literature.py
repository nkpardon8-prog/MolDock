from fastapi import APIRouter, HTTPException, Query, Request

from api.db import (
    delete_literature_search,
    get_literature_search,
    get_literature_searches,
    save_literature_search,
    update_literature_search,
    verify_literature_owner,
)
from api.schemas import LiteratureSearchRequest, UpdateLiteratureTagsRequest

router = APIRouter(prefix="/literature", tags=["literature"])


@router.post("/search")
def search_literature(request: Request, body: LiteratureSearchRequest):
    user_id: str = request.state.user_id

    if body.source_type == "pubmed":
        from core.literature import search_pubmed

        try:
            results = search_pubmed(body.query, max_results=body.max_results)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    elif body.source_type == "chembl":
        from core.literature import get_known_actives

        try:
            results = get_known_actives(target_name=body.query)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    elif body.source_type == "uniprot":
        from core.literature import get_uniprot_info

        try:
            results = get_uniprot_info(protein_name=body.query)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    elif body.source_type == "perplexity":
        from core.literature import search_perplexity

        try:
            results = search_perplexity(body.query)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source_type: {body.source_type}. Use 'pubmed', 'chembl', 'uniprot', or 'perplexity'.",
        )

    row = save_literature_search(
        user_id=user_id,
        query=body.query,
        source_type=body.source_type,
        results=results,
    )

    return row


@router.get("/searches")
def list_searches(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user_id: str = request.state.user_id
    rows = get_literature_searches(user_id=user_id, limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}


@router.get("/searches/{search_id}")
def get_search(request: Request, search_id: str):
    user_id: str = request.state.user_id
    try:
        row = verify_literature_owner(search_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return row


@router.put("/searches/{search_id}")
def update_search(request: Request, search_id: str, body: UpdateLiteratureTagsRequest):
    user_id: str = request.state.user_id
    try:
        verify_literature_owner(search_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    row = update_literature_search(search_id, tags=body.tags)
    return row


@router.delete("/searches/{search_id}")
def delete_search(request: Request, search_id: str):
    user_id: str = request.state.user_id
    try:
        verify_literature_owner(search_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    delete_literature_search(search_id)
    return {"detail": "deleted"}
