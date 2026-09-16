"""OpenAI (second cloud option) and its embedding model."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.llm.base import ChatMessage, ChatProviderError, CompletionResult, ToolCall

BASE = "https://api.openai.com/v1"


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_chat_model
        if not self.api_key:
            raise ChatProviderError(self.name, "OPENAI_API_KEY is not set.")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CompletionResult:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            m.to_openai() for m in messages
        ]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens or settings.max_output_tokens,
            "temperature": settings.temperature if temperature is None else temperature,
        }
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]

        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            resp = await client.post(
                f"{BASE}/chat/completions", headers=self._headers, json=body
            )
        if resp.status_code >= 400:
            raise ChatProviderError(
                self.name, f"HTTP {resp.status_code}: {resp.text[:400]}",
                retryable=resp.status_code in (429, 500, 502, 503),
            )
        data = resp.json()
        choice = data["choices"][0]["message"]
        calls = []
        for tc in choice.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                continue
            calls.append(ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=args))
        usage = data.get("usage", {})
        return CompletionResult(
            text=choice.get("content") or "",
            provider=self.name,
            model=self.model,
            tool_calls=calls,
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            m.to_openai() for m in messages
        ]
        body = {
            "model": self.model,
            "messages": msgs,
            "stream": True,
            "max_tokens": max_tokens or settings.max_output_tokens,
        }
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            async with client.stream(
                "POST", f"{BASE}/chat/completions", headers=self._headers, json=body
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    piece = event["choices"][0].get("delta", {}).get("content")
                    if piece:
                        yield piece

    async def health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "model": self.model, "error": "OPENAI_API_KEY unset"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{BASE}/models", headers=self._headers)
            return {"ok": resp.status_code < 400, "model": self.model,
                    "status": resp.status_code}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)}


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_embedding_model
        self.dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise ChatProviderError(self.name, "OPENAI_API_KEY is not set.")
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            resp = await client.post(
                f"{BASE}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
        if resp.status_code >= 400:
            raise ChatProviderError(
                self.name, f"HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return [d["embedding"] for d in resp.json()["data"]]

    async def health(self) -> dict[str, Any]:
        try:
            vec = await self.embed(["health check"])
            return {"ok": True, "model": self.model, "dim": len(vec[0])}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)}
