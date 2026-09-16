"""Structured logging.

One logger factory, one format decision, made once at startup. Every log line
carries `trace_id` when one is active so a single user turn can be followed
across HTTP, retrieval, model, and database boundaries.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.config import settings

_CONFIGURED = False


def _add_trace_id(_: Any, __: str, event_dict: dict) -> dict:
    from app.obs.trace import current_trace

    trace = current_trace()
    if trace is not None:
        event_dict.setdefault("trace_id", trace.trace_id)
        if trace.session_id:
            event_dict.setdefault("session_id", trace.session_id)
    return event_dict


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_trace_id,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str = "lenny") -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
