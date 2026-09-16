# Architecture decision records

One file per decision that could reasonably have gone the other way. Each records the forces at the time, the alternatives, and — the part that matters most — the conditions under which the decision should be revisited.

Decisions that had only one sensible answer (FastAPI, PostgreSQL, React) are not recorded here. An ADR that says "we chose the obvious thing" is filler.

| # | Decision | Status |
|---|---|---|
| [001](ADR-001-grounding-gate.md) | Abstain below a grounding threshold, and measure over-refusal | Accepted |
| [002](ADR-002-vector-store.md) | pgvector in the application database, not a dedicated vector store | Accepted |
| [003](ADR-003-hybrid-retrieval.md) | Hybrid retrieval fused with RRF, no reranker | Accepted |
| [004](ADR-004-sql-bootstrap.md) | Idempotent SQL at startup instead of Alembic | Accepted, with a stated expiry |
| [005](ADR-005-agent-runtime.md) | Two agent runtimes behind one tool schema | Accepted |
