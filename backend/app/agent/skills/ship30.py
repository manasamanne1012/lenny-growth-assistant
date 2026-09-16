"""The Ship 30 for 30 essay skill.

This is a *skill*, not a prompt. Three parts, each independently testable:

  1.  `SHIP30_RUBRIC` — the writing principles, encoded as structured constraints
      rather than prose advice. Derived from the Ship 30 for 30 "start writing
      online" guide, restated in our own words and adapted to the client's
      1,250-word target.
  2.  `score_essay()` — a deterministic validator. No model involved. It measures
      what the rubric can measure mechanically: length, hook shape, heading
      count, skimmability, bold density, citation coverage, takeaway presence.
  3.  `write_ship30_essay()` — draft, score, and if the draft misses the rubric,
      send the specific failures back for one targeted revision.

The revision loop is the reason this is a skill. A single prompt produces essays
that pass sometimes; a scored loop produces essays that pass reliably, and when
one does not, the caller gets a report saying which rule it broke.

**A note on the word count.** A canonical Ship 30 atomic essay is ~250 words and
fits one screen. The client asked for ~1,250. We honour the client's number and
keep the atomic structure by treating the piece as four to six stacked atomic
beats under one thesis, rather than as one essay stretched five times longer.
That decision is recorded in docs/PRD.md §Scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.llm import ChatMessage
from app.obs import current_trace, get_logger
from app.rag.retriever import RetrievalResult

log = get_logger("skill.ship30")

CITATION = re.compile(r"\[S(\d+)\]")

SHIP30_RUBRIC: dict[str, Any] = {
    "target_words": 1250,
    "word_tolerance": 0.20,
    "hook_max_words": 22,
    "min_h2": 4,
    "max_h2": 7,
    "min_bullet_blocks": 2,
    "bold_phrases": (4, 14),
    "max_avg_sentence_words": 22,
    "min_citation_coverage": 0.6,
    "principles": [
        "One idea per essay. If a second idea is interesting, it is a different essay.",
        "Write to one named reader, not an audience. Specificity is what makes it land.",
        "The first sentence has one job: make the second sentence get read.",
        "Open with tension — a wrong belief, a costly mistake, a surprising number — "
        "not with context or a definition.",
        "Prove, do not assert. Every claim carries a concrete example from a real "
        "operator, named.",
        "Short sentences. Vary the rhythm. A one-line paragraph is a legitimate "
        "emphasis device.",
        "Skimmable by default: descriptive subheads, short paragraphs, lists where "
        "the content is genuinely a list.",
        "Bold the line a reader should remember, not every line you like.",
        "Close with one specific action the reader can take this week, not a summary.",
    ],
}

SYSTEM = """You write in the Ship 30 for 30 style for an internal product and growth \
audience. You are given excerpts from Lenny's Podcast transcripts and must build the \
essay from them.

STRUCTURE
- Title as an H1. Make it a specific claim or a sharp question, not a topic label.
- Hook: the first sentence is under 22 words and creates tension — a wrong belief, \
a costly mistake, or a number that should not be true. Never open with "In today's \
fast-paced world" or any variant of it.
- 4 to 6 H2 sections. Each H2 is a descriptive sentence fragment that tells the \
skimmer what they get, not a one-word label.
- Each section: a claim, then proof from the transcripts with the operator named, \
then what it means for the reader.
- At least two bulleted blocks where the content is genuinely enumerable.
- Bold 4 to 14 short phrases — only the lines worth remembering.
- Close with "The one thing to do this week" as the final H2, containing one \
specific, concrete action.

VOICE
- Second person. Plain verbs. Short sentences; average under 22 words.
- Name the operator behind every idea: "Shreyas Doshi's framing of ..." not \
"experts suggest".
- No filler transitions ("Moreover", "Furthermore", "In conclusion").
- No em-dash-heavy asides and no "it's not X, it's Y" constructions.

