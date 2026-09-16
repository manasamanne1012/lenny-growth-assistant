"""The chat endpoint — one turn in, one persisted turn out."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import generate_title, run_turn
from app.config import settings
from app.db import get_session, session_scope
from app.db import repository as repo
from app.llm import get_chat_provider
from app.obs import get_logger, new_trace
from app.rag.retriever import retrieve
from app.schemas import (
    ArtifactOut,
    ChatRequest,
    ChatResponse,
    MessageOut,
    SearchRequest,
    SearchResponse,
)

log = get_logger("api.chat")
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Send a message")
async def chat(
    payload: ChatRequest, db: AsyncSession = Depends(get_session)
) -> ChatResponse:
    started = time.perf_counter()
    trace = new_trace(payload.session_id)

    # --- session ---------------------------------------------------------
    is_new = payload.session_id is None
    if is_new:
        session = await repo.create_session(
            db, user_id=payload.user_id, provider=settings.chat_provider
        )
        session_id = str(session["id"])
        title = "New chat"
    else:
        row = await repo.get_session_row(db, payload.session_id)  # type: ignore[arg-type]
        if not row:
            session = await repo.create_session(db, user_id=payload.user_id)
            session_id = str(session["id"])
            title = "New chat"
            is_new = True
        else:
            session_id = str(row["id"])
            title = row["title"]
    trace.session_id = session_id

    await repo.add_message(db, session_id=session_id, role="user",
                           content=payload.message)

    # --- agent -----------------------------------------------------------
    outcome = await run_turn(
        db, session_id=session_id, message=payload.message,
        force_skill=payload.force_skill,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    # --- persist ---------------------------------------------------------
    assistant = await repo.add_message(
        db,
        session_id=session_id,
        role="assistant",
        content=outcome.text,
        skill=outcome.skill,
        grounding=outcome.grounding,
        citations=outcome.citations,
        trace=trace.to_dict(),
        provider=outcome.provider,
        model=outcome.model,
        latency_ms=latency_ms,
        token_usage=outcome.usage,
    )

    artifact_out = None
    if outcome.artifact:
        row = await repo.add_artifact(
            db,
            session_id=session_id,
            message_id=str(assistant["id"]),
            kind=outcome.artifact["kind"],
            title=outcome.artifact["title"],
            content=outcome.artifact["content"],
            sanitized=True,
            sanitizer_report=outcome.artifact["sanitizer_report"],
        )
        artifact_out = ArtifactOut(**{**row, "id": str(row["id"])})

    if is_new or title == "New chat":
        title = await generate_title(get_chat_provider(), payload.message)
    await repo.touch_session(db, session_id, title=title,
                             provider=outcome.provider, model=outcome.model)

    log.info(
        "api.chat.complete",
        skill=outcome.skill,
        grounding=outcome.grounding,
        latency_ms=latency_ms,
        provider=outcome.provider,
        citations=len(outcome.citations),
        artifact=bool(artifact_out),
    )

    return ChatResponse(
        session_id=session_id,
        session_title=title,
        message=MessageOut(
            **{
                **assistant,
                "id": str(assistant["id"]),
                "session_id": session_id,
                "token_usage": assistant.get("token_usage") or {},
            }
        ),
        artifact=artifact_out,
        essay_report=outcome.essay_report,
        route=outcome.route,
        notices=outcome.notices,
        trace_id=trace.trace_id,
    )


@router.post("/chat/stream", summary="Send a message (server-sent events)")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Token streaming for the grounded-answer path.

    Skills that post-process their own output (the Ship 30 rubric loop, artifact
    sanitization) cannot be streamed honestly — you would be showing the user
    text that is about to be revised or stripped. Those fall back to a single
    `done` event carrying the complete result, and the UI shows a working state
    instead of a fake token stream.
    """

    async def events():
        trace = new_trace(payload.session_id)
        try:
            async with session_scope() as db:
                is_new = payload.session_id is None
                if is_new:
                    session = await repo.create_session(db, user_id=payload.user_id)
                    session_id = str(session["id"])
                else:
                    row = await repo.get_session_row(db, payload.session_id)  # type: ignore
                    session_id = str(row["id"]) if row else str(
                        (await repo.create_session(db, user_id=payload.user_id))["id"]
                    )
                trace.session_id = session_id
                yield _sse("session", {"session_id": session_id,
                                       "trace_id": trace.trace_id})

                await repo.add_message(db, session_id=session_id, role="user",
                                       content=payload.message)

                from app.agent.router import route

                decision = await route(payload.message)
                yield _sse("route", decision.to_dict())

                if decision.skill != "grounded_qa":
                    yield _sse("status", {
                        "state": "working",
                        "detail": "Drafting and validating against the skill rubric."
                    })
                    outcome = await run_turn(
                        db, session_id=session_id, message=payload.message,
                        force_skill=decision.skill,
                    )
                    yield _sse("done", {
                        "text": outcome.text,
                        "skill": outcome.skill,
                        "grounding": outcome.grounding,
                        "citations": outcome.citations,
                        "artifact": outcome.artifact,
                        "essay_report": outcome.essay_report,
                        "notices": outcome.notices,
                    })
                    return

                started = time.perf_counter()
                retrieval = await retrieve(db, payload.message)
                yield _sse("sources", {
                    "sufficiency": retrieval.sufficiency,
                    "reason": retrieval.reason,
                    "citations": retrieval.citations(),
                })

                from app.agent.skills.qa import answer_question

                history = await repo.recent_turns(
                    db, session_id, turns=settings.history_turns_in_context
                )
                provider = get_chat_provider()
                answer = await answer_question(
                    provider, payload.message, retrieval, history
                )
                for i in range(0, len(answer.text), 24):
                    yield _sse("token", {"text": answer.text[i : i + 24]})

                latency_ms = int((time.perf_counter() - started) * 1000)
                await repo.add_message(
                    db, session_id=session_id, role="assistant",
                    content=answer.text, skill="grounded_qa",
                    grounding=answer.grounding, citations=answer.citations,
                    trace=trace.to_dict(), provider=answer.provider,
                    model=answer.model, latency_ms=latency_ms,
                    token_usage=answer.usage,
                )
                await repo.touch_session(db, session_id,
                                         provider=answer.provider, model=answer.model)
                yield _sse("done", {
                    "text": answer.text,
                    "skill": "grounded_qa",
                    "grounding": answer.grounding,
                    "citations": answer.citations,
                    "latency_ms": latency_ms,
                })
        except Exception as exc:  # noqa: BLE001 - the stream must close cleanly
            log.exception("api.chat.stream_failed")
            yield _sse("error", {"message": str(exc), "trace_id": trace.trace_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/search", response_model=SearchResponse,
             summary="Search transcripts without generating an answer")
async def search(
    payload: SearchRequest, db: AsyncSession = Depends(get_session)
) -> SearchResponse:
    """Retrieval on its own.

    Exposed because retrieval quality and answer quality fail differently, and
    an evaluator debugging a bad answer needs to see which one broke.
    """
    new_trace()
    result = await retrieve(db, payload.query, top_k=payload.top_k)
    return SearchResponse(
        query=payload.query,
        sufficiency=result.sufficiency,
        reason=result.reason,
        degraded=result.degraded,
        results=result.citations(),  # type: ignore[arg-type]
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
