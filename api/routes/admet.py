from fastapi import APIRouter, HTTPException, Request

from api.schemas import AdmetRequest

router = APIRouter(prefix="/admet", tags=["admet"])


@router.post("")
def run_admet(request: Request, body: AdmetRequest):
    from core.admet_check import full_admet

    try:
        result = full_admet(body.smiles)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result
