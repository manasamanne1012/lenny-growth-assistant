"""Ollama — the mandatory local demo path.

Ollama's /api/chat supports tool calling for tool-capable models (llama3.1,
qwen2.5, mistral-nemo). Smaller models emit malformed tool JSON often enough
that the agent's native loop treats any parse failure as "no tool call" and
falls through to a direct grounded answer rather than erroring. See ADR-005.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.llm.base import ChatMessage, ChatProviderError, CompletionResult, ToolCall
from app.obs import get_logger

log = get_logger("llm.ollama")


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_chat_model

    def _payload(self, messages, system, tools, max_tokens, temperature) -> dict:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in messages:
            role = "tool" if m.role == "tool" else m.role
            msgs.append({"role": role, "content": m.content})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "options": {
                "temperature": (
                    settings.temperature if temperature is None else temperature
                ),
                "num_predict": max_tokens or settings.max_output_tokens,
            },
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]
        return payload

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CompletionResult:
        payload = self._payload(messages, system, tools, max_tokens, temperature)
        payload["stream"] = False
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise ChatProviderError(
                self.name,
                f"cannot reach Ollama at {self.base_url}. Is `ollama serve` running? ({exc})",
                retryable=True,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ChatProviderError(
                self.name,
                f"timed out after {settings.request_timeout_s}s — try a smaller model",
                retryable=True,
            ) from exc

        if resp.status_code == 404:
            raise ChatProviderError(
                self.name,
                f"model '{self.model}' is not pulled. Run: ollama pull {self.model}",
            )
        if resp.status_code >= 400:
            raise ChatProviderError(
                self.name, f"HTTP {resp.status_code}: {resp.text[:400]}",
                retryable=resp.status_code >= 500,
            )

        data = resp.json()
        message = data.get("message", {})
        return CompletionResult(
            text=message.get("content", "") or "",
            provider=self.name,
            model=self.model,
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
            finish_reason=data.get("done_reason", "stop"),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, system, None, max_tokens, temperature)
        payload["stream"] = True
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode()[:400]
                        raise ChatProviderError(
                            self.name, f"HTTP {resp.status_code}: {body}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        piece = chunk.get("message", {}).get("content")
                        if piece:
                            yield piece
                        if chunk.get("done"):
                            break
        except httpx.ConnectError as exc:
            raise ChatProviderError(
                self.name, f"cannot reach Ollama at {self.base_url}", retryable=True
            ) from exc

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", [])]
            pulled = any(n == self.model or n.startswith(f"{self.model}") for n in names)
            return {
                "ok": pulled,
                "reachable": True,
                "model": self.model,
                "model_pulled": pulled,
                "available_models": names[:20],
                "hint": None if pulled else f"ollama pull {self.model}",
            }
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {
                "ok": False,
                "reachable": False,
                "model": self.model,
                "error": str(exc),
                "hint": (
                    "Start Ollama with `ollama serve`. From Docker, the host is "
                    "http://host.docker.internal:11434."
                ),
            }


def _parse_tool_calls(raw: list[dict]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for i, tc in enumerate(raw):
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                log.warning("llm.ollama.tool_args_unparseable", raw=args[:200])
                continue
        if not fn.get("name"):
            continue
        calls.append(
            ToolCall(id=tc.get("id") or f"call_{i}", name=fn["name"], arguments=args)
        )
    return calls


class OllamaEmbedder:
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_embedding_model
        self.dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            for chunk in texts:
                try:
                    resp = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": chunk},
                    )
                except httpx.ConnectError as exc:
                    raise ChatProviderError(
                        self.name,
                        f"cannot reach Ollama at {self.base_url} for embeddings",
                        retryable=True,
                    ) from exc
                if resp.status_code == 404:
                    raise ChatProviderError(
                        self.name,
                        f"embedding model '{self.model}' not pulled. "
                        f"Run: ollama pull {self.model}",
                    )
                resp.raise_for_status()
                vec = resp.json().get("embedding")
                if not vec:
                    raise ChatProviderError(self.name, "empty embedding returned")
                out.append(vec)
        return out

    async def health(self) -> dict[str, Any]:
        try:
            vec = await self.embed(["health check"])
            return {"ok": True, "model": self.model, "dim": len(vec[0])}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)}
