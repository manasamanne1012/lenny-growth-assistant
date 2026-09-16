"""Per-turn trace.

The assignment asks for "enough visibility to diagnose model, retrieval,
database, and artifact-rendering failures". Logs alone make an evaluator grep.
Instead every chat turn builds a small trace object of named spans, which is
persisted with the message and rendered in the UI's inspector panel. Debugging
becomes a click rather than a log search.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

_CURRENT: ContextVar[Trace | None] = ContextVar("current_trace", default=None)


@dataclass
class TraceSpan:
    name: str
    started_at: float
    duration_ms: float | None = None
    status: str = "ok"
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms else None,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class Trace:
    trace_id: str
    session_id: str | None = None
    spans: list[TraceSpan] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    _t0: float = field(default_factory=time.perf_counter)

    @contextmanager
    def span(self, name: str, **detail: Any) -> Iterator[TraceSpan]:
        sp = TraceSpan(name=name, started_at=time.perf_counter(), detail=dict(detail))
        self.spans.append(sp)
        try:
            yield sp
        except Exception as exc:  # noqa: BLE001 - recorded then re-raised
            sp.status = "error"
            sp.detail["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            sp.duration_ms = (time.perf_counter() - sp.started_at) * 1000

    def fact(self, key: str, value: Any) -> None:
        self.facts[key] = value

    @property
    def total_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "total_ms": round(self.total_ms, 2),
            "spans": [s.to_dict() for s in self.spans],
            "facts": self.facts,
        }


def new_trace(session_id: str | None = None) -> Trace:
    trace = Trace(trace_id=uuid.uuid4().hex[:16], session_id=session_id)
    _CURRENT.set(trace)
    return trace


def current_trace() -> Trace | None:
    return _CURRENT.get()
