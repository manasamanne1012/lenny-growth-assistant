# Architecture

---

## 1. Shape of the system

```
Browser
  │  React 18 + TypeScript (Vite), one hand-written stylesheet
  │  · session rail   · conversation + provenance rail
  │  · artifact viewer (sandboxed iframe)   · trace inspector
  ▼  /api  — JSON, plus SSE on the streaming Q&A path
FastAPI  (app/main.py)
  │  trace middleware → X-Trace-Id, X-Response-Time-Ms on every response
  │
  ├── app/api/         routes + a single structured error envelope
  ├── app/agent/
  │     router.py        deterministic rules → LLM classifier only if ambiguous
  │     orchestrator.py  route → retrieve → skill → assemble → persist
  │     tools.py         provider-neutral JSON Schema tool definitions
  │     skills/          grounded_qa · ship30_essay · artifact
  │     claude_sdk_runtime.py   optional Claude Agent SDK runtime
  ├── app/rag/         parser → chunker → embed → retriever
  ├── app/llm/         ollama · anthropic · openai · echo  +  registry
  ├── app/security/    HTML allowlist sanitizer
  ├── app/db/          engine · bootstrap migrations · repository (all SQL)
  └── app/obs/         structlog setup · per-turn Trace
         │
         ▼
PostgreSQL 16 + pgvector + pg_trgm
  sessions · messages · artifacts · transcripts · chunks · eval_runs
```

Three containers: `postgres`, `backend`, `frontend`. Ollama runs on the **host**, reached via `host.docker.internal`, because a containerised Ollama gets no GPU on macOS or Windows and the local-model demo would be unwatchable.

---

## 2. Request lifecycle — one grounded answer

```
POST /api/chat
  │
  1  new_trace()                     trace id bound to a contextvar for the turn
  2  session resolved or created     unknown session_id → new session, not a 404
  3  user message persisted          before the model runs, so a crash loses nothing
  4  route(message, history)         rules first; classifier only when ambiguous
  5  query expansion                 follow-ups get the prior user turn prepended
  6  retrieve()                      vector + FTS, fused by RRF, in one SQL statement
  7  sufficiency gate                insufficient → abstain, no model call for prose
  8  skill executes                  numbered [S#] context block → provider
  9  grounding verdict               computed from the markers actually emitted
 10  assistant message persisted     with citations, trace, provider, model, usage
 11  artifact sanitized + stored     if the skill produced one
 12  title generated                 first turn only
  ▼
ChatResponse { message, artifact, essay_report, route, notices, trace_id }
```

Each numbered step opens a named trace span. Those spans are what the Inspector renders.

---

## 3. Knowledge pipeline

### Ingestion (`app/rag/ingest.py`)

```
transcripts/*.md
  → parse    front-matter → H1 → filename fallback; warnings recorded, never fatal
  → hash     SHA-256 of content; unchanged files are skipped entirely
  → chunk    speaker-turn aware, ~700 tokens, whole-turn overlap, timestamps carried
  → embed    batched through the configured embedding provider
  → upsert   transcripts + chunks, transactionally per file
  → ANALYZE  so the planner sees the new distribution
```

**Incremental by content hash.** Re-running after adding twenty episodes re-embeds twenty episodes, not the archive. `--force` overrides.

**Per-file failure isolation.** One malformed transcript fails that file, records the reason in the report, and the run continues. An ingest of 400 files that aborts on file 7 is worse than useless.

**Speaker-turn chunking** rather than fixed windows. A transcript's natural semantic unit is a turn: one person answering one question. Overlap is whole turns, never mid-sentence, so a chunk never opens in the middle of someone's thought. Timestamps propagate to every chunk derived from a turn, which is what makes citations point at a moment rather than an episode.

### Retrieval (`app/rag/retriever.py`, `db/repository.hybrid_search`)

Two rankings, one SQL statement, fused by **Reciprocal Rank Fusion**:

```sql
WITH vec AS (   -- pgvector cosine, top N
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> :q) AS rank ...
), lex AS (     -- Postgres full-text, top N
  SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, query) DESC) AS rank ...
)
SELECT id, SUM(1.0 / (:rrf_k + rank)) AS score
FROM (vec UNION ALL lex) GROUP BY id ORDER BY score DESC LIMIT :k
```

Why RRF and not a weighted blend: a blend needs a weight, a weight needs labelled tuning data, and that data does not exist for this corpus. RRF needs only rank positions, so no fabricated constant is quietly encoding a guess. `RRF_K=60` is the paper's value and moves only with eval evidence. Full reasoning in [ADR-003](decisions/ADR-003-hybrid-retrieval.md).

**Sufficiency grading.** The retriever returns `sufficient` / `thin` / `insufficient` based on top fused score against `MIN_GROUNDING_SCORE`. `insufficient` short-circuits to abstention.

**Graceful degradation.** If the embedding service is unreachable, retrieval runs lexical-only and the trace records `degraded: true`. A keyword answer that says it is a keyword answer beats a 500.

---

## 4. Agent layer

### Routing

Deterministic regex rules run first ("write an essay", "make me a checklist"). Only genuinely ambiguous input reaches an LLM classifier. Rules are faster, free, testable, and — on a local 8B model — more reliable than the classifier. The router **never raises**: any failure falls through to `grounded_qa`, the safe default.

### Skills

A skill owns its prompt contract, its output contract, and its validation.

| Skill | Contract | Validation |
|---|---|---|
| `grounded_qa` | Answer only from the numbered context block; cite `[S#]`; abstain if the block is thin | Markers are matched against real chunks; the verdict reflects what was emitted, not what was asked for |
| `ship30_essay` | Ship 30 structure, grounded, ~1,250 words | `score_essay()` — a pure function, no model, no network — then one targeted revision, kept only if strictly fewer failures |
| `artifact` | Markdown or HTML document | Server-side allowlist sanitization before persistence |

