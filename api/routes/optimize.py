from fastapi import APIRouter, HTTPException, Request
from api.schemas import OptimizeRequest, JobResponse
from api.db import create_job

router = APIRouter()

@router.post("/", response_model=JobResponse)
def submit_optimization(req: OptimizeRequest, request: Request):
    user_id = str(request.state.user_id)

    smiles = req.smiles
    if not smiles and req.compound:
        from core.fetch_compounds import search_pubchem
        results = search_pubchem(req.compound, max_results=1)
        if not results or not results[0].get("smiles"):
            raise HTTPException(status_code=400, detail=f"Could not resolve compound '{req.compound}' to SMILES")
        smiles = results[0]["smiles"]
    if not smiles:
        raise HTTPException(status_code=422, detail="Either 'smiles' or 'compound' is required")

    params = req.model_dump()
    params["smiles"] = smiles
    params.pop("compound", None)
    if params.get("property_name"):
        name = params["property_name"]
        canonical = {"qed": "QED", "plogp": "plogP"}
        params["property_name"] = canonical.get(name.lower(), name)
    job = create_job(user_id=user_id, job_type="optimize", input_data=params)

    from api.jobs import run_optimize_job
    run_optimize_job.delay(str(job["id"]), params)

    return JobResponse(job_id=str(job["id"]), status="pending")
