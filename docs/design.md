# Design — interface, interaction, and the artifact threat model

---

## 1. What the interface is trying to say

The subject of this product is spoken conversation, transcribed and made searchable. The interface is built as a **listening desk**: a quiet, low-glare surface for long reading, with exactly one loud element — the provenance rail under each answer.

That is the whole design thesis. A tool whose entire value proposition is *you can check this* should spend its visual budget on the checking, not on the chrome.

### What was deliberately avoided

The default aesthetic for an AI chat product in 2026 is well established and therefore says nothing: cream-and-terracotta "warm minimalism", or acid green on near-black, purple-to-blue gradients, glassmorphic cards, a rounded sans at four weights. Landing on any of those would have signalled "assembled from defaults".

### What was chosen instead

**Palette — a recording booth, not a dashboard.** Deep teal ink (`#0b1418` → `#1b2f39`) for the surfaces, warm paper (`#edeae3`) for the reading column. One amber signal lamp (`#e0a33c`) for work in progress. One desaturated sage (`#74b79a`) reserved **exclusively** for verified grounding.

The sage rule is the design's one law: **if sage is on screen, a claim is sourced.** It never appears decoratively, never as a hover state, never as a brand accent. This makes grounding legible at a glance, from across a room, without reading a word — which is precisely the affordance a trust interface needs.

**Type — two families with different jobs.** IBM Plex Sans for chrome: engineered, neutral, honest at 12px. Newsreader for answers and essays, because the output here is prose to be *read*, not data to be scanned. Rendering an answer drawn from a two-hour human conversation in the same UI sans as the button labels flattens it into a status message.

**Layout — three zones, one reading column.**

```
┌──────────┬────────────────────────────┬─────────────────┐
│ sessions │  conversation (68ch)       │ artifact /      │
│ 244px    │  ── provenance rail ──     │ inspector       │
│          │  composer + skill chips    │ 460px, tabbed   │
└──────────┴────────────────────────────┴─────────────────┘
```

68ch is a reading measure, not a layout accident. Artifact and Inspector share a tabbed panel because both are *evidence about the answer you just read* — same moment, same attention, and giving each a permanent column would leave one empty most of the time.

Below 1180px the panel becomes an overlay; below 820px the session rail slides over a scrim. Reduced motion, visible focus rings, and a skip link are in the stylesheet, not in a follow-up ticket.

---

## 2. The provenance rail

The one element allowed to be loud.

```
┌─ Grounded in the transcripts ────────────────────────────┐
│  [S1]  Finding product-market fit — Priya Raman  12:04   │
│        "…you stop having to push. People start…"         │
│  [S2]  Onboarding and activation — Marcus Feld   31:47   │
└──────────────────────────────────────────────────────────┘
```

Design choices worth stating:

- **The verdict comes first**, before the sources. A user scanning downward learns whether to trust the answer before they learn where it came from.
- **The verdict is computed from the model's actual output**, not from its instructions. Four states: grounded, partial, ungrounded, abstained. "Ungrounded" is shown, in alert colour, with the answer still visible. Hiding a weak answer would be the dishonest design.
- **Citation markers in the prose are interactive chips.** Clicking `[S1]` expands that source inline — verification without leaving the sentence.
- **Excerpts are shown, not just titles.** A title tells you an episode exists; an excerpt tells you the answer is actually in it.
- **"How this answer was built"** sits at the bottom of the rail, because the people who want the trace want it *after* they have doubted something.

---

## 3. Interaction decisions

**Skill chips over slash commands.** The composer offers Answer / Essay / Document as optional chips. The router infers intent by default; the chips exist for when it is wrong. Discoverable without documentation, and they make the skill taxonomy visible — which is itself a way of telling the user what the tool can do.

**Optimistic user turns, never optimistic assistant turns.** The user's message appears immediately. The assistant's message is only ever rendered from the server response. Nothing about an answer is invented client-side, including its citations.

**Failures return the message.** A failed send restores the text to the composer and shows the backend's `code`, `hint`, and trace id. A user who lost a carefully-worded question to a 500 does not come back.

**Autoscroll that yields.** The thread follows new content unless the user has scrolled up to read something. Reading history is a deliberate act; stealing the viewport punishes it.

**Empty state as a test plan.** The five starters are chosen to demonstrate the product's range in one screen — including one question about an episode that does not exist, so the very first thing a new evaluator can do is watch the assistant refuse.

