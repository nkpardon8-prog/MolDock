import asyncio
import json
from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as aioredis

from api.config import settings
from api.db import get_job, verify_job_owner

router = APIRouter()

@router.get("/{job_id}")
def get_job_status(job_id: str, request: Request):
    user_id = str(request.state.user_id)
    try:
        job = verify_job_owner(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return job

@router.get("/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    user_id = str(request.state.user_id)
    try:
        verify_job_owner(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    async def event_generator():
        r = aioredis.from_url(settings.redis_url)
        seen_events = set()

        # Subscribe FIRST (before replay) to catch events in the gap
        pubsub = r.pubsub()
        await pubsub.subscribe(f"job:{job_id}")

        try:
            # Then replay buffered events
            buffered = await r.lrange(f"job:{job_id}:events", 0, -1)
            for raw in buffered:
                raw_str = raw if isinstance(raw, str) else raw.decode()
                seen_events.add(raw_str)
                data = json.loads(raw_str)
                yield {"event": data["event"], "data": json.dumps(data["payload"])}
                if data["event"] in ("complete", "error"):
                    return

            # Listen for new events with 5-minute timeout
            deadline = asyncio.get_event_loop().time() + 300
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    yield {"event": "error", "data": json.dumps({"error": "Stream timeout"})}
                    return
                if await request.is_disconnected():
                    return

                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    continue

                if message and message["type"] == "message":
                    raw_str = message["data"] if isinstance(message["data"], str) else message["data"].decode()
                    if raw_str in seen_events:
                        continue
                    seen_events.add(raw_str)
                    data = json.loads(raw_str)
                    yield {"event": data["event"], "data": json.dumps(data["payload"])}
                    if data["event"] in ("complete", "error"):
                        return
        finally:
            await pubsub.unsubscribe(f"job:{job_id}")
            await r.close()

    return EventSourceResponse(event_generator())
