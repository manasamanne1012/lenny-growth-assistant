"""Grounded question answering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agent import prompts
from app.config import settings
from app.llm import ChatMessage, CompletionResult
from app.obs import current_trace, get_logger
from app.rag.retriever import RetrievalResult

log = get_logger("skill.qa")

CITATION = re.compile(r"\[S(\d+)\]")


@dataclass
class GroundedAnswer:
    text: str
    grounding: str            # grounded | partial | ungrounded | abstained
    citations: list[dict[str, Any]]
    usage: dict[str, int]
    provider: str
    model: str
    coverage: float           # share of paragraphs carrying at least one citation


async def answer_question(
    provider,
    question: str,
    retrieval: RetrievalResult,
    history: list[dict[str, str]],
) -> GroundedAnswer:
    if not retrieval.is_answerable:
        return await _abstain(provider, question, retrieval)

    messages: list[ChatMessage] = []
    for turn in history[-settings.history_turns_in_context :]:
        messages.append(ChatMessage(role=turn["role"], content=turn["content"]))

    hedge = (
        "\n\nNOTE: retrieval was thin. Scope the answer tightly to what these "
        "excerpts actually say and name the limitation in one sentence."
        if retrieval.sufficiency == "thin"
        else ""
    )
    messages.append(
        ChatMessage(
            role="user",
            content=(
                f"TRANSCRIPT EXCERPTS\n\n{retrieval.context_block()}\n\n"
                f"QUESTION\n{question}{hedge}"
            ),
        )
    )

    trace = current_trace()
    if trace:
        with trace.span("llm_answer", provider=provider.name, model=provider.model):
            result: CompletionResult = await provider.complete(
                messages, system=prompts.GROUNDED_QA
            )
    else:
        result = await provider.complete(messages, system=prompts.GROUNDED_QA)

    used, coverage = _citation_stats(result.text)
    cited = [c for c in retrieval.citations() if c["marker"] in used]
    grounding = _verdict(retrieval, used, coverage)

    if trace:
        trace.fact(
            "grounding",
            {
                "verdict": grounding,
                "markers_used": sorted(used),
                "paragraph_coverage": round(coverage, 2),
                "retrieval_sufficiency": retrieval.sufficiency,
            },
        )
    log.info("skill.qa.answered", grounding=grounding, cited=len(cited),
             coverage=round(coverage, 2))

    return GroundedAnswer(
        text=result.text.strip(),
        grounding=grounding,
        citations=cited or retrieval.citations()[:3],
        usage=result.usage,
        provider=result.provider,
        model=result.model,
        coverage=coverage,
    )


async def _abstain(provider, question: str, retrieval: RetrievalResult) -> GroundedAnswer:
    log.info("skill.qa.abstained", reason=retrieval.reason)
    try:
        result = await provider.complete(
            [ChatMessage(role="user", content=f"User asked: {question}")],
            system=prompts.ABSTAIN,
            max_tokens=300,
        )
        text = result.text.strip()
        usage, name, model = result.usage, result.provider, result.model
    except Exception as exc:  # noqa: BLE001 - abstention must work even if the model is down
        log.warning("skill.qa.abstain_llm_failed", error=str(exc))
        text = (
            "I could not find anything in the Lenny's Podcast transcripts that "
            "supports an answer to this. Rather than guess, I would rather say so.\n\n"
            "Try narrowing the question to a topic the show covers directly — "
            "pricing, onboarding, PLG motions, hiring PMs, growth loops — or name "
            "a guest whose episode you have in mind."
        )
        usage, name, model = {}, getattr(provider, "name", "unknown"), getattr(
            provider, "model", "unknown"
        )

    return GroundedAnswer(
        text=text,
        grounding="abstained",
        citations=[],
        usage=usage,
        provider=name,
        model=model,
        coverage=0.0,
    )


def _citation_stats(text: str) -> tuple[set[str], float]:
    markers = {f"S{n}" for n in CITATION.findall(text)}
    paragraphs = [
        p for p in text.split("\n\n")
        if len(p.strip()) > 80 and not p.strip().startswith("#")
    ]
    if not paragraphs:
        return markers, 1.0 if markers else 0.0
    with_citation = sum(1 for p in paragraphs if CITATION.search(p))
    return markers, with_citation / len(paragraphs)


def _verdict(retrieval: RetrievalResult, used: set[str], coverage: float) -> str:
    """The verdict shown on the message badge.

    It is computed from what the model actually produced, not from what we asked
    for. A model that ignores the citation instruction gets marked ungrounded and
    the UI says so — a visible failure is better than an invisible one.
    """
    if not used:
        return "ungrounded"
    if retrieval.sufficiency == "sufficient" and coverage >= 0.7 and len(used) >= 2:
        return "grounded"
    if coverage >= 0.4:
        return "partial"
    return "ungrounded"
