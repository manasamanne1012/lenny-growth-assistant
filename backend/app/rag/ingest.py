"""Ingestion pipeline.

Run with `make ingest`. Properties that matter for handoff:

  * **Incremental.** Each transcript is hashed; unchanged files are skipped, so
    re-running after a repo refresh costs seconds, not a full re-embed.
  * **Traceable.** Every chunk keeps its transcript's `source_id` (the repo file
    path), so any sentence in an answer can be walked back to a file on disk.
  * **Resumable.** Failures are per-file and reported; one malformed transcript
    does not abort the run.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text

from app.db import session_scope
from app.db import repository as repo
from app.llm import get_embedder
from app.obs import get_logger
from app.rag.chunker import chunk_transcript
from app.rag.parser import find_transcripts, parse_transcript_file

log = get_logger("rag.ingest")

EMBED_BATCH = 16


@dataclass
class IngestReport:
    files_found: int = 0
    transcripts_new: int = 0
    transcripts_updated: int = 0
    transcripts_skipped: int = 0
    chunks_written: int = 0
    failures: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Ingestion complete",
            f"  files found       : {self.files_found}",
            f"  new transcripts   : {self.transcripts_new}",
            f"  updated           : {self.transcripts_updated}",
            f"  unchanged/skipped : {self.transcripts_skipped}",
            f"  chunks written    : {self.chunks_written}",
            f"  failures          : {len(self.failures)}",
        ]
        for f in self.failures[:10]:
            lines.append(f"    ! {f['file']}: {f['error']}")
        if self.warnings:
            lines.append(f"  warnings          : {len(self.warnings)} (first 5)")
            lines += [f"    - {w}" for w in self.warnings[:5]]
        return "\n".join(lines)


async def ingest_directory(
    root: Path, *, limit: int | None = None, force: bool = False
) -> IngestReport:
    report = IngestReport()
    files = find_transcripts(root)
    if limit:
        files = files[:limit]
    report.files_found = len(files)

    if not files:
        log.error("rag.ingest.no_files", root=str(root))
        report.failures.append(
            {
                "file": str(root),
                "error": "No .md/.txt transcripts found. Run `make fetch-transcripts` "
                         "first, or point TRANSCRIPTS_DIR at a local copy.",
            }
        )
        return report

    embedder = get_embedder()
    log.info("rag.ingest.start", files=len(files), embedder=embedder.model)

    for i, path in enumerate(files, 1):
        try:
            parsed = parse_transcript_file(path, root)
            report.warnings.extend(f"{parsed.source_id}: {w}" for w in parsed.warnings)

            async with session_scope() as db:
                transcript_id, changed = await repo.upsert_transcript(
                    db,
                    source_id=parsed.source_id,
                    title=parsed.title,
                    guest=parsed.guest,
                    episode_url=parsed.episode_url,
                    published_on=parsed.published_on,
                    source_path=parsed.source_path,
                    content_hash=parsed.content_hash,
                    word_count=parsed.word_count,
                )

            if not changed and not force:
                report.transcripts_skipped += 1
                continue

            chunks = chunk_transcript(parsed.body)
            if not chunks:
                report.failures.append(
                    {"file": parsed.source_id, "error": "produced zero chunks"}
                )
                continue

            vectors: list[list[float]] = []
            for start in range(0, len(chunks), EMBED_BATCH):
                batch = [c.content for c in chunks[start : start + EMBED_BATCH]]
                vectors.extend(await embedder.embed(batch))

            payload = [
                {
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "heading": c.heading,
                    "speaker": c.speaker,
                    "start_char": c.start_char,
                    "token_estimate": c.token_estimate,
                    "embedding": vec,
                }
                for c, vec in zip(chunks, vectors)
            ]
            async with session_scope() as db:
                written = await repo.insert_chunks(db, transcript_id, payload)

            report.chunks_written += written
            report.transcripts_new += 1
            log.info(
                "rag.ingest.file",
                progress=f"{i}/{len(files)}",
                source=parsed.source_id,
                chunks=written,
            )
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            log.error("rag.ingest.file_failed", file=str(path), error=str(exc))
            report.failures.append({"file": str(path), "error": str(exc)})

    # Rebuild planner statistics so the ivfflat index is actually used.
    try:
        async with session_scope() as db:
            await db.execute(text("ANALYZE chunks"))
    except Exception as exc:  # noqa: BLE001
        log.warning("rag.ingest.analyze_failed", error=str(exc))

    log.info("rag.ingest.done", **{
        k: v for k, v in report.__dict__.items() if not isinstance(v, list)
    })
    return report


def main() -> None:
    import argparse
    import os

    from app.db.bootstrap import apply_migrations

    parser = argparse.ArgumentParser(description="Ingest Lenny's Podcast transcripts.")
    parser.add_argument(
        "--source",
        default=os.getenv("TRANSCRIPTS_DIR", "./data/lennys-podcast-transcripts"),
        help="Directory containing transcript Markdown files.",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Ingest only the first N files (useful for a quick demo).")
    parser.add_argument("--force", action="store_true",
                        help="Re-embed even when the content hash is unchanged.")
    args = parser.parse_args()

    async def run() -> None:
        await apply_migrations()
        report = await ingest_directory(
            Path(args.source).resolve(), limit=args.limit, force=args.force
        )
        print(report.render())

    asyncio.run(run())


if __name__ == "__main__":
    main()
