# Product Requirements — The Lenny Growth Assistant

> This is written as a forward-deployment discovery brief, not as a feature list. The brief I was given describes a system; the job of this document is to work out what problem that system solves, who has it, and which parts of the described system actually matter for solving it.

---

## 1. Who this is for

**Primary user: a growth or product lead at a Series A–C company, three to eighteen months into the role.**

They have a specific, recurring problem. They face a decision — pricing model, activation funnel, when to add a sales motion, how to know if they have product-market fit — and they know that somewhere in a few hundred hours of Lenny's Podcast, four or five operators have already lived through exactly that decision. They cannot get to it. The archive is long-form spoken audio; search is either YouTube's transcript box or memory.

What they do instead: ask a general-purpose LLM, get a confident, plausible, uncited synthesis of Twitter-grade product advice, and have no way to tell which parts came from an operator who shipped it and which parts the model made up.

**Secondary user: a content marketer** who needs to turn what the archive says about a topic into publishable writing without misattributing a claim to a guest who never made it.

## 2. The problem, stated precisely

> A practitioner cannot get a trustworthy, attributable answer out of a large spoken archive fast enough for it to affect a decision they are making this week.

Three words in that sentence are doing the work:

- **Trustworthy** — the answer must be checkable. An uncited answer from an archive assistant is strictly worse than no answer, because it carries borrowed authority it has not earned.
- **Attributable** — down to the episode and the guest. "Several founders say" is not usable in a strategy document.
- **Fast enough** — if verifying the answer takes longer than skimming two episodes, the tool has not saved anything.

## 3. Success metric

**Primary:** the proportion of answers a user accepts without opening the source to check — measured against a baseline where they do check, so that acceptance reflects earned trust rather than laziness.

That is not measurable inside a take-home. The proxy shipped here:

| Metric | Where | Why it stands in |
|---|---|---|
| Citation coverage | grounding verdict, per turn | An uncitable answer cannot be trusted; the UI shows the verdict even when it is bad |
| Abstention accuracy | `make eval` | Refusing the unanswerable is what makes the answerable believable |
| Over-refusal rate | `make eval` | Measured because the cheap way to score well on abstention is to refuse everything |
| Time to first answer | per-turn trace | A correct answer arriving after the meeting is not an answer |

The pairing of abstention accuracy with over-refusal rate is the important part. Either number alone is trivially gameable; together they describe calibration.

## 4. Assumptions, and what breaks if they are wrong

| Assumption | If wrong |
|---|---|
| Users care more about attribution than fluency | The provenance rail is visual noise; simplify to a source list |
| The corpus is the whole world of the answer | Abstention frustrates rather than reassures; we would need to say "not in the archive, but generally…" behind a clear label |
| Transcripts are reasonably clean Markdown | The parser already degrades (front-matter → H1 → filename) and records warnings, but chunk quality drops |
| One user per deployment | Sessions need auth and per-user isolation; currently `user_id` is a stub |
| Speaker turns are a good chunk boundary | Chunking would need a semantic splitter; the chunker is isolated so this is a contained change |

## 5. Scope

### In

1. **Grounded conversational Q&A** with per-claim citations, multi-turn follow-ups, and explicit abstention.
2. **Ship 30 for 30 essay generation** as a rubric-validated skill.
3. **Artifact generation and an in-app viewer** with documented isolation.
4. **Session persistence** in PostgreSQL with independent context per session.
5. **Provider switching** between cloud and local without code changes, visible in the UI.
6. **A knowledge pipeline** — ingest, chunk, index, incremental refresh, traceability from answer to source file.
7. **An evaluation harness** over a golden set.
8. **One-command startup**, preflight diagnostics, structured errors, per-turn traces.

### Out, deliberately

| Not doing | Why |
|---|---|
| Authentication / multi-tenancy | Single-user local tool. Adding auth would consume time better spent on grounding quality, and stub it badly. |
| Audio playback or timestamp deep-links | Timestamps are captured and displayed; linking to the episode at the second requires per-episode video IDs the corpus does not reliably carry. High value, clean follow-up. |
| Cross-encoder reranking | Second local model for a precision gain I cannot yet measure. Revisit when the eval set is large enough to show the gap. ADR-003. |
| Agentic web search beyond the archive | Directly undermines the core promise. The value is that answers come *only* from the archive. |
| Streaming for essays and artifacts | Watching a draft get revised against a rubric is confusing, not reassuring. |
| Fine-tuning | No training data, no need; the failure mode here is retrieval, not style. |

## 6. Key product decisions

### 6.1 Abstention is a feature, and it is measured in both directions

The default behaviour of every RAG demo is to answer. The default behaviour of this one is to answer *if it can show its work*. Below `MIN_GROUNDING_SCORE` the skill abstains and says what it searched for.

