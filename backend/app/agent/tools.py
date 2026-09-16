"""Tool definitions shared by both agent runtimes.

Declared once, in provider-neutral JSON Schema. The native loop converts them to
Ollama/OpenAI function schemas; the Claude Agent SDK runtime converts them to
SDK tools. Keeping one definition means a tool can never drift between runtimes.
"""

from __future__ import annotations

from typing import Any

SEARCH_TRANSCRIPTS: dict[str, Any] = {
    "name": "search_transcripts",
    "description": (
        "Search Lenny's Podcast transcripts and return the most relevant excerpts "
        "with [S#] citation markers. Call this before answering any question about "
        "product, growth, or anything a guest may have discussed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Use the user's own terminology.",
            },
            "top_k": {
                "type": "integer",
                "description": "How many excerpts to return (1-12).",
                "default": 8,
            },
        },
        "required": ["query"],
    },
}

WRITE_SHIP30_ESSAY: dict[str, Any] = {
    "name": "write_ship30_essay",
    "description": (
        "Write a ~1,250-word Ship 30 for 30-style essay grounded in the transcripts. "
        "Use when the user asks for an essay, post, article, or long-form content."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "The essay's subject."},
        },
        "required": ["topic"],
    },
}

CREATE_ARTIFACT: dict[str, Any] = {
    "name": "create_artifact",
    "description": (
        "Create a Markdown or self-contained HTML document rendered in the app's "
        "artifact viewer. Use for one-pagers, checklists, tables, dashboards, "
        "mockups, and anything the user wants to look at rather than read in chat."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "request": {"type": "string", "description": "What to build."},
            "kind": {
                "type": "string",
                "enum": ["markdown", "html"],
                "description": "markdown for documents, html for anything visual "
                               "or interactive.",
            },
        },
        "required": ["request", "kind"],
    },
}

ALL_TOOLS = [SEARCH_TRANSCRIPTS, WRITE_SHIP30_ESSAY, CREATE_ARTIFACT]
