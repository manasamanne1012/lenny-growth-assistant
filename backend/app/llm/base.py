"""Provider-agnostic contracts.

Everything above this file — the agent, the skills, the routes — speaks only
these types. Adding a provider means adding one module and one registry entry;
it never means touching application logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]


class ChatProviderError(RuntimeError):
    """Raised for any provider failure the caller may want to fall back from."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.retryable = retryable


@dataclass
class ChatMessage:
    role: Role
    content: str
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class CompletionResult:
    text: str
    provider: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CompletionResult: ...

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]: ...

    async def health(self) -> dict[str, Any]: ...


@runtime_checkable
class Embedder(Protocol):
    name: str
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def health(self) -> dict[str, Any]: ...
