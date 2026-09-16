"""Artifact generation.

Produces a Markdown or HTML document from the current conversation and the
retrieved transcript context, then hands it to the sanitizer before it is ever
persisted or returned. The skill also writes the short chat-side message that
accompanies the artifact, so the conversation stays readable instead of being
flooded with markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from app.agent import prompts
from app.llm import ChatMessage
from app.obs import current_trace, get_logger
from app.rag.retriever import RetrievalResult
from app.security import sanitize_artifact

log = get_logger("skill.artifact")


@dataclass
class ArtifactDraft:
    kind: Literal["markdown", "html"]
    title: str
    content: str
    sanitizer_report: dict[str, Any]
    chat_message: str
    usage: dict[str, int]


async def generate_artifact(
    provider,
    request: str,
    retrieval: RetrievalResult,
    history: list[dict[str, str]],
    *,
    kind: Literal["markdown", "html"] = "markdown",
) -> ArtifactDraft:
    context = retrieval.context_block(max_chars=14_000) if retrieval.chunks else ""
    convo = "\n".join(
        f"{t['role']}: {t['content'][:600]}" for t in history[-6:]
    )

    user_block = (
        (f"TRANSCRIPT EXCERPTS\n\n{context}\n\n" if context else "")
        + (f"CONVERSATION SO FAR\n{convo}\n\n" if convo else "")
        + f"REQUEST\n{request}"
    )
    system = prompts.ARTIFACT_HTML if kind == "html" else prompts.ARTIFACT_MARKDOWN

    trace = current_trace()
    if trace:
        with trace.span("llm_artifact", kind=kind, provider=provider.name):
            result = await provider.complete(
                [ChatMessage(role="user", content=user_block)],
                system=system,
                max_tokens=6000,
            )
    else:
        result = await provider.complete(
            [ChatMessage(role="user", content=user_block)],
            system=system,
            max_tokens=6000,
        )

    raw = _strip_fences(result.text, kind)
    clean, report = sanitize_artifact(raw, kind)
    title = _title_for(clean, kind, request)

    if trace:
        trace.fact("artifact", {
            "kind": kind,
            "bytes": len(clean),
            "sanitizer": report.to_dict(),
        })
    log.info(
        "skill.artifact.generated",
        kind=kind,
        bytes=len(clean),
        clean=report.clean,
        removed=sorted(set(report.removed_elements)),
    )

    return ArtifactDraft(
        kind=kind,
        title=title,
        content=clean,
        sanitizer_report=report.to_dict(),
        chat_message=_chat_message(title, kind, report, retrieval),
        usage=result.usage,
    )


def _strip_fences(text: str, kind: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:html|markdown|md)?\s*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    if kind == "html":
        # Models sometimes prepend a sentence before the doctype.
        m = re.search(r"(<!DOCTYPE html|<html|<div|<section|<style)", t, re.I)
        if m and m.start() > 0:
            t = t[m.start():]
    return t.strip()


def _title_for(content: str, kind: str, request: str) -> str:
    if kind == "html":
        m = re.search(r"<title>(.*?)</title>", content, re.I | re.S)
        if m:
            return m.group(1).strip()[:120]
        m = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.I | re.S)
        if m:
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()[:120]
    else:
        m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if m:
            return m.group(1).strip()[:120]
    return request.strip()[:80] or "Untitled artifact"


def _chat_message(title, kind, report, retrieval: RetrievalResult) -> str:
    lines = [f'Created **{title}** as {"an HTML" if kind == "html" else "a Markdown"} '
             "artifact. It is open in the viewer on the right."]
    if retrieval.chunks:
        episodes = sorted({c.title for c in retrieval.chunks})[:3]
        lines.append("Grounded in: " + "; ".join(episodes) + ".")
    if not report.clean:
        removed = sorted(set(report.removed_elements + report.removed_attributes))
        lines.append(
            "The viewer removed " + ", ".join(removed[:6]) +
            " before rendering. Generated markup is treated as untrusted."
        )
    return "\n\n".join(lines)
