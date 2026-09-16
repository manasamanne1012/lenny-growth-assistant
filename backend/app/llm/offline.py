"""Offline providers used by tests and CI.

`EchoProvider` and `HashEmbedder` make the whole pipeline — routing, retrieval,
ranking, citation assembly, artifact sanitization, persistence — testable with
no model server and no API key. They are deliberately not usable for a real
demo: the echo provider says so in its own output.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.llm.base import ChatMessage, CompletionResult


class EchoProvider:
    """Deterministic stand-in. Extracts context snippets so retrieval assertions
    remain meaningful without a model."""

    name = "echo"

    def __init__(self, model: str = "echo-1"):
        self.model = model

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CompletionResult:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        cited = re.findall(r"\[S(\d+)\]", "\n".join(m.content for m in messages))
        marks = " ".join(f"[S{n}]" for n in dict.fromkeys(cited)) or "[S1]"
        return CompletionResult(
            text=(
                "ECHO PROVIDER (test only, not a real model). "
                f"Question: {last_user[:200]} Sources: {marks}"
            ),
            provider=self.name,
            model=self.model,
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        result = await self.complete(messages, system=system)
        for word in result.text.split(" "):
            yield word + " "

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "model": self.model, "note": "offline test provider"}


class HashEmbedder:
    """Deterministic hashed bag-of-words embedding.

    Not semantically meaningful. It exists so retrieval, RRF fusion, and the
    pgvector round-trip can be exercised deterministically in CI.
    """

    name = "hash"

    def __init__(self, dim: int | None = None):
        self.model = "hash-bow"
        self.dim = dim or settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in re.findall(r"[a-z0-9']+", text.lower()):
            h = int(hashlib.blake2b(token.encode(), digest_size=8).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "model": self.model, "dim": self.dim,
                "note": "offline test embedder"}
