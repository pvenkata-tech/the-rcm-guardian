"""Database URI helpers (async SQLAlchemy vs LangGraph / psycopg checkpointer)."""

from __future__ import annotations


def asyncpg_to_psycopg_conninfo(database_url: str) -> str:
    """Convert SQLAlchemy asyncpg URL to a psycopg/libpq connection URI."""
    u = database_url.strip()
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if u.startswith(prefix):
            return "postgresql://" + u[len(prefix) :]
    return u
