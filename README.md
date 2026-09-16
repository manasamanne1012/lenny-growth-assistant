# The Lenny Growth Assistant

A conversational assistant over the [Lenny's Podcast transcript archive](https://github.com/ChatPRD/lennys-podcast-transcripts). It answers growth and product questions from what guests actually said, shows you which episode every claim came from, writes Ship 30 for 30 style essays, and builds sandboxed artifacts you can read side by side with the conversation.

It also refuses to answer things the archive does not cover. That refusal is the feature this repository is built around.

---

## The thirty-second version

```bash
git clone <this-repo> && cd lenny-growth-assistant
cp .env.example .env
make up                       # postgres + backend + frontend
make doctor                   # tells you exactly what is missing, if anything
make fetch-transcripts        # clone the corpus
make ingest LIMIT=25          # index a subset; drop LIMIT for the full archive
open http://localhost:5173
```

No transcripts, no network, no Ollama? `make demo-seed` indexes three bundled sample episodes so the app is usable immediately.

**Prerequisites:** Docker Desktop, and [Ollama](https://ollama.com) on the host for the local-model path:

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

---

## What it does

| | |
|---|---|
| **Grounded Q&A** | Answers are assembled only from retrieved transcript passages, with inline `[S1]` markers that expand into the episode, guest, and timestamp they came from. Follow-up questions inherit the session's context. |
| **Abstention** | When retrieval comes back thin, the assistant says so instead of filling the gap. Ask it about a Lenny's episode that does not exist and it will tell you it cannot find one. |
| **Ship 30 essays** | A first-class skill, not a prompt: a machine-checkable rubric, a draft, a deterministic score, and one targeted revision against the specific rules the draft missed. |
| **Artifacts** | Markdown and HTML documents render in an in-app viewer with script isolation and a visible report of what the sanitizer stripped. |
| **Provider switching** | Cloud (Anthropic / OpenAI) and local (Ollama) are one environment variable apart. The badge in the UI reads the live value, so the screen always tells the truth about which model answered. |
| **Per-turn traces** | Every answer carries "How this answer was built" — routing decision, retrieval scores, span timings, token counts. |

---

## The decisions worth defending

Most of this brief has one obvious implementation. These are the places where it did not, and where the choice says something.

### 1. The system is allowed to say no, and that is measured

A retrieval assistant that always produces an answer is not trustworthy; it is just fluent. Every answer passes a grounding gate before it is returned: if the best fused retrieval score is below `MIN_GROUNDING_SCORE`, the skill abstains rather than paraphrasing whatever the index happened to return.

The hard part is that abstention is easy to over-apply. So both directions are measured. `make eval` runs a golden set and reports:

- **abstention accuracy** — did it refuse the questions it should have refused?
- **over-refusal rate** — did it refuse anything it should have answered?

The golden set includes a fabricated episode ("the one where Genghis Khan explains B2B pricing") precisely because that is the failure a demo will never surface and a user will find in week one.

Tuning `MIN_GROUNDING_SCORE` without running `make eval` afterwards is how this system regresses. That is written in `.env.example` next to the knob.

### 2. Hybrid retrieval, fused by rank, with no tuned weights

Vector search alone misses exact terms — a guest's name, "PLG", "NPS", a specific company. Keyword search alone misses paraphrase, which is most of how people actually ask questions. So both run, and results are combined with **Reciprocal Rank Fusion** in a single SQL statement (pgvector cosine + Postgres full-text, `repository.hybrid_search`).

RRF was chosen over a weighted score blend on purpose: blending requires a weight, a weight requires tuning data, and tuning data for this corpus does not exist. RRF only needs rank positions, so there is no magic number quietly encoding my guesses. A cross-encoder reranker would likely beat it — and would also add a second model to the local-first setup the brief requires. That trade is written up in `docs/decisions/ADR-003.md`.

If the embedding service is unreachable, retrieval degrades to lexical-only and the trace says `degraded: true` rather than the app failing.

### 3. Ship 30 is a skill with a validator, not a long prompt

Anyone can put "write in Ship 30 style" in a system prompt and hope. Here the style is encoded as `SHIP30_RUBRIC` — word band, hook length cap, H2 count, bulleted blocks, bold phrase range, average sentence length, citation coverage, explicit takeaway — and `score_essay()` checks it as a pure function with no model and no network.

The loop is: draft → score → if it failed, send back *only the specific failures* → rescore. **The revision is kept only if it has strictly fewer failures than the draft.** Models often "improve" writing by flattening it; this guards against a revision that fixes one rule and breaks two.

The rubric report is shown in the Inspector, so you can see which rules the essay passed rather than taking my word for it.

> **A scope note I want to be explicit about.** Ship 30 for 30's canonical atomic essay is ~250 words. The brief asks for ~1,250. Rather than stretch a 250-word form five times its natural length, the skill treats the deliverable as **four to six stacked atomic beats under one thesis** — each beat keeping the atomic discipline (one idea, hook, payoff) while the whole reads as one essay. The rubric enforces that structure. `docs/PRD.md` records the reasoning; if the real preference is five separate 250-word essays, that is a change to `SHIP30_RUBRIC`, not to the code.

### 4. Artifacts are treated as untrusted input, because they are

Model-generated HTML rendered in the app's own origin is a stored-XSS primitive with extra steps. The defences are layered and documented as a threat model in `docs/design.md`:

1. **Server-side sanitizer** (allowlist, not blocklist) before anything reaches the database: `iframe`, `object`, `embed`, `form`, `base`, `meta refresh`, every `on*` handler, `javascript:` URLs, and remote script sources are removed.
2. **`sandbox="allow-scripts"` with no `allow-same-origin`.** That pairing gives the frame an opaque origin: no cookies, no storage, no parent DOM, no same-origin fetches. Inline scripts *are* allowed to run, because interactive artifacts are the point — the sandbox, not the sanitizer, is the security boundary.
3. **`Content-Security-Policy: default-src 'none'`** with no `connect-src`, so an artifact cannot exfiltrate anything even if it executes.
4. **A visible "What the viewer blocked" panel.** A security control the user cannot see is a control they cannot trust.

`ALLOW_ARTIFACT_SCRIPTS=false` drops interactivity for a smaller blast radius, in one environment variable.

### 5. Observability is for the user, not just the operator

Structured logs with trace ids exist. But the trace is also attached to each message and rendered on demand in the UI, so "why was this slow" and "why did it say that" are answerable with a click instead of a grep. Errors surface the backend's `hint` field and the trace id rather than a generic apology.

### 6. `make doctor` before anything else

The failure modes of a local-first RAG stack are boring and predictable: Ollama is not running, the model was never pulled, `EMBEDDING_DIM` no longer matches the vector column, the index is empty. `make doctor` checks each one and prints the exact command to fix it. The time it saves on a fresh machine is the whole reason it exists.

---

## Architecture

```
┌──────────────────────────────┐
│  React + TypeScript (Vite)   │  session rail · conversation · panel
│  provenance rail · inspector │  artifact viewer (sandboxed iframe)
└───────────────┬──────────────┘
                │  /api  (JSON + SSE)
┌───────────────▼──────────────┐
│  FastAPI                     │
│  ├─ router    deterministic rules → LLM classifier only when ambiguous
│  ├─ skills    grounded_qa · ship30_essay · artifact
│  ├─ tools     provider-neutral JSON Schema, shared by both runtimes
│  └─ runtimes  native tool loop  |  Claude Agent SDK
└───────┬───────────────┬──────┘
        │               │
┌───────▼──────┐  ┌─────▼──────────────────────────┐
│ LLM registry │  │ PostgreSQL 16 + pgvector       │
│ ollama       │  │ sessions · messages · chunks   │
│ anthropic    │  │ artifacts · transcripts        │
│ openai       │  │ hybrid search (vector + FTS,   │
│ echo (tests) │  │ fused with RRF in one query)   │
└──────────────┘  └────────────────────────────────┘
```

Full detail in [`docs/architecture.md`](docs/architecture.md). Product reasoning in [`docs/PRD.md`](docs/PRD.md). Interface and threat model in [`docs/design.md`](docs/design.md). Individual trade-offs in [`docs/decisions/`](docs/decisions/).

---

## Switching models

Both required paths are one edit away. Nothing else changes.

**Local (required for the demo):**
```env
CHAT_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
EMBEDDING_DIM=768
```

**Cloud:**
```env
CHAT_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Then `make restart`. The badge in the UI updates from `/api/config`.

Changing the *embedding* model changes the vector width, and Postgres will not accept that silently:

```bash
make resize-embeddings DIM=1536
make ingest FORCE=1
```

The agent runtime switches the same way: `AGENT_RUNTIME=claude_sdk` uses the Anthropic Claude Agent SDK (cloud only, `pip install claude-agent-sdk`); `native` is the in-repo tool loop that works with every provider including Ollama, which is why it is the default. Both call the same tool definitions. See [`ADR-005`](docs/decisions/ADR-005-agent-runtime.md).

---

## Testing

```bash
make test      # unit suite — offline providers, no network, no database
make eval      # golden set: pass rate, abstention accuracy, over-refusal, latency
make lint
```

The unit suite runs against `CHAT_PROVIDER=echo` and `EMBEDDING_PROVIDER=hash`, deterministic stubs that make the parts most likely to break silently — chunking, routing, sanitization, grounding verdicts, the API contract — testable in seconds without a key or a GPU. Each sanitizer test names the attack it prevents.

Manual UI coverage, including the cases automation should not be trusted with, is in [`docs/manual-test-plan.md`](docs/manual-test-plan.md).

---

## Repository layout

```
backend/
  app/
    agent/        router, orchestrator, tools, two runtimes, skills/
    rag/          parser, chunker, retriever, ingest
    llm/          provider adapters + registry
    db/           engine, bootstrap migrations, all SQL in repository.py
    security/     HTML sanitizer
    api/          routes, structured errors
    obs/          structured logging, per-turn traces
  evals/          golden_set.yaml + harness
  migrations/     SQL schema
  scripts/        doctor, fetch-transcripts, resize-embeddings
  tests/
  data/sample_transcripts/   works with no network
frontend/src/     components, lib, one hand-written stylesheet
docs/             PRD · design · architecture · handoff · manual test plan · ADRs
agent-transcripts/  how this was built, including what failed
```

---

## Known limits

Stated plainly, because the useful version of this section is the honest one.

- **Local 8B models are the quality ceiling here.** `llama3.1:8b` follows the citation contract most of the time; cloud models follow it nearly always. The grounding verdict is computed from what the model *actually produced*, so when a local model ignores its instructions the UI says "Not cited" rather than hiding it.
- **Full-corpus ingestion on a local embedding model takes a while** (tens of minutes, CPU-dependent). `make ingest LIMIT=25` exists for this reason.
- **Retrieval is fused ranks, not a reranker.** Good enough to be honest about; a cross-encoder would improve precision at the cost of a second local model.
- **Sessions are not authenticated.** Single-user local tool, `user_id` is a stub. Multi-tenancy would need auth, per-user filtering, and row-level policies — out of scope, noted in the PRD.
- **Streaming covers the Q&A path only.** Essays and artifacts return in one response, because a half-written essay that fails its rubric and gets revised would be actively confusing to watch.
- **Title generation costs one extra model call** on the first turn of a session.

---

## Where everything is

| Deliverable | Location |
|---|---|
| Product requirements | [`docs/PRD.md`](docs/PRD.md) |
| Design + artifact threat model | [`docs/design.md`](docs/design.md) |
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| Decision records | [`docs/decisions/`](docs/decisions/) |
| Handoff notes | [`docs/handoff.md`](docs/handoff.md) |
| Manual UI test plan | [`docs/manual-test-plan.md`](docs/manual-test-plan.md) |
| Build transcripts, including what failed | [`agent-transcripts/`](agent-transcripts/) |
| Automated tests | `backend/tests/`, `make test` |
| Evaluation harness | `backend/evals/`, `make eval` |

---

## License

MIT.
