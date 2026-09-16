"""Preflight check — `make doctor`.

Run this before the demo. It checks each dependency in the order the app needs
them and prints the exact command to fix whatever is broken, so a failed demo
becomes a 30-second fix instead of a debugging session.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.db import ping, session_scope
from app.db import repository as repo
from app.llm import provider_health

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def line(ok: bool | None, label: str, detail: str = "", fix: str = "") -> bool:
    mark = f"{GREEN}ok{RESET}" if ok else (
        f"{YELLOW}warn{RESET}" if ok is None else f"{RED}FAIL{RESET}"
    )
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok and fix:
        print(f"         fix: {fix}")
    return bool(ok)


async def main() -> int:
    print("\n  Lenny Growth Assistant — preflight\n")
    healthy = True

    # 1. database
    try:
        info = await ping()
        healthy &= line(True, "Postgres", f"server {info['server_version']}")
        healthy &= line(
            info["pgvector"], "pgvector extension",
            fix="The pgvector/pgvector image provides it. "
                "Check `docker compose ps postgres`.",
        )
    except Exception as exc:  # noqa: BLE001
        healthy &= line(
            False, "Postgres", str(exc)[:90],
            fix="docker compose up -d postgres  (then confirm DATABASE_URL)",
        )
        print("\n  Cannot continue without the database.\n")
        return 1

    # 2. knowledge base
    async with session_scope() as db:
        stats = await repo.knowledge_base_stats(db)
    ready = stats["chunks"] > 0
    healthy &= line(
        ready, "Knowledge base",
        f"{stats['transcripts']} transcripts, {stats['chunks']} chunks",
        fix="make fetch-transcripts && make ingest",
    )
    if ready and stats["unembedded"]:
        line(None, "Embeddings", f"{stats['unembedded']} chunks have no vector",
             fix="make ingest FORCE=1")

    # 3. models
    health = await provider_health()
    chat = health.get("chat", {})
    healthy &= line(
        chat.get("ok"), f"Chat provider ({settings.chat_provider})",
        chat.get("model", ""),
        fix=chat.get("hint") or "Check CHAT_PROVIDER and the matching API key in .env",
    )
    emb = health.get("embedding", {})
    healthy &= line(
        emb.get("ok"), f"Embedding provider ({settings.embedding_provider})",
        emb.get("model", ""),
        fix=emb.get("hint") or f"ollama pull {settings.ollama_embedding_model}",
    )
    if emb.get("ok") and emb.get("dim") and emb["dim"] != settings.embedding_dim:
        healthy &= line(
            False, "Embedding dimension",
            f"model returns {emb['dim']}, EMBEDDING_DIM is {settings.embedding_dim}",
            fix=f"make resize-embeddings DIM={emb['dim']} && make ingest",
        )

    # 4. agent runtime
    if settings.agent_runtime == "claude_sdk":
        from app.agent.claude_sdk_runtime import availability

        a = availability()
        healthy &= line(a["available"], "Claude Agent SDK",
                        fix=a["install"] + "  (or set AGENT_RUNTIME=native)")
    else:
        line(True, "Agent runtime", "native tool loop")

    print(
        f"\n  {GREEN}Ready.{RESET}\n" if healthy
        else f"\n  {RED}Not ready.{RESET} Fix the items above, then re-run "
             "`make doctor`.\n"
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
