"""Transcript parsing.

The ChatPRD/lennys-podcast-transcripts repository stores one Markdown file per
episode. Files are not perfectly uniform: some carry YAML front matter, some
open with an H1, some name the guest in the filename only. The parser is
therefore forgiving and records what it could not determine rather than
guessing, so a citation never claims a guest name the source did not state.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SPEAKER_LINE = re.compile(r"^\*{0,2}([A-Z][\w .'-]{1,40}?)\*{0,2}\s*[:：]\s", re.MULTILINE)
TIMESTAMP = re.compile(r"[\[(]?(\d{1,2}:\d{2}(?::\d{2})?)[\])]?")


@dataclass
class ParsedTranscript:
    source_id: str
    title: str
    body: str
    source_path: str
    guest: str | None = None
    episode_url: str | None = None
    published_on: date | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    @property
    def word_count(self) -> int:
        return len(self.body.split())


def parse_transcript_file(path: Path, root: Path) -> ParsedTranscript:
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta: dict[str, str] = {}
    warnings: list[str] = []

    fm = FRONT_MATTER.match(raw)
    if fm:
        meta = _parse_front_matter(fm.group(1))
        raw = raw[fm.end():]

    title = meta.get("title") or _first_heading(raw) or _title_from_filename(path)
    guest = meta.get("guest") or meta.get("author") or _guest_from_title(title)
    if not guest:
        warnings.append("guest not identified; citations will show episode title only")

    published = _parse_date(meta.get("date") or meta.get("published"))
    url = meta.get("url") or meta.get("link") or _first_youtube_url(raw)

    return ParsedTranscript(
        source_id=str(path.relative_to(root)).replace("\\", "/"),
        title=title.strip(),
        body=raw.strip(),
        source_path=str(path),
        guest=guest,
        episode_url=url,
        published_on=published,
        warnings=warnings,
    )


def _parse_front_matter(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip().lower()] = value.strip().strip("\"'")
    return out


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _title_from_filename(path: Path) -> str:
    return re.sub(r"[-_]+", " ", path.stem).strip().title()


def _guest_from_title(title: str) -> str | None:
    """Episode titles commonly read '<topic> | <Guest> (<company>)'."""
    if "|" in title:
        tail = title.split("|")[-1].strip()
        tail = re.sub(r"\(.*?\)", "", tail).strip()
        if 2 <= len(tail.split()) <= 4:
            return tail
    m = re.search(r"\bwith ([A-Z][\w.'-]+(?: [A-Z][\w.'-]+){0,2})", title)
    return m.group(1) if m else None


def _first_youtube_url(text: str) -> str | None:
    m = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+", text)
    return m.group(0).rstrip(").,") if m else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def find_transcripts(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() in {".md", ".markdown", ".txt"}
        and not p.name.lower().startswith("readme")
        and ".git" not in p.parts
    )
