from fastapi import APIRouter, Request, Query, HTTPException
from api.db import (
    create_chat_session, save_chat_message, get_chat_messages,
    get_chat_sessions, delete_chat_session, create_job,
    verify_session_owner,
)
from api.schemas import ChatRequest

router = APIRouter()

@router.get("/sessions")
def list_sessions(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    user_id = str(request.state.user_id)
    return get_chat_sessions(user_id, limit=limit, offset=offset)

@router.get("/{session_id}/messages")
def get_messages(session_id: str, request: Request):
    user_id = str(request.state.user_id)
    try:
        verify_session_owner(session_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return get_chat_messages(session_id)

@router.post("/")
def send_message(req: ChatRequest, request: Request):
    user_id = str(request.state.user_id)
    if not req.session_id:
        session = create_chat_session(user_id, title=req.message[:50])
        session_id = str(session["id"])
    else:
        try:
            verify_session_owner(req.session_id, user_id)
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))
        session_id = req.session_id

    save_chat_message(session_id, role="user", content=req.message)
    job = create_job(user_id=user_id, job_type="chat", input_data={"session_id": session_id, "message": req.message})
    from api.jobs import run_chat_job
    run_chat_job.delay(str(job["id"]), session_id, req.message)
    return {"job_id": str(job["id"]), "session_id": session_id}

@router.delete("/sessions/{session_id}")
def remove_session(session_id: str, request: Request):
    user_id = str(request.state.user_id)
    try:
        verify_session_owner(session_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    delete_chat_session(session_id)
    return {"status": "deleted"}
