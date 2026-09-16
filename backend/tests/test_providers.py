"""Provider abstraction and configuration switching."""

import pytest

from app.llm import describe_providers, get_chat_provider, get_embedder
from app.llm.base import ChatMessage, ChatProviderError
from app.llm.offline import EchoProvider, HashEmbedder
from app.llm.registry import _build_chat


@pytest.mark.asyncio
async def test_echo_provider_satisfies_the_provider_contract():
    p = EchoProvider()
    result = await p.complete([ChatMessage(role="user", content="hello")])
    assert result.provider == "echo"
    assert result.text
    assert "input_tokens" in result.usage


@pytest.mark.asyncio
async def test_streaming_reassembles_to_the_same_text():
    p = EchoProvider()
    full = (await p.complete([ChatMessage(role="user", content="hi")])).text
    streamed = "".join([c async for c in p.stream([ChatMessage(role="user", content="hi")])])
    assert streamed.strip() == full.strip()


@pytest.mark.asyncio
async def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder(dim=64)
    a = (await e.embed(["product market fit"]))[0]
    b = (await e.embed(["product market fit"]))[0]
    assert a == b
    assert abs(sum(v * v for v in a) ** 0.5 - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_different_text_produces_different_vectors():
    e = HashEmbedder(dim=128)
    a, b = await e.embed(["onboarding activation", "enterprise pricing"])
    assert a != b


def test_unknown_provider_fails_loudly_rather_than_silently():
    with pytest.raises(ChatProviderError):
        _build_chat("not-a-real-provider")


def test_anthropic_without_a_key_raises_a_configuration_error(monkeypatch):
    monkeypatch.setattr("app.config.settings.anthropic_api_key", None)
    with pytest.raises(ChatProviderError) as exc:
        _build_chat("anthropic")
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_describe_providers_reports_everything_the_ui_badge_needs():
    info = describe_providers()
    assert set(info) >= {"chat", "embedding", "agent_runtime"}
    assert "provider" in info["chat"] and "model" in info["chat"]
    assert "is_local" in info["chat"]


def test_providers_are_cached_so_clients_are_reused():
    assert get_chat_provider() is get_chat_provider()
    assert get_embedder() is get_embedder()


@pytest.mark.asyncio
async def test_health_never_raises_even_when_the_backend_is_down():
    from app.llm.ollama_provider import OllamaProvider

    p = OllamaProvider(base_url="http://127.0.0.1:1", model="nope")
    health = await p.health()
    assert health["ok"] is False
    assert health["hint"]
