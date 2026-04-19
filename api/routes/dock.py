from fastapi import APIRouter, Request
from api.schemas import DockRequest, JobResponse
from api.db import create_job

router = APIRouter()

@router.post("/", response_model=JobResponse)
def submit_dock(req: DockRequest, request: Request):
    user_id = str(request.state.user_id)
    params = req.model_dump()
    params["user_id"] = user_id
    job = create_job(user_id=user_id, job_type="dock", input_data=params)

    from api.jobs import run_dock_job
    run_dock_job.delay(str(job["id"]), params)

    return JobResponse(job_id=str(job["id"]), status="pending")