GROUNDING
- Every factual claim, framework, number, and example comes from the excerpts and \
carries its [S#] marker at the end of the sentence.
- If the excerpts do not support a section you planned, cut the section. Do not \
invent supporting evidence.

FINAL OUTPUT CHECK — DO THIS SILENTLY BEFORE YOU ANSWER

You MUST satisfy every requirement below:
- Write between 1,000 and 1,500 words. Never stop at 300–500 words.
- Include exactly 5 H2 sections.
- Include at least 2 genuine bulleted lists, with at least 2 bullets in each.
- Keep the average sentence length at 22 words or fewer.
- Include 4–14 bold phrases.
- Put [S#] citations on factual claims supported by the excerpts.
- End with the H2 "The one thing to do this week" and one concrete action.

If the draft is too short, KEEP WRITING until it reaches at least 1,000 words.
Do not summarize. Do not stop early.

Output the essay only — no preamble, no notes.
"""

@dataclass
class EssayReport:
    word_count: int = 0
    hook_words: int = 0
    h2_count: int = 0
    bullet_blocks: int = 0
    bold_phrases: int = 0
    avg_sentence_words: float = 0.0
    citation_coverage: float = 0.0
    distinct_citations: int = 0
    has_takeaway: bool = False
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "word_count": self.word_count,
            "hook_words": self.hook_words,
            "h2_count": self.h2_count,
            "bullet_blocks": self.bullet_blocks,
            "bold_phrases": self.bold_phrases,
            "avg_sentence_words": round(self.avg_sentence_words, 1),
            "citation_coverage": round(self.citation_coverage, 2),
            "distinct_citations": self.distinct_citations,
            "has_takeaway": self.has_takeaway,
            "failures": self.failures,
        }

    def revision_note(self) -> str:
        return (
            "Your draft missed these rubric rules. Fix exactly these and change "
            "nothing else. Output the full revised essay only.\n\n- "
            + "\n- ".join(self.failures)
        )


def score_essay(text: str) -> EssayReport:
    """Deterministic rubric check. No model, no network - pure function."""
    r = SHIP30_RUBRIC
    report = EssayReport()

    body = re.sub(r"^#\s+.*$", "", text, count=1, flags=re.MULTILINE)
    words = body.split()
    report.word_count = len(words)

    lo = int(r["target_words"] * (1 - r["word_tolerance"]))
    hi = int(r["target_words"] * (1 + r["word_tolerance"]))
    if not lo <= report.word_count <= hi:
        report.failures.append(
            f"Length is {report.word_count} words; the target is {lo}–{hi}. "
            + ("Expand the thinnest sections with more transcript evidence."
               if report.word_count < lo else
               "Cut the weakest section entirely rather than trimming everywhere.")
        )

    # Hook: first non-heading, non-empty sentence.
    hook = ""
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "-", "*", ">")):
            hook = re.split(r"(?<=[.!?])\s", s)[0]
            break
    report.hook_words = len(hook.split())
    if report.hook_words == 0:
        report.failures.append("No opening sentence found before the first heading.")
    elif report.hook_words > r["hook_max_words"]:
        report.failures.append(
            f"The opening sentence is {report.hook_words} words; the rubric caps the "
            f"hook at {r['hook_max_words']}. Split it and lead with the tension."
        )

    headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    report.h2_count = len(headings)
    if not r["min_h2"] <= report.h2_count <= r["max_h2"]:
        report.failures.append(
            f"There are {report.h2_count} H2 sections; the rubric wants "
            f"{r['min_h2']}–{r['max_h2']}."
        )
    generic = [h for h in headings if len(h.split()) <= 2]
    if generic:
        report.failures.append(
            "These headings are labels, not descriptive promises to a skimmer: "
            + ", ".join(f'"{h}"' for h in generic[:3])
        )

    report.bullet_blocks = len(
        re.findall(r"(?:^[-*]\s+.+\n){2,}", text, flags=re.MULTILINE)
    )
    if report.bullet_blocks < r["min_bullet_blocks"]:
        report.failures.append(
            f"Only {report.bullet_blocks} bulleted block(s); the rubric wants at "
            f"least {r['min_bullet_blocks']} where the content is genuinely a list."
        )

    report.bold_phrases = len(re.findall(r"\*\*[^*\n]{3,120}\*\*", text))
    bmin, bmax = r["bold_phrases"]
    if not bmin <= report.bold_phrases <= bmax:
        report.failures.append(
            f"{report.bold_phrases} bold phrases; the rubric wants {bmin}–{bmax}. "
            + ("Bold the lines worth remembering." if report.bold_phrases < bmin
               else "Over-bolding removes the emphasis. Keep only the strongest.")
        )

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"[#*`>-]", "", body))
                 if len(s.split()) > 2]
    if sentences:
        report.avg_sentence_words = sum(len(s.split()) for s in sentences) / len(sentences)
        if report.avg_sentence_words > r["max_avg_sentence_words"]:
            report.failures.append(
                f"Average sentence length is {report.avg_sentence_words:.0f} words; "
                f"the rubric caps it at {r['max_avg_sentence_words']}. Break up the "
                "longest sentences."
            )

    clean_body = re.sub(r"^#{1,6}\s+.*$", "", body, flags=re.MULTILINE)

    paragraphs = [
        p for p in clean_body.split("\n\n")
        if len(p.split()) > 25 and not p.strip().startswith(("#", "-", "*"))
    ]

    cited = sum(1 for p in paragraphs if CITATION.search(p))
    report.citation_coverage = cited / len(paragraphs) if paragraphs else 0.0
    report.distinct_citations = len(set(CITATION.findall(text)))
    if report.citation_coverage < r["min_citation_coverage"]:
        report.failures.append(
            f"Only {report.citation_coverage:.0%} of substantive paragraphs carry a "
            f"[S#] citation; the rubric requires {r['min_citation_coverage']:.0%}. "
            "Add markers or cut the unsupported claims."
        )
    if report.distinct_citations < 2:
        report.failures.append(
            "The essay leans on fewer than two distinct sources. Draw on more of "
            "the retrieved excerpts or narrow the thesis."
        )

    tail = "\n".join(text.splitlines()[-25:]).lower()
    report.has_takeaway = bool(
        re.search(r"##\s+the one thing to do this week", text, re.I)
    ) or any(k in tail for k in ("this week", "start by", "do this", "your next step"))
    if not report.has_takeaway:
        report.failures.append(
            'Missing the closing takeaway. End with an H2 "The one thing to do this '
            'week" containing one concrete action.'
        )

    return report


async def write_ship30_essay(
    provider,
    topic: str,
    retrieval: RetrievalResult,
    *,
    max_revisions: int = 1,
) -> tuple[str, EssayReport, dict[str, int]]:
    """Draft - score - one targeted revision. Returns (essay, report, usage)."""
    trace = current_trace()
    usage = {"input_tokens": 0, "output_tokens": 0}

    brief = (
        f"TRANSCRIPT EXCERPTS\n\n{retrieval.context_block(max_chars=22_000)}\n\n"
        f"ESSAY BRIEF\nWrite the essay on: {topic}\n\n"
        "Pick the single sharpest thesis these excerpts support. Do not try to "
        "cover everything in them."
    )
    messages = [ChatMessage(role="user", content=brief)]

    span_name = "llm_essay_draft"
    if trace:
        with trace.span(span_name, provider=provider.name):
            result = await provider.complete(messages, system=SYSTEM, max_tokens=6000)
    else:
        result = await provider.complete(messages, system=SYSTEM, max_tokens=6000)
    _accumulate(usage, result.usage)

    essay = _strip_fences(result.text)
    report = score_essay(essay)
    log.info("skill.ship30.draft", **report.to_dict())

    attempts = 0
    while not report.passed and attempts < max_revisions:
        attempts += 1
        messages = [
            ChatMessage(role="user", content=brief),
            ChatMessage(role="assistant", content=essay),
            ChatMessage(role="user", content=report.revision_note()),
        ]
        if trace:
            with trace.span(f"llm_essay_revision_{attempts}") as span:
                result = await provider.complete(messages, system=SYSTEM, max_tokens=6000)
                span.detail["fixing"] = report.failures
        else:
            result = await provider.complete(messages, system=SYSTEM, max_tokens=6000)
        _accumulate(usage, result.usage)

        revised = _strip_fences(result.text)
        revised_report = score_essay(revised)
        # Only keep the revision if it is genuinely better — a local model can
        # make things worse when asked to fix several rules at once.
        if len(revised_report.failures) < len(report.failures):
            essay, report = revised, revised_report
        log.info("skill.ship30.revision", attempt=attempts, **revised_report.to_dict())

    if trace:
        trace.fact("ship30", {**report.to_dict(), "revisions": attempts})
    return essay, report, usage


def _strip_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:markdown|md)?\s*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def _accumulate(total: dict[str, int], new: dict[str, int]) -> None:
    for k, v in (new or {}).items():
        total[k] = total.get(k, 0) + v
