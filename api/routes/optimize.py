from fastapi import APIRouter, Request
from api.schemas import OptimizeRequest, JobResponse
from api.db import create_job

router = APIRouter()

@router.post("/", response_model=JobResponse)
def submit_optimization(req: OptimizeRequest, request: Request):
    user_id = str(request.state.user_id)
    params = req.model_dump()
    job = create_job(user_id=user_id, job_type="optimize", input_data=params)

    from api.jobs import run_optimize_job
    run_optimize_job.delay(str(job["id"]), params)

    return JobResponse(job_id=str(job["id"]), status="pending")
