"""Anthropic Claude via the Messages API (cloud option)."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.config import settings
from app.llm.base import ChatMessage, ChatProviderError, CompletionResult, ToolCall

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_chat_model
        if not self.api_key:
            raise ChatProviderError(
                self.name, "ANTHROPIC_API_KEY is not set. Set it or use CHAT_PROVIDER=ollama."
            )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _body(self, messages, system, tools, max_tokens, temperature) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or settings.max_output_tokens,
            "temperature": (
                settings.temperature if temperature is None else temperature
            ),
            "messages": [_to_anthropic(m) for m in messages],
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object"}),
                }
                for t in tools
            ]
        return body

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CompletionResult:
        body = self._body(messages, system, tools, max_tokens, temperature)
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
                resp = await client.post(API_URL, headers=self._headers, json=body)
        except httpx.TimeoutException as exc:
            raise ChatProviderError(self.name, "request timed out", retryable=True) from exc

        if resp.status_code == 401:
            raise ChatProviderError(self.name, "invalid API key (401)")
        if resp.status_code == 429:
            raise ChatProviderError(self.name, "rate limited (429)", retryable=True)
        if resp.status_code >= 400:
            raise ChatProviderError(
                self.name, f"HTTP {resp.status_code}: {resp.text[:400]}",
                retryable=resp.status_code >= 500,
            )

        data = resp.json()
        text_parts, calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block.get("input", {}),
                    )
                )
        usage = data.get("usage", {})
        return CompletionResult(
            text="".join(text_parts),
            provider=self.name,
            model=self.model,
            tool_calls=calls,
            usage={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
            finish_reason=data.get("stop_reason", "stop"),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        body = self._body(messages, system, None, max_tokens, temperature)
        body["stream"] = True
        async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
            async with client.stream(
                "POST", API_URL, headers=self._headers, json=body
            ) as resp:
                if resp.status_code >= 400:
                    body_text = (await resp.aread()).decode()[:400]
                    raise ChatProviderError(
                        self.name, f"HTTP {resp.status_code}: {body_text}"
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        piece = event.get("delta", {}).get("text")
                        if piece:
                            yield piece

    async def health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "model": self.model, "error": "ANTHROPIC_API_KEY unset"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    API_URL,
                    headers=self._headers,
                    json={
                        "model": self.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
            return {
                "ok": resp.status_code < 400,
                "model": self.model,
                "status": resp.status_code,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)}


def _to_anthropic(m: ChatMessage) -> dict[str, Any]:
    if m.role == "tool":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id or "unknown",
                    "content": m.content,
                }
            ],
        }
    return {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
