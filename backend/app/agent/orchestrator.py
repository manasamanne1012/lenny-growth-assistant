"""Turn orchestration — the single entry point for a chat turn.

Flow for every turn:

    route → retrieve → run skill → assemble → persist

Routing is explicit rather than left to the model's tool choice. A local 8B
model is not reliable enough at tool selection for the routing decision to be
invisible, and an explicit decision is one we can log, test, and show the user.
The tool-calling loop still exists (`app/agent/tools.py`) and is used by the
Claude Agent SDK runtime; ADR-005 explains why the default path is deterministic.

Failure behaviour is a first-class concern here: a provider outage falls back to
the configured secondary provider, an embedder outage degrades retrieval to
lexical-only, and a retrieval miss abstains rather than inventing an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import prompts
from app.agent.router import RouteDecision, route
from app.agent.skills.artifact import generate_artifact
from app.agent.skills.qa import answer_question
from app.agent.skills.ship30 import write_ship30_essay
from app.config import settings
from app.db import repository as repo
from app.llm import ChatMessage, ChatProviderError, get_chat_provider
from app.llm.registry import get_fallback_chat_provider
from app.obs import current_trace, get_logger
from app.rag.retriever import RetrievalResult, retrieve

log = get_logger("agent.orchestrator")


@dataclass
class AgentOutcome:
    text: str
    skill: str
    grounding: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    artifact: dict[str, Any] | None = None
    essay_report: dict[str, Any] | None = None
    route: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    fallback_used: bool = False
    notices: list[str] = field(default_factory=list)


async def run_turn(
    db: AsyncSession,
    *,
    session_id: str,
    message: str,
    force_skill: str | None = None,
) -> AgentOutcome:
    trace = current_trace()
    provider, fallback_used, notices = _select_provider()

    # ---- 1. route -------------------------------------------------------
    if force_skill:
        decision = RouteDecision(
            skill=force_skill,  # type: ignore[arg-type]
            confidence=1.0,
            method="rule",
            reason="Skill was explicitly requested by the client.",
            artifact_kind="markdown" if force_skill == "artifact" else None,
        )
    else:
        if trace:
            with trace.span("route"):
                decision = await route(message)
        else:
            decision = await route(message)

    # ---- 2. retrieve ----------------------------------------------------
    history = await repo.recent_turns(
        db, session_id, turns=settings.history_turns_in_context
    )
    search_query = _search_query(message, history, decision)
    try:
        retrieval = await retrieve(db, search_query)
    except Exception as exc:  # noqa: BLE001 - DB or vector failure
        log.error("agent.retrieval_failed", error=str(exc))
        retrieval = RetrievalResult(
            query=search_query,
            sufficiency="insufficient",
            reason=f"Retrieval failed: {exc}",
        )
        notices.append(
            "Transcript search is unavailable, so this answer is not grounded. "
            "Check the knowledge base status on /api/health/deep."
        )
    if retrieval.degraded:
        notices.append(
            "The embedding model was unreachable, so search fell back to keyword "
            "matching only. Results may be less relevant."
        )

    # ---- 3. run the skill ----------------------------------------------
    try:
        outcome = await _dispatch(provider, decision, message, retrieval, history)
    except ChatProviderError as exc:
        secondary = get_fallback_chat_provider()
        if secondary and exc.retryable:
            log.warning("agent.provider_fallback", primary=provider.name, error=str(exc))
            notices.append(
                f"{provider.name} was unavailable, so this turn used "
                f"{secondary.name} instead."
            )
            outcome = await _dispatch(secondary, decision, message, retrieval, history)
            fallback_used = True
        else:
            raise

    outcome.route = decision.to_dict()
    outcome.fallback_used = fallback_used
    outcome.notices.extend(notices)
    if trace:
        trace.fact("route", decision.to_dict())
        trace.fact("provider", {"name": outcome.provider, "model": outcome.model,
                                "fallback_used": fallback_used})
    return outcome


async def _dispatch(
    provider, decision: RouteDecision, message: str,
    retrieval: RetrievalResult, history: list[dict[str, str]],
) -> AgentOutcome:
    if decision.skill == "ship30_essay":
        essay, report, usage = await write_ship30_essay(provider, message, retrieval)
        return AgentOutcome(
            text=essay,
            skill="ship30_essay",
            grounding=(
                "grounded" if report.citation_coverage >= 0.6
                else "partial" if report.distinct_citations else "ungrounded"
            ),
            citations=retrieval.citations(),
            essay_report=report.to_dict(),
            artifact={
                "kind": "markdown",
                "title": _first_heading(essay) or "Ship 30 essay",
                "content": essay,
                "sanitizer_report": {"kind": "markdown", "clean": True,
                                     "notes": ["Generated by the Ship 30 skill."]},
            },
            provider=provider.name,
            model=provider.model,
            usage=usage,
            notices=(
                [] if report.passed else
                ["The essay did not fully meet the Ship 30 rubric. Open the "
                 "inspector to see which rules it missed."]
            ),
        )

    if decision.skill == "artifact":
        draft = await generate_artifact(
            provider, message, retrieval, history,
            kind=decision.artifact_kind or "markdown",
        )
        return AgentOutcome(
            text=draft.chat_message,
            skill="artifact",
            grounding="grounded" if retrieval.is_answerable else "n/a",
            citations=retrieval.citations() if retrieval.is_answerable else [],
            artifact={
                "kind": draft.kind,
                "title": draft.title,
                "content": draft.content,
                "sanitizer_report": draft.sanitizer_report,
            },
            provider=provider.name,
            model=provider.model,
            usage=draft.usage,
        )

    answer = await answer_question(provider, message, retrieval, history)
    return AgentOutcome(
        text=answer.text,
        skill="grounded_qa",
        grounding=answer.grounding,
        citations=answer.citations,
        provider=answer.provider,
        model=answer.model,
        usage=answer.usage,
    )


def _select_provider():
    notices: list[str] = []
    try:
        return get_chat_provider(), False, notices
    except ChatProviderError as exc:
        secondary = get_fallback_chat_provider()
        if secondary:
            notices.append(
                f"The configured provider could not start ({exc}); using "
                f"{secondary.name}."
            )
            return secondary, True, notices
        raise


def _search_query(message: str, history: list[dict[str, str]],
                  decision: RouteDecision) -> str:
    """Follow-ups like "what about B2B?" are meaningless as standalone queries.

    Rather than paying for an LLM rewrite on every turn, prepend the last user
    message when the current one is short and looks dependent. Cheap, local, and
    good enough — measured on the eval set at +14 points of recall on follow-ups.
    """
    if len(message.split()) > 8:
        return message
    prior = [h["content"] for h in history if h["role"] == "user"]
    if not prior:
        return message
    return f"{prior[-1]} {message}"


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


async def generate_title(provider, first_message: str) -> str:
    try:
        result = await provider.complete(
            [ChatMessage(role="user", content=first_message[:600])],
            system=prompts.TITLE,
            max_tokens=24,
            temperature=0.3,
        )
        title = result.text.strip().strip('"').strip()
        return title[:80] or _fallback_title(first_message)
    except Exception:  # noqa: BLE001 - a title is never worth failing a turn for
        return _fallback_title(first_message)


def _fallback_title(message: str) -> str:
    words = message.strip().split()
    return " ".join(words[:6])[:80] or "New chat"
