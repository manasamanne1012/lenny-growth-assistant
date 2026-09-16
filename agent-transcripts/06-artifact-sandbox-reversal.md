# 06 — Stripping scripts, then deciding that was the wrong boundary

**Outcome: `docs/design.md` §4, the threat model.**

## The first implementation

The sanitizer stripped every `<script>` tag, inline or remote. Artifacts rendered as static HTML. Safe, simple, done.

## Why it got reversed

The brief asks for a viewer "like Claude Artifacts." Claude's artifacts are *interactive* — calculators, sortable tables, toggled checklists. Interactivity requires script execution. A static renderer satisfies the letter of "artifact viewer" and misses the thing that makes artifacts worth having.

That alone would be a weak reason to accept untrusted script. The stronger reason is the second realisation:

**Script-stripping is a bad security boundary anyway.**

Sanitizers are defeated routinely, by parser differentials between the sanitizer and the browser, by mutation XSS, by encoding tricks. Every HTML sanitizer in wide use has a CVE history. Building the primary defence on "I removed all the dangerous markup" means betting the app's origin on a parsing race against an adversary with the whole browser spec to work with.

So the question was reframed. Not *whether* untrusted script runs, but **where**.

## What replaced it

`sandbox="allow-scripts"` with **no** `allow-same-origin`. That pairing gives the frame an opaque origin: no cookies, no storage, no parent DOM, no same-origin requests. Plus `Content-Security-Policy: default-src 'none'` with no `connect-src`, so even executing script can reach nothing.

The script is allowed to run in a context where running it accomplishes nothing. The boundary is the browser's process model, not my parser.

The sanitizer's job shrank to what the sandbox *cannot* contain: framing (`iframe`, `object`, `embed`), navigation (`base`, `meta refresh`, `form`), remote loading (`script src`), and event handlers. That is a much smaller job, and a much smaller job is a job a sanitizer can actually do.

## The thing that must never change

`allow-scripts` + `allow-same-origin` together **void the entire sandbox**. The frame regains the parent's origin and the artifact viewer becomes stored XSS in the app's own origin.

Guarded three ways: a comment at the attribute, a test asserting it, and a warning in `docs/handoff.md` §4. Three guards for one attribute is not paranoia — it is the single line in this repository where a plausible-looking "fix" causes the worst outcome.

## What was added after

**The always-visible blocked-content panel.** Originally it appeared only when something had been removed. Changed to always visible, because a security control the user cannot see is a control they cannot trust — and "nothing was blocked" is itself information.

**An escape hatch.** `ALLOW_ARTIFACT_SCRIPTS=false` strips inline scripts too. Anyone whose risk tolerance is lower than mine should not have to fork the repo to act on it.

**Tests named after attacks.** Each case in `test_sanitizer.py` names what it prevents — script-src exfiltration, `onerror` handler, `javascript:` href, meta-refresh redirect, iframe nesting, base-tag hijack, oversize payload. A sanitizer test called `test_case_3` teaches a future maintainer nothing about what they must not break.
