# 02 — Deciding what would make this not-generic

## The problem

The baseline submission for this brief is predictable: FastAPI, pgvector, a chat UI, citations underneath, a README with setup steps. It satisfies every stated requirement. It is also what most submissions will be, which means satisfying the requirements is table stakes rather than a differentiator.

So before writing code: what would a reviewer see here that they would not see in twenty other repos?

## Rejected differentiators

**More features.** Voice input, episode recommendations, a guest comparison mode, a Chrome extension. Rejected — breadth against a fixed deadline produces a demo where everything half-works, and the brief explicitly grades "product judgment", which includes knowing what not to build.

**A prettier UI.** Worth doing, but not a differentiator on its own; a good-looking chat interface is a weekend of taste, and reviewers of an engineering brief discount it fast.

**More models supported.** Adding Gemini, Mistral, Groq. Rejected — the registry already proves the abstraction with three real providers. A fourth demonstrates nothing new.

## What was chosen, and why each

Six things, chosen because each one answers a question a skeptical reviewer would actually ask:

1. **An eval harness with a golden set** (`make eval`), reporting abstention accuracy *and* over-refusal rate.
   → *"How do you know it works?"* Most submissions cannot answer this. Reporting both metrics is the part that matters: refusing everything scores perfectly on the first one.

2. **Hybrid retrieval fused by RRF, with no tuned weights.**
   → *"Why these numbers?"* The answer is that there are no invented numbers to defend. See log 04.

3. **The per-turn trace surfaced in the UI**, not just in logs.
   → *"Why did it say that?"* Answerable by the user with a click, not by an operator with grep.

4. **Ship 30 as a rubric + deterministic validator + bounded revision loop.**
   → *"Is this a skill or a long prompt?"* A pure scoring function with no model call is the difference.

5. **An artifact sandbox with a written threat model.**
   → *"Did you think about this, or did you sanitize and hope?"*

6. **`make doctor`.**
   → *"What happens when it breaks on my laptop?"* The failure modes of a local RAG stack are few and predictable; checking them by name costs an hour and saves the reviewer's first impression.

## The through-line

Five of the six are about **making the system's own reliability legible**. That is deliberate. The product's core promise is "you can trust this answer because you can check it." A repository that makes the same promise about itself — here is how it is measured, here is what it refuses, here is what it blocked, here is why it was slow — is arguing its thesis in its own structure.
