# 05 — The 250-word / 1,250-word contradiction

## The contradiction

The brief asks for essays in **Ship 30 for 30 style**, approximately **1,250 words**.

Ship 30's signature form is the *atomic essay*: roughly 250 words, one idea, readable on a phone screen. The word limit is not incidental to the style — it is the mechanism that produces it. Remove the constraint and you have a blog post that happens to use bold text.

So "Ship 30 style, 1,250 words" is, read literally, "a 250-word form at five times its length."

## Options

**A. Write 1,250 words and call it Ship 30.** Satisfies the number, loses the method. Would produce exactly the padded listicle the style exists to prevent.

**B. Write 250 words and cite the methodology.** Satisfies the style, ignores a stated requirement. Arrogant, and a reviewer counting words sees a miss.

**C. Five separate 250-word essays.** Faithful to both numbers. Rejected because the brief asks for "an essay," and a bundle of five is a different deliverable.

**D. Four to six stacked atomic beats under one thesis.** Chosen.

## What D means concretely

Each beat keeps atomic discipline — one idea, its own hook, its own payoff. The whole reads as one essay, with one thesis and one takeaway. Which is, in fairness, how longer Ship 30 work actually reads in the wild.

Encoded in `SHIP30_RUBRIC`: word band, hook length cap, H2 count (4–6, which is what enforces the beat structure), bulleted blocks, bold phrase range, average sentence length, citation coverage, explicit takeaway.

## The part that mattered more than the choice

This is a forward-deployment brief, and in a real deployment this is a two-minute Slack message to the client, not a decision to agonise over. But a take-home has no client to message.

So the decision is recorded in `docs/PRD.md` §6.2 with both alternatives, and the implementation is a **dict, not code**. If the real preference is five separate essays, that is an edit to `SHIP30_RUBRIC` and nothing else changes.

The deliverable is not the word count. It is arriving at the conversation with a position and a cheap way to reverse it.

## The revision guard

The first version of `write_ship30_essay()` drafted, scored, revised on failure, and returned the revision unconditionally.

That is wrong, and it took writing a rubric test to see it. Models frequently "improve" writing by flattening it — fixing the sentence-length rule by removing every interesting sentence, fixing hook length by making the hook boring. A revision can easily net *worse* against the rubric than the draft.

Final version: the revision is kept **only if it has strictly fewer failures than the draft.** Otherwise the draft is returned with its report. Six lines, and it is the difference between a loop that improves output and a loop that merely changes it.