This is the decision most likely to be argued with, so it is instrumented rather than asserted: the golden set contains out-of-scope cases (a medical dosage question, a question about a future event, and a question about a fabricated episode) alongside in-scope ones, and the harness reports refusal accuracy and over-refusal separately.

### 6.2 The Ship 30 word-count conflict

Ship 30 for 30's atomic essay is ~250 words by design — that constraint *is* the method. The brief specifies ~1,250.

**Decision:** treat the deliverable as **four to six stacked atomic beats under a single thesis**. Each beat keeps atomic discipline (one idea, its own hook, its own payoff); the whole reads as one essay with one takeaway. `SHIP30_RUBRIC` enforces the structure — H2 count, hook length cap, bulleted blocks, bold phrase band, average sentence length, citation coverage, explicit takeaway.

**Alternative considered:** generate five separate 250-word essays. Rejected because the brief asks for "an essay", and a bundle of five is a different artifact.

This is exactly the kind of ambiguity that, in a real deployment, is a two-minute conversation with the client. It is recorded here so that conversation starts from a position rather than from a blank page. Changing the answer is an edit to a dict, not to the code.

### 6.3 Show the grounding verdict even when it is bad

The verdict is computed from what the model actually produced, not from what it was told to produce. When a local 8B model ignores the citation contract, the UI says "Not cited — treat with caution."

The tempting alternative is to suppress or retry such answers. That would make the product feel better and be less trustworthy. A user who once sees the assistant admit an answer is weak will believe it the next time it says an answer is strong.

### 6.4 Provider state is read live, never cached in the client

"Which model answered this?" must never be a guess. The badge reads `/api/config`, health is re-probed on an interval, and each stored message records the provider and model that produced it — including whether a fallback was used.

## 7. Core flows

### 7.1 Ask a grounded question
1. User types a question. The router classifies it — deterministic rules first, LLM classifier only for genuinely ambiguous input.
2. Follow-ups are expanded with the previous user turn so that "what about for B2B?" retrieves usefully.
3. Hybrid retrieval returns fused candidates; sufficiency is graded `sufficient` / `thin` / `insufficient`.
4. If insufficient → abstain, naming what was searched.
5. Otherwise the model answers from a numbered context block and cites `[S#]`.
6. The UI renders the answer, the provenance rail, and a trace.

**Acceptance:** an in-scope question returns ≥1 citation resolving to a real transcript file; an out-of-scope question returns an abstention with no fabricated episode name.

### 7.2 Write a Ship 30 essay
1. User picks the Essay skill or asks for an essay.
2. Retrieval gathers grounding material.
3. Draft → `score_essay()` → if failures, one targeted revision naming only those failures → rescore.
4. The revision is kept **only** if it has strictly fewer failures.
5. The essay is stored as an artifact; the rubric report is shown in the Inspector.

**Acceptance:** output lands in the word band, carries a takeaway, and every major claim is traceable. The report is visible whether or not it passed.

### 7.3 Generate and view an artifact
1. User asks for a document, checklist, or interactive summary.
2. The model produces Markdown or HTML; HTML passes the server-side allowlist sanitizer before storage.
3. The viewer renders HTML in a sandboxed, opaque-origin iframe under `default-src 'none'`.
4. The "what was blocked" panel is always visible.

**Acceptance:** an artifact containing `<script>alert(1)</script>`, an `onerror` handler, and a remote script tag renders with the inline script confined to the sandbox, the handler stripped, the remote source blocked, and all three listed in the panel.

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Model fabricates a citation marker | High | Verdict computed from actual markers; unmatched markers downgrade the verdict |
| Local model too slow to demo | Medium | `LIMIT` on ingest, streaming on the Q&A path, honest latency in the trace |
| Embedding dim drift after model change | Medium | Startup warns; `make doctor` catches it; `make resize-embeddings` fixes it |
| Over-refusal makes the tool feel useless | Medium | Measured explicitly; gate is a single tunable env var |
| Artifact XSS | High | Four layers, threat-modelled in `docs/design.md`, tested per-attack |
| Corpus format changes upstream | Low | Forgiving parser, per-file failure isolation, warnings surfaced in the ingest report |

## 9. What I would build next

In order, if this continued past the take-home:

1. **Timestamp deep-links to the episode video.** The single largest trust multiplier available, and cheap once episode IDs are mapped.
2. **Grow the golden set to ~60 cases**, with a held-out slice, so retrieval changes can be judged rather than argued.
3. **Cross-encoder reranking**, evaluated against that set rather than adopted on faith.
4. **A "compare guests" mode** — the question practitioners actually ask is not "what is the answer" but "who disagrees, and why".
5. **Auth and per-user isolation**, at the point this stops being a single-user tool.
