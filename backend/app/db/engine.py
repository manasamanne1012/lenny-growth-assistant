"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.obs import get_logger

log = get_logger("db")

_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


def get_engine():
    return _engine


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transaction per unit of work. Commits on success, rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with session_scope() as session:
        yield session


async def ping() -> dict:
    """Cheap liveness probe used by the deep health check."""
    async with SessionLocal() as session:
        version = (await session.execute(text("SHOW server_version"))).scalar_one()
        has_vector = (
            await session.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            )
        ).scalar_one()
    return {"server_version": version, "pgvector": bool(has_vector)}


@asynccontextmanager
async def lifespan_db() -> AsyncIterator[None]:
    try:
        yield
    finally:
        await _engine.dispose()
        log.info("db.engine.disposed")
