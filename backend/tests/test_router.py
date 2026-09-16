"""Routing. The rule layer is deterministic, so it is fully testable."""

import pytest

from app.agent.router import route, route_by_rules


@pytest.mark.parametrize(
    "message",
    [
        "Write a ship 30 essay on onboarding",
        "write me an essay about growth loops",
        "Draft a LinkedIn post on pricing",
        "I need an atomic essay on activation",
    ],
)
def test_essay_requests_route_to_ship30(message):
    decision = route_by_rules(message)
    assert decision and decision.skill == "ship30_essay"


@pytest.mark.parametrize(
    "message,kind",
    [
        ("Build me an HTML dashboard of activation metrics", "html"),
        ("Make me a one-pager on pricing", "markdown"),
        ("Give me a checklist as a markdown document", "markdown"),
        ("Create an interactive calculator widget", "html"),
    ],
)
def test_artifact_requests_route_with_correct_kind(message, kind):
    decision = route_by_rules(message)
    assert decision and decision.skill == "artifact"
    assert decision.artifact_kind == kind


@pytest.mark.parametrize(
    "message",
    [
        "How do guests define product-market fit?",
        "What moves activation during onboarding?",
    ],
)
def test_plain_questions_do_not_match_a_rule(message):
    assert route_by_rules(message) is None


@pytest.mark.asyncio
async def test_router_never_raises_and_always_returns_a_skill():
    decision = await route("something completely ambiguous", use_classifier=False)
    assert decision.skill in ("grounded_qa", "ship30_essay", "artifact")
    assert decision.method == "fallback"


@pytest.mark.asyncio
async def test_explicit_rule_beats_the_classifier():
    decision = await route("write me an essay on churn")
    assert decision.method == "rule"
    assert decision.skill == "ship30_essay"
