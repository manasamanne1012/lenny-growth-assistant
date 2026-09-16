# 04 — A weighted hybrid scorer, written and then deleted

**Outcome: ADR-003.**

## What was built first

The initial `hybrid_search` normalised both rankings and blended them:

```sql
-- first version, since deleted
SELECT id,
       0.7 * (1 - (embedding <=> :q))
     + 0.3 * ts_rank_cd(tsv, plainto_tsquery(:q))
       AS score
...
```

It worked. It was also wrong, and the reason it was wrong is worth recording.

## Why it was deleted

Three problems, in increasing order of how much they mattered:

1. **The scores are not commensurable.** Cosine similarity and `ts_rank_cd` have different ranges and different distributions. Adding them requires normalisation, and normalisation requires its own unjustified choices.

2. **`0.7` and `0.3` were invented.** Not derived, not measured — typed. There is no labelled relevance data for this corpus.

3. **This is the one that decided it.** Six months later, those constants are indistinguishable from tuned values. Nothing in the code says "these were a guess." A future engineer sees two decimals in a SQL query and reasonably assumes someone measured something. The number is a lie with a long half-life.

## What replaced it

Reciprocal Rank Fusion. Two ranked lists, fused as `Σ 1 / (k + rank)`, `k = 60`.

RRF consumes only **rank positions** — no score normalisation, no relevance data, no weight to invent. `k = 60` comes from Cormack et al. and is documented as "do not move without eval evidence." It is a cited constant, not a guessed one, and the difference is the entire point.

## The rule this produced

**A magic number is only acceptable if you can say where it came from.**

That rule then applied everywhere else in the build. `MIN_GROUNDING_SCORE = 0.018` is the exception that proves it: it *is* empirical and corpus-dependent, so it sits in `.env` with a comment saying it must be re-tuned with `make eval` open, and the handoff doc warns that it looks like a typo and is not.

## Also rejected: a cross-encoder reranker

Would probably improve precision. Rejected for now because it adds a second model to a setup that must run locally, and with ten eval cases I cannot demonstrate the gain. Adopting unmeasured complexity is precisely the habit the section above is arguing against — it would have been inconsistent to reject invented weights and then accept an unmeasured reranker in the same file. Logged as the top retrieval item in the PRD's "what next."
