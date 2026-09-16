# 07 — Two visual directions discarded before the third

## The starting constraint

An AI chat product in 2026 has a default look, and the default look says nothing: cream and terracotta "warm minimalism", or acid green on near-black, purple-to-blue gradients, glass cards, one rounded sans at four weights. Landing on any of those signals "assembled from defaults" before a reviewer reads a line.

So the first step was writing down what *not* to do, and holding to it.

## Direction 1 — "Studio" · rejected

Warm off-white paper, a single ink-blue accent, generous whitespace, serif headings. Calm, readable, reference-like.

Rejected for being **indistinguishable from every documentation site**. It read as trustworthy in the way that a template reads as trustworthy — nothing in it was a decision. It also had no natural home for the provenance rail, which is the one element that needed to be loud.

## Direction 2 — "Console" · rejected

Near-black, monospace throughout, green-on-black, retrieval scores exposed as raw numbers, a terminal feel.

Rejected for two reasons. It is the acid-green cliché this was trying to avoid. And more substantively: the product's output is **prose drawn from a two-hour human conversation**. Rendering it in a terminal font flattens a guest's answer into a log line. The form was fighting the content.

## Direction 3 — "Listening desk" · chosen

The subject is spoken conversation, transcribed. So: a recording booth rather than a dashboard.

- **Deep teal ink** surfaces (`#0b1418` → `#1b2f39`), **warm paper** (`#edeae3`) for the reading column.
- **One amber signal lamp** (`#e0a33c`) for work in progress.
- **One desaturated sage** (`#74b79a`) reserved *exclusively* for verified grounding.
- **IBM Plex Sans** for chrome, **Newsreader** for answers and essays.

## The one rule the whole design rests on

**If sage is on screen, a claim is sourced.**

Never decorative, never a hover state, never a brand accent. This makes grounding legible at a glance, without reading a word — which is exactly the affordance a trust interface needs, and it is a rule a stylesheet can be audited against. It is written at the top of `app.css` and repeated in `docs/handoff.md`, because the most likely way to destroy it is a well-meaning designer using it as an accent.

## Where the boldness went

One element is allowed to be loud: the **provenance rail** under each answer. Everything else stays out of the way.

That is a deliberate allocation. A product whose entire value proposition is *you can check this* should spend its visual budget on the checking. Spreading emphasis evenly would have been the safer-looking choice and the weaker one.

## A late correction

The grounding verdict originally sat *below* the source list. Moved above it, because a user scanning downward should learn whether to trust the answer before they learn where it came from. Ordering is an argument about what matters most, and that one was initially backwards.
