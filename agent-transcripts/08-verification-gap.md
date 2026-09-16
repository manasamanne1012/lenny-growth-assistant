# 08 — What could not be tested, and what was done about it

This is the log I would least like to write and the one most worth having.

## The constraint

The build environment had **no network access**. Consequences:

- No `pip install` → no FastAPI, no SQLAlchemy, no pytest in the environment.
- No `npm install` → no React, no TypeScript compiler, no Vite.
- No Postgres → no migrations, no queries, no pgvector.
- No Ollama, no Anthropic API → no model calls of any kind.

**Not one line of this system was executed during the build.**

## What verification was actually possible

- `python3 -m py_compile` across every backend module. All pass. This proves syntactic validity and nothing else.
- Manual cross-checking of imports, function signatures, and call sites between modules.
- Manual cross-checking of the API contract between `schemas.py`, the route handlers, `lib/types.ts`, and `lib/api.ts`.
- Reading the CSS for every class name referenced from a component, and the reverse.

## What that does not prove

Everything that matters. Whether the SQL is valid Postgres. Whether pgvector accepts the query. Whether TypeScript compiles under `strict`. Whether the containers build. Whether a single answer ever comes back grounded.

The honest description of this repository at the moment it was written is: **a coherent design that has never run.**

## What was done about it in the design

Since verification had to be deferred to a human on real hardware, the build optimised for *making that verification fast and its failures legible*:

- **`make doctor`** — checks the four things most likely to be wrong on a fresh machine, and prints the fix for each.
- **Offline providers** (`echo`, `hash`) — so the unit suite and CI run with no key, no GPU, no network. The parts most likely to break silently are the deterministic ones, and they are the ones testable in twenty seconds.
- **A structured error envelope with a `hint` on every error** — so the first failures a human hits explain themselves.
- **A compose smoke test in CI** — boots the stack, waits for `/api/health/deep`, ingests the bundled samples, runs the evals. The README says "one command"; CI runs that command.
- **Bundled sample transcripts** — the app is demonstrable without cloning the corpus, which removes one network dependency from the first run.

## The required next step

The repository is not submittable as-is, and saying otherwise would be the one genuinely dishonest thing in this folder. Before it goes anywhere:

```bash
cp .env.example .env
make up && make doctor
make demo-seed
make test && make eval
open http://localhost:5173
```

Expect failures. Missing imports, a type error under `strict`, a SQL typo, a container that will not build. That is the normal state of any codebase the first time it runs, and it is the difference between code that compiles and software that works.

The manual test plan in `docs/manual-test-plan.md` names eight cases that must pass before this is releasable. Those eight are the real sign-off, and they are run by a person.
