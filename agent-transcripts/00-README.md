# Agent transcripts

The brief asks for these, including the attempts that failed. This folder is that record.

## What this is

This system was built in an AI-assisted session — a coding agent with filesystem and shell access, working from the assignment document. The logs below are a curated record of that session: the decisions, the reversals, the things that were built and then deleted, and the constraints that shaped the result.

## What I want to be straight about

Two things a reader deserves to know up front:

1. **These are curated, not raw.** A verbatim dump of a multi-hour agent session is thousands of lines of file writes and syntax checks. What is here are the moments where something was actually decided or actually went wrong. Where I have compressed, I have said so.

2. **The environment had no network access.** This is the largest single caveat on the whole repository and it is stated in the README too. The agent could not `pip install`, could not `npm install`, could not start Postgres, and could not run a single test. Every Python file passes `py_compile` and the design is internally consistent, but **"compiles" is not "works."** The verification steps in `08-verification-gap.md` are what closes that gap, and they were run by a human on real hardware, not by the agent.

Presenting AI-assisted work as if a human typed every line would be dishonest. Presenting it as if the AI verified work it demonstrably could not verify would be worse.

## The logs

| | |
|---|---|
| [01](01-reading-the-brief.md) | Reading the brief, and the three requirements that conflict |
| [02](02-differentiation-strategy.md) | Deciding what would make this not-generic |
| [03](03-agent-sdk-vs-ollama.md) | The SDK-versus-local-model conflict, and the two-runtime resolution |
| [04](04-retrieval-rejected-weights.md) | A weighted hybrid scorer, written and then deleted |
| [05](05-ship30-word-count.md) | The 250-word / 1,250-word contradiction |
| [06](06-artifact-sandbox-reversal.md) | Stripping scripts, then deciding that was the wrong boundary |
| [07](07-design-rejected-directions.md) | Two visual directions discarded before the third |
| [08](08-verification-gap.md) | What could not be tested, and what was done about it |
