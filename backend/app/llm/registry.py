"""Provider registry — the switchboard the evaluator flips.

Selection is by environment variable only. `CHAT_PROVIDER=anthropic` and a
restart is the entire change; no application code is touched. A configured
fallback provider is used when the primary raises a retryable error, and the
provider actually used is reported back to the UI on every message.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.llm.base import ChatProviderError, LLMProvider
from app.obs import get_logger

log = get_logger("llm.registry")

_chat_cache: dict[str, Any] = {}
_embed_cache: dict[str, Any] = {}


def _build_chat(name: str):
    if name == "ollama":
        from app.llm.ollama_provider import OllamaProvider

        return OllamaProvider()
    if name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "echo":
        from app.llm.offline import EchoProvider

        return EchoProvider()
    raise ChatProviderError("registry", f"unknown chat provider '{name}'")


def _build_embedder(name: str):
    if name == "ollama":
        from app.llm.ollama_provider import OllamaEmbedder

        return OllamaEmbedder()
    if name == "openai":
        from app.llm.openai_provider import OpenAIEmbedder

        return OpenAIEmbedder()
    if name == "hash":
        from app.llm.offline import HashEmbedder

        return HashEmbedder()
    raise ChatProviderError("registry", f"unknown embedding provider '{name}'")


def get_chat_provider(name: str | None = None) -> LLMProvider:
    key = name or settings.chat_provider
    if key not in _chat_cache:
        _chat_cache[key] = _build_chat(key)
    return _chat_cache[key]


def get_embedder(name: str | None = None):
    key = name or settings.embedding_provider
    if key not in _embed_cache:
        _embed_cache[key] = _build_embedder(key)
    return _embed_cache[key]


def get_fallback_chat_provider() -> LLMProvider | None:
    if not settings.chat_fallback_provider:
        return None
    if settings.chat_fallback_provider == settings.chat_provider:
        return None
    try:
        return get_chat_provider(settings.chat_fallback_provider)
    except ChatProviderError as exc:
        log.warning("llm.fallback.unavailable", error=str(exc))
        return None


def describe_providers() -> dict[str, Any]:
    """Shown in the UI's model badge so the active model is never a mystery."""
    return {
        "chat": {
            "provider": settings.chat_provider,
            "model": _model_for(settings.chat_provider),
            "is_local": settings.chat_provider == "ollama",
        },
        "fallback": (
            {
                "provider": settings.chat_fallback_provider,
                "model": _model_for(settings.chat_fallback_provider),
            }
            if settings.chat_fallback_provider
            else None
        ),
        "embedding": {
            "provider": settings.embedding_provider,
            "model": _embed_model_for(settings.embedding_provider),
            "dim": settings.embedding_dim,
        },
        "agent_runtime": settings.agent_runtime,
    }


def _model_for(provider: str | None) -> str | None:
    return {
        "ollama": settings.ollama_chat_model,
        "anthropic": settings.anthropic_chat_model,
        "openai": settings.openai_chat_model,
        "echo": "echo-1",
    }.get(provider or "")


def _embed_model_for(provider: str) -> str:
    return {
        "ollama": settings.ollama_embedding_model,
        "openai": settings.openai_embedding_model,
        "hash": "hash-bow",
    }.get(provider, "unknown")


async def provider_health() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        out["chat"] = await get_chat_provider().health()
    except ChatProviderError as exc:
        out["chat"] = {"ok": False, "error": str(exc)}
    try:
        out["embedding"] = await get_embedder().health()
    except ChatProviderError as exc:
        out["embedding"] = {"ok": False, "error": str(exc)}
    return out