### Two runtimes, one set of tools

`tools.py` defines the tool schemas once, provider-neutrally:

- **`native`** — the in-repo tool loop, bounded by `MAX_TOOL_ITERATIONS`. Works with every provider including Ollama, so it is the default and the path the demo uses.
- **`claude_sdk`** — the Anthropic Claude Agent SDK (`@tool`, `create_sdk_mcp_server`, `ClaudeSDKClient`). Cloud only; imported behind a guard so the package is not a hard dependency.

Both exist because the brief requires the SDK *and* requires a local model demo, and the SDK does not serve Ollama. Shipping only the SDK path would have meant the required demo could not run. [ADR-005](decisions/ADR-005-agent-runtime.md).

---

## 5. Model provider layer

`app/llm/registry.py` resolves providers from settings alone; nothing else in the app knows which model is in use.

| Provider | Chat | Embeddings | Role |
|---|---|---|---|
| `ollama` | ✅ | ✅ | local; required for the demo |
| `anthropic` | ✅ | — | cloud |
| `openai` | ✅ | ✅ | cloud |
| `echo` / `hash` | ✅ | ✅ | deterministic offline stubs for tests and CI |

**Fallback.** If `CHAT_FALLBACK_PROVIDER` is set and the primary errors, the turn is retried once on the fallback and the response carries a notice. Silently substituting a different model would break the product's core promise that the screen tells the truth about what answered.

**Embedding dimension is a schema concern.** Changing embedding model changes vector width; the bootstrap warns on mismatch, `make doctor` catches it, `make resize-embeddings DIM=n` fixes it, and re-ingestion is required. Made explicit rather than automatic, because it is destructive.

---

## 6. Data model

```
sessions   id · user_id · title · provider · model · created_at · updated_at · archived
messages   id · session_id → sessions · role · content · skill · grounding
           citations jsonb · trace jsonb · provider · model · latency_ms · token_usage
artifacts  id · session_id · message_id · kind · title · content
           sanitized · sanitizer_report jsonb
transcripts id · source_path · content_hash · title · guest · episode_url · ingested_at
chunks     id · transcript_id → transcripts · ordinal · heading · speaker · timestamp
           content · embedding vector(768) · tsv tsvector GENERATED
eval_runs  id · label · started_at · metrics jsonb · cases jsonb
```

Indexes: `ivfflat` on `chunks.embedding` (cosine), `GIN` on `chunks.tsv`, `pg_trgm` on titles for fuzzy episode lookup, FK indexes on the session paths.

Citations and traces are stored denormalised as `jsonb` on the message. They are read as a unit with the message, never queried across, and — most importantly — they are a *record of what happened at that moment*. Normalising them would let a later re-ingest silently rewrite history a user already read.

**Migrations are idempotent SQL applied at startup**, not Alembic. For a single-service take-home that must survive `docker compose up` on a stranger's laptop, a migration runner with its own state table and version conflicts is more failure surface than it removes. The reasoning, and the point at which this becomes the wrong call, are in [ADR-004](decisions/ADR-004-sql-bootstrap.md).

---

## 7. Observability

**Structured logs** (structlog; `console` for humans, `json` for shipping) with the trace id bound for the whole turn.

**Per-turn traces** as named spans with durations and details, persisted on the message and rendered in the Inspector. Observability that only an operator can reach answers "is it up"; observability the user can reach answers "why did it say that".

**Response headers** `X-Trace-Id` and `X-Response-Time-Ms` on every response.

**Health.** `/api/health` is liveness. `/api/health/deep` checks the database, the chat provider, the embedding provider, and the chunk count, returning `ok` / `degraded` / `down` per component — so a missing Ollama shows as *degraded*, not as an outage.

**Errors.** One envelope everywhere:

```json
{ "error": { "code": "provider_unreachable",
             "message": "The local model did not respond.",
             "hint": "Is Ollama running? Try: ollama serve, then make doctor.",
             "trace_id": "…" } }
```

Every error carries a `hint`. An error message that does not tell you what to do next is a log line pretending to be a user interface.

---

## 8. Resilience

| Failure | Behaviour |
|---|---|
| Ollama down | Fallback provider if configured, else a structured error naming the fix; health shows `degraded` |
| Embedding service down | Retrieval degrades to lexical-only; trace records `degraded: true` |
| Postgres slow on first boot | Compose gates on `pg_isready`; lifespan retries migrations |
| Malformed transcript | That file fails, the reason is reported, the run continues |
| Model emits invalid tool JSON | Parse failure logged, loop continues to the next iteration, never crashes the turn |
| Model ignores the citation contract | Verdict downgraded; the UI says so |
| Oversized artifact | Truncated at `ARTIFACT_MAX_BYTES`, reported in the sanitizer panel |
| Unknown `session_id` | New session created rather than a 404 |

---

## 9. Performance notes

- Embeddings batched during ingest; re-ingest skips unchanged files by hash.
- One SQL round trip for hybrid retrieval — not two queries fused in Python.
- `ivfflat` needs `ANALYZE` to be useful, so ingest runs it.
- The Q&A path streams over SSE; nginx sets `proxy_buffering off`, without which SSE arrives in one lump at the end and looks like a hang.
- `HISTORY_TURNS_IN_CONTEXT` bounds context growth so a long session does not slowly become a latency problem.

## 10. Where this stops scaling

`ivfflat` is fine for one archive and one user; past a few million chunks it wants HNSW and tuned probes. Sessions are unauthenticated. Ingestion is synchronous and single-process — the natural next step is a worker queue. Everything is one backend replica; the app is stateless apart from Postgres, so horizontal scaling is a deployment change rather than a code change.
