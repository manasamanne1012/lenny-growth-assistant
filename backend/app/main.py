"""Application entrypoint."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router, errors
from app.config import settings
from app.db.bootstrap import apply_migrations
from app.db.engine import get_engine
from app.llm import describe_providers
from app.obs import configure_logging, current_trace, get_logger, new_trace

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("app.starting", version=__version__, environment=settings.environment,
             providers=describe_providers())
    try:
        await apply_migrations()
    except Exception as exc:  # noqa: BLE001
        # A database that is still booting should not kill the container; the
        # readiness probe will report the real state and Compose will retry.
        log.error(
            "app.migrations_failed", error=str(exc),
            hint="Postgres may still be starting. Check /api/health/deep.",
        )
    yield
    await get_engine().dispose()
    log.info("app.stopped")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Grounded question answering, Ship 30 essay generation, and sandboxed "
        "artifact rendering over Lenny's Podcast transcripts.\n\n"
        "Start at `GET /api/health/deep` — it reports every dependency with a fix "
        "hint for each failure."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id", "X-Response-Time-Ms"],
)

errors.install(app)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Give every request a trace id and record its duration."""
    started = time.perf_counter()
    trace = current_trace() or new_trace()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Trace-Id"] = trace.trace_id
    response.headers["X-Response-Time-Ms"] = f"{elapsed:.1f}"
    if not request.url.path.startswith(("/api/health", "/docs", "/openapi")):
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed, 1),
        )
    return response


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health/deep",
    }


app.include_router(api_router)
