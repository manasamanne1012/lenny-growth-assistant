# ADR-005 — Two agent runtimes behind one tool schema

**Status:** Accepted · **Date:** 2026-09 · **Affects:** `agent/tools.py`, `agent/orchestrator.py`, `agent/claude_sdk_runtime.py`

## Context

The brief contains two requirements that pull against each other:

1. Use the **Anthropic Claude Agent SDK** (or Pi Coding Agent) for the agent layer.
2. Demonstrate a **local model via Ollama**, mandatory for the demo.

The Claude Agent SDK orchestrates Claude models through Anthropic's API. It does not drive an Ollama endpoint. Implementing only the SDK path would mean the mandatory local demo could not run; implementing only a local loop would ignore an explicit requirement.

## Decision

Define the tool contract once, provider-neutrally, and give it two runtimes.

- **`tools.py`** — tool definitions as JSON Schema, plus their implementations (`search_transcripts`, `fetch_chunk`, `list_episodes`). No SDK types leak into this module.
- **`native`** (default) — an in-repo tool loop bounded by `MAX_TOOL_ITERATIONS`, driving whatever the registry returns: Ollama, Anthropic, OpenAI, or the offline `echo` stub. This is the path the demo and the test suite use.
- **`claude_sdk`** — the same tools registered via `@tool` and `create_sdk_mcp_server`, executed through `ClaudeSDKClient`. Cloud only. The import is guarded, so `claude-agent-sdk` is an optional dependency and its absence produces a clear configuration error rather than an import crash at boot.

Selected by `AGENT_RUNTIME`, like every other provider choice.

## Alternatives considered

**SDK only.** Rejected: breaks the mandatory local-model demo.

**Native only.** Rejected: ignores a stated requirement, and the SDK genuinely offers things the native loop does not (managed context compaction, richer permission hooks, session forking).

**An adapter layer trying to make Ollama look like the SDK's transport.** Rejected: a large amount of fragile code impersonating an interface I do not control, to reach a capability the native loop already provides honestly. The failure modes would be mine to own and impossible to explain.

## Consequences

- Both requirements are met without compromising either.
- Tool logic is written and tested once; runtimes are thin.
- `claude-agent-sdk` stays an optional install, listed and commented in `requirements-dev.txt`.
- Two code paths to maintain. Contained by keeping all real behaviour in `tools.py` and the skills.
- The SDK path is only exercisable with an API key, so CI covers the native path. Stated plainly rather than papered over.

## Revisit when

The SDK supports non-Anthropic model endpoints, at which point the native loop can retire; or when SDK-specific features (subagents, context compaction) become load-bearing for the product, at which point the SDK becomes the default and the native loop is kept solely for local operation.
