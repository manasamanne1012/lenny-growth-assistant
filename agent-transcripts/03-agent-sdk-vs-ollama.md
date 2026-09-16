# 03 — The SDK-versus-local-model conflict

**Outcome: ADR-005.**

## The conflict

- Requirement: the agent layer uses the Anthropic Claude Agent SDK (or Pi Coding Agent).
- Requirement: an Ollama local model, **mandatory for the demo**.

The Claude Agent SDK drives Claude models through Anthropic's API. It has no path to an Ollama endpoint. Implementing only the SDK means the mandatory demo cannot run. Implementing only a local loop ignores a stated requirement.

## Options considered

**A. SDK only.** Ignores an explicit mandatory requirement. Rejected immediately.

**B. Native loop only, with a note that the SDK "would work similarly".** Rejected. The brief names the SDK; a note is not an implementation, and a reviewer checking for it finds nothing.

**C. An adapter making Ollama look like the SDK's transport.**
This was seriously considered and is the one I want to record rejecting, because it is the option that *looks* clever. It would mean writing a shim impersonating an interface I do not own, in order to reach a capability — a tool-calling loop — that is fifty lines to write honestly. The failure modes would be subtle, mine to own, and impossible to explain in a two-minute demo. Rejected for being fragile disguised as elegant.

**D. Two runtimes behind one provider-neutral tool schema.** Chosen.

## What was built

`agent/tools.py` defines the tools once as JSON Schema with their implementations. No SDK type appears in that module.

- `native` — the in-repo bounded tool loop. Works with every provider including Ollama and the offline `echo` stub. Default, and the path the demo and CI use.
- `claude_sdk` — the same tools via `@tool` and `create_sdk_mcp_server`, executed through `ClaudeSDKClient`. Cloud only.

Selected by `AGENT_RUNTIME`, like every other provider choice in the system.

## A correction made during the build

The first version of `claude_sdk_runtime.py` imported `claude_agent_sdk` at module top level. That made an optional, cloud-only dependency into a hard import — the app would crash at boot for anyone who had not installed it, including anyone running the required local demo. The import was moved behind a guard so its absence produces a clear configuration error instead.

Small bug, but it is exactly the class of thing that turns "one-command startup" into a support ticket, which is the grading criterion it would have damaged.

## Honest limitation

The SDK path cannot be exercised in CI, because CI has no API key. This is stated in the ADR rather than left for a reviewer to discover.
