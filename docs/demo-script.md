# Demo video script — 2m45s

The brief asks for 2–3 minutes, camera on. This is a shooting script: what to say, what to show, and what to cut.

**Before you record:** `make up`, `make doctor` clean, corpus ingested, one session already populated so you are not waiting on a local model on camera. Have a second terminal open with `make logs`. Decide in advance which provider you start on.

---

### 0:00–0:20 · Who and what (camera on you)

> "I'm [name]. This is the Lenny Growth Assistant — it answers product and growth questions from the Lenny's Podcast archive, and it shows you which episode every claim came from. The thing I want to show you first isn't an answer. It's a refusal."

*Keep the camera on yourself for this whole opening. Do not narrate the architecture yet.*

### 0:20–0:50 · Abstention (screen)

Type: **"What did Lenny's guest say in the episode where Genghis Khan explains B2B pricing?"**

> "There's no such episode. A model asked this cold will invent a guest and a quote. This one says it can't find it — and that refusal is enforced in code, before generation, not asked for in a prompt. It's also measured: `make eval` reports how often it correctly refuses and, just as importantly, how often it refuses something it shouldn't have."

*This is your strongest thirty seconds. Do not rush it.*

### 0:50–1:25 · Grounded answer + provenance (screen)

Ask: **"How do guests describe knowing you've hit product-market fit?"**

Let it answer. Click an inline `[S1]` chip.

> "Every claim carries a marker. Clicking it opens the episode, the guest, the timestamp, and the actual passage — so you can check it without leaving the sentence. And the verdict at the top is computed from what the model actually produced, not from what it was told to do. If it ignores the citation contract, this says so."

Then click **"How this answer was built."**

> "Routing, retrieval scores, which episodes were hit, timings, tokens. Observability the user can reach, not just the operator."

### 1:25–1:50 · Provider switch (screen + terminal)

> "The brief asks for cloud and local. It's one environment variable."

Show `.env`, change `CHAT_PROVIDER`, run `make restart`, reload, point at the badge.

> "The badge reads the live config, so the screen can't disagree with what's actually answering. The agent runtime switches the same way — a native tool loop that works with Ollama, or the Claude Agent SDK on cloud, behind one set of tool definitions."

### 1:50–2:20 · Essay and artifact (screen)

Show a pre-generated Ship 30 essay. Open the Inspector.

> "Ship 30 is a skill, not a prompt — the style is a rubric scored by a pure function, and the revision is only kept if it has strictly fewer failures than the draft."

Switch to an HTML artifact. Open the blocked panel.

> "Artifacts are model output, which is untrusted input. This runs in a sandboxed frame with no same-origin access and a CSP that allows no network at all — and the viewer tells you exactly what it stripped."

### 2:20–2:45 · Close (camera on you)

> "Everything here starts with `make up`. The decisions I'd defend in review are written up as ADRs — including the places where the brief contradicted itself, like Ship 30's 250-word form against a 1,250-word target, and the Agent SDK against a mandatory local model. Those are in the repo with the reasoning and the alternatives. Thanks."

---

## Notes

- **Camera on at the start and the end, minimum.** The brief asks for it explicitly and it is the easiest requirement to fail.
- If the local model is slow, pre-warm it and have the PMF answer already generated in a second session you can switch to.
- Record twice. The second take is always better and this is under three minutes.
- Do not read the architecture diagram aloud. It is in the README; the video is for the things a README cannot show.
