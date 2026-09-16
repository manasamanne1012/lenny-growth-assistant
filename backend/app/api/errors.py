"""Structured error handling.

Every failure leaves the API in the same envelope: a stable `code`, a plain
message, a `hint` naming the most likely fix, and the `trace_id` so the
corresponding log line can be found. An evaluator hitting a wall gets an
instruction, not a stack trace.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.llm.base import ChatProviderError
from app.obs import current_trace, get_logger

log = get_logger("api.errors")


def _envelope(code: str, message: str, hint: str | None, status: int) -> JSONResponse:
    trace = current_trace()
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "hint": hint,
                "trace_id": trace.trace_id if trace else None,
            }
        },
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "body"
        return _envelope(
            "validation_error",
            f"{field}: {first.get('msg', 'invalid value')}",
            "Check the request body against the schema at /docs.",
            422,
        )

    @app.exception_handler(ChatProviderError)
    async def _provider(request: Request, exc: ChatProviderError):
        log.warning("api.provider_error", provider=exc.provider, error=str(exc))
        hints = {
            "ollama": "Start Ollama (`ollama serve`) and pull the model named in "
                      "OLLAMA_CHAT_MODEL. From Docker, OLLAMA_BASE_URL should be "
                      "http://host.docker.internal:11434.",
            "anthropic": "Set ANTHROPIC_API_KEY in .env, or set CHAT_PROVIDER=ollama.",
            "openai": "Set OPENAI_API_KEY in .env, or set CHAT_PROVIDER=ollama.",
        }
        return _envelope(
            "model_provider_unavailable",
            str(exc),
            hints.get(exc.provider, "Check CHAT_PROVIDER and the provider's health "
                                    "at /api/health/deep."),
            503,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return _envelope(
            {404: "not_found", 405: "method_not_allowed"}.get(
                exc.status_code, "http_error"
            ),
            str(exc.detail),
            "See /docs for the available endpoints." if exc.status_code == 404 else None,
            exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("api.unhandled", path=request.url.path)
        message = str(exc)
        code, hint = "internal_error", "Check the server logs for this trace_id."
        lowered = message.lower()
        if "connect" in lowered and ("5432" in message or "postgres" in lowered):
            code = "database_unavailable"
            hint = ("Postgres is not reachable. Run `docker compose up -d postgres` "
                    "and confirm DATABASE_URL.")
        elif "vector" in lowered and "dimension" in lowered:
            code = "embedding_dim_mismatch"
            hint = ("The embedding column width does not match EMBEDDING_DIM. Run "
                    "`make resize-embeddings DIM=<n>` then `make ingest`.")
        return _envelope(code, message, hint, 500)
