import type { EssayReport, Message, TraceSpan } from "../lib/types";

/**
 * The trace inspector.
 *
 * "Observability" usually means logs an operator greps after the fact. Here the
 * per-turn trace is attached to the message and rendered on demand, so an
 * evaluator can answer "why was this slow / why was this wrong" with a click.
 */
export function Inspector({ message }: { message: Message | null }) {
  if (!message) {
    return (
      <div className="panel__body">
        <p className="panel__heading">Nothing selected</p>
        <p className="panel__sub">
          Choose "How this answer was built" under any answer to see its retrieval,
          routing, and timing.
        </p>
      </div>
    );
  }

  const trace = message.trace ?? {};
  const spans: TraceSpan[] = trace.spans ?? [];
  const facts = (trace.facts ?? {}) as Record<string, any>;
  const slowest = Math.max(1, ...spans.map((s) => s.duration_ms ?? 0));

  return (
    <div className="panel__body">
      <p className="panel__heading">How this answer was built</p>
      <p className="panel__sub">trace {trace.trace_id ?? "—"}</p>

      <dl className="kv">
        <dt>Skill</dt>
        <dd>{message.skill?.replace(/_/g, " ") ?? "—"}</dd>
        <dt>Routed by</dt>
        <dd>
          {facts.route
            ? `${facts.route.method} — ${facts.route.reason}`
            : "—"}
        </dd>
        <dt>Model</dt>
        <dd>
          {message.model ?? "—"} ({message.provider ?? "—"})
          {facts.provider?.fallback_used ? " · fallback used" : ""}
        </dd>
        <dt>Grounding</dt>
        <dd>{message.grounding ?? "—"}</dd>
        <dt>Retrieval</dt>
        <dd>
          {facts.retrieval
            ? `${facts.retrieval.hits} chunks · ${facts.retrieval.sufficiency}` +
              (facts.retrieval.degraded ? " · keyword-only fallback" : "")
            : "—"}
        </dd>
        <dt>Episodes</dt>
        <dd>{facts.retrieval?.episodes?.join("; ") ?? "—"}</dd>
        <dt>Tokens</dt>
        <dd>
          {message.token_usage?.input_tokens ?? 0} in ·{" "}
          {message.token_usage?.output_tokens ?? 0} out
        </dd>
        <dt>Total</dt>
        <dd>{message.latency_ms ? `${message.latency_ms} ms` : "—"}</dd>
      </dl>

      <p className="panel__heading">Where the time went</p>
      <p className="panel__sub">Each stage of the turn, longest first.</p>
      {spans.length === 0 ? (
        <p className="panel__sub">No spans recorded for this turn.</p>
      ) : (
        [...spans]
          .sort((a, b) => (b.duration_ms ?? 0) - (a.duration_ms ?? 0))
          .map((span, i) => (
            <div className="span" key={`${span.name}-${i}`} data-status={span.status}>
              <span className="span__name">{span.name.replace(/_/g, " ")}</span>
              <span className="span__ms">
                {span.duration_ms ? `${Math.round(span.duration_ms)} ms` : "—"}
              </span>
              <div className="meter__track" style={{ gridColumn: "1 / -1" }}>
                <div
                  className="meter__fill"
                  style={{ width: `${((span.duration_ms ?? 0) / slowest) * 100}%` }}
                />
              </div>
            </div>
          ))
      )}

      {message.essay_report && <RubricReport report={message.essay_report} />}
    </div>
  );
}

function RubricReport({ report }: { report: EssayReport }) {
  const meters: [string, number, number][] = [
    ["Words", report.word_count, 1500],
    ["Hook words", report.hook_words, 22],
    ["Sections", report.h2_count, 7],
    ["Bold phrases", report.bold_phrases, 14],
    ["Avg sentence", report.avg_sentence_words, 22],
  ];

  return (
    <div className="rubric" style={{ marginTop: "1.4rem" }}>
      <p className="panel__heading">Ship 30 rubric</p>
      <p className="panel__sub">
        Checked mechanically after drafting, not judged by a model.
      </p>
      <p className="rubric__verdict" data-passed={report.passed}>
        {report.passed
          ? "Meets every rule in the rubric"
          : `Misses ${report.failures.length} rule${report.failures.length === 1 ? "" : "s"}`}
      </p>

      {meters.map(([label, value, limit]) => (
        <div className="meter" key={label}>
          <span>{label}</span>
          <div className="meter__track">
            <div
              className="meter__fill"
              data-over={value > limit}
              style={{ width: `${Math.min(100, (value / limit) * 100)}%` }}
            />
          </div>
          <span className="meter__value">{Math.round(value)}</span>
        </div>
      ))}

      <div className="meter">
        <span>Cited paragraphs</span>
        <div className="meter__track">
          <div
            className="meter__fill"
            style={{ width: `${report.citation_coverage * 100}%` }}
          />
        </div>
        <span className="meter__value">
          {Math.round(report.citation_coverage * 100)}%
        </span>
      </div>

      {report.failures.length > 0 && (
        <ul style={{ marginTop: "0.7rem", paddingLeft: "1.1rem" }}>
          {report.failures.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
