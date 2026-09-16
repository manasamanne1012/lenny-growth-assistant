"""Claude Agent SDK runtime (optional, cloud-only).

Enabled with `AGENT_RUNTIME=claude_sdk` and an `ANTHROPIC_API_KEY`. The SDK owns
the tool loop and the conversation state; our skills are exposed to it as
in-process SDK tools, so the same three skills back both runtimes.

Why this is not the default: the demo the assignment asks for runs on Ollama,
and the Agent SDK drives Claude specifically. Making the SDK the only runtime
would mean the mandatory local demo could not use the agent layer at all. The
native loop in `orchestrator.py` is therefore the default and the SDK runtime is
the cloud path. ADR-005 records the reasoning in full.

The import is guarded: if `claude-agent-sdk` is not installed, selecting this
runtime produces a clear startup error rather than an import crash.
"""

from __future__ import annotations

from typing import Any

from app.obs import get_logger

log = get_logger("agent.claude_sdk")

_IMPORT_ERROR: str | None = None

try:  # pragma: no cover - exercised only when the extra is installed
    from claude_agent_sdk import (  # type: ignore
        ClaudeAgentOptions,
        ClaudeSDKClient,
        create_sdk_mcp_server,
        tool,
    )

    SDK_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    SDK_AVAILABLE = False
    _IMPORT_ERROR = str(exc)


def availability() -> dict[str, Any]:
    return {
        "available": SDK_AVAILABLE,
        "error": _IMPORT_ERROR,
        "install": "pip install 'claude-agent-sdk>=0.1.0'",
    }


def build_server(handlers: dict[str, Any]):
    """Wrap our skill handlers as SDK tools.

    `handlers` maps tool name -> async callable(args) -> str, supplied by the
    orchestrator so the SDK path and the native path execute identical code.
    """
    if not SDK_AVAILABLE:
        raise RuntimeError(
            "AGENT_RUNTIME=claude_sdk but claude-agent-sdk is not installed. "
            "Run: pip install 'claude-agent-sdk>=0.1.0', or set AGENT_RUNTIME=native."
        )

    @tool(
        "search_transcripts",
        "Search Lenny's Podcast transcripts for relevant excerpts.",
        {"query": str},
    )
    async def search_transcripts(args):  # pragma: no cover
        text = await handlers["search_transcripts"](args)
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "write_ship30_essay",
        "Write a Ship 30 for 30-style essay grounded in the transcripts.",
        {"topic": str},
    )
    async def write_ship30_essay(args):  # pragma: no cover
        text = await handlers["write_ship30_essay"](args)
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "create_artifact",
        "Create a Markdown or HTML artifact rendered in the app viewer.",
        {"request": str, "kind": str},
    )
    async def create_artifact(args):  # pragma: no cover
        text = await handlers["create_artifact"](args)
        return {"content": [{"type": "text", "text": text}]}

    return create_sdk_mcp_server(
        name="lenny-skills",
        version="1.0.0",
        tools=[search_transcripts, write_ship30_essay, create_artifact],
    )


async def run(prompt: str, system: str, handlers: dict[str, Any]) -> str:  # pragma: no cover
    """Single turn through the SDK. Returns the assistant's final text."""
    server = build_server(handlers)
    options = ClaudeAgentOptions(
        system_prompt=system,
        mcp_servers={"lenny": server},
        allowed_tools=[
            "mcp__lenny__search_transcripts",
            "mcp__lenny__write_ship30_essay",
            "mcp__lenny__create_artifact",
        ],
        max_turns=4,
    )
    chunks: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
    return "".join(chunks)
