import { useMemo, useState } from "react";
import { artifactDocument, renderMarkdown } from "../lib/markdown";
import type { Artifact } from "../lib/types";

/**
 * The artifact viewer.
 *
 * HTML artifacts render inside an iframe with `sandbox="allow-scripts"` and no
 * `allow-same-origin`. That combination gives the frame an opaque origin: the
 * artifact can run its own scripts — which is what makes interactive artifacts
 * possible — but it has no cookies, no storage, no access to the parent
 * document, and a CSP that permits no network requests at all.
 *
 * Markdown artifacts render in the main document, so they go through DOMPurify
 * instead. Both paths also passed the server-side sanitizer before storage.
 *
 * The "What the viewer blocked" panel is deliberately always visible. A
 * security control the user cannot see is a security control they cannot trust.
 */
export function ArtifactViewer({ artifact }: { artifact: Artifact }) {
  const [view, setView] = useState<"rendered" | "source">("rendered");

  const doc = useMemo(
    () => (artifact.kind === "html" ? artifactDocument(artifact.content) : ""),
    [artifact.content, artifact.kind]
  );
  const markdownHtml = useMemo(
    () => (artifact.kind === "markdown" ? renderMarkdown(artifact.content) : ""),
    [artifact.content, artifact.kind]
  );

  const copy = () => navigator.clipboard?.writeText(artifact.content);

  const download = () => {
    const blob = new Blob([artifact.content], {
      type: artifact.kind === "html" ? "text/html" : "text/markdown",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.title.replace(/[^\w -]/g, "").trim() || "artifact"}.${
      artifact.kind === "html" ? "html" : "md"
    }`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="artifact__bar">
        <span className="artifact__name" title={artifact.title}>
          {artifact.title}
        </span>
        <div className="convo__spacer" />
        <button
          className="ghost-btn"
          aria-pressed={view === "source"}
          onClick={() => setView(view === "source" ? "rendered" : "source")}
        >
          {view === "source" ? "Show rendered" : "Show source"}
        </button>
        <button className="ghost-btn" onClick={copy}>
          Copy
        </button>
        <button className="ghost-btn" onClick={download}>
          Download
        </button>
      </div>

      {view === "source" ? (
        <pre className="artifact__source">{artifact.content}</pre>
      ) : artifact.kind === "html" ? (
        <iframe
          className="artifact__frame"
          title={artifact.title}
          srcDoc={doc}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="artifact__doc">
          <div className="prose" dangerouslySetInnerHTML={{ __html: markdownHtml }} />
        </div>
      )}

      <SecurityPanel artifact={artifact} />
    </>
  );
}

function SecurityPanel({ artifact }: { artifact: Artifact }) {
  const report = artifact.sanitizer_report ?? {};
  const removed = [
    ...(report.removed_elements ?? []),
    ...(report.removed_attributes ?? []),
  ];
  const clean = removed.length === 0 && (report.blocked_urls ?? []).length === 0;

  return (
    <aside className="shield" aria-label="What the viewer blocked">
      <p className="shield__title" data-clean={clean}>
        {clean
          ? "Nothing needed removing from this artifact"
          : `${removed.length} unsafe construct${removed.length === 1 ? "" : "s"} removed before rendering`}
      </p>

      {!clean && (
        <ul>
          {removed.slice(0, 6).map((item) => (
            <li key={item}>{item}</li>
          ))}
          {(report.blocked_urls ?? []).slice(0, 3).map((url) => (
            <li key={url}>blocked URL: {url}</li>
          ))}
        </ul>
      )}

      <p style={{ marginTop: "0.45rem" }}>
        {artifact.kind === "html"
          ? "Runs in a sandboxed frame with its own origin: no cookies, no storage, no access to this page, and no network access."
          : "Rendered in this page after a second sanitization pass. Scripts and styles are stripped."}
        {report.truncated ? " The artifact exceeded the size limit and was truncated." : ""}
      </p>
    </aside>
  );
}
