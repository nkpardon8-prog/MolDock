from pathlib import Path

import redis
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api import db_reports
from api.config import settings
from api.schemas import (
    GenerateReportRequest,
    ProjectRollupRequest,
    RegenerateReportRequest,
    RunReportResponse,
)

router = APIRouter(tags=["reports"])
_redis = redis.from_url(settings.redis_url)

GENERATE_RATE = 20     # per user per hour
REGENERATE_RATE = 40   # per user per hour


def _check_rate(user_id: str, bucket: str, limit: int) -> None:
    key = f"ratelimit:reports:{bucket}:{user_id}"
    count = _redis.incr(key)
    if count == 1:
        _redis.expire(key, 3600)
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit}/hour for {bucket}",
        )


# IMPORTANT — FastAPI matches routes in registration order. `/by-run/{run_id}`
# MUST be declared before `/{report_id}` or `/by-run/abc` resolves to
# `report_id="by-run"` and 404s.

@router.get("/by-run/{run_id}")
def get_report_by_run(run_id: str, run_type: str, request: Request):
    """Lookup by (run_id, run_type). Frontend uses this to decide whether
    to show 'Generate' or the existing report."""
    user_id = str(request.state.user_id)
    row = db_reports.get_report_by_run(run_id, run_type)
    if not row:
        raise HTTPException(status_code=404, detail="Not generated")
    if row.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return row


@router.get("/{report_id}", response_model=RunReportResponse)
def get_report(report_id: str, request: Request):
    user_id = str(request.state.user_id)
    row = db_reports.get_report_by_id(report_id)
    if not row or row.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/generate")
def generate(body: GenerateReportRequest, request: Request):
    user_id = str(request.state.user_id)
    _check_rate(user_id, "generate", GENERATE_RATE)
    from core.report_service import generate_report

    try:
        return generate_report(
            body.run_id,
            body.run_type,
            body.research_question,
            user_id,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this run")


@router.post("/{report_id}/regenerate")
def regenerate(report_id: str, body: RegenerateReportRequest, request: Request):
    user_id = str(request.state.user_id)
    _check_rate(user_id, "regenerate", REGENERATE_RATE)
    from core.report_service import regenerate_sections

    try:
        return regenerate_sections(
            report_id,
            list(body.sections),
            body.research_question,
            user_id,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized")


@router.post("/project")
def generate_project(body: ProjectRollupRequest, request: Request):
    user_id = str(request.state.user_id)
    _check_rate(user_id, "generate", GENERATE_RATE)
    from core.report_service import generate_report

    try:
        return generate_report(
            None,
            "project",
            body.research_question,
            user_id,
            body.source_run_ids,
        )
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Not authorized for one or more runs",
        )


@router.get("/{report_id}/export")
def export(report_id: str, fmt: str, request: Request):
    user_id = str(request.state.user_id)
    from core.report_service import render_for_export

    try:
        markdown, title = render_for_export(report_id, user_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized")

    fmt = fmt.lower()
    if fmt == "docx":
        from core.export_docs import export_docx

        path = export_docx(markdown_text=markdown, title=title)
        return FileResponse(
            path,
            filename=Path(path).name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if fmt == "pdf":
        from core.export_docs import export_pdf

        path = export_pdf(markdown_text=markdown, title=title)
        return FileResponse(
            path,
            filename=Path(path).name,
            media_type="application/pdf",
        )
    raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")
