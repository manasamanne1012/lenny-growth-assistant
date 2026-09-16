"""Chunking.

Podcast transcripts are long, loosely structured, and speaker-turn based. Three
choices matter for answer quality and are worth stating plainly:

1.  Split on speaker turns and headings first, then pack turns up to a token
    budget. A chunk therefore never begins mid-sentence and usually contains a
    complete thought from one speaker.
2.  Overlap by whole turns, not characters, so a claim spanning a turn boundary
    is still retrievable intact.
3.  Carry the nearest preceding timestamp on each chunk so a citation can point
    the reader to the moment in the episode, not just the episode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings

SPEAKER_TURN = re.compile(
    r"(?m)^\*{0,2}(?P<speaker>[A-Z][\w .'-]{1,40}?)\*{0,2}\s*:\s*\*{0,2}"
)
HEADING = re.compile(r"(?m)^#{1,3} +(?P<heading>.+)$")
TIMESTAMP = re.compile(r"[\[(]?(\d{1,2}:\d{2}(?::\d{2})?)[\])]?")


@dataclass
class Chunk:
    chunk_index: int
    content: str
    heading: str | None
    speaker: str | None
    start_char: int
    token_estimate: int


def estimate_tokens(text: str) -> int:
    """~4 characters per token. Good enough for budgeting; never used for billing."""
    return max(1, len(text) // 4)


def _segments(body: str) -> list[tuple[int, str | None, str | None, str]]:
    """Split into (start_char, speaker, heading, text) units."""
    boundaries: list[tuple[int, str | None, str | None]] = []
    for m in SPEAKER_TURN.finditer(body):
        boundaries.append((m.start(), m.group("speaker"), None))
    for m in HEADING.finditer(body):
        boundaries.append((m.start(), None, m.group("heading")))
    boundaries.sort(key=lambda b: b[0])

    if not boundaries:
        # Unstructured wall of text: fall back to paragraph splits.
        out, cursor = [], 0
        for para in body.split("\n\n"):
            if para.strip():
                out.append((cursor, None, None, para.strip()))
            cursor += len(para) + 2
        return out

    segments = []
    if boundaries[0][0] > 0 and body[: boundaries[0][0]].strip():
        segments.append((0, None, None, body[: boundaries[0][0]].strip()))
    for i, (start, speaker, heading) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(body)
        text = body[start:end].strip()
        if text:
            segments.append((start, speaker, heading, text))
    return segments


def chunk_transcript(
    body: str,
    *,
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    target = target_tokens or settings.chunk_target_tokens
    overlap = overlap_tokens or settings.chunk_overlap_tokens

    segments = _segments(body)
    chunks: list[Chunk] = []
    buffer: list[tuple[int, str | None, str | None, str]] = []
    buffer_tokens = 0
    current_heading: str | None = None
    index = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens, index
        if not buffer:
            return
        text = "\n\n".join(s[3] for s in buffer)
        speakers = [s[1] for s in buffer if s[1]]
        chunks.append(
            Chunk(
                chunk_index=index,
                content=text,
                heading=current_heading,
                speaker=speakers[0] if speakers else None,
                start_char=buffer[0][0],
                token_estimate=estimate_tokens(text),
            )
        )
        index += 1
        # Overlap by whole trailing segments, never mid-sentence.
        carried: list = []
        carried_tokens = 0
        for seg in reversed(buffer):
            t = estimate_tokens(seg[3])
            if carried_tokens + t > overlap:
                break
            carried.insert(0, seg)
            carried_tokens += t
        buffer = carried
        buffer_tokens = carried_tokens

    for seg in segments:
        if seg[2]:
            current_heading = seg[2]
        seg_tokens = estimate_tokens(seg[3])

        # A single oversized turn becomes its own chunk, split on sentences.
        if seg_tokens > target * 1.6:
            flush()
            for piece in _split_long(seg[3], target):
                chunks.append(
                    Chunk(
                        chunk_index=index,
                        content=piece,
                        heading=current_heading,
                        speaker=seg[1],
                        start_char=seg[0],
                        token_estimate=estimate_tokens(piece),
                    )
                )
                index += 1
            continue

        if buffer_tokens + seg_tokens > target and buffer:
            flush()
        buffer.append(seg)
        buffer_tokens += seg_tokens

    flush()
    return [c for c in chunks if c.content.strip()]


def _split_long(text: str, target: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out, cur, cur_tokens = [], [], 0
    for s in sentences:
        t = estimate_tokens(s)
        if cur_tokens + t > target and cur:
            out.append(" ".join(cur))
            cur, cur_tokens = [], 0
        cur.append(s)
        cur_tokens += t
    if cur:
        out.append(" ".join(cur))
    return out


def nearest_timestamp(content: str) -> str | None:
    m = TIMESTAMP.search(content)
    return m.group(1) if m else None
