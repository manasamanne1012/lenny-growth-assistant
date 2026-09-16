"""Session and message endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.db import repository as repo
from app.schemas import ArtifactOut, MessageOut, SessionCreate, SessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201, summary="Start a new chat")
async def create_session(
    payload: SessionCreate, db: AsyncSession = Depends(get_session)
) -> SessionOut:
    """Each session holds its own message history; context never crosses sessions."""
    row = await repo.create_session(
        db,
        title=payload.title or "New chat",
        user_id=payload.user_id,
        user_metadata=payload.user_metadata,
        provider=settings.chat_provider,
        model=None,
    )
    return SessionOut(**{**row, "id": str(row["id"]), "message_count": 0})


@router.get("", response_model=list[SessionOut], summary="List chats")
async def list_sessions(
    user_id: str = Query("local-evaluator"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
) -> list[SessionOut]:
    rows = await repo.list_sessions(db, user_id=user_id, limit=limit)
    return [SessionOut(**{**r, "id": str(r["id"])}) for r in rows]


@router.get("/{session_id}/messages", response_model=list[MessageOut],
            summary="Full transcript of a chat")
async def get_messages(
    session_id: str, db: AsyncSession = Depends(get_session)
) -> list[MessageOut]:
    if not await repo.get_session_row(db, session_id):
        raise HTTPException(404, "No session with that id.")
    rows = await repo.list_messages(db, session_id)
    return [
        MessageOut(
            **{
                **r,
                "id": str(r["id"]),
                "session_id": str(r["session_id"]),
                "token_usage": r.get("token_usage") or {},
            }
        )
        for r in rows
    ]


@router.get("/{session_id}/artifacts", response_model=list[ArtifactOut],
            summary="Artifacts produced in a chat")
async def get_artifacts(
    session_id: str, db: AsyncSession = Depends(get_session)
) -> list[ArtifactOut]:
    rows = await repo.list_artifacts(db, session_id)
    return [ArtifactOut(**{**r, "id": str(r["id"])}) for r in rows]


@router.delete("/{session_id}", status_code=200, summary="Archive a chat")
async def archive_session(
    session_id: str, db: AsyncSession = Depends(get_session)
) -> None:
    """Soft delete. Conversations are retained for evaluation; see the data
    retention note in docs/architecture.md."""
    if not await repo.archive_session(db, session_id):
        raise HTTPException(404, "No active session with that id.")
