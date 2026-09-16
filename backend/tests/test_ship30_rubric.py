"""The Ship 30 rubric validator.

These tests are what make the skill a skill: the rubric is executable, so the
essay quality bar is enforced rather than hoped for.
"""

from app.agent.skills.ship30 import SHIP30_RUBRIC, score_essay


def _essay(
    *, words=1250, h2=5, bullets=2, bold=8, hook="Your onboarding flow is losing "
    "users before they ever see value.", cite_every=True, takeaway=True
) -> str:
    parts = [f"# Why most onboarding flows fail\n\n{hook}\n"]
    per_section = max(30, words // max(h2, 1))
    for i in range(h2):
        parts.append(f"\n## The specific reason section {i} matters to you\n")
        filler = " ".join(["Teams often miss this detail."] * (per_section // 5))
        marker = " [S1]" if cite_every else ""
        parts.append(f"{filler}{marker}\n")
        if i < bullets:
            parts.append("\n- First concrete point\n- Second concrete point\n")
        if i < bold:
            parts.append(f"\n**Remember this line {i}.**\n")
    for i in range(max(0, bold - h2)):
        parts.append(f"\n**Extra emphasis {i}.**\n")
    parts.append("\nA second source backs this up. [S2]\n")
    if takeaway:
        parts.append(
            "\n## The one thing to do this week\n\nPick one activation event and "
            "instrument it. [S1]\n"
        )
    return "".join(parts)


def test_a_conforming_essay_passes():
    report = score_essay(_essay())
    assert report.passed, report.failures


def test_short_essay_is_rejected_with_an_actionable_message():
    report = score_essay(_essay(words=300))
    assert not report.passed
    assert any("Length" in f for f in report.failures)
    assert any("Expand" in f for f in report.failures)


def test_long_hook_is_rejected():
    long_hook = " ".join(["word"] * 40) + "."
    report = score_essay(_essay(hook=long_hook))
    assert any("opening sentence" in f for f in report.failures)


def test_missing_takeaway_is_caught():
    report = score_essay(_essay(takeaway=False))
    assert any("takeaway" in f.lower() for f in report.failures)


def test_uncited_essay_fails_the_grounding_rule():
    report = score_essay(_essay(cite_every=False))
    assert any("citation" in f.lower() for f in report.failures)


def test_over_bolding_is_caught_not_just_under_bolding():
    report = score_essay(_essay(bold=40))
    assert any("bold" in f.lower() for f in report.failures)


def test_label_headings_are_flagged_as_unskimmable():
    essay = _essay().replace(
        "## The specific reason section 0 matters to you", "## Background"
    )
    report = score_essay(essay)
    assert any("labels" in f for f in report.failures)


def test_revision_note_lists_only_actual_failures():
    report = score_essay(_essay(words=200, takeaway=False))
    note = report.revision_note()
    assert "Length" in note and "takeaway" in note.lower()
    assert len(report.failures) == note.count("\n- ") + (0 if "\n- " in note else 1)


def test_rubric_constants_are_internally_consistent():
    assert SHIP30_RUBRIC["min_h2"] < SHIP30_RUBRIC["max_h2"]
    lo, hi = SHIP30_RUBRIC["bold_phrases"]
    assert lo < hi
