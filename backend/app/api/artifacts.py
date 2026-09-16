"""Artifact retrieval and the sandboxed render endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.db import repository as repo
from app.schemas import ArtifactOut

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

# No default-src 'self': the artifact must not be able to reach this origin.
ARTIFACT_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; "
    "img-src data:; "
    "font-src data:; "
    "form-action 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'self'"
)


@router.get("/{artifact_id}", response_model=ArtifactOut, summary="Fetch an artifact")
async def get_artifact(
    artifact_id: str, db: AsyncSession = Depends(get_session)
) -> ArtifactOut:
    row = await repo.get_artifact(db, artifact_id)
    if not row:
        raise HTTPException(404, "No artifact with that id.")
    return ArtifactOut(**{**row, "id": str(row["id"])})


@router.get("/{artifact_id}/raw", response_class=PlainTextResponse,
            summary="Artifact source, as text")
async def get_artifact_raw(
    artifact_id: str, db: AsyncSession = Depends(get_session)
) -> PlainTextResponse:
    row = await repo.get_artifact(db, artifact_id)
    if not row:
        raise HTTPException(404, "No artifact with that id.")
    return PlainTextResponse(
        row["content"],
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{artifact_id}/render", response_class=HTMLResponse,
            summary="Artifact rendered for the sandboxed viewer")
async def render_artifact(
    artifact_id: str, db: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    """Served with a deny-everything CSP.

    The frontend renders artifacts from `srcdoc` inside a sandboxed iframe, so
    this endpoint exists mainly for "open in a new tab" and for evaluators who
    want to inspect the served headers directly. Both paths carry the same CSP.
    """
    row = await repo.get_artifact(db, artifact_id)
    if not row:
        raise HTTPException(404, "No artifact with that id.")
    if row["kind"] != "html":
        raise HTTPException(
            400, "Only HTML artifacts render here. Markdown is rendered client-side."
        )
    return HTMLResponse(
        row["content"],
        headers={
            "Content-Security-Policy": ARTIFACT_CSP,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )
