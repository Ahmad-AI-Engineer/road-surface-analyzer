"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router as api_router
from .config import settings
from .db import init_db
from .processing import reap_interrupted_jobs, shutdown as shutdown_worker
from .schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
logger = logging.getLogger("rda")

# httpx logs the full request URL (including our Roboflow ?api_key=... query
# param) at INFO level. Silence it so the API key never lands in container
# logs (`docker compose logs`); our own logging above still records progress.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()

    if settings.mock_detector:
        logger.warning("MOCK_DETECTOR=1 — using deterministic fake detections.")
    elif not settings.roboflow_configured:
        logger.error(
            "ROBOFLOW_API_KEY / MODEL_ID are not configured. Uploads will fail "
            "until they are set, or run with MOCK_DETECTOR=1."
        )
    else:
        logger.info("Roboflow Hosted Inference API configured: %s", settings.model_id)

    logger.info(
        "conf_threshold=%.2f frame_stride=%d max_upload_mb=%d media_root=%s",
        settings.conf_threshold,
        settings.frame_stride,
        settings.max_upload_mb,
        settings.media_root,
    )

    reaped = reap_interrupted_jobs()
    if reaped:
        logger.warning("Marked %d interrupted job(s) as failed.", reaped)

    app.state.settings = settings
    yield
    shutdown_worker(wait=False)


app = FastAPI(
    title="Road Surface Conditions Analyzer",
    description="Roboflow Hosted Inference API road damage detection demo.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak stack traces / internals to the client (OWASP A05 —
    # Security Misconfiguration). Full details still go to the server log.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again."},
    )


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        roboflow_configured=settings.roboflow_configured,
        mock_detector=settings.mock_detector,
        model_id=settings.model_id,
        frame_stride=settings.frame_stride,
        conf_threshold=settings.conf_threshold,
    )
