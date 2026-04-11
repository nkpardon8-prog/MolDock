import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.auth import AuthMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="MoleCopilot API", version="0.1.0")

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Route includes (lazy — files created in later tasks)
# ---------------------------------------------------------------------------

def _include_routes():
    from api.routes import (
        chat,
        dock,
        proteins,
        compounds,
        admet,
        results,
        literature,
        optimize,
        export,
        jobs,
    )
    app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
    app.include_router(dock.router, prefix="/api/dock", tags=["Dock"])
    app.include_router(proteins.router, prefix="/api")
    app.include_router(compounds.router, prefix="/api")
    app.include_router(admet.router, prefix="/api")
    app.include_router(results.router, prefix="/api")
    app.include_router(literature.router, prefix="/api")
    app.include_router(optimize.router, prefix="/api/optimize", tags=["Optimize"])
    app.include_router(export.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])


try:
    _include_routes()
except Exception as exc:
    logger.error("Failed to load API routes: %s", exc, exc_info=True)
    raise


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/stats")
def get_dashboard_stats():
    from api.db import get_stats
    return get_stats()
