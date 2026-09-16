# Handoff

Written for the person who inherits this repository and has to change something in it on their second day. It assumes you have read the README and nothing else.

---

## 1. Get it running

```bash
cp .env.example .env
make up                 # postgres + backend + frontend
make doctor             # the important step — see §2
make demo-seed          # index the 3 bundled sample episodes (no network needed)
open http://localhost:5173
```

For the real corpus:

```bash
make fetch-transcripts
make ingest LIMIT=25    # drop LIMIT once you are confident; the full run is slow
```

For the local-model path you also need Ollama running **on the host**, not in a container:

```bash
ollama serve
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

## 2. `make doctor` first, always

Roughly nine out of ten "it's broken" reports on a stack like this are one of four things: Ollama isn't running, the model was never pulled, `EMBEDDING_DIM` no longer matches the vector column, or nothing has been ingested. `doctor` checks each and prints the command that fixes it. Run it before you read any logs.

## 3. Where things live

| You want to change… | Go to |
|---|---|
| Anything configurable | `backend/app/config.py` — and only there. No other module reads the environment. |
| How questions are classified into skills | `backend/app/agent/router.py` |
| How an answer is assembled | `backend/app/agent/skills/qa.py` |
| Ship 30 writing rules | `SHIP30_RUBRIC` in `backend/app/agent/skills/ship30.py` |
| Retrieval behaviour | `backend/app/rag/retriever.py` + `hybrid_search` in `backend/app/db/repository.py` |
| Chunking | `backend/app/rag/chunker.py` |
| Any SQL at all | `backend/app/db/repository.py` — SQL lives nowhere else |
| What HTML artifacts may contain | `backend/app/security/sanitizer.py` |
| Visual system | `frontend/src/styles/app.css` (one file, commented by section) |
| Evaluation cases | `backend/evals/golden_set.yaml` — data, not code |

## 4. Things that will bite you

**Changing the embedding model is a schema change.** The vector column has a fixed width. Postgres will not silently accept a different one.

```bash
# in .env: EMBEDDING_PROVIDER=openai, EMBEDDING_DIM=1536
make resize-embeddings DIM=1536
make ingest FORCE=1
```
Skipping the re-ingest leaves you with an empty index and no error message that says so. `make doctor` catches it.

**`MIN_GROUNDING_SCORE` is calibrated against the current embedding model and corpus.** It is the single knob controlling how often the assistant refuses. Change it and run `make eval` in the same sitting — the over-refusal rate is what tells you whether you went too far. Tuning it by feel is how this product quietly becomes either a liar or useless.

**Fused RRF scores are small and unitless.** `0.018` looks like a typo and is not. Do not "fix" it to `0.5`.

**Never add `allow-same-origin` to the artifact iframe.** Combined with the existing `allow-scripts` it voids the entire sandbox and turns the artifact viewer into stored XSS in the app's own origin. There is a comment and a test guarding this. Read `docs/design.md` §4 before touching `ArtifactViewer.tsx`.

**Migrations are idempotent SQL run at startup, not Alembic.** New DDL goes in a new numbered file in `backend/migrations/` and must be safe to run twice. Anything destructive does *not* go there — it goes in a script invoked from the Makefile, like `002_embedding_dim.sql`. See ADR-004.

**SSE needs buffering off.** If streaming answers arrive all at once at the end, something re-introduced proxy buffering. Check `frontend/nginx.conf`.

**Ollama inside Docker is `host.docker.internal`, not `localhost`.** Running the backend directly on your host instead? Then it *is* `localhost:11434`.

## 5. Common tasks

**Add a new skill**
1. Write it in `backend/app/agent/skills/`, returning the same outcome shape as `qa.py`.
2. Add a routing rule in `router.py` and a test for that rule.
3. Add a chip in `frontend/src/components/Composer.tsx`.
4. Add at least one golden-set case.

**Add a model provider**
1. Implement the `ChatProvider` protocol in `backend/app/llm/`.
2. Register it in `registry.py` and add the literal to `config.py`.
3. Document its env vars in `.env.example`.
Nothing else needs to change — the UI badge reads whatever the registry reports.

**Add eval cases.** Append to `golden_set.yaml`. No code change. Cases that should be refused are the valuable ones.

**Change the look.** `app.css` is organised by section with the reasoning in comments at the top. One rule to respect: **sage (`--sage`) means verified grounding and nothing else.** If you use it decoratively you destroy the one signal the interface is built to carry.

## 6. Debugging a bad answer

Every response carries `X-Trace-Id`. The same id is in the logs and in the UI under "How this answer was built". Work in this order:

1. **Inspector → Retrieval.** Did it find the right episodes? If not, the problem is retrieval, not the model.
2. **Inspector → Routed by.** Did it pick the right skill?
3. **Grounding verdict.** "Not cited" means the model ignored the citation contract — usually a small local model. Try a cloud provider to confirm before changing prompts.
4. **`degraded: true`** on retrieval means the embedding service was unreachable and the answer came from keyword search alone.
5. Only then look at the prompt.

## 7. Operational notes

- `/api/health` = liveness. `/api/health/deep` = per-component readiness; a missing Ollama shows as `degraded`, not `down`.
- Logs: `LOG_FORMAT=console` locally, `json` anywhere that ships them.
- `make logs` follows the backend.
- Data lives in the `pgdata` volume. `make down` keeps it; `make nuke` deletes it.
- There is no auth. Do not expose this to a network you do not control.

## 8. Known debt, honestly

- Ingestion is synchronous and single-process. A worker queue is the natural next step.
- Sessions are unauthenticated; `user_id` is a stub.
- The golden set is 10 cases — enough to catch regressions, not enough to optimise against.
- The Claude Agent SDK runtime is not covered by CI, because CI has no API key.
- `ivfflat` is fine at this scale and wants to become HNSW past a few million chunks.
