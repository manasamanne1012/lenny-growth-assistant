"""Artifact sanitization — server side of a two-layer defence.

Threat model. Artifact HTML is written by a language model whose input includes
podcast transcripts we do not control. Treat it as attacker-controlled. Three
things must not happen when the viewer renders it:

  1.  **Session theft.** The artifact must not read cookies, localStorage, or
      anything else on the app's origin.
  2.  **Exfiltration.** It must not phone home with conversation content.
  3.  **UI redress.** It must not escape its frame or overlay the real app.

Two layers, because either alone is brittle:

  *Layer 1 (here).* Strip categorically dangerous constructs before the content
  is ever persisted: script sources from remote origins, event-handler
  attributes, `javascript:` URLs, form actions, iframes/objects/embeds, and
  meta-refresh redirects. Every removal is recorded and returned, so the UI can
  tell the user exactly what was stripped instead of silently altering their
  document.

  *Layer 2 (frontend).* Render inside `<iframe sandbox="allow-scripts">` with no
  `allow-same-origin`, which gives the frame an opaque origin — so even markup
  that slips past Layer 1 has no cookies, no storage, no parent DOM — plus a
  restrictive CSP that blocks all network egress. See `docs/architecture.md`.

Inline `<script>` is *permitted* by default because interactive artifacts are
the point of the feature, and the sandbox is what makes it safe. Operators who
want static-only artifacts set `ALLOW_ARTIFACT_SCRIPTS=false`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from app.config import settings

# Elements dropped wholesale, contents and all.
FORBIDDEN_ELEMENTS = {
    "iframe", "object", "embed", "applet", "base", "form", "portal",
}
# Attributes never allowed on any element.
FORBIDDEN_ATTR_PREFIXES = ("on",)          # onclick, onerror, onload, ...
FORBIDDEN_ATTRS = {"srcdoc", "formaction", "ping", "http-equiv"}
URL_ATTRS = {"href", "src", "action", "xlink:href", "poster", "data"}
DANGEROUS_SCHEMES = re.compile(r"^\s*(javascript|vbscript|data:text/html|file)\s*:", re.I)

# Remote script/style/font/image origins are blocked by CSP at render time too;
# stripping here means the user is told rather than seeing a silently broken box.
REMOTE_URL = re.compile(r"^\s*(?:https?:)?//", re.I)


@dataclass
class SanitizerReport:
    kind: str
    removed_elements: list[str] = field(default_factory=list)
    removed_attributes: list[str] = field(default_factory=list)
    blocked_urls: list[str] = field(default_factory=list)
    truncated: bool = False
    inline_scripts_kept: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (
            self.removed_elements or self.removed_attributes or self.blocked_urls
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "clean": self.clean,
            "removed_elements": sorted(set(self.removed_elements)),
            "removed_attributes": sorted(set(self.removed_attributes)),
            "blocked_urls": self.blocked_urls[:20],
            "inline_scripts_kept": self.inline_scripts_kept,
            "truncated": self.truncated,
            "notes": self.notes,
        }


class _Sanitizer(HTMLParser):
    def __init__(self, report: SanitizerReport):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.report = report
        self._skip_depth = 0
        self._skip_tag: str | None = None
        self._in_script = False

    # ---- helpers ----
    def _filter_attrs(self, tag: str, attrs) -> list[tuple[str, str | None]]:
        kept = []
        for name, value in attrs:
            lname = name.lower()
            if lname.startswith(FORBIDDEN_ATTR_PREFIXES) or lname in FORBIDDEN_ATTRS:
                self.report.removed_attributes.append(f"{tag}[{lname}]")
                continue
            if lname in URL_ATTRS and value:
                if DANGEROUS_SCHEMES.match(value):
                    self.report.blocked_urls.append(value[:120])
                    self.report.removed_attributes.append(f"{tag}[{lname}]")
                    continue
                if tag in ("script", "link") and REMOTE_URL.match(value):
                    self.report.blocked_urls.append(value[:120])
                    self.report.removed_attributes.append(f"{tag}[{lname}]")
                    continue
            kept.append((name, value))
        return kept

    def _emit_start(self, tag: str, attrs, self_closing: bool) -> None:
        bits = [tag]
        for name, value in attrs:
            if value is None:
                bits.append(name)
            else:
                escaped = (
                    value.replace("&", "&amp;").replace('"', "&quot;")
                    .replace("<", "&lt;").replace(">", "&gt;")
                )
                bits.append(f'{name}="{escaped}"')
        self.out.append(f"<{' '.join(bits)}{' /' if self_closing else ''}>")

    # ---- HTMLParser hooks ----
    def handle_starttag(self, tag, attrs):
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag in FORBIDDEN_ELEMENTS:
            self.report.removed_elements.append(tag)
            self._skip_depth, self._skip_tag = 1, tag
            return
        if tag == "meta" and any(
            n.lower() == "http-equiv" for n, _ in attrs
        ):
            self.report.removed_elements.append("meta[http-equiv]")
            return
        if tag == "script":
            if not settings.allow_artifact_scripts:
                self.report.removed_elements.append("script")
                self._skip_depth, self._skip_tag = 1, "script"
                return
            src = next((v for n, v in attrs if n.lower() == "src"), None)
            if src and REMOTE_URL.match(src or ""):
                self.report.blocked_urls.append(src[:120])
                self.report.removed_elements.append("script[remote src]")
                self._skip_depth, self._skip_tag = 1, "script"
                return
            self.report.inline_scripts_kept += 1
            self._in_script = True
        self._emit_start(tag, self._filter_attrs(tag, attrs), self_closing=False)

    def handle_startendtag(self, tag, attrs):
        if self._skip_depth:
            return
        if tag in FORBIDDEN_ELEMENTS:
            self.report.removed_elements.append(tag)
            return
        self._emit_start(tag, self._filter_attrs(tag, attrs), self_closing=True)

    def handle_endtag(self, tag):
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    self._skip_tag = None
            return
        if tag == "script":
            self._in_script = False
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._skip_depth:
            return
        self.out.append(data)

    def handle_entityref(self, name):
        if not self._skip_depth:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self._skip_depth:
            self.out.append(f"&#{name};")

    def handle_comment(self, data):
        # Comments are dropped: conditional comments are a legacy XSS vector and
        # nothing in a generated artifact needs them.
        return


def sanitize_artifact(content: str, kind: str) -> tuple[str, SanitizerReport]:
    """Returns (safe_content, report). Never raises on malformed input."""
    report = SanitizerReport(kind=kind)

    if len(content.encode("utf-8")) > settings.artifact_max_bytes:
        content = content.encode("utf-8")[: settings.artifact_max_bytes].decode(
            "utf-8", errors="ignore"
        )
        report.truncated = True
        report.notes.append(
            f"Artifact exceeded ARTIFACT_MAX_BYTES ({settings.artifact_max_bytes}) "
            "and was truncated."
        )

    if kind == "markdown":
        # Markdown may embed raw HTML, so it goes through the same pass.
        # Rendering is done by the frontend with DOMPurify as a second gate.
        cleaned, report = _run(content, report)
        report.notes.append(
            "Markdown is rendered client-side with DOMPurify and displayed in the "
            "main document, not an iframe; raw HTML inside it is sanitized twice."
        )
        return cleaned, report

    cleaned, report = _run(content, report)
    report.notes.append(
        "HTML is rendered in a sandboxed iframe with an opaque origin "
        "(sandbox=\"allow-scripts\", no allow-same-origin) and a CSP that blocks "
        "all network requests."
    )
    return cleaned, report


def _run(content: str, report: SanitizerReport) -> tuple[str, SanitizerReport]:
    parser = _Sanitizer(report)
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:  # noqa: BLE001 - never fail the turn on bad markup
        report.notes.append(f"Parser recovered from malformed markup: {exc}")
    return "".join(parser.out), report