---

## 4. Threat model — artifacts

The artifact viewer renders HTML produced by a language model, which may itself have been influenced by transcript text ingested from a third-party repository. **Every byte of an artifact is untrusted input.** Treating it otherwise would make this feature a stored-XSS delivery mechanism sitting inside the application's own origin.

### Assets

| Asset | Consequence if compromised |
|---|---|
| Application origin (cookies, `localStorage`) | Session theft |
| Conversation history and artifacts | Data exfiltration |
| The backend API, reachable as the user | Unauthorised actions |
| The user's browser | Drive-by whatever |

### Adversaries

1. A **poisoned transcript** in the upstream corpus carrying injection text.
2. A **prompt-injecting user** who asks for an artifact engineered to break out.
3. A **model failure** that emits dangerous markup with no adversary at all — the most likely of the three.

### Controls

Layered, because any single one of these has known bypasses.

| # | Control | Stops | Where |
|---|---|---|---|
| 1 | **Allowlist sanitizer** — unknown elements and attributes dropped, not filtered. Removes `iframe`, `object`, `embed`, `form`, `base`, `meta refresh`, all `on*` handlers, `javascript:` URLs, remote `script src`. | Nesting/framing attacks, handler injection, remote payload loading | `app/security/sanitizer.py`, before persistence |
| 2 | **Size cap** (`ARTIFACT_MAX_BYTES`) | Storage and render DoS | sanitizer |
| 3 | **`sandbox="allow-scripts"` with no `allow-same-origin`** → opaque origin: no cookies, no storage, no parent DOM, no same-origin requests | Origin access, session theft, DOM tampering | `ArtifactViewer.tsx` |
| 4 | **`Content-Security-Policy: default-src 'none'`**, no `connect-src`, no `img-src` remote | Exfiltration, beaconing, remote loading | `artifactDocument()` in `lib/markdown.ts`; same CSP on `/api/artifacts/{id}/render` |
| 5 | **DOMPurify** on the Markdown path, which renders in the main document | XSS via Markdown-embedded HTML | `lib/markdown.ts` |
| 6 | **Visible blocked-content report** | Silent failure; user cannot audit | always-on panel in the viewer |
| 7 | **`ALLOW_ARTIFACT_SCRIPTS=false`** | Everything script-based, at the cost of interactivity | `config.py` |

### The deliberate decision to allow inline scripts

Inline scripts survive sanitization when `ALLOW_ARTIFACT_SCRIPTS=true`. This is intentional and is the most consequential security decision in the repository.

The reasoning: interactive artifacts — a calculator, a sortable table, a toggled checklist — are a large part of what makes this feature worth having, and they require script execution. The question is not *whether* untrusted script runs but *where*. Sanitizing scripts away is a brittle boundary (parser differentials, mutation XSS, encoding tricks all defeat it eventually). An opaque-origin sandbox with `default-src 'none'` is a boundary enforced by the browser's process model.

So the script is allowed to run, in a context where running it accomplishes nothing: no origin, no storage, no network, no parent. The sanitizer's job is reduced to removing what the sandbox *cannot* contain — framing, remote loading, navigation.

### Residual risks, named

- **Browser sandbox escape.** Out of scope to mitigate in application code; accepted.
- **Visual phishing inside the frame.** The artifact chrome is always visible and labelled. Not fully solved.
- **`allow-scripts` + `allow-same-origin` together would void control 3.** Pinned in code, in a comment explaining why, and asserted by a test.
- **CPU exhaustion** by a `while(true)` in an artifact. Contained to the frame's task; the tab stays responsive. Not otherwise mitigated.

### Tests

`tests/test_sanitizer.py` names the attack in each test case: script-src exfiltration, `onerror` handler, `javascript:` href, `meta` refresh redirect, `iframe` nesting, `base` tag hijack, oversize payload. The name is part of the test — a sanitizer test called `test_case_3` teaches a future maintainer nothing about what they must not break.

---

## 5. Accessibility

Landmarks and labelled regions; the panel is a tablist with real `aria-selected`; the provenance rail is a labelled section. Focus is visible in amber at 2px offset and never removed. Reduced motion collapses the signal lamp's pulse. A skip link reaches the conversation. Colour is never the sole carrier of meaning — the verdict is always written in words as well as coloured.
