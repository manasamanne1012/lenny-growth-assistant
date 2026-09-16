"""Evaluation harness.

`make eval` runs this. It answers three questions an evaluator actually has:

  1.  Does retrieval find the right material? (recall proxy: citations returned)
  2.  Does the assistant cite what it used? (citation coverage)
  3.  Does it refuse when it should? (abstention accuracy — the one that matters)

The abstention rate is reported separately and prominently because it is the
metric that separates a system a growth team will trust from one they will stop
using after the first confident fabrication.

Results are written to `evals/results/` and persisted to the `eval_runs` table,
so two runs can be diffed after a prompt or retrieval change.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.agent.orchestrator import run_turn
from app.agent.skills.ship30 import score_essay
from app.config import settings
from app.db import repository as repo
from app.db import session_scope
from app.db.bootstrap import apply_migrations
from app.obs import configure_logging, new_trace

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "results"

ABSTAIN_MARKERS = (
    "do not cover", "don't cover", "not covered", "no transcript",
    "could not find", "couldn't find", "does not support", "doesn't support",
    "nothing in the", "not something the",
)


@dataclass
class CaseResult:
    id: str
    kind: str
    passed: bool
    latency_ms: int
    grounding: str = ""
    citations: int = 0
    abstained: bool = False
    expected_abstain: bool = False
    failures: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


async def run_case(case: dict) -> CaseResult:
    started = time.perf_counter()
    failures: list[str] = []
    new_trace()

    async with session_scope() as db:
        session = await repo.create_session(
            db, title=f"eval:{case['id']}", user_id="eval-harness"
        )
        session_id = str(session["id"])

        if case.get("preceding_turn"):
            await run_turn(db, session_id=session_id, message=case["preceding_turn"])

        outcome = await run_turn(
            db,
            session_id=session_id,
            message=case["question"],
            force_skill=_force_skill(case["kind"]),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    lowered = outcome.text.lower()
    abstained = outcome.grounding == "abstained" or any(
        m in lowered for m in ABSTAIN_MARKERS
    )
    expected_abstain = bool(case.get("expect_abstain"))

    if expected_abstain and not abstained:
        failures.append(
            "Answered a question the knowledge base cannot support. This is the "
            "hallucination case — it should have abstained."
        )
    if not expected_abstain and abstained:
        failures.append("Abstained on an in-scope question (over-refusal).")

    if not expected_abstain:
        needed = case.get("min_citations", 0)
        if len(outcome.citations) < needed:
            failures.append(
                f"{len(outcome.citations)} citations returned; {needed} expected."
            )
        terms = case.get("must_mention_any")
        if terms and not any(t.lower() in lowered for t in terms):
            failures.append(
                "None of the expected topical terms appeared: " + ", ".join(terms)
            )

    detail: dict = {"route": outcome.route, "notices": outcome.notices}

    if case["kind"] == "ship30" and case.get("rubric_must_pass"):
        report = score_essay(outcome.text)
        detail["rubric"] = report.to_dict()
        if not report.passed:
            failures.append("Ship 30 rubric failed: " + "; ".join(report.failures[:3]))

    if case["kind"] == "artifact":
        art = outcome.artifact
        if not art:
            failures.append("No artifact was produced.")
        else:
            detail["artifact"] = {
                "kind": art["kind"],
                "bytes": len(art["content"]),
                "sanitizer": art["sanitizer_report"],
            }
            if case.get("expect_kind") and art["kind"] != case["expect_kind"]:
                failures.append(
                    f"Artifact kind was {art['kind']}, expected {case['expect_kind']}."
                )
            if case.get("expect_sanitizer_clean") and not art["sanitizer_report"].get(
                "clean", True
            ):
                failures.append(
                    "Sanitizer stripped forbidden constructs: "
                    + ", ".join(art["sanitizer_report"].get("removed_elements", []))
                )

    return CaseResult(
        id=case["id"],
        kind=case["kind"],
        passed=not failures,
        latency_ms=latency_ms,
        grounding=outcome.grounding,
        citations=len(outcome.citations),
        abstained=abstained,
        expected_abstain=expected_abstain,
        failures=failures,
        detail=detail,
    )


def _force_skill(kind: str) -> str | None:
    return {"ship30": "ship30_essay", "artifact": "artifact", "qa": None}.get(kind)


def summarise(results: list[CaseResult]) -> dict:
    total = len(results)
    passed = sum(r.passed for r in results)
    abstain_cases = [r for r in results if r.expected_abstain]
    answer_cases = [r for r in results if not r.expected_abstain]
    correct_abstain = sum(r.abstained for r in abstain_cases)
    over_refusals = sum(r.abstained for r in answer_cases)
    latencies = sorted(r.latency_ms for r in results)

    return {
        "cases": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0,
        "abstention_accuracy": (
            round(correct_abstain / len(abstain_cases), 3) if abstain_cases else None
        ),
        "over_refusal_rate": (
            round(over_refusals / len(answer_cases), 3) if answer_cases else None
        ),
        "mean_citations_on_answers": (
            round(sum(r.citations for r in answer_cases) / len(answer_cases), 2)
            if answer_cases else 0
        ),
        "latency_ms": {
            "p50": latencies[len(latencies) // 2] if latencies else 0,
            "p95": latencies[int(len(latencies) * 0.95) - 1] if latencies else 0,
            "max": latencies[-1] if latencies else 0,
        },
    }


def render(summary: dict, results: list[CaseResult]) -> str:
    lines = [
        "",
        "  Lenny Growth Assistant — evaluation",
        f"  provider {settings.chat_provider} / {_model()}",
        "  " + "-" * 62,
    ]
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{mark}] {r.id:<30} {r.latency_ms:>6}ms  {r.grounding}")
        for f in r.failures:
            lines.append(f"         -> {f}")
    lines += [
        "  " + "-" * 62,
        f"  pass rate            {summary['pass_rate']:.0%} "
        f"({summary['passed']}/{summary['cases']})",
        f"  abstention accuracy  {_pct(summary['abstention_accuracy'])}  "
        "(refuses when the library cannot answer)",
        f"  over-refusal rate    {_pct(summary['over_refusal_rate'])}  "
        "(refuses when it should not)",
        f"  citations per answer {summary['mean_citations_on_answers']}",
        f"  latency p50/p95      {summary['latency_ms']['p50']}ms / "
        f"{summary['latency_ms']['p95']}ms",
        "",
    ]
    return "\n".join(lines)


def _pct(v):
    return "n/a" if v is None else f"{v:.0%}"


def _model() -> str:
    return {
        "ollama": settings.ollama_chat_model,
        "anthropic": settings.anthropic_chat_model,
        "openai": settings.openai_chat_model,
    }.get(settings.chat_provider, "unknown")


async def main_async(args) -> int:
    configure_logging()
    await apply_migrations()

    cases = yaml.safe_load((HERE / args.file).read_text())["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    if args.kind:
        cases = [c for c in cases if c["kind"] == args.kind]

    results: list[CaseResult] = []
    for case in cases:
        print(f"  running {case['id']} ...", flush=True)
        try:
            results.append(await run_case(case))
        except Exception as exc:  # noqa: BLE001
            results.append(
                CaseResult(
                    id=case["id"], kind=case["kind"], passed=False, latency_ms=0,
                    failures=[f"harness error: {type(exc).__name__}: {exc}"],
                )
            )

    summary = summarise(results)
    print(render(summary, results))

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stamp}-{settings.chat_provider}.json"
    out.write_text(
        json.dumps(
            {"summary": summary, "results": [r.to_dict() for r in results]},
            indent=2, default=str,
        )
    )
    print(f"  written to {out.relative_to(HERE.parent)}\n")

    try:
        async with session_scope() as db:
            await repo.save_eval_run(
                db, label=args.label or stamp, provider=settings.chat_provider,
                model=_model(), summary=summary,
                results=[r.to_dict() for r in results],
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not persist run: {exc})")

    return 0 if summary["pass_rate"] >= args.threshold else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Run the grounding evaluation suite.")
    p.add_argument("--file", default="golden_set.yaml")
    p.add_argument("--only", help="Comma-separated case ids.")
    p.add_argument("--kind", choices=["qa", "ship30", "artifact"])
    p.add_argument("--label", help="Label stored with the run.")
    p.add_argument("--threshold", type=float, default=0.7,
                   help="Exit non-zero below this pass rate.")
    raise SystemExit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
