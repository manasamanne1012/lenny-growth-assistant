"""Skill routing.

Deliberately a two-stage router: a fast deterministic pass over explicit intent
signals, then an LLM classifier only for the genuinely ambiguous remainder.

Why not route with the model every time? Three reasons that show up in
production: a local 8B model classifies "write me an essay on this" incorrectly
often enough to matter; the extra round trip adds 1–3s to every turn on CPU
inference; and deterministic routing is testable. The rules cover the explicit
phrasings users actually type, and the classifier catches the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.llm import ChatMessage, get_chat_provider
from app.obs import get_logger

log = get_logger("agent.router")

Skill = Literal["grounded_qa", "ship30_essay", "artifact"]

_ESSAY = re.compile(
    r"\b(ship\s*30|ship30|atomic essay|write (?:me )?(?:an?|the) (?:essay|post|article)"
    r"|essay (?:on|about)|linkedin post|newsletter (?:draft|post)|blog post"
    r"|thought leadership)\b",
    re.I,
)
_ARTIFACT = re.compile(
    r"\b("
    r"artifact"
    r"|render (?:it|this|that)"
    r"|html (?:page|snippet|mockup|widget|dashboard)"
    r"|landing page"
    r"|make (?:me )?(?:a|an) (?:one[- ]pager|dashboard|checklist|template|"
    r"cheat ?sheet|scorecard|calculator|table)"
    r"|create (?:me )?(?:a|an)? ?(?:interactive )?(?:calculator|widget|dashboard|page)"
    r"|build (?:me )?(?:a|an) (?:page|widget|visual|dashboard)"
    r"|as (?:a )?(?:markdown|html) document"
    r")\b",
    re.I,
)
_HTML_HINT = re.compile(r"\b(html|css|web page|webpage|interactive|widget|calculator)\b", re.I)


@dataclass
class RouteDecision:
    skill: Skill
    confidence: float
    method: Literal["rule", "classifier", "fallback"]
    reason: str
    artifact_kind: Literal["markdown", "html"] | None = None

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "confidence": round(self.confidence, 2),
            "method": self.method,
            "reason": self.reason,
            "artifact_kind": self.artifact_kind,
        }


def route_by_rules(message: str) -> RouteDecision | None:
    if _ESSAY.search(message):
        return RouteDecision(
            skill="ship30_essay",
            confidence=0.95,
            method="rule",
            reason="Message explicitly requests long-form written content.",
        )
    if _ARTIFACT.search(message):
        kind = "html" if _HTML_HINT.search(message) else "markdown"
        return RouteDecision(
            skill="artifact",
            confidence=0.9,
            method="rule",
            reason=f"Message explicitly requests a rendered {kind} artifact.",
            artifact_kind=kind,
        )
    if len(message.split()) <= 3 and message.endswith("?"):
        return RouteDecision(
            skill="grounded_qa",
            confidence=0.7,
            method="rule",
            reason="Short interrogative — treated as a question.",
        )
    return None


CLASSIFIER_PROMPT = """Classify the user's request into exactly one label.

grounded_qa   - a question to be answered from podcast transcripts
ship30_essay  - a request for a long-form essay, post, or article
artifact      - a request for a rendered document, page, table, or widget

Reply with the label alone. No explanation."""


async def route(message: str, *, use_classifier: bool = True) -> RouteDecision:
    rule = route_by_rules(message)
    if rule:
        log.info("agent.route", **rule.to_dict())
        return rule

    if not use_classifier:
        return RouteDecision(
            skill="grounded_qa", confidence=0.5, method="fallback",
            reason="Classifier disabled; defaulting to question answering.",
        )

    try:
        provider = get_chat_provider()
        result = await provider.complete(
            [ChatMessage(role="user", content=message[:1500])],
            system=CLASSIFIER_PROMPT,
            max_tokens=12,
            temperature=0.0,
        )
        label = result.text.strip().lower()
        for candidate in ("ship30_essay", "artifact", "grounded_qa"):
            if candidate in label:
                decision = RouteDecision(
                    skill=candidate,  # type: ignore[arg-type]
                    confidence=0.75,
                    method="classifier",
                    reason=f"Model classified the request as {candidate}.",
                    artifact_kind=(
                        ("html" if _HTML_HINT.search(message) else "markdown")
                        if candidate == "artifact"
                        else None
                    ),
                )
                log.info("agent.route", **decision.to_dict())
                return decision
    except Exception as exc:  # noqa: BLE001 - routing must never fail the turn
        log.warning("agent.route.classifier_failed", error=str(exc))

    decision = RouteDecision(
        skill="grounded_qa", confidence=0.5, method="fallback",
        reason="Classifier unavailable or unclear; defaulting to question answering.",
    )
    log.info("agent.route", **decision.to_dict())
    return decision
