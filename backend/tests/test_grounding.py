"""The grounding gate and citation verdict.

This is the behaviour the product's trustworthiness rests on, so it is tested
without a model in the loop.
"""

import pytest

from app.agent.skills.qa import _citation_stats, _verdict
from app.config import settings
from app.rag.retriever import RetrievalResult, RetrievedChunk, _assess


def _chunk(marker: str, score: float, transcript: str = "t1") -> RetrievedChunk:
    return RetrievedChunk(
        marker=marker, chunk_id=f"c-{marker}", transcript_id=transcript,
        source_id=f"{transcript}.md", title="Episode", guest="Guest",
        episode_url=None, content="Retention flattens when you have fit.",
        score=score, semantic_rank=1, lexical_rank=1, heading=None, timestamp=None,
    )


def test_empty_retrieval_is_insufficient():
    r = RetrievalResult(query="q")
    _assess(r)
    assert r.sufficiency == "insufficient"
    assert not r.is_answerable


def test_weak_scores_are_insufficient_so_the_agent_abstains():
    floor = settings.min_grounding_score
    r = RetrievalResult(query="q", chunks=[_chunk("S1", floor * 0.1)])
    _assess(r)
    assert r.sufficiency == "insufficient"
    assert "grounding floor" in r.reason


def test_single_strong_chunk_is_thin_not_sufficient():
    """One source is answerable but must be hedged — corroboration matters."""
    r = RetrievalResult(query="q", chunks=[_chunk("S1", settings.min_grounding_score * 2)])
    _assess(r)
    assert r.sufficiency == "thin"
    assert r.is_answerable


def test_multiple_episodes_give_sufficient_grounding():
    s = settings.min_grounding_score * 2
    r = RetrievalResult(
        query="q",
        chunks=[_chunk("S1", s, "t1"), _chunk("S2", s, "t2"), _chunk("S3", s, "t1")],
    )
    _assess(r)
    assert r.sufficiency == "sufficient"


def test_three_chunks_from_one_episode_is_only_thin():
    """Three chunks of the same episode is one opinion, not corroboration."""
    s = settings.min_grounding_score * 2
    r = RetrievalResult(
        query="q",
        chunks=[_chunk("S1", s, "t1"), _chunk("S2", s, "t1"), _chunk("S3", s, "t1")],
    )
    _assess(r)
    assert r.sufficiency == "thin"


def test_context_block_uses_stable_markers_the_model_must_cite():
    r = RetrievalResult(query="q", chunks=[_chunk("S1", 0.5), _chunk("S2", 0.4)])
    block = r.context_block()
    assert "[S1]" in block and "[S2]" in block


def test_context_block_respects_its_character_budget():
    chunks = [_chunk(f"S{i}", 0.5) for i in range(1, 40)]
    r = RetrievalResult(query="q", chunks=chunks)
    assert len(r.context_block(max_chars=500)) <= 600


@pytest.mark.parametrize(
    "text,expected_markers",
    [
        ("Retention flattens. [S1]", {"S1"}),
        ("A claim [S1] and another [S3].", {"S1", "S3"}),
        ("No citations at all.", set()),
    ],
)
def test_citation_extraction(text, expected_markers):
    markers, _ = _citation_stats(text)
    assert markers == expected_markers


def test_uncited_answer_is_marked_ungrounded_even_with_good_retrieval():
    """A model that ignores the citation instruction must be visibly caught."""
    s = settings.min_grounding_score * 2
    r = RetrievalResult(query="q", chunks=[_chunk("S1", s, "t1"), _chunk("S2", s, "t2")])
    _assess(r)
    assert _verdict(r, used=set(), coverage=0.0) == "ungrounded"


def test_well_cited_answer_over_strong_retrieval_is_grounded():
    s = settings.min_grounding_score * 2
    r = RetrievalResult(
        query="q",
        chunks=[_chunk("S1", s, "t1"), _chunk("S2", s, "t2"), _chunk("S3", s, "t3")],
    )
    _assess(r)
    assert _verdict(r, used={"S1", "S2"}, coverage=0.9) == "grounded"


def test_partial_coverage_is_reported_as_partial():
    s = settings.min_grounding_score * 2
    r = RetrievalResult(query="q", chunks=[_chunk("S1", s, "t1")])
    _assess(r)
    assert _verdict(r, used={"S1"}, coverage=0.5) == "partial"
