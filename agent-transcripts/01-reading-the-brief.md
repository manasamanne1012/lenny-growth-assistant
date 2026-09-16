# 01 — Reading the brief, and the three requirements that conflict

## What happened

The assignment arrived as a `.docx`. First action was to convert it with pandoc and read it in full rather than skim it, because the interesting content in a brief like this is usually in the constraints, not the feature list.

## What the pass turned up

Most of the brief has one obvious implementation. Three things did not:

**Conflict 1 — "Use the Claude Agent SDK" + "Ollama local model is mandatory for the demo."**
The SDK orchestrates Anthropic models through Anthropic's API. It does not drive an Ollama endpoint. These two requirements cannot both be satisfied by a single code path. Resolved in log 03.

**Conflict 2 — "Ship 30 for 30 style" + "approximately 1,250 words."**
Ship 30's atomic essay is ~250 words, and that constraint *is* the method. Resolved in log 05.

**Conflict 3 — "Render untrusted HTML artifacts" + "Claude-Artifacts-like."**
Claude's artifacts are interactive, which means scripts run. Sanitizing scripts away gives up the feature; not sanitizing gives up the origin. Resolved in log 06.

## The decision that came out of this

Treat each conflict as a product decision to be **documented with a rationale**, not as an ambiguity to be quietly resolved in whichever direction was easiest to build.

The reasoning: this is a *forward deployed engineer* brief. The job being tested is not "can you build a RAG app" — it is "what do you do when the client's requirements contradict each other." An engineer who silently picks one and ships it has failed the actual test, even with working code. An engineer who stops and asks has failed differently, because the take-home has no client to ask.

So: pick a position, implement it, write down why, and state the conditions under which the other choice would be right. That is what the ADRs and the PRD scope notes are for.

## Rejected approach

Starting to write code first and discovering the conflicts during implementation. Tempting under time pressure, and it is how the SDK/Ollama conflict in particular would have surfaced two-thirds of the way in, after the agent layer was already written against one assumption.
