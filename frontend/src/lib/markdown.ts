/**
 * Markdown rendering and citation linking.
 *
 * Two things happen here, in this order, and the order matters:
 *
 *  1.  Markdown is rendered to HTML. `html: true` is on because artifacts
 *      legitimately contain inline HTML.
 *  2.  The result is sanitized with DOMPurify before it is ever inserted into
 *      the document. Markdown is rendered in the main document rather than an
 *      iframe, so DOMPurify — not the sandbox — is the boundary here. The
 *      backend sanitizer already made one pass; this is the second, and it is
 *      the one that runs on the origin that matters.
 *
 * Citation markers like [S2] are converted into focusable buttons after
 * sanitization, from a fixed allowlist of markers the server actually returned,
 * so the transformation cannot be used to inject anything.
 */
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";

const md = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: false,
  typographer: true,
});

// Links inside rendered content open in a new tab with no referrer, and can
// never navigate the app itself.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node instanceof HTMLElement && node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer nofollow");
  }
});

const PURIFY_CONFIG = {
  FORBID_TAGS: ["style", "form", "iframe", "object", "embed", "base", "script"],
  FORBID_ATTR: ["style", "srcdoc", "formaction", "ping"],
  ALLOW_DATA_ATTR: false,
};

export function renderMarkdown(source: string): string {
  return DOMPurify.sanitize(md.render(source), PURIFY_CONFIG);
}

/** Render markdown, then turn [S#] markers into clickable citation chips. */
export function renderWithCitations(source: string, markers: string[]): string {
  const html = renderMarkdown(source);
  if (markers.length === 0) return html;
  const allowed = new Set(markers.map((m) => m.replace(/[^A-Za-z0-9]/g, "")));
  return html.replace(/\[S(\d+)\]/g, (whole, n: string) => {
    const marker = `S${n}`;
    if (!allowed.has(marker)) return whole;
    return `<button class="cite" data-marker="${marker}" type="button" aria-label="Show source ${marker}">[${marker}]</button>`;
  });
}

/**
 * The document loaded into the artifact iframe.
 *
 * The CSP here is the second half of the isolation story. `default-src 'none'`
 * with no `connect-src` means the artifact cannot make a network request of any
 * kind — no beacons, no fetch, no image pixel. Combined with
 * sandbox="allow-scripts" (and deliberately *without* allow-same-origin), the
 * frame runs on an opaque origin: no cookies, no localStorage, no access to the
 * parent document.
 */
export function artifactDocument(html: string): string {
  const csp = [
    "default-src 'none'",
    "style-src 'unsafe-inline'",
    "script-src 'unsafe-inline'",
    "img-src data:",
    "font-src data:",
    "form-action 'none'",
    "base-uri 'none'",
  ].join("; ");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<style>
  :root { color-scheme: light; }
  html, body { margin: 0; background: #fff; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color: #17232a; line-height: 1.55; padding: 20px;
  }
  img, svg, table { max-width: 100%; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
  }
</style>
</head>
<body>
${html}
</body>
</html>`;
}
