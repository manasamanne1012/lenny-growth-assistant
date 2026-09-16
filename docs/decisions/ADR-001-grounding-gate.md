# ADR-001 — Abstain below a grounding threshold, and measure over-refusal

**Status:** Accepted · **Date:** 2026-09 · **Affects:** `rag/retriever.py`, `agent/skills/qa.py`, `evals/`

## Context

The brief asks for grounded answers with citations and for the assistant to say when it does not know. That second half is easy to write into a system prompt and almost never actually happens: given retrieved passages that are merely *adjacent* to the question, a model will produce a fluent answer and attach the nearest citations to it. The result reads as grounded and is not.

This is the specific failure that destroys trust in an archive assistant, because a user has no way to detect it without doing the work the tool was supposed to save.

## Decision

Abstention is enforced **before generation**, in code, not requested in a prompt.

1. Hybrid retrieval returns a fused top score.
2. The retriever grades sufficiency: `sufficient` / `thin` / `insufficient` against `MIN_GROUNDING_SCORE`.
3. `insufficient` short-circuits — the skill returns an abstention naming what it searched for, and no prose-generating model call is made.
4. `thin` proceeds but the prompt states the evidence is weak and instructs the model to say so.
5. After generation, the grounding verdict is computed from the `[S#]` markers the model **actually** emitted, matched against real chunks. Unmatched markers downgrade the verdict.

Both directions are measured. `evals/run_evals.py` reports **abstention accuracy** and **over-refusal rate** separately, because refusing everything scores perfectly on the first and is a useless product.

The threshold is `MIN_GROUNDING_SCORE`, a single env var, documented next to the instruction to re-run `make eval` after touching it.

## Alternatives considered

**Prompt-only instruction ("say I don't know if unsure").** Rejected: unreliable in general and markedly worse on local 8B models, which is exactly the configuration the demo requires. It also leaves nothing to measure.

**LLM-as-judge on the generated answer.** Rejected for the primary gate: doubles latency and cost per turn, and asks a model to audit a model. Viable as an offline eval signal later.

**Answer always, show a confidence score.** Rejected: pushes the judgement onto the user at precisely the moment they are least equipped to make it. A number next to a fluent paragraph is not a defence.

**Fixed similarity floor per query type.** Rejected as premature: no data yet to justify the extra complexity.

## Consequences

- Some answerable questions get refused. This is visible in the over-refusal metric rather than hidden.
- The threshold is corpus- and embedding-model-dependent. Changing the embedding model invalidates its calibration — noted in `.env.example` and caught by `make doctor`.
- The evaluation set carries real weight: it is how the gate is tuned. It is currently ten cases, which is enough to catch regressions and not enough to optimise against. Growing it is the first item in the PRD's "what next".

## Revisit when

The golden set exceeds ~50 cases (tune the threshold empirically per skill), or when over-refusal exceeds roughly 15% on in-scope questions.
