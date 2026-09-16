import { useEffect, useRef, useState } from "react";
import { renderWithCitations } from "../lib/markdown";
import type { Citation, Message } from "../lib/types";

const VERDICT: Record<string, string> = {
  grounded: "Grounded in the transcripts",
  partial: "Partly grounded — some claims are not cited",
  ungrounded: "Not cited — treat with caution",
  abstained: "No answer given: the archive does not cover this",
  "n/a": "No grounding required for this turn",
};

/**
 * One turn in the conversation.
 *
 * Assistant turns carry a provenance rail underneath: the grounding verdict,
 * then each source the answer drew on. The verdict is computed server-side from
 * what the model actually produced, so "Not cited" appears when the model
 * ignored its instructions. Showing that is more useful than hiding it.
 */
export function Turn({
  message,
  onOpenTrace,
}: {
  message: Message;
  onOpenTrace: (message: Message) => void;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [openSource, setOpenSource] = useState<string | null>(null);

  const markers = message.citations.map((c) => c.marker);
  const html = renderWithCitations(message.content, markers);

  // Citation chips are rendered from sanitized HTML, so the click handler is
  // attached by delegation rather than by React.
  useEffect(() => {
    const node = bodyRef.current;
    if (!node) return;
    const handler = (event: Event) => {
      const target = (event.target as HTMLElement).closest(".cite");
      if (!target) return;
      const marker = target.getAttribute("data-marker");
      if (marker) setOpenSource((current) => (current === marker ? null : marker));
    };
    node.addEventListener("click", handler);
    return () => node.removeEventListener("click", handler);
  }, [html]);

  if (message.role === "user") {
    return (
      <article className="turn turn--user">
        <p className="turn__who">You</p>
        <div className="turn__body">{message.content}</div>
      </article>
    );
  }

  const grounding = message.grounding ?? "n/a";

  return (
    <article className="turn">
      <p className="turn__who">
        Assistant
        {message.latency_ms ? ` · ${(message.latency_ms / 1000).toFixed(1)}s` : ""}
        {message.skill ? ` · ${message.skill.replace(/_/g, " ")}` : ""}
      </p>

      <div
        ref={bodyRef}
        className="prose"
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {message.notices?.map((notice) => (
        <p className="notice" key={notice}>
          {notice}
        </p>
      ))}

      {(message.citations.length > 0 || grounding === "abstained") && (
        <section
          className="provenance"
          data-grounding={grounding}
          aria-label="Sources for this answer"
        >
          <p className="provenance__verdict">{VERDICT[grounding] ?? grounding}</p>

          {message.citations.map((c) => (
            <SourceRow
              key={c.chunk_id}
              citation={c}
              open={openSource === c.marker}
              onToggle={() =>
                setOpenSource((current) => (current === c.marker ? null : c.marker))
              }
            />
          ))}

          <button className="ghost-btn" onClick={() => onOpenTrace(message)}>
            How this answer was built
          </button>
        </section>
      )}
    </article>
  );
}

function SourceRow({
  citation,
  open,
  onToggle,
}: {
  citation: Citation;
  open: boolean;
  onToggle: () => void;
}) {
  const meta = [
    citation.guest,
    citation.timestamp ? `at ${citation.timestamp}` : null,
    citation.retrieved_by === "both"
      ? "matched on meaning and keywords"
      : citation.retrieved_by === "semantic"
        ? "matched on meaning"
        : "matched on keywords",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      <button className="source" onClick={onToggle} aria-expanded={open}>
        <span className="source__marker">[{citation.marker}]</span>
        <span className="source__title">{citation.title}</span>
        <span className="source__meta"> {meta}</span>
      </button>
      {open && (
        <blockquote className="source__excerpt">
          {citation.excerpt}
          {citation.episode_url && (
            <>
              {" "}
              <a
                href={citation.episode_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open the episode
              </a>
            </>
          )}
        </blockquote>
      )}
    </div>
  );
}
