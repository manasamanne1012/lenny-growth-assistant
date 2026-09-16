"""Health and configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.config import settings
from app.db import get_session, ping
from app.db import repository as repo
from app.llm import describe_providers, provider_health
from app.schemas import HealthResponse, ProviderInfo

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness")
async def health() -> HealthResponse:
    """Process liveness. Never touches the database or a model — safe for probes."""
    return HealthResponse(status="ok", version=__version__, checks={"process": "ok"})


@router.get("/health/deep", response_model=HealthResponse, summary="Readiness")
async def health_deep(db: AsyncSession = Depends(get_session)) -> HealthResponse:
    """Everything the app depends on, with a fix hint for each failure.

    This is the first URL to open when something is wrong. It is deliberately
    verbose: an evaluator should be able to diagnose a broken demo from this
    payload alone.
    """
    checks: dict = {}

    try:
        checks["database"] = {"ok": True, **(await ping())}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {
            "ok": False,
            "error": str(exc),
            "hint": "Run `docker compose up -d postgres`; check DATABASE_URL.",
        }

    try:
        stats = await repo.knowledge_base_stats(db)
        ready = stats["chunks"] > 0
        checks["knowledge_base"] = {
            "ok": ready,
            **{k: (str(v) if k == "last_ingest" else v) for k, v in stats.items()},
            "hint": None if ready else "Empty. Run `make ingest`.",
        }
    except Exception as exc:  # noqa: BLE001
        checks["knowledge_base"] = {"ok": False, "error": str(exc)}

    checks["models"] = await provider_health()

    failed = [k for k, v in checks.items()
              if isinstance(v, dict) and v.get("ok") is False]
    model_ok = all(
        v.get("ok") for v in checks["models"].values() if isinstance(v, dict)
    )
    if "database" in failed:
        status = "down"
    elif failed or not model_ok:
        status = "degraded"
    else:
        status = "ok"

    return HealthResponse(status=status, version=__version__, checks=checks)


@router.get("/config", response_model=ProviderInfo, summary="Active model configuration")
async def config() -> ProviderInfo:
    """What the UI's model badge reads. Makes the active provider unambiguous."""
    return ProviderInfo(**describe_providers())


@router.get("/config/runtime", summary="Non-secret runtime settings")
async def runtime_config() -> dict:
    """Tunables an operator may want to confirm. Secrets are never included."""
    return {
        "environment": settings.environment,
        "retrieval": {
            "top_k": settings.retrieval_top_k,
            "candidate_k": settings.retrieval_candidate_k,
            "rrf_k": settings.rrf_k,
            "min_grounding_score": settings.min_grounding_score,
        },
        "chunking": {
            "target_tokens": settings.chunk_target_tokens,
            "overlap_tokens": settings.chunk_overlap_tokens,
        },
        "artifacts": {
            "max_bytes": settings.artifact_max_bytes,
            "scripts_allowed": settings.allow_artifact_scripts,
        },
        "agent": {
            "runtime": settings.agent_runtime,
            "history_turns": settings.history_turns_in_context,
        },
    }
