"""Chunking behaviour that answer quality depends on."""

from app.rag.chunker import chunk_transcript, estimate_tokens, nearest_timestamp
from app.rag.parser import _guest_from_title, _title_from_filename


def test_chunks_never_start_mid_sentence(sample_transcript):
    chunks = chunk_transcript(sample_transcript, target_tokens=40, overlap_tokens=10)
    assert chunks
    for c in chunks:
        first = c.content.lstrip()[0]
        assert first.isupper() or first in "*#[-", (
            f"chunk begins mid-sentence: {c.content[:60]!r}"
        )


def test_speaker_is_captured_for_attribution(sample_transcript):
    chunks = chunk_transcript(sample_transcript, target_tokens=40, overlap_tokens=5)
    assert any(c.speaker for c in chunks), (
        "no speaker captured — citations could not attribute a claim to a person"
    )


def test_overlap_preserves_claims_across_boundaries(sample_transcript):
    chunks = chunk_transcript(sample_transcript, target_tokens=30, overlap_tokens=15)
    assert len(chunks) > 1
    joined = " ".join(c.content for c in chunks)
    assert joined.count("Retention flattening") >= 1


def test_oversized_turn_is_split_rather_than_dropped():
    long_turn = "**Guest:** " + ("This is a complete sentence. " * 400)
    chunks = chunk_transcript(long_turn, target_tokens=100, overlap_tokens=10)
    assert len(chunks) > 3
    assert all(c.token_estimate <= 200 for c in chunks)


def test_unstructured_text_falls_back_to_paragraphs():
    body = "\n\n".join(f"Paragraph number {i} with some content." for i in range(12))
    chunks = chunk_transcript(body, target_tokens=30, overlap_tokens=5)
    assert len(chunks) >= 2


def test_timestamp_extracted_for_citation_depth():
    assert nearest_timestamp("[00:02:14] Retention flattening.") == "00:02:14"
    assert nearest_timestamp("no timestamp here") is None


def test_token_estimate_is_monotonic():
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 100)


def test_guest_parsed_from_pipe_separated_title():
    assert _guest_from_title("How to find PMF | Priya Raman (Northwind)") == "Priya Raman"


def test_title_falls_back_to_filename():
    from pathlib import Path

    assert _title_from_filename(Path("how-to-price-b2b.md")) == "How To Price B2B".title()
